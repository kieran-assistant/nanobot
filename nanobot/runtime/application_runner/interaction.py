"""
Module Purpose: Application interaction tool for running repository code in Docker with I/O capture.

Responsibilities:
    - Prepare isolated sandbox environment for application execution
    - Copy repository code into sandbox directory
    - Write input data files for application consumption
    - Execute application via DockerExecuteTool
    - Capture and attempt to parse structured JSON output
    - Return execution results with sandbox metadata

Dependencies:
    - nanobot.config.settings (sandbox configuration)
    - nanobot.runtime.application_runner.docker_tool.DockerExecuteTool (container execution)
    - pathlib (sandbox directory management)
    - shutil (file copying)
    - json (output parsing)
    - uuid (unique run directory naming)

Why this module exists:
    Enables the system to run arbitrary applications from GitHub repos in a controlled,
    isolated environment. This is critical for learning from running applications
    and extracting patterns from their execution.
"""

from __future__ import annotations

from pathlib import Path
import json
import shutil
import uuid
from typing import Any

from nanobot.config import settings
from nanobot.runtime.application_runner.docker_tool import DockerExecuteTool


# ---------- Public API: AppInteractionTool ----------


class AppInteractionTool:
    """Run an application workspace in Docker with optional input payload."""

    # ---------- Initialization ----------

    def __init__(self):
        """Initialize with Docker tool dependency."""
        self.docker_tool = DockerExecuteTool()

    # ---------- Execution Entry Point ----------

    def execute(
        self,
        app_path: str,
        command: str,
        input_data: str = "",
        timeout: int = 60,
        image: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute an application from a local path in a Docker sandbox.

        Process:
        1. Create isolated run directory under sandbox root
        2. Copy application code into run directory (or fail if not found)
        3. Write input data to input.txt file if provided
        4. Execute via DockerExecuteTool with selected/default image
        5. Attempt to parse stdout as JSON for structured output
        6. Return complete execution context including sandbox directory

        Returns dict with: success, output, stderr, exit_code, structured, command, sandbox_dir
        """
        sandbox_root = Path(settings.app_runner_sandbox_dir).resolve()
        sandbox_root.mkdir(parents=True, exist_ok=True)

        # Create unique run directory per execution (prevents conflicts)
        run_dir = sandbox_root / f"run_{uuid.uuid4().hex[:8]}"
        run_dir.mkdir(parents=True, exist_ok=True)

        # Copy application code into isolated sandbox
        src = Path(app_path).resolve()
        target_repo = run_dir / "repo"
        if src.is_dir():
            shutil.copytree(src, target_repo, dirs_exist_ok=True)
        else:
            run_dir.rmdir()
            return {
                "success": False,
                "error": f"Application path not found: {app_path}",
            }

        # Write input data file if provided (applications can read this for test cases)
        if input_data:
            (run_dir / "input.txt").write_text(input_data, encoding="utf-8")

        # Use specified image or fall back to configured default
        selected_image = image or settings.app_runner_default_image

        # Execute application in sandboxed container
        docker_result = self.docker_tool.execute(
            image=selected_image,
            command=command,
            sandbox_dir=run_dir,
            timeout=timeout,
        )

        # Try to parse JSON output (many tools return structured data)
        parsed = self._try_parse_output(docker_result.stdout)

        return {
            "success": docker_result.success,
            "output": docker_result.stdout,
            "stderr": docker_result.stderr,
            "exit_code": docker_result.exit_code,
            "structured": parsed,
            "command": docker_result.command,
            "sandbox_dir": str(run_dir),
        }

    # ---------- Output Parsing ----------

    def _try_parse_output(self, output: str) -> Any:
        """
        Attempt to parse application output as structured JSON.

        Many tools return JSON for machine-readable output, but not all do.
        This function gracefully handles both cases:
        - Valid JSON: Return parsed Python object
        - Invalid JSON or non-JSON: Return None (caller can use raw stdout)
        """
        text = (output or "").strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            return None
