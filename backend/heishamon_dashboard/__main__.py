"""`python -m heishamon_dashboard`: read the configuration from the environment and serve.

SIGTERM/SIGINT make uvicorn shut down gracefully; the app's lifespan then flushes (spec §5.1).
No `.env` file is read here; compose or the shell supplies the environment.
"""
import logging
import os
import sys

import uvicorn

from heishamon_dashboard.app import DEFAULT_STATIC_DIR, build
from heishamon_dashboard.config import ConfigError, load

GRACEFUL_SHUTDOWN_S = 45  # compose allows 60 s (stop_grace_period)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        config = load(os.environ)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    app = build(config, static_dir=os.environ.get("STATIC_DIR") or DEFAULT_STATIC_DIR)
    uvicorn.run(app, host="0.0.0.0", port=config.http_port, log_level="info",
                timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_S)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
