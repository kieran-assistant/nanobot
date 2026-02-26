# nanobot/core/adapter.py
import asyncio
import subprocess
import shlex
from pathlib import Path
from abc import ABC
from nanobot.meta.metaclasses import ToolMeta
from loguru import logger
from nanobot.security.policy import (
    ALLOWED_COMMANDS,
    validate_shell_command,
    is_path_within_root,
)

# Mock kernel functions (placeholders - will be replaced by actual kernel imports)
WORKSPACE_ROOT = Path.cwd().resolve()

def kernel_execute_bash(command: str) -> str:
    """Mock kernel shell execution with allowlisted argv commands."""
    try:
        validation = validate_shell_command(command)
        if not validation.allowed:
            return f"Error: {validation.reason}."

        args = shlex.split(command)

        result = subprocess.run(args, shell=False, capture_output=True, text=True, timeout=30)
        return result.stdout or result.stderr
    except subprocess.TimeoutExpired:
        return "Error: Command timed out."
    except ValueError as e:
        return f"Error: Invalid command syntax: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"

def kernel_read_file(path: str) -> str:
    """Mock kernel file read."""
    try:
        requested_path = Path(path).expanduser().resolve()
        if not is_path_within_root(str(requested_path), WORKSPACE_ROOT):
            raise PermissionError("Access denied")

        with requested_path.open('r', encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"Error: File not found: {path}"
    except PermissionError:
        return "Error: Permission denied"
    except Exception as e:
        return f"Error: {str(e)}"

class BaseTool(ABC, metaclass=ToolMeta):
    """Base class for all wrapped Kernel tools."""
    
    tool_name: str = "base_tool"
    description: str = "Base tool class"
    parameters_schema: dict = {}
    
    async def execute(self, *args, **kwargs):
        raise NotImplementedError

    async def _safe_run(self, func, *args, **kwargs):
        """
        Runs a synchronous kernel function in a separate thread
        to avoid blocking the async event loop.
        """
        try:
            return await asyncio.to_thread(func, *args, **kwargs)
        except Exception as e:
            logger.error(f"Kernel Tool Error [{self.tool_name}]: {e}")
            return f"Error: {str(e)}"

class ShellTool(BaseTool):
    tool_name = "shell_exec"
    description = "Executes a shell command. Wrapped with safety checks."
    parameters_schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The shell command to execute"}
        },
        "required": ["command"]
    }

    async def execute(self, command: str):
        # 1. Safety Layer
        validation = validate_shell_command(command)
        if not validation.allowed:
            logger.warning(f"Blocked unsafe command: {command}")
            return "Error: Unsafe command Blocked by Adaptive Shell."
        
        # 2. Execution Layer (Delegating to Kernel)
        logger.info(f"Executing shell: {command}")
        return await self._safe_run(kernel_execute_bash, command)

class FileReadTool(BaseTool):
    tool_name = "read_file"
    description = "Reads content from a file path."
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file"}
        },
        "required": ["path"]
    }

    async def execute(self, path: str):
        # 1. Safety Layer (Path Traversal)
        if path.startswith("/etc/") or path.startswith("/root/"):
            return "Error: Access denied to sensitive path."
        try:
            if not is_path_within_root(path, WORKSPACE_ROOT):
                return "Error: Access denied to sensitive path."
        except Exception:
            return "Error: Access denied to sensitive path."
        
        # 2. Execution Layer
        return await self._safe_run(kernel_read_file, path)

# --- Initialization Function ---

async def initialize_kernel():
    """
    Called at startup to register all primitive tools into the DB.
    """
    from nanobot.meta.registry import registry
    try:
        # Import side-effect registration for context graph query tool.
        import nanobot.agent.tools.context_tool  # noqa: F401
    except Exception as exc:
        logger.warning(f"Context tool registration import failed: {exc}")
    # The registry automatically picked up the classes above due to ToolMeta.
    # Now we sync to DB.
    await registry.sync_to_database()
    logger.success("Primitive Kernel Initialized and Registered.")
