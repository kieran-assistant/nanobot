# tests/test_kernel_adapter.py
import pytest
from nanobot.db.engine import db
from nanobot.db.repositories import SystemModelRepository
from nanobot.core.adapter import ShellTool, FileReadTool, initialize_kernel

@pytest.mark.asyncio
async def test_tool_wrapper_execution():
    """Test that the wrapped shell tool works and respects safety."""
    tool = ShellTool()
    
    # Test Safe Command
    result = await tool.execute(command="echo Hello")
    assert "Hello" in result
    
    # Test Unsafe Command (Blocked)
    result = await tool.execute(command="rm -rf /")
    assert "Blocked" in result

@pytest.mark.asyncio
async def test_registry_sync(require_db):
    """Test that tools are registered in the database."""
    # Initialize the kernel (which triggers registry sync)
    await initialize_kernel()
    
    # Check if ShellTool is in DB
    record = await SystemModelRepository.get_component("tool", "shell_exec")
    
    assert record is not None
    assert record['source_layer'] == "primitive_kernel"
    assert record['definition_json']['name'] == "shell_exec"
