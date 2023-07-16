from __future__ import annotations

from panel import logger
from panel.common import threads
from panel.config import config
from panel.functions import PlayerCountCollection
from panel.init_app import wsgi_app


def main() -> int:
    logger.configure_logging("DEBUG" if config.app_developer_build else "INFO")
    # Temporary.
    threads.run(
        PlayerCountCollection,
        True,
    )

    wsgi_app.run(host=config.http_host, port=config.http_port, threaded=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
