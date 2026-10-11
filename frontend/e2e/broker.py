"""Embedded MQTT broker for the end-to-end run. Binds an ephemeral loopback port, prints it as
`PORT <n>` on stdout, and runs until SIGTERM/SIGINT."""
import asyncio
import signal
import socket

from amqtt.broker import Broker


async def main() -> None:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    broker = Broker({
        "listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{port}"}},
        "sys_interval": 0,
        "auth": {"allow-anonymous": True, "plugins": ["auth_anonymous"]},
        "topic-check": {"enabled": False},
    })
    await broker.start()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    print(f"PORT {port}", flush=True)
    await stop.wait()
    try:
        await asyncio.wait_for(broker.shutdown(), 5)
    except Exception:
        pass


asyncio.run(main())
