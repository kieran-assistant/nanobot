# nanobot/core/adapter.py
import asyncio
import os
import subprocess
from abc import ABC
from nanobot.meta.metaclasses import ToolMeta
from loguru import logger

# Mock kernel functions (placeholders - will be replaced by actual kernel imports)
def kernel_execute_bash(command: str) -> str:
    """Mock kernel shell execution."""
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        return result.stdout or result.stderr
    except subprocess.TimeoutExpired:
        return "Error: Command timed out."
    except Exception as e:
        return f"Error: {str(e)}"

def kernel_read_file(path: str) -> str:
    """Mock kernel file read."""
    try:
        # Prevent directory traversal
        if ".." in path or path.startswith("/etc/") or path.startswith("/root/"):
            raise PermissionError("Access denied")
        with open(path, 'r') as f:
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
        if "rm -rf /" in command or ":(){ :|:& };:" in command:
            logger.warning(f"Blocked unsafe command: {command}")
            return "Error: Unsafe command blocked by Adaptive Shell."
        
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
        if ".." in path or path.startswith("/etc/") or path.startswith("/root/"):
            return "Error: Access denied to sensitive path."
        
        # 2. Execution Layer
        return await self._safe_run(kernel_read_file, path)

# --- Initialization Function ---

async def initialize_kernel():
    """
    Called at startup to register all primitive tools into the DB.
    """
    from nanobot.meta.registry import registry
    # The registry automatically picked up the classes above due to ToolMeta.
    # Now we sync to DB.
    await registry.sync_to_database()
    logger.success("Primitive Kernel Initialized and Registered.")
