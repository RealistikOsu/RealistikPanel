from panel.adapters.mysql import MySQLPool
from panel.adapters.sqlite import Sqlite

from redis import Redis

database: MySQLPool
sqlite: Sqlite
redis: Redis