import sqlite3

from panel import logger

from typing import Any
from typing import Optional

class Sqlite:
    def __init__(self, db: str):
        self.db = db
        self.conn = sqlite3.connect(self.db)

    def execute(self, query: str, args: tuple = (), commit: bool = True) -> int:
        cursor = self.conn.cursor()
        cursor.execute(query, args)

        if commit is True:
            self.conn.commit()

        row_id = cursor.lastrowid if cursor.lastrowid else 0

        logger.debug(f"Sqlite: {row_id!r}, {query!r}, {args!r}")

        cursor.close()
        return row_id

    def fetch_one(self, query: str, args: tuple = ()) -> Optional[tuple]:
        cursor = self.conn.cursor()
        cursor.execute(query, args)

        row = cursor.fetchone()

        logger.debug(f"Sqlite: {row!r}, {query!r}, {args!r}")

        cursor.close()
        return row

    def fetch_all(self, query: str, args: tuple = ()) -> list[tuple]:
        cursor = self.conn.cursor()
        cursor.execute(query, args)

        rows = cursor.fetchall()

        logger.debug(f"Sqlite: {rows!r}, {query!r}, {args!r}")

        cursor.close()
        return rows
    
    def fetch_val(self, query: str, args: tuple = ()) -> Any:
        cursor = self.conn.cursor()
        cursor.execute(query, args)

        val = cursor.fetchone()

        logger.debug(f"Sqlite: {val!r}, {query!r}, {args!r}")

        cursor.close()
        if val is None:
            return None

        return val[0]

    def close(self):
        self.conn.close()