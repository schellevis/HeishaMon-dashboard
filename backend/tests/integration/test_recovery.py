"""Integrated recovery (plan re-review I-R1): MQTT → State → Store through the embedded broker.

A topic-scoped outage (`dropped` after a buffer overflow, `ignored` after un-ignore) must end at the
first receipt after the cause is gone, that receipt must be stored even when its value equals what
was cached, and coverage must be 0 inside the outage and > 0 after it.
"""
import pytest

from .rig import FakeClock, hms

A = "main/Heat_Power_Production"
B = "main/Compressor_Freq"


def raw_coverage(app, topic, start, end):
    body = app.client.get("/api/history", params={"topics": topic, "from": start, "to": end,
                                                  "max_points": 1000}).json()
    assert body["resolution"] == "raw"
    return body["series"][topic]


def covered_ms(intervals, a, b):
    """Milliseconds of `intervals` that fall inside [a, b)."""
    return sum(max(0, min(e, b) - max(s, a)) for s, e in intervals)


def samples(app, topic):
    with app.db() as conn:
        rows = conn.execute("SELECT s.ts, s.num FROM samples s JOIN topics t ON t.id = s.topic_id "
                            "WHERE t.key = ? ORDER BY s.ts", (topic,)).fetchall()
    return [(r[0], r[1]) for r in rows]


@pytest.mark.parametrize("recovery", ["1000", "2000"], ids=["equal-to-stored", "equal-to-cached"])
def test_recovery_after_a_dropped_outage(broker, make_app, recovery):
    """A=1000 is flushed, its 2000 change is pushed out of the buffer, then A reports `recovery`.

    `1000` equals the last *stored* value (the plan's case); `2000` equals the value the state cache
    holds, so without the pending-outage bypass the store would drop it as unchanged.
    """
    app = make_app(clock=FakeClock(hms(6, 59, 30)), BUFFER_MAX_ENTRIES=1000)
    with app:
        app.feed("LWT", "Online", at=hms(7))
        app.feed(A, "1000", at=hms(7, 0, 5))
        app.flush(at=hms(7, 0, 30))
        assert samples(app, A) == [(hms(7, 0, 5), 1000.0)]

        app.feed(A, "2000", at=hms(7, 1))
        # no flush: 2100 changes on B overflow the buffer (> 2 × BUFFER_MAX_ENTRIES) and push A's sample out
        app.feed_many([(B, str(i)) for i in range(1, 2101)], at=hms(7, 1, 1))
        assert app.system()["buffer"]["samples"] <= 2000
        app.feed("LWT", "Online", at=hms(7, 1, 30))

        app.feed(A, recovery, at=hms(7, 5))
        app.feed("LWT", "Online", at=hms(7, 5, 10))
        app.flush(at=hms(7, 6))

        # the recovery sample is stored, whatever its value
        assert samples(app, A) == [(hms(7, 0, 5), 1000.0), (hms(7, 5), float(recovery))]
        # the topic's `dropped` outage ends at that receipt's timestamp
        assert app.outages(kind="dropped", topic=A) == [(hms(7, 1), hms(7, 5), "dropped", A)]
        events = app.client.get("/api/events", params={"kind": "buffer_overflow"}).json()["events"]
        assert events and events[0]["detail"]["count"] >= 1

        series = raw_coverage(app, A, hms(7), hms(7, 6))
        intervals = series["coverage"]
        assert covered_ms(intervals, hms(7, 1), hms(7, 5)) == 0  # nothing carried across the drop
        assert covered_ms(intervals, hms(7, 0, 5), hms(7, 1)) == 55_000
        assert covered_ms(intervals, hms(7, 5), hms(7, 6)) > 0
        assert series["breaks"] == []  # 4 min, below the 10 min chart-break threshold
        # LOCF never shows 1000 W after the drop: the first point after 07:01:00 is the recovery sample
        assert [p for p in series["points"] if p[0] > hms(7, 1)] == [[hms(7, 5), float(recovery)]]


def prefs_with(app, key, state):
    prefs = app.client.get("/api/prefs").json()
    visibility = dict(prefs["topic_visibility"])
    if state is None:
        visibility.pop(key, None)
    else:
        visibility[key] = state
    prefs["topic_visibility"] = visibility
    response = app.client.put("/api/prefs", json=prefs)
    assert response.status_code == 200, response.text


def test_recovery_after_un_ignore(broker, make_app):
    """A=500 is ignored, un-ignored, and then reports 500 again (equal to the cached value)."""
    app = make_app(clock=FakeClock(hms(7, 59, 30)))
    with app:
        app.feed("LWT", "Online", at=hms(8))
        app.feed(A, "500", at=hms(8, 0, 1))
        app.flush(at=hms(8, 0, 2))

        app.clock.t = hms(8, 0, 30)
        prefs_with(app, A, "ignored")
        app.feed(A, "500", at=hms(8, 10))  # ignored: not stored
        app.clock.t = hms(8, 30)
        prefs_with(app, A, None)  # un-ignored; the outage stays open until the next value
        app.feed("LWT", "Online", at=hms(8, 30, 30))
        assert app.outages(kind="ignored") == []  # nothing flushed yet: still only in memory

        app.feed(A, "500", at=hms(8, 31))  # unchanged, but must be stored
        app.feed("LWT", "Online", at=hms(8, 31, 30))
        app.flush(at=hms(8, 32))

        assert samples(app, A) == [(hms(8, 0, 1), 500.0), (hms(8, 31), 500.0)]
        assert app.outages(kind="ignored", topic=A) == [(hms(8, 0, 30), hms(8, 31), "ignored", A)]

        series = raw_coverage(app, A, hms(8), hms(8, 32))
        assert covered_ms(series["coverage"], hms(8, 0, 30), hms(8, 31)) == 0
        assert covered_ms(series["coverage"], hms(8, 0, 1), hms(8, 0, 30)) == 29_000
        assert covered_ms(series["coverage"], hms(8, 31), hms(8, 32)) > 0
        assert [p for p in series["points"] if p[0] > hms(8, 0, 30)] == [[hms(8, 31), 500]]
