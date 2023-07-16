import mysql.connector.pooling

from panel import logger

from typing import Any
from typing import Optional

class MySQLPool:
    """
    Create a pool when connect mysql, which will decrease the time spent in 
    request connection, create connection and close connection.
    """
    def __init__(
        self,
        host: str = "172.0.0.1", 
        port: int = 3306, 
        user: str = "root",
        password: str = "123456", 
        database: str = "test", 
        pool_name: str = "mypool",
        pool_size: int = 10,
    ) -> None:
        res = {}
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._database = database

        res["host"] = self._host
        res["port"] = self._port
        res["user"] = self._user
        res["password"] = self._password
        res["database"] = self._database
        self.dbconfig = res
        self.pool = self.create_pool(pool_name=pool_name, pool_size=pool_size)

    def create_pool(self, pool_name: str = "mypool", pool_size: int = 10):
        """
        Create a connection pool, after created, the request of connecting 
        MySQL could get a connection from this pool instead of request to 
        create a connection.
        :param pool_name: the name of pool, default is "mypool"
        :param pool_size: the size of pool, default is 3
        :return: connection pool
        """
        pool = mysql.connector.pooling.MySQLConnectionPool(
            pool_name=pool_name,
            pool_size=pool_size,
            pool_reset_session=True,
            **self.dbconfig)
        return pool

    def close(self, conn, cursor):
        """
        A method used to close connection of mysql.
        :param conn: 
        :param cursor: 
        :return: 
        """
        cursor.close()
        conn.close()

    def execute(self, query: str, args: tuple = (), commit: bool = True) -> int:
        """
        Execute a sql, it could be with args and with out args. The usage is 
        similar with execute() function in module pymysql.
        :param sql: sql clause
        :param args: args need by sql clause
        :param commit: whether to commit
        :return: last row id
        """
        # get connection form connection pool instead of create one.
        conn = self.pool.get_connection()
        cursor = conn.cursor()

        cursor.execute(query, args)
        if commit is True:
            conn.commit()
        
        row = cursor.lastrowid

        logger.debug(f"MySQL: {row!r}, {query!r}, {args!r}")

        self.close(conn, cursor)
        return row
    
    def fetch_one(self, query: str, args: tuple = ()) -> Optional[tuple]:
        """
        Fetch one row from database.
        :param sql: sql clause
        :param args: args need by sql clause
        :return: one row
        """

        conn = self.pool.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, args)
        row = cursor.fetchone()

        logger.debug(f"MySQL: {row!r}, {query!r}, {args!r}")

        self.close(conn, cursor)
        return row
    
    def fetch_all(self, query: str, args: tuple = ()) -> list[tuple]:
        """
        Fetch all rows from database.
        :param sql: sql clause
        :param args: args need by sql clause
        :return: all rows
        """

        conn = self.pool.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, args)
        rows = cursor.fetchall()

        logger.debug(f"MySQL: {rows!r}, {query!r}, {args!r}")

        self.close(conn, cursor)
        return rows
    
    def fetch_val(self, query: str, args: tuple = ()) -> Any:
        """
        Fetch one value from database.
        :param sql: sql clause
        :param args: args need by sql clause
        :return: one value
        """

        conn = self.pool.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, args)

        val = cursor.fetchone()

        logger.debug(f"MySQL: {val!r}, {query!r}, {args!r}")

        self.close(conn, cursor)
        if val is None:
            return None
        
        return val[0]