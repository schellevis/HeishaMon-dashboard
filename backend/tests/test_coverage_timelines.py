"""Spec §5.4 worked timelines T1-T9, asserted literally, plus retention behaviour."""
import sqlite3
from datetime import datetime, timezone

import pytest

from heishamon_dashboard.store import Store
from heishamon_dashboard.types import Liveness, Receipt

TOPIC = "main/Heat_Power_Production"
DAY0 = int(datetime(2026, 10, 11, tzinfo=timezone.utc).timestamp() * 1000)
MIN = 60_000


def t(hms: str) -> int:
    h, m, s = (int(x) for x in hms.split(":"))
    return DAY0 + ((h * 60 + m) * 60 + s) * 1000


def rcpt(topic, value, ts, *, changed=True, qualifying=False, retained=False):
    return Receipt(topic=topic, raw=str(value), value=float(value), valid=True, retained=retained,
                   ts=ts, qualifying=qualifying, changed=changed)


def live_msg(ts):  # LWT=Online heartbeat: qualifying, not a value change
    return Receipt(topic="LWT", raw="Online", value="Online", valid=True, retained=False,
                   ts=ts, qualifying=True, changed=False)


def online(last_q):
    return Liveness("online", last_q, None)


def offline(last_q, since):
    return Liveness("offline", last_q, since)


def ro(path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def minute_rows(path, topic=TOPIC) -> dict[str, tuple]:
    """{'hh:mm': (covered_seconds, avg, min, max, last)}"""
    c = ro(path)
    out = {}
    for b, cov, avg, mn, mx, last in c.execute(
        "SELECT bucket, covered_seconds, avg, min, max, last FROM rollup_1m r "
        "JOIN topics t ON t.id = r.topic_id WHERE t.key = ? ORDER BY bucket", (topic,)
    ):
        ms = b * MIN
        out[datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%H:%M")] = (cov, avg, mn, mx, last)
    c.close()
    return out


def hour_rows(path, topic=TOPIC) -> dict[str, tuple]:
    c = ro(path)
    out = {}
    for b, cov, avg in c.execute(
        "SELECT bucket, covered_seconds, avg FROM rollup_1h r "
        "JOIN topics t ON t.id = r.topic_id WHERE t.key = ? ORDER BY bucket", (topic,)
    ):
        out[datetime.fromtimestamp(b * 3600, timezone.utc).strftime("%H:%M")] = (cov, avg)
    c.close()
    return out


def energy(rows: dict[str, tuple], lo="00:00", hi="23:59") -> float:
    return sum(v[1] * v[0] for k, v in rows.items() if lo <= k <= hi and v[1] is not None)


def outage_rows(path) -> list[tuple]:
    c = ro(path)
    out = c.execute(
        "SELECT start_ts, end_ts, kind, (SELECT key FROM topics WHERE id = topic_id) FROM outages "
        "ORDER BY start_ts, kind"
    ).fetchall()
    c.close()
    return out


@pytest.fixture
def path(tmp_path):
    return str(tmp_path / "t.db")


def test_t1_change_inside_bucket_flush_mid_bucket(path):
    s = Store(path)
    s.observe(rcpt(TOPIC, 1000, t("00:00:00")))
    s.observe(rcpt(TOPIC, 2000, t("00:00:30")))
    assert s.flush(t("00:01:30"), online(t("00:01:30"))).ok
    rows = minute_rows(path)
    assert rows["00:00"] == (60.0, 1500.0, 1000.0, 2000.0, 2000.0)
    assert rows["00:00"][1] * rows["00:00"][0] == pytest.approx(90_000)
    assert rows["00:01"][0] == 30.0 and rows["00:01"][1] == 2000.0

    assert s.flush(t("00:02:00"), online(t("00:02:00"))).ok
    rows = minute_rows(path)
    assert rows["00:01"] == (60.0, 2000.0, 2000.0, 2000.0, 2000.0)
    assert set(rows) == {"00:00", "00:01"}
    assert energy(rows) == pytest.approx(210_000)
    assert hour_rows(path)["00:00"] == (120.0, 1750.0)


def test_t2_unchanged_hours(path):
    s = Store(path)
    s.observe(rcpt(TOPIC, 500, t("01:00:00")))
    assert s.flush(t("03:00:00"), online(t("03:00:00"))).ok
    rows = minute_rows(path)
    assert len(rows) == 120
    assert all(v[0] == 60.0 and v[1] == 500.0 for v in rows.values())
    hours = hour_rows(path)
    assert hours == {"01:00": (3600.0, 500.0), "02:00": (3600.0, 500.0)}
    assert energy(rows) == pytest.approx(3_600_000)


def test_t3_short_outage(path):
    s = Store(path)
    s.observe(rcpt(TOPIC, 1000, t("04:00:00")))
    s.observe(live_msg(t("04:02:10")))
    s.open_outage("offline", t("04:02:10"))  # opened at 04:02:40 by the 30 s timeout, backdated
    s.observe(live_msg(t("04:04:00")))
    assert s.flush(t("04:05:00"), online(t("04:04:55"))).ok
    assert outage_rows(path) == [(t("04:02:10"), t("04:04:00"), "offline", None)]
    rows = minute_rows(path)
    assert [rows[k][0] for k in ("04:00", "04:01", "04:02", "04:03", "04:04")] == [60.0, 60.0, 10.0, 0.0, 60.0]
    assert rows["04:03"][1] is None
    assert energy(rows, "04:00", "04:04") == pytest.approx(190_000)
    # 110 s: the chart line stays continuous
    h = s.history([TOPIC], t("04:00:00"), t("04:05:00"), 1000, t("04:05:00"), online(t("04:04:55")))
    assert h["series"][TOPIC]["breaks"] == []


def test_t4_restart_with_retained_snapshot(path):
    s = Store(path)
    s.observe(rcpt(TOPIC, 800, t("04:30:00")))
    assert s.flush(t("05:00:00"), online(t("04:59:55"))).ok
    assert s.frontier() == {"flush_ts": t("05:00:00"), "device_online": "online",
                            "last_qualifying_ts": t("04:59:55")}
    del s  # crash at 05:07:00: nothing since 05:00:00 survives
    s = Store(path)
    s.startup(t("05:20:00"))
    s.observe(rcpt(TOPIC, 800, t("05:20:01"), retained=True))  # retained: sets LOCF, never coverage
    s.observe(live_msg(t("05:20:04")))
    assert s.flush(t("05:21:00"), online(t("05:21:00"))).ok
    assert outage_rows(path) == [(t("05:00:00"), t("05:20:04"), "restart", None)]
    rows = minute_rows(path)
    assert all(rows[f"05:{m:02d}"][0] == 0.0 for m in range(0, 20))
    assert rows["05:20"][0] == 56.0 and rows["05:20"][1] == 800.0
    h = s.history([TOPIC], t("05:00:00"), t("05:21:00"), 1000, t("05:21:00"), online(t("05:21:00")))
    assert h["series"][TOPIC]["breaks"] == [[t("05:00:00"), t("05:20:04")]]  # > 10 min: the line breaks


def test_t5_failed_flush_with_overflow(path, monkeypatch):
    s = Store(path, buffer_max_entries=1000)
    real = s._flush_tx

    def disk_full(*a, **k):
        raise sqlite3.OperationalError("database or disk is full")

    monkeypatch.setattr(s, "_flush_tx", disk_full)
    for i in range(1200):  # 1 change/s from 06:00:00, 1000 W at even seconds
        ts = t("06:00:00") + i * 1000
        s.observe(rcpt(TOPIC, 1000 if i % 2 == 0 else 2000, ts))
        if s.needs_flush and not s.failing:
            assert not s.flush(ts, online(ts)).ok
        assert s.sample_count <= 1000
    assert s.sample_count == 1000
    monkeypatch.setattr(s, "_flush_tx", real)
    assert s.flush(t("06:20:00"), online(t("06:19:59"))).ok
    assert outage_rows(path) == [(t("06:00:00"), t("06:03:20"), "dropped", TOPIC)]
    rows = minute_rows(path)
    assert [rows[f"06:0{m}"][0] for m in range(3)] == [0.0, 0.0, 0.0]
    assert rows["06:03"][0] == 40.0 and rows["06:03"][1] == 1500.0
    for m in range(4, 20):
        assert rows[f"06:{m:02d}"][0] == 60.0 and rows[f"06:{m:02d}"][1] == 1500.0
    c = ro(path)
    ev = c.execute("SELECT detail FROM events WHERE kind = 'buffer_overflow'").fetchall()
    c.close()
    assert len(ev) == 1
    import json
    assert json.loads(ev[0][0]) == {"count": 200, "first_ts": t("06:00:00"), "last_ts": t("06:03:19")}


def test_t6_restart_while_already_offline(path):
    s = Store(path)
    s.observe(rcpt(TOPIC, 1000, t("04:00:00")))
    s.observe(live_msg(t("04:02:10")))
    s.open_outage("offline", t("04:02:10"))  # opened at 04:02:40
    assert s.flush(t("04:03:00"), offline(t("04:02:10"), t("04:02:10"))).ok
    assert s.frontier() == {"flush_ts": t("04:03:00"), "device_online": "offline",
                            "last_qualifying_ts": t("04:02:10")}
    del s
    s = Store(path)
    s.startup(t("04:10:00"))
    s.observe(live_msg(t("04:10:05")))
    assert s.flush(t("04:11:00"), online(t("04:11:00"))).ok
    assert outage_rows(path) == [
        (t("04:02:10"), t("04:10:05"), "offline", None),
        (t("04:03:00"), t("04:10:05"), "restart", None),
    ]
    rows = minute_rows(path)
    covered = sum(v[0] for k, v in rows.items() if "04:00" <= k <= "04:10")
    assert covered == 185.0 == 130 + 55
    assert energy(rows, "04:00", "04:10") == pytest.approx(185_000)


def test_t7_flush_before_a_backdated_timeout(path):
    s = Store(path)
    s.observe(rcpt(TOPIC, 1000, t("04:00:00")))
    s.observe(live_msg(t("04:02:10")))
    res = s.flush(t("04:02:30"), online(t("04:02:10")))
    assert res.ok and res.horizon == t("04:02:10")
    assert minute_rows(path)["04:02"][0] == 30.0  # provisional
    s.open_outage("offline", t("04:02:10"))  # 04:02:40 timeout, backdated
    assert s.flush(t("04:05:00"), offline(t("04:02:10"), t("04:02:10"))).ok
    rows = minute_rows(path)
    assert rows["04:02"][0] == 10.0  # replaces the provisional 30 s
    assert rows["04:03"][0] == 0.0 and rows["04:04"][0] == 0.0
    assert energy(rows, "04:00", "04:04") == pytest.approx(130_000)


def test_t8_only_one_topics_change_dropped(path, monkeypatch):
    a, b = "main/A", "main/B"
    s = Store(path, buffer_max_entries=100)
    s.observe(rcpt(a, 1000, t("07:00:00")))
    assert s.flush(t("07:00:10"), online(t("07:00:10"))).ok
    real = s._flush_tx

    def disk_full(*args, **kw):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(s, "_flush_tx", disk_full)
    assert not s.flush(t("07:00:30"), online(t("07:00:30"))).ok  # disk full from 07:00:30
    for sec in range(30, 331):  # 07:00:30 .. 07:05:30; B changes every second
        ts = t("07:00:00") + sec * 1000
        if ts == t("07:01:00"):
            s.observe(rcpt(a, 2000, ts))
        if ts == t("07:05:00"):
            s.observe(rcpt(a, 2000, ts, changed=False))  # full re-publish, equal to the cached value
        s.observe(rcpt(b, sec, ts))
    monkeypatch.setattr(s, "_flush_tx", real)
    assert s.flush(t("07:06:00"), online(t("07:06:00"))).ok
    out = {r[3]: r for r in outage_rows(path)}
    assert out[a][:3] == (t("07:01:00"), t("07:05:00"), "dropped")  # closed by the re-publish
    c = ro(path)
    b_oldest = c.execute(
        "SELECT MIN(ts) FROM samples WHERE topic_id = (SELECT id FROM topics WHERE key = ?)", (b,)).fetchone()[0]
    a_ts = [r[0] for r in c.execute(
        "SELECT ts FROM samples WHERE topic_id = (SELECT id FROM topics WHERE key = ?) ORDER BY ts", (a,))]
    c.close()
    assert out[b][:3] == (t("07:00:30"), b_oldest, "dropped")
    assert a_ts == [t("07:00:00"), t("07:05:00")]  # the 07:05:00 value is stored although unchanged
    rows = minute_rows(path, a)
    assert rows["07:00"][:2] == (60.0, 1000.0)
    assert all(rows[f"07:0{m}"][0] == 0.0 for m in range(1, 5))
    assert rows["07:05"][:2] == (60.0, 2000.0)  # A's LOCF never carries 1000 W past 07:01:00


def test_t9_ignore_and_unignore(path):
    s = Store(path)
    s.observe(rcpt(TOPIC, 500, t("07:50:00")))
    s.set_ignored(TOPIC, True, t("08:00:00"))
    s.observe(rcpt(TOPIC, 600, t("08:15:00")))  # ignored: not stored
    s.set_ignored(TOPIC, False, t("08:30:00"))
    s.observe(rcpt(TOPIC, 500, t("08:31:00"), changed=False))
    assert s.flush(t("08:40:00"), online(t("08:40:00"))).ok
    assert outage_rows(path) == [(t("08:00:00"), t("08:31:00"), "ignored", TOPIC)]
    c = ro(path)
    stamps = [r[0] for r in c.execute("SELECT ts FROM samples ORDER BY ts")]
    c.close()
    assert stamps == [t("07:50:00"), t("08:31:00")]
    rows = minute_rows(path)
    assert all(rows[f"08:{m:02d}"][0] == 0.0 for m in range(0, 31))
    assert rows["08:31"][:2] == (60.0, 500.0)
    assert rows["07:59"][:2] == (60.0, 500.0)


def test_retention_purge_keeps_anchor_and_history_identical(path):
    d = 86_400_000
    topic = "main/X"
    s = Store(path)
    s.observe(rcpt(topic, 100, DAY0 + d))
    s.observe(rcpt(topic, 200, DAY0 + d + 6 * 3600_000))
    s.open_outage("offline", DAY0 + d + 3600_000)
    s.close_outage("offline", DAY0 + d + 2 * 3600_000)  # 1 h outage: a chart break
    assert s.flush(DAY0 + 2 * d, online(DAY0 + 2 * d)).ok
    frm, to = DAY0 + d, DAY0 + d + 12 * 3600_000
    short_to = DAY0 + d + 3600_000
    before = s.history([topic], frm, to, 10_000, DAY0 + 2 * d, online(DAY0 + 2 * d))
    assert before["resolution"] == "1m"  # 12 h > 6 h
    assert s.history([topic], frm, short_to, 10_000, DAY0 + 2 * d, None)["resolution"] == "raw"
    one_hour_before = s.history([topic], frm, DAY0 + 20 * d, 10_000, DAY0 + 2 * d, None)
    assert one_hour_before["resolution"] == "1h"
    s.close()

    s = Store(path, raw_retention_days=1)
    s.observe(rcpt(topic, 300, DAY0 + 5 * d + 600_000))
    now = DAY0 + 6 * d
    assert s.flush(now, online(now)).ok
    c = ro(path)
    stamps = [r[0] for r in c.execute("SELECT ts FROM samples ORDER BY ts")]
    c.close()
    assert stamps == [DAY0 + d + 6 * 3600_000, DAY0 + 5 * d + 600_000]  # anchor kept, older purged
    after = s.history([topic], frm, to, 10_000, now, online(now))
    assert after["resolution"] == "1m"
    assert after["series"][topic]["points"] == before["series"][topic]["points"]
    assert after["series"][topic]["breaks"] == before["series"][topic]["breaks"] == [
        [DAY0 + d + 3600_000, DAY0 + d + 2 * 3600_000]]
    # <= 6 h on expired history is served at 1m, never raw
    short = s.history([topic], frm, short_to, 10_000, now, online(now))
    assert short["resolution"] == "1m"
    exp_pts = [p for p in before["series"][topic]["points"] if p[0] < short_to]
    assert short["series"][topic]["points"] == exp_pts
    # 1h identical too
    h1 = s.history([topic], frm, DAY0 + 20 * d, 10_000, now, online(now))
    assert h1["resolution"] == "1h"
    pre = [p for p in one_hour_before["series"][topic]["points"] if p[0] < DAY0 + 2 * d]
    assert [p for p in h1["series"][topic]["points"] if p[0] < DAY0 + 2 * d] == pre
    # the anchor still gives the LOCF carry-in for an unexpired raw query
    raw = s.history([topic], DAY0 + 5 * d, DAY0 + 5 * d + 3600_000, 10_000, now, online(now))
    assert raw["resolution"] == "raw"
    assert raw["series"][topic]["points"][0] == [DAY0 + 5 * d, 200.0]
    assert raw["series"][topic]["points"][1] == [DAY0 + 5 * d + 600_000, 300.0]
