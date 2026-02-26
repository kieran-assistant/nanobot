# nanobot/db/engine.py
import asyncio
import asyncpg
from loguru import logger
from typing import Optional
from pathlib import Path
from nanobot.config import settings
from nanobot.db.schema_utils import split_sql_statements

class Database:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self._schema_lock = asyncio.Lock()
        self._schema_checked = False

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
            await self._ensure_schema_initialized()

    async def disconnect(self):
        """Closes the connection pool."""
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("Database connection pool closed.")

    async def _ensure_schema_initialized(self):
        """Bootstraps schema.sql if core tables do not exist."""
        if self._schema_checked:
            return

        async with self._schema_lock:
            if self._schema_checked:
                return

            async with self.pool.acquire() as connection:
                system_model_exists = await connection.fetchval(
                    "SELECT to_regclass('public.system_model') IS NOT NULL"
                )
                if system_model_exists:
                    self._schema_checked = True
                    return

                schema_path = Path(__file__).resolve().parents[2] / "sql" / "schema.sql"
                if not schema_path.exists():
                    raise FileNotFoundError(f"Schema file not found at {schema_path}")

                logger.warning("Database schema missing. Applying sql/schema.sql bootstrap...")
                schema_sql = schema_path.read_text(encoding="utf-8")
                statements = split_sql_statements(schema_sql)
                for statement in statements:
                    await connection.execute(statement)

                self._schema_checked = True
                logger.success("Database schema bootstrap completed.")

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
