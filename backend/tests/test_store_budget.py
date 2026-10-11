"""Buffer caps and the protected-record budget (spec §5.1)."""
import sqlite3

import pytest

from heishamon_dashboard.store import RESERVED_SLOTS, Store, StorageUnavailable
from heishamon_dashboard.types import Liveness, Receipt

T0 = 1_791_000_000_000


def rcpt(topic, value, ts, changed=True):
    return Receipt(topic=topic, raw=str(value), value=float(value), valid=True, retained=False,
                   ts=ts, qualifying=False, changed=changed)


def up(ts):
    return Liveness("online", ts, None)


def cmd(i, ts=T0):
    return {"uuid": f"u{i}", "submitted_ts": ts, "published_ts": None, "name": f"Set{i}", "payload": "1",
            "retained": False, "class": "setting", "prev_value": None, "status": "pending",
            "confirmed_ts": None, "attempts": 0, "detail": None, "keys": None}


def break_disk(store, monkeypatch):
    def boom(*a, **k):
        raise sqlite3.OperationalError("database or disk is full")
    real = store._flush_tx
    monkeypatch.setattr(store, "_flush_tx", boom)
    return lambda: monkeypatch.setattr(store, "_flush_tx", real)


def test_entry_cap_triggers_flush_then_drops_oldest_only_when_flush_fails(tmp_path, monkeypatch):
    s = Store(str(tmp_path / "a.db"), buffer_max_entries=50)
    for i in range(49):
        s.observe(rcpt("main/A", i, T0 + i))
    assert not s.needs_flush
    s.observe(rcpt("main/A", 49, T0 + 49))
    assert s.needs_flush and s.sample_count == 50
    break_disk(s, monkeypatch)
    assert not s.flush(T0 + 60, up(T0 + 60)).ok and s.failing
    for i in range(50, 200):
        s.observe(rcpt("main/A", i, T0 + i))
        assert s.sample_count <= 50
    assert s.sample_count == 50
    # oldest dropped first: the newest 50 remain
    assert [x.ts for x in s._buf] == [T0 + i for i in range(150, 200)]


def test_hard_backstop_without_a_failed_flush(tmp_path):
    s = Store(str(tmp_path / "b.db"), buffer_max_entries=50)
    for i in range(1000):  # the caller never flushes: RAM stays bounded
        s.observe(rcpt("main/A", i, T0 + i))
        assert s.sample_count <= 100


def test_byte_cap(tmp_path, monkeypatch):
    s = Store(str(tmp_path / "c.db"), buffer_max_bytes=1000)
    break_disk(s, monkeypatch)
    s.observe(rcpt("main/A", 1, T0))
    s.flush(T0, up(T0))
    for i in range(200):
        s.observe(rcpt("main/A", i, T0 + i + 1))
        assert s.sample_bytes <= 1000
    assert s.needs_flush and 0 < s.sample_count < 20


def test_buffer_overflow_event_aggregated_in_place(tmp_path, monkeypatch):
    s = Store(str(tmp_path / "d.db"), buffer_max_entries=20)
    break_disk(s, monkeypatch)
    s.flush(T0, up(T0))
    for i in range(500):
        s.observe(rcpt("main/A", i, T0 + i + 1))
    ev = [e for e in s._events if e["kind"] == "buffer_overflow"]
    assert len(ev) == 1 and ev[0]["detail"]["count"] == 480
    assert ev[0]["detail"]["first_ts"] == T0 + 1 and ev[0]["detail"]["last_ts"] == T0 + 480
    # one scoped dropped outage, extended in place
    assert [o for o in s._outages if o.kind == "dropped"] == [s._drops["main/A"]]
    assert s._drops["main/A"].end == T0 + 481
    for _ in range(3):  # repeated failing flushes also aggregate in place
        s.flush(T0 + 1000, up(T0 + 1000))
    failed = [e for e in s._events if e["kind"] == "flush_failed"]
    assert len(failed) == 1 and failed[0]["detail"]["count"] == 4


def test_saturation_reserves_66_slots_and_replaces_outage_records(tmp_path, monkeypatch):
    amax = 200
    limit = amax - RESERVED_SLOTS
    assert RESERVED_SLOTS == 66
    s = Store(str(tmp_path / "e.db"), audit_buffer_max=amax)
    for i in range(64):  # 64 in-flight commands, flushed earlier
        s.append_command(cmd(i))
    s.observe(rcpt("main/A", 1, T0))
    assert s.flush(T0 + 1000, up(T0 + 1000)).ok
    assert s.audit_count() == 0
    s.open_outage("offline", T0 + 2000)  # a persisted-open outage to close later
    s.flush(T0 + 3000, Liveness("offline", T0 + 2000, T0 + 2000))
    open_before = s.audit_count()
    assert open_before == 0

    n = 0
    while s.protected_budget_ok():
        assert s.append_event(T0 + 4000 + n, "mode_change", {"n": n})
        n += 1
    assert s.audit_count() == limit + 1  # `limit` records + the saturation outage (reserved slot)
    assert n == limit
    assert [o for o in s._outages if o.saturation][0].start == T0 + 4000 + n - 1

    # saturated: events are counted, not appended; new commands refused
    assert not s.append_event(T0 + 5000, "valve_change")
    assert not s.append_event(T0 + 5001, "mode_change")
    dropped = [e for e in s._events if e["kind"] == "events_dropped"]
    assert len(dropped) == 1
    assert dropped[0]["detail"] == {"count": 2, "kinds": {"valve_change": 1, "mode_change": 1}}
    with pytest.raises(StorageUnavailable):
        s.append_command(cmd(999))
    count = s.audit_count()
    # no other outage record of any kind or scope is appended
    assert s.open_outage("dropped", T0 + 6000, "main/A") is None
    assert s.open_outage("ignored", T0 + 6000, "main/B") is None
    s.set_ignored("main/C", True, T0 + 6000)
    assert s.audit_count() == count
    # in-place closing of an already-open persisted outage still works
    assert s.close_outage("offline", T0 + 7000)
    # in-flight commands complete at the boundary: 64 terminal updates fit the reserve exactly
    for i in range(64):
        s.update_command(f"u{i}", {"status": "confirmed", "confirmed_ts": T0 + 8000})
    assert s.audit_count() == amax
    for i in range(64):  # further updates of the same command stay in place
        s.update_command(f"u{i}", {"detail": "again"})
    assert s.audit_count() == amax
    assert all(s.get_command(f"u{i}")["status"] == "confirmed" for i in range(64))

    # zero coverage for every topic from the saturation instant to the flush
    t_sat = T0 + 4000 + n - 1
    assert s.flush(T0 + 600_000, Liveness("offline", T0 + 2000, T0 + 2000)).ok
    c = sqlite3.connect(str(tmp_path / "e.db"))
    sat = c.execute("SELECT start_ts, end_ts, kind, topic_id FROM outages WHERE start_ts = ?", (t_sat,)).fetchall()
    assert sat == [(t_sat, T0 + 600_000, "dropped", None)]
    assert c.execute("SELECT COUNT(*) FROM outages WHERE kind = 'dropped'").fetchone()[0] == 1
    assert c.execute("SELECT COUNT(*) FROM commands WHERE status = 'confirmed'").fetchone()[0] == 64
    assert c.execute("SELECT detail FROM events WHERE kind = 'events_dropped'").fetchone() is not None
    cov = dict(c.execute(
        "SELECT bucket, covered_seconds FROM rollup_1m WHERE topic_id = (SELECT id FROM topics WHERE key='main/A')"))
    c.close()
    assert all(v == 0.0 for b, v in cov.items() if b * 60_000 >= t_sat // 60_000 * 60_000 + 60_000)
    # end of saturation: budget back, offline reopened at the flush time (device is offline)
    assert s.protected_budget_ok() and not s.saturated
    assert [(o.kind, o.start, o.end) for o in s._outages] == [("offline", T0 + 600_000, None)]
    assert s.audit_count() == 1
    s.append_command(cmd(1000))


def test_scoped_drop_and_ignore_cycles_at_the_cap(tmp_path, monkeypatch):
    amax = 100
    s = Store(str(tmp_path / "f.db"), audit_buffer_max=amax, buffer_max_entries=20)
    break_disk(s, monkeypatch)
    s.flush(T0, up(T0))
    ts = T0
    for cycle in range(300):
        topic = f"main/T{cycle}"
        ts += 10
        s.set_ignored(topic, True, ts)  # opens an `ignored` outage (until saturation)
        s.set_ignored(topic, False, ts + 1)
        s.observe(rcpt(topic, 1, ts + 2, changed=False))  # re-establishes: outage closed
        # drop cycle: overflow the sample buffer with one topic so it gets a scoped outage
        for k in range(25):
            s.observe(rcpt(f"main/D{cycle}", k, ts + 3 + k))
        ts += 40
        assert s.audit_count() <= amax
    assert s.saturated
    sats = [o for o in s._outages if o.saturation]
    assert len(sats) == 1 and sats[0].topic is None and sats[0].kind == "dropped"
    outage_records = [o for o in s._outages if o.rowid is None]
    assert len(outage_records) <= amax - RESERVED_SLOTS + 1
    before = len(s._outages)
    s.set_ignored("main/late", True, ts)
    s.observe(rcpt("main/zz", 1, ts))
    assert len(s._outages) == before
    # ignored receipts are still not stored while saturated
    n = s.sample_count
    s.observe(rcpt("main/late", 5, ts + 1))
    assert s.sample_count == n


def test_failed_flush_keeps_everything_for_retry(tmp_path, monkeypatch):
    s = Store(str(tmp_path / "g.db"))
    s.append_command(cmd(1))
    s.append_event(T0, "mode_change", {})
    s.open_outage("offline", T0)
    s.observe(rcpt("main/A", 1, T0))
    restore = break_disk(s, monkeypatch)
    assert not s.flush(T0 + 10, up(T0 + 10)).ok
    assert s.last_error and s.failing
    restore()
    assert s.flush(T0 + 20, up(T0 + 20)).ok and not s.failing
    c = sqlite3.connect(str(tmp_path / "g.db"))
    assert c.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 1
    assert c.execute("SELECT COUNT(*) FROM commands").fetchone()[0] == 1
    assert c.execute("SELECT COUNT(*) FROM outages").fetchone()[0] == 1
    assert c.execute("SELECT COUNT(*) FROM events WHERE kind='flush_failed'").fetchone()[0] == 1
    c.close()
