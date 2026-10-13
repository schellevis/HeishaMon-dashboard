"""R7: reads run on a second `query_only` connection and never hold the ingest lock while scanning."""
import os
import sqlite3
import threading
import time

import pytest

from heishamon_dashboard.store import Store
from heishamon_dashboard.store.rollups import DataView
from heishamon_dashboard.types import Liveness, Receipt

T0 = 1_791_000_000_000
MIN = 60_000
TOPIC = "main/Outside_Temp"


def rcpt(topic, value, ts):
    return Receipt(topic=topic, raw=str(value), value=float(value), valid=True, retained=False,
                   ts=ts, qualifying=False, changed=True)


def up(ts):
    return Liveness("online", ts, None)


def fill(s: Store, n: int, start: int = T0) -> None:
    for i in range(n):
        s.observe(rcpt(TOPIC, 10 + i % 7, start + i * MIN))


def slow_scan(monkeypatch, store: Store, seconds: float, started: threading.Event):
    """Make every scan on the reader connection sleep; the writer's own scans stay fast."""
    real = DataView.samples

    def samples(self, *a, **k):
        if self.conn is store._rconn:
            started.set()
            time.sleep(seconds)
        return real(self, *a, **k)

    monkeypatch.setattr(DataView, "samples", samples)


def test_reader_connection_is_query_only(tmp_path):
    s = Store(str(tmp_path / "s.db"))
    assert s._rconn is not s._conn
    assert s._rconn.execute("PRAGMA query_only").fetchone()[0] == 1
    with pytest.raises(sqlite3.OperationalError):
        s._rconn.execute("INSERT INTO prefs (key, value) VALUES ('k', '1')")
    assert s._conn.execute("PRAGMA query_only").fetchone()[0] == 0


def test_slow_read_does_not_block_observe(tmp_path, monkeypatch):
    s = Store(str(tmp_path / "s.db"))
    fill(s, 30)
    assert s.flush(T0 + 40 * MIN, up(T0 + 40 * MIN)).ok
    started = threading.Event()
    slow_scan(monkeypatch, s, 2.0, started)
    result = {}
    reader = threading.Thread(
        target=lambda: result.update(h=s.history([TOPIC], T0, T0 + 30 * MIN, 1000, T0 + 40 * MIN, up(T0 + 40 * MIN))))
    reader.start()
    assert started.wait(5)
    slowest = 0.0
    for i in range(20):
        t = time.perf_counter()
        s.observe(rcpt(TOPIC, 100 + i, T0 + 41 * MIN + i * 1000))
        slowest = max(slowest, time.perf_counter() - t)
    t = time.perf_counter()
    s.append_event(T0 + 41 * MIN, "x", {})
    slowest = max(slowest, time.perf_counter() - t)
    assert reader.is_alive(), "the read must still be running while the writes were measured"
    assert slowest <= 0.05
    reader.join(10)
    assert result["h"]["series"][TOPIC]["points"]


def test_flush_runs_while_a_read_is_scanning(tmp_path, monkeypatch):
    s = Store(str(tmp_path / "s.db"))
    fill(s, 5)
    started = threading.Event()
    slow_scan(monkeypatch, s, 1.0, started)
    reader = threading.Thread(target=lambda: s.rollups_1m([TOPIC], T0, T0 + 10 * MIN, T0 + 10 * MIN, up(T0 + 10 * MIN)))
    reader.start()
    assert started.wait(5)
    assert s.flush(T0 + 10 * MIN, up(T0 + 10 * MIN)).ok
    assert reader.is_alive()
    reader.join(10)


@pytest.mark.parametrize("span_min", [30, 8 * 60])  # raw, then 1-minute rollups
def test_flush_between_ram_copy_and_scan_changes_nothing(tmp_path, monkeypatch, span_min):
    s = Store(str(tmp_path / "s.db"))
    fill(s, 40)
    assert s.flush(T0 + 50 * MIN, up(T0 + 50 * MIN)).ok
    fill(s, 20, T0 + 60 * MIN)  # unflushed
    s.open_outage("dropped", T0 + 65 * MIN, TOPIC)
    s.close_outage("dropped", T0 + 70 * MIN, TOPIC)
    now = T0 + 90 * MIN
    args = ([TOPIC], now - span_min * MIN, now, 100_000, now, up(now))
    baseline = s.history(*args)
    base_outages = s.outages_list()
    assert baseline["series"][TOPIC]["points"] and baseline["series"][TOPIC]["breaks"] == []

    real = DataView.samples
    flushed = []

    def samples(self, *a, **k):
        if self.conn is s._rconn and not flushed:
            flushed.append(s.flush(now, up(now)))  # the copied RAM state is now stale
        return real(self, *a, **k)

    monkeypatch.setattr(DataView, "samples", samples)
    again = s.history(*args)
    assert flushed and flushed[0].ok
    assert again == baseline
    monkeypatch.undo()
    assert s.outages_list() == base_outages


def test_reads_merge_database_and_ram_across_flushes(tmp_path):
    s = Store(str(tmp_path / "s.db"))
    fill(s, 10)
    assert s.flush(T0 + 20 * MIN, up(T0 + 20 * MIN)).ok
    fill(s, 5, T0 + 30 * MIN)
    now = T0 + 40 * MIN
    pts = s.history([TOPIC], T0, now, 1000, now, up(now))["series"][TOPIC]["points"]
    assert len(pts) == 15  # 10 flushed + 5 buffered
    assert [p[0] for p in pts] == sorted(p[0] for p in pts)


def test_command_and_event_reads_see_unflushed_and_flushed_records(tmp_path):
    s = Store(str(tmp_path / "s.db"))
    rec = {"uuid": "u1", "submitted_ts": T0, "name": "SetCurves", "payload": "{}", "retained": False,
           "class": "setting", "status": "pending", "attempts": 0, "keys": ["z1_heat_target_high"]}
    s.append_command(rec)
    s.append_event(T0, "mode_change", {"to": 1})
    assert s.get_command("u1")["status"] == "pending"
    assert [e["kind"] for e in s.events_list()] == ["mode_change"]
    assert s.flush(T0 + MIN, up(T0 + MIN)).ok
    s.update_command("u1", {"status": "confirmed", "confirmed_ts": T0 + 5})
    assert s.get_command("u1")["status"] == "confirmed"
    assert [c["uuid"] for c in s.list_commands()] == ["u1"]
    assert s.last_confirmed_setcurves("z1", "heat") == T0 + 5
    # a returned record is a copy: changing it never touches the buffered one
    got = s.get_command("u1")
    got["status"] = "tampered"
    assert s.get_command("u1")["status"] == "confirmed"


def test_concurrent_reads_are_serialised_and_correct(tmp_path):
    s = Store(str(tmp_path / "s.db"))
    fill(s, 20)
    assert s.flush(T0 + 30 * MIN, up(T0 + 30 * MIN)).ok
    expect = s.rollups_1m([TOPIC], T0, T0 + 30 * MIN, T0 + 30 * MIN, up(T0 + 30 * MIN))
    out, errors = [], []

    def work():
        try:
            for _ in range(10):
                out.append(s.rollups_1m([TOPIC], T0, T0 + 30 * MIN, T0 + 30 * MIN, up(T0 + 30 * MIN)))
                s.observe(rcpt("main/Other", 1, T0 + 31 * MIN))
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(4)]
    [t.start() for t in threads]
    [t.join(20) for t in threads]
    assert not errors and len(out) == 40 and all(o == expect for o in out)


def test_close_closes_both_connections_and_removes_the_wal(tmp_path):
    p = str(tmp_path / "s.db")
    s = Store(p)
    fill(s, 3)
    assert s.flush(T0 + 10 * MIN, up(T0 + 10 * MIN)).ok
    s.history([TOPIC], T0, T0 + 5 * MIN, 100, T0 + 10 * MIN, None)
    s.close()
    with pytest.raises(sqlite3.ProgrammingError):
        s._rconn.execute("SELECT 1")
    with pytest.raises(sqlite3.ProgrammingError):
        s._conn.execute("SELECT 1")
    assert not os.path.exists(p + "-wal")
