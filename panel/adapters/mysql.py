from __future__ import annotations

import urllib.parse
from typing import Any
from typing import Optional

from databases import Database
from databases import DatabaseURL
from databases.interfaces import Record

from panel import logger


class MySQLPool:
    """
    Async MySQL connection pool backed by the `databases` library.

    Uses named parameters (`:name`) with dict values. Returned rows are
    `databases` `Record` objects, which support both positional (`row[0]`)
    and mapping (`row["col"]`) access.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 3306,
        user: str = "root",
        password: str = "123456",
        database: str = "test",
        pool_name: str = "mypool",
        pool_size: int = 10,
    ) -> None:
        database_url = DatabaseURL(
            "mysql+aiomysql://{user}:{password}@{host}:{port}/{db}".format(
                user=user,
                password=urllib.parse.quote(password),
                host=host,
                port=port,
                db=database,
            ),
        )
        self._database = Database(
            database_url,
            min_size=1,
            max_size=pool_size,
        )

    async def connect(self) -> None:
        """Initializes the connection pool."""
        await self._database.connect()

    async def close(self) -> None:
        """Closes the connection pool."""
        await self._database.disconnect()

    async def execute(self, query: str, args: Optional[dict[str, Any]] = None) -> Any:
        """
        Execute a sql statement, returning the last inserted row id.
        """
        row_id = await self._database.execute(query, args)
        logger.debug(f"MySQL: {row_id!r}, {query!r}, {args!r}")
        return row_id

    async def fetch_one(
        self,
        query: str,
        args: Optional[dict[str, Any]] = None,
    ) -> Optional[Record]:
        """
        Fetch one row from database.
        """
        row = await self._database.fetch_one(query, args)
        logger.debug(f"MySQL: {row!r}, {query!r}, {args!r}")
        return row

    async def fetch_all(
        self,
        query: str,
        args: Optional[dict[str, Any]] = None,
    ) -> list[Record]:
        """
        Fetch all rows from database.
        """
        rows = await self._database.fetch_all(query, args)
        logger.debug(f"MySQL: {rows!r}, {query!r}, {args!r}")
        return rows

    async def fetch_val(self, query: str, args: Optional[dict[str, Any]] = None) -> Any:
        """
        Fetch one value from database.
        """
        val = await self._database.fetch_val(query, args)
        logger.debug(f"MySQL: {val!r}, {query!r}, {args!r}")
        return val
