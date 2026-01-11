from __future__ import annotations


from panel import logger
from panel.config import config
from panel.init_app import app


def main() -> int:
    # ddtrace.patch_all()
    logger.configure_logging("DEBUG" if config.app_developer_build else "INFO")

    app.run(
        host=config.http_host, port=config.http_port, debug=config.app_developer_build
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
