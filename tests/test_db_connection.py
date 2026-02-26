# tests/test_db_connection.py
import pytest
from nanobot.db.engine import db
from nanobot.config import settings

@pytest.mark.asyncio
async def test_database_connection():
    """Test that we can connect and execute a simple query."""
    await db.connect()
    
    # Test basic query
    val = await db.fetchval("SELECT 1")
    assert val == 1
    
    # Test table existence (checking one of our new tables)
    table_name = await db.fetchval(
        "SELECT table_name FROM information_schema.tables WHERE table_name = 'system_model'"
    )
    assert table_name == 'system_model'
    
    await db.disconnect()

@pytest.mark.asyncio
async def test_insert_system_model():
    """Test writing to the system_model table."""
    await db.connect()
    
    from nanobot.db.repositories import SystemModelRepository
    
    # Insert a dummy component
    await SystemModelRepository.register_component(
        comp_type="test_tool",
        name="hello_world",
        definition={"param": "value"},
        layer="test_layer"
    )
    
    # Retrieve it
    comp = await SystemModelRepository.get_component("test_tool", "hello_world")
    assert comp is not None
    assert comp['component_name'] == "hello_world"
    
    # Cleanup
    await db.execute("DELETE FROM system_model WHERE component_type = 'test_tool'")
    
    await db.disconnect()
