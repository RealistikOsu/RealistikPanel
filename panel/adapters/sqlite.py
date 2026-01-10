from __future__ import annotations

import aiosqlite
from typing import Any
from typing import Optional

from panel import logger


class Sqlite:
    def __init__(self, db: str):
        self.db = db
        self.conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self.conn = await aiosqlite.connect(self.db)

    async def execute(self, query: str, args: tuple = (), commit: bool = True) -> int:
        if not self.conn:
             raise RuntimeError("Sqlite connection not initialized.")
        
        cursor = await self.conn.execute(query, args)
        
        if commit:
            await self.conn.commit()

        row_id = cursor.lastrowid if cursor.lastrowid else 0
        logger.debug(f"Sqlite: {row_id!r}, {query!r}, {args!r}")
        await cursor.close()
        return row_id

    async def fetch_one(self, query: str, args: tuple = ()) -> Optional[tuple]:
        if not self.conn:
             raise RuntimeError("Sqlite connection not initialized.")

        cursor = await self.conn.execute(query, args)
        row = await cursor.fetchone()
        logger.debug(f"Sqlite: {row!r}, {query!r}, {args!r}")
        await cursor.close()
        return row

    async def fetch_all(self, query: str, args: tuple = ()) -> list[tuple]:
        if not self.conn:
             raise RuntimeError("Sqlite connection not initialized.")

        cursor = await self.conn.execute(query, args)
        rows = await cursor.fetchall()
        logger.debug(f"Sqlite: {rows!r}, {query!r}, {args!r}")
        await cursor.close()
        return rows

    async def fetch_val(self, query: str, args: tuple = ()) -> Any:
        if not self.conn:
             raise RuntimeError("Sqlite connection not initialized.")

        cursor = await self.conn.execute(query, args)
        val = await cursor.fetchone()
        logger.debug(f"Sqlite: {val!r}, {query!r}, {args!r}")
        await cursor.close()
        
        if val is None:
            return None

        return val[0]

    async def close(self):
        if self.conn:
            await self.conn.close()