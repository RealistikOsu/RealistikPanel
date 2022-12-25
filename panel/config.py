from __future__ import annotations

import os
from dataclasses import dataclass
from dataclasses import field
from json import dump
from json import load
from typing import Any
from typing import get_type_hints

from panel import logger


@dataclass
class Config:
    http_port: int = 1337
    http_host: str = "127.0.0.1"
    sql_host: str = "localhost"
    sql_port: int = 3306
    sql_user: str = "rosu"
    sql_password: str = ""
    sql_database: str = "rosu"
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""
    srv_name: str = "RealistikOsu!"
    srv_url: str = "https://ussr.pl/"
    srv_supports_relax: bool = True
    srv_supports_autopilot: bool = True
    srv_switcher_ips: str = "173.249.42.180"
    srv_donor_badge_id: int = 1002
    api_lets_url: str = "https://old.ussr.pl/letsapi/"
    api_avatar_url: str = "https://a.ussr.pl/"
    api_bancho_url: str = "https://c.ussr.pl/"
    api_geoloc_url: str = "https://ip.zxq.co/"
    api_foka_key: str = ""
    webhook_ranked: str = ""
    webhook_admin_log: str = ""
    app_repo_url: str = "https://github.com/RealistikOsu/RealistikPanel"
    app_time_offset: int = 0
    app_developer_build: bool = False


def read_config_json() -> dict[str, Any]:
    with open("config.json") as f:
        return load(f)


def write_config(config: Config):
    with open("config.json", "w") as f:
        dump(config.__dict__, f, indent=4)


def load_json_config() -> Config:
    """Loads the config from the file, handling config updates.
    Note:
        Raises `SystemExit` on config update.
    """

    config_dict = {}

    if os.path.exists("config.json"):
        config_dict = read_config_json()

    # Compare config json attributes with config class attributes
    missing_keys = [key for key in Config.__annotations__ if key not in config_dict]

    # Remove extra fields
    for key in tuple(
        config_dict,
    ):  # Tuple cast is necessary to create a copy of the keys.
        if key not in Config.__annotations__:
            del config_dict[key]

    # Create config regardless, populating it with missing keys.
    config = Config(**config_dict)

    if missing_keys:
        logger.info(f"Your config has been updated with {len(missing_keys)} new keys.")
        logger.debug("Missing keys: " + ", ".join(missing_keys))
        write_config(config)
        raise SystemExit(0)

    return config


def load_env_config() -> Config:
    conf = Config()

    for key, cast in get_type_hints(conf).items():
        if (env_value := os.environ.get(key.upper())) is not None:
            setattr(conf, key, cast(env_value))

    return conf


def load_config() -> Config:
    if os.environ.get("USE_ENV_CONFIG") == "1":
        return load_env_config()
    return load_json_config()


config = load_config()
