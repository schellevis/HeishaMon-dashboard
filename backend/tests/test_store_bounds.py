"""B1: history never scans or returns much more than it was asked for; energy is never thinned."""
from heishamon_dashboard import derived
from heishamon_dashboard.store import Store
from heishamon_dashboard.types import Liveness, Receipt

T0 = 1_791_000_000_000 // 3_600_000 * 3_600_000
MIN = 60_000
HOUR = 3_600_000


def rcpt(topic, value, ts, text=False):
    return Receipt(topic=topic, raw=str(value), value=value if text else float(value), valid=True,
                   retained=False, ts=ts, qualifying=False, changed=True)


def up(ts):
    return Liveness("online", ts, None)


def test_text_history_scan_capped(tmp_path):
    s = Store(str(tmp_path / "s.db"))
    for i in range(500):
        s.observe(rcpt("main/Error", f"E{i:03d}", T0 + i * MIN, text=True))
    now = T0 + 600 * MIN
    s.flush(now, up(now))
    h = s.history(["main/Error"], T0, now, 10, now, up(now))
    err = h["series"]["main/Error"]
    assert h["partial"] is True and err["truncated"] is True
    assert len(err["points"]) == 10 and err["points"][-1][1] == "E499"
    assert err["coverage"][0][0] >= T0 + (500 - 40) * MIN  # scan stopped at max_points × 4 rows
    # an untrimmed series carries no flag
    small = s.history(["main/Error"], T0 + 495 * MIN, now, 10, now, up(now))
    assert small["partial"] is False and "truncated" not in small["series"]["main/Error"]


def test_energy_not_thinned(tmp_path, monkeypatch):
    s = Store(str(tmp_path / "s.db"))
    prod, cons = derived.power_topics(None)[0]["heat"]
    days = 20  # > 14 days: hourly rollups
    for i in range(days * 24):
        s.observe(rcpt(prod, 1000, T0 + i * HOUR))
        s.observe(rcpt(cons, 250, T0 + i * HOUR))
    end = T0 + days * 24 * HOUR
    s.flush(end, up(end))

    def boom(*a, **k):
        raise AssertionError("energy must not use the thinned history path")

    monkeypatch.setattr(Store, "history", boom)
    out = derived.energy_joules(s, T0, end, "day", end, None, up(end))
    total = sum(m["heat"]["production_j"] for m in out.values())
    assert total == 1000 * days * 24 * 3600
    assert len(out) >= days
