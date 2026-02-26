import pytest

from nanobot.db.engine import db


@pytest.fixture
async def require_db():
    try:
        await db.connect()
    except Exception as exc:
        pytest.skip(f"Database unavailable: {exc}")
    try:
        yield
    finally:
        await db.disconnect()
