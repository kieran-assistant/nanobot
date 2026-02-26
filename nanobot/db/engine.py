# nanobot/db/engine.py
import asyncpg
from loguru import logger
from typing import Optional
from nanobot.config import settings

class Database:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Establishes the connection pool."""
        if not self.pool:
            logger.info(f"Connecting to database at {settings.db_host}...")
            self.pool = await asyncpg.create_pool(
                user=settings.db_user,
                password=settings.db_password,
                database=settings.db_name,
                host=settings.db_host,
                port=settings.db_port,
                min_size=5,
                max_size=20
            )
            logger.info("Database connection pool created.")

    async def disconnect(self):
        """Closes the connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("Database connection pool closed.")

    async def execute(self, query, *args):
        """Executes a query without returning results."""
        async with self.pool.acquire() as connection:
            return await connection.execute(query, *args)

    async def fetch(self, query, *args):
        """Executes a query and returns multiple rows."""
        async with self.pool.acquire() as connection:
            return await connection.fetch(query, *args)

    async def fetchrow(self, query, *args):
        """Executes a query and returns a single row."""
        async with self.pool.acquire() as connection:
            return await connection.fetchrow(query, *args)

    async def fetchval(self, query, *args):
        """Executes a query and returns a single value."""
        async with self.pool.acquire() as connection:
            return await connection.fetchval(query, *args)

# Global database instance
db = Database()
