from __future__ import annotations

from typing import Any
from typing import Optional

import aiomysql

from panel import logger


class MySQLPool:
    """
    Async MySQL connection pool wrapper using aiomysql.
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
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._database = database
        self._pool_size = pool_size
        self.pool: Optional[aiomysql.Pool] = None

    async def connect(self) -> None:
        """Initializes the connection pool."""
        self.pool = await aiomysql.create_pool(
            host=self._host,
            port=self._port,
            user=self._user,
            password=self._password,
            db=self._database,
            minsize=1,
            maxsize=self._pool_size,
            autocommit=True,
        )

    async def close(self) -> None:
        """Closes the connection pool."""
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()

    async def execute(self, query: str, args: tuple = (), commit: bool = True) -> int:
        """
        Execute a sql statement.
        """
        if not self.pool:
            raise RuntimeError("Database pool not initialized. Call connect() first.")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, args)
                if commit:
                    await conn.commit()
                
                row_id = cursor.lastrowid
                logger.debug(f"MySQL: {row_id!r}, {query!r}, {args!r}")
                return row_id

    async def fetch_one(self, query: str, args: tuple = ()) -> Optional[tuple]:
        """
        Fetch one row from database.
        """
        if not self.pool:
            raise RuntimeError("Database pool not initialized. Call connect() first.")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, args)
                row = await cursor.fetchone()
                logger.debug(f"MySQL: {row!r}, {query!r}, {args!r}")
                return row

    async def fetch_all(self, query: str, args: tuple = ()) -> list[tuple]:
        """
        Fetch all rows from database.
        """
        if not self.pool:
            raise RuntimeError("Database pool not initialized. Call connect() first.")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, args)
                rows = await cursor.fetchall()
                logger.debug(f"MySQL: {rows!r}, {query!r}, {args!r}")
                return rows

    async def fetch_val(self, query: str, args: tuple = ()) -> Any:
        """
        Fetch one value from database.
        """
        if not self.pool:
            raise RuntimeError("Database pool not initialized. Call connect() first.")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, args)
                val = await cursor.fetchone()
                logger.debug(f"MySQL: {val!r}, {query!r}, {args!r}")
                
                if val is None:
                    return None
                return val[0]