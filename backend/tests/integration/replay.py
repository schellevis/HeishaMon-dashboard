"""Replay fixtures: the synthetic generator (simulator output) and the player used by the replay tests.

Regenerate the synthetic fixture with:

    PYTHONPATH=backend .venv/bin/python -m backend.tests.integration.replay
"""
import json
import sys

from .rig import FIXTURES, TOOLS, FakeClock, load_sim_modules

SYNTHETIC = FIXTURES / "replay_synthetic.json"
REAL = FIXTURES / "replay_real.json"
DURATION_S = 330  # one 300 s full re-publish plus a margin


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def generate_synthetic() -> dict:
    """Run the simulator (`heat_dhw` preset) for 330 s and sanitize its output like a real capture."""
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    import capture

    simulator, _presets = load_sim_modules()
    clock = FakeClock(0)
    sanitizer = capture.Sanitizer()
    messages = []

    def publish(topic, payload, retained):
        # `retained` as a subscriber sees it: only the snapshot delivered at subscribe time is flagged
        cleaned = sanitizer.clean(topic, str(payload))
        if cleaned is not None:
            messages.append({"t": clock.t, "topic": cleaned[0], "payload": cleaned[1], "retained": bool(retained) and clock.t == 0})

    sim = simulator.Simulator("heat_dhw", {}, publish, clock)
    commands = {60: ("SetDHWTemp", "50"), 120: ("SetDHWTemp", "52"), 180: ("SetDHWTemp", "50")}
    sim.start()
    for second in range(5, DURATION_S + 1, 5):
        clock.t = second * 1000
        # HeishaMon publishes `stats` every 5 s; its non-version fields are dropped by the sanitizer
        publish("stats", json.dumps({"version": "v4.2.3", "uptime": second, "heap": 40000}), False)
        sim.tick()
        if second in commands:
            sim.command(*commands[second])
    return {"format": capture.FORMAT, "synthetic": True, "duration_s": DURATION_S,
            "note": "synthetic: generated from tools/simulator.py (heat_dhw preset); not a real capture",
            "dropped": dict(sorted(sanitizer.dropped.items())), "messages": messages}


def play(app, document, *, start):
    """Publish a fixture through the broker into `app`, with the app clock following the fixture time.

    Messages flagged `retained` are the snapshot a late subscriber receives; they must be seeded
    *before* the app connects (see `seed`). Everything else is published live, in time order.
    """
    live = [m for m in document["messages"] if not is_seed(m)]
    index = 0
    while index < len(live):
        t = live[index]["t"]
        batch = []
        while index < len(live) and live[index]["t"] == t:
            batch.append((live[index]["topic"], live[index]["payload"]))
            index += 1
        app.feed_many(batch, at=start + t)
    return start + max((m["t"] for m in document["messages"]), default=0)


def is_seed(message):
    return message["retained"]


def seed(broker, document):
    for message in document["messages"]:
        if is_seed(message):
            broker.publish(message["topic"], message["payload"], True)
    broker.drain()


if __name__ == "__main__":
    SYNTHETIC.write_text(json.dumps(generate_synthetic(), indent=1) + "\n", encoding="utf-8")
    print(f"wrote {SYNTHETIC}")
