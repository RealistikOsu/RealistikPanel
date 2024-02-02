from __future__ import annotations

from redis import Redis

from panel.adapters.mysql import MySQLPool
from panel.adapters.sqlite import Sqlite

database: MySQLPool
sqlite: Sqlite
redis: Redis
