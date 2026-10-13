"""Schema, flush transaction, collision bump, prefs and History shape."""
import json
import sqlite3

import pytest

from heishamon_dashboard.db import SCHEMA_VERSION, SchemaError
from heishamon_dashboard.store import Store
from heishamon_dashboard.types import Liveness, Receipt

T0 = 1_791_000_000_000


def rcpt(topic, value, ts, changed=True, qualifying=False, retained=False):
    is_text = isinstance(value, str)
    return Receipt(topic=topic, raw=str(value), value=value if is_text else float(value), valid=True,
                   retained=retained, ts=ts, qualifying=qualifying, changed=changed)


def up(ts):
    return Liveness("online", ts, None)


def test_schema_and_pragmas(tmp_path):
    p = str(tmp_path / "s.db")
    s = Store(p)
    c = sqlite3.connect(p)
    tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"schema_version", "topics", "samples", "rollup_1m", "rollup_1h", "rollup_state", "commands",
            "events", "prefs", "outages", "frontier"} <= tables
    assert c.execute("SELECT version FROM schema_version").fetchall() == [(SCHEMA_VERSION,)]
    cols = [r[1] for r in c.execute("PRAGMA table_info(rollup_1m)")]
    assert cols == ["topic_id", "bucket", "first_ts", "last_ts", "covered_seconds", "avg", "min", "max", "last"]
    cols = [r[1] for r in c.execute("PRAGMA table_info(commands)")]
    assert cols == ["id", "uuid", "submitted_ts", "published_ts", "name", "payload", "retained", "class",
                    "prev_value", "status", "confirmed_ts", "attempts", "detail", "keys"]
    assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert s._conn.execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL
    assert s._conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    c.close()
    s.close()
    c = sqlite3.connect(p)
    c.execute("UPDATE schema_version SET version = 99")
    c.commit()
    c.close()
    with pytest.raises(SchemaError):
        Store(p)


def test_flush_is_one_transaction(tmp_path):
    s = Store(str(tmp_path / "s.db"))
    s.observe(rcpt("main/A", 1, T0))
    s.observe(rcpt("main/B", 2, T0 + 1))
    s.append_command({"uuid": "u1", "submitted_ts": T0, "name": "SetX", "payload": "1", "retained": False,
                      "class": "setting", "status": "pending", "attempts": 0})
    s.append_event(T0, "mode_change", {"to": 1})
    s.open_outage("offline", T0)
    stmts = []
    s._conn.set_trace_callback(stmts.append)
    assert s.flush(T0 + 120_000, up(T0 + 120_000)).ok
    s._conn.set_trace_callback(None)
    kinds = [x.split()[0].upper() for x in stmts]
    assert kinds.count("BEGIN") == 1 and kinds.count("COMMIT") == 1
    assert kinds[0] == "BEGIN" and kinds[-1] == "COMMIT"
    assert "ROLLBACK" not in kinds
    # nothing is written to the database before the flush
    s.observe(rcpt("main/A", 3, T0 + 200_000))
    c = sqlite3.connect(str(tmp_path / "s.db"))
    assert c.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 2
    c.close()


def test_dedup_and_collision_bump(tmp_path):
    s = Store(str(tmp_path / "s.db"))
    s.observe(rcpt("main/A", 1, T0))
    s.observe(rcpt("main/A", 1, T0 + 5, changed=False))  # periodic re-publish: dedup'd away
    assert s.sample_count == 1
    s.observe(rcpt("main/A", 2, T0))  # same millisecond
    s.observe(rcpt("main/A", 3, T0))
    s.observe(rcpt("main/B", 9, T0))  # other topic unaffected
    assert [x.ts for x in s._topic_buf["main/A"]] == [T0, T0 + 1, T0 + 2]
    assert [x.ts for x in s._topic_buf["main/B"]] == [T0]
    s.flush(T0 + 1000, up(T0 + 1000))
    s.observe(rcpt("main/A", 4, T0 + 1))  # collides with an already flushed ts
    assert s._topic_buf["main/A"][0].ts == T0 + 3
    s.flush(T0 + 2000, up(T0 + 2000))
    c = sqlite3.connect(str(tmp_path / "s.db"))
    ts = [r[0] for r in c.execute(
        "SELECT ts FROM samples WHERE topic_id = (SELECT id FROM topics WHERE key = 'main/A') ORDER BY ts")]
    c.close()
    assert ts == [T0, T0 + 1, T0 + 2, T0 + 3]


def test_prefs_are_written_immediately(tmp_path):
    p = str(tmp_path / "s.db")
    s = Store(p)
    prefs = {"write_lock": True, "topic_visibility": {"main/A": "ignored"}, "tiles": ["main/A"]}
    s.prefs_put(prefs)
    c = sqlite3.connect(p)  # no flush
    got = {k: json.loads(v) for k, v in c.execute("SELECT key, value FROM prefs")}
    c.close()
    assert got == prefs and s.prefs_get() == prefs
    s.close()
    s2 = Store(p)  # ignored topics are restored from prefs
    s2.observe(rcpt("main/A", 5, T0))
    assert s2.sample_count == 0


def test_commands_in_place_update_and_confirmed_setcurves(tmp_path):
    p = str(tmp_path / "s.db")
    s = Store(p)
    base = {"submitted_ts": T0, "retained": False, "class": "setting", "attempts": 0}
    s.append_command({**base, "uuid": "a", "name": "SetCurves", "payload": "{}", "status": "pending",
                      "keys": {"Z1_Heat_Curve_Target_High_Temp": {"expected": 1, "status": "pending"}}})
    s.append_command({**base, "uuid": "b", "name": "SetCurves", "payload": "{}", "status": "pending",
                      "keys": {"Z2_Cool_Curve_Outside_Low_Temp": {"expected": 1, "status": "pending"}}})
    s.update_command("a", {"status": "confirmed", "confirmed_ts": T0 + 50, "detail": "x" * 5000})
    assert s.audit_count() == 2  # in place: still two records
    assert len(s.get_command("a")["detail"]) == 2048
    assert s.last_confirmed_setcurves(1, "heat") == T0 + 50
    assert s.last_confirmed_setcurves(1, "cool") is None
    assert s.last_confirmed_setcurves(2, "cool") is None
    s.flush(T0 + 100, up(T0 + 100))
    s.update_command("b", {"status": "confirmed", "confirmed_ts": T0 + 90})  # update of a flushed command
    assert s.audit_count() == 1
    assert s.last_confirmed_setcurves(2, "cool") == T0 + 90
    s.update_command("a", {"confirmed_ts": T0 + 95})
    s.flush(T0 + 200, up(T0 + 200))
    c = sqlite3.connect(p)
    rows = c.execute("SELECT uuid, status, confirmed_ts, keys FROM commands ORDER BY uuid").fetchall()
    c.close()
    assert rows[0][:3] == ("a", "confirmed", T0 + 95) and json.loads(rows[0][3])
    assert rows[1][:3] == ("b", "confirmed", T0 + 90)
    assert s.last_confirmed_setcurves("Z1", "Heat") == T0 + 95
    assert {r["uuid"] for r in s.list_commands()} == {"a", "b"}


def test_startup_keeps_open_outages_and_opens_restart(tmp_path):
    p = str(tmp_path / "s.db")
    s = Store(p)
    assert s.frontier() is None
    s.startup(T0)  # first ever run: restart outage from now
    assert [(o["kind"], o["start_ts"], o["end_ts"]) for o in s.outages_list()] == [("restart", T0, None)]
    s.flush(T0 + 1000, up(T0 + 1000))
    s.open_outage("offline", T0 + 1500)
    s.flush(T0 + 2000, Liveness("offline", T0 + 1000, T0 + 1500))
    s.close()
    s = Store(p)
    s.startup(T0 + 9000)
    got = [(o["kind"], o["start_ts"], o["end_ts"]) for o in s.outages_list()]
    # the restart outage left open by the earlier run is kept, not duplicated
    assert got == [("restart", T0, None), ("offline", T0 + 1500, None)]
    assert s.open_outage("offline", T0 + 9999).start == T0 + 1500  # idempotent
    s.close_outage("restart", T0 + 9500)
    assert all(o["end_ts"] == T0 + 9500 for o in s.outages_list() if o["kind"] == "restart")
    assert s.close_outage("offline", T0 + 1500)  # never closed at or before its own start
    assert [o for o in s.outages_list() if o["kind"] == "offline"][0]["end_ts"] == T0 + 1501


def test_history_shapes_numeric_text_and_truncation(tmp_path):
    s = Store(str(tmp_path / "s.db"))
    base = T0 - T0 % 3_600_000
    for i in range(30):  # one change per minute
        s.observe(rcpt("main/A", i, base + i * 60_000))
    s.observe(rcpt("main/Error", "F12", base + 10 * 60_000))
    s.observe(rcpt("main/Error", "H00", base + 20 * 60_000))
    now = base + 30 * 60_000
    frm, to = base + 5 * 60_000 + 30_000, now
    lv = up(now)

    h = s.history(["main/A", "main/Error"], frm, to, 1000, now, lv)  # buffer only, nothing flushed
    assert h["resolution"] == "raw" and h["partial"] is False
    a = h["series"]["main/A"]
    assert a["kind"] == "number" and a["breaks"] == []
    assert a["points"][0] == [frm, 5.0]  # LOCF carried in at `from`
    assert a["points"][1] == [base + 6 * 60_000, 6.0]
    assert a["coverage"] == [[frm, to]]
    e = h["series"]["main/Error"]
    assert e["kind"] == "text" and e["coverage"] == [[base + 10 * 60_000, to]]
    assert e["points"] == [[base + 10 * 60_000, "F12"], [base + 20 * 60_000, "H00"]]

    # same query after a flush gives the same raw points
    s.flush(now, lv)
    h2 = s.history(["main/A", "main/Error"], frm, to, 1000, now, lv)
    assert h2 == h

    # rollup resolution: [bucket_start_ts, avg, covered_seconds], coverage null, text stays raw
    h3 = s.history(["main/A", "main/Error"], frm, to, 10, now, lv)
    assert h3["resolution"] == "1m" and h3["partial"] is True
    a3 = h3["series"]["main/A"]
    assert a3["coverage"] is None and len(a3["points"]) == 10
    assert a3["points"][-1] == [base + 29 * 60_000, 29.0, 60.0]
    assert [p[0] for p in a3["points"]] == [base + m * 60_000 for m in range(20, 30)]  # newest kept
    assert h3["series"]["main/Error"]["points"][0] == [base + 10 * 60_000, "F12"]

    # live recompute through now for a constant topic (no change buffered, nothing flushed yet)
    later = now + 3 * 60_000
    h4 = s.history(["main/A"], now, later, 10, later, up(later))
    assert h4["resolution"] == "raw" and h4["series"]["main/A"]["coverage"] == [[now, later]]
    s2 = s.rollups_1m(["main/A"], now - 5 * 60_000, later, later, up(later))["main/A"]
    assert [r[0] for r in s2] == [(now - 5 * 60_000) // 60_000 + i for i in range(8)]
    assert s2[-1][3] == 60.0 and s2[-1][4] == 29.0 and s2[-1][7] == 29.0
    assert len(s2[0]) == 8


def test_unknown_topic_and_empty_range(tmp_path):
    s = Store(str(tmp_path / "s.db"))
    h = s.history(["main/Nope"], T0, T0 + 1000, 100, T0 + 1000, None)
    assert h["series"]["main/Nope"]["points"] == [] and h["series"]["main/Nope"]["breaks"] == []
    assert s.rollups_1m(["main/Nope"], T0, T0 + 1000, T0 + 1000, None) == {"main/Nope": []}


def test_event_detail_truncated_before_buffer(tmp_path):
    from heishamon_dashboard.store import DETAIL_MAX_BYTES

    s = Store(str(tmp_path / "s.db"))
    s.append_event(T0, "big", {"text": "x" * 100_000})
    s.append_event(T0 + 1, "small", {"n": 1})
    big, small = s._events[-2], s._events[-1]
    assert len(json.dumps(big["detail"]).encode()) <= DETAIL_MAX_BYTES + 64
    assert big["detail"].get("truncated") is True
    assert small["detail"] == {"n": 1}
