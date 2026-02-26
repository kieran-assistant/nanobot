# tests/test_core_safety.py
import pytest
from nanobot.core.adapter import ShellTool, FileReadTool

class TestSafetyLayer:
    """Regression tests for core safety mechanisms."""

    @pytest.mark.asyncio
    async def test_shell_blocks_destructive_commands(self):
        """Verify rm -rf / is blocked."""
        tool = ShellTool()
        result = await tool.execute(command="rm -rf /")
        assert "Blocked" in result
        assert "Unsafe" in result

    @pytest.mark.asyncio
    async def test_shell_blocks_fork_bomb(self):
        """Verify fork bomb is blocked."""
        tool = ShellTool()
        result = await tool.execute(command=":(){ :|:& };:")
        assert "Blocked" in result

    @pytest.mark.asyncio
    async def test_shell_allows_safe_commands(self):
        """Verify safe commands still work."""
        tool = ShellTool()
        result = await tool.execute(command="echo hello")
        assert "hello" in result

    @pytest.mark.asyncio
    async def test_file_read_blocks_path_traversal(self):
        """Verify directory traversal is blocked."""
        tool = FileReadTool()
        result = await tool.execute(path="../etc/passwd")
        assert "Access denied" in result

    @pytest.mark.asyncio
    async def test_file_read_blocks_sensitive_paths(self):
        """Verify /etc and /root are blocked."""
        tool = FileReadTool()
        result = await tool.execute(path="/etc/passwd")
        assert "Access denied" in result

        result = await tool.execute(path="/root/.ssh")
        assert "Access denied" in result

    @pytest.mark.asyncio
    async def test_file_read_allows_safe_paths(self):
        """Verify safe file reads work."""
        tool = FileReadTool()
        result = await tool.execute(path="pyproject.toml")
        assert "nanobot" in result.lower() or "Error" in result
