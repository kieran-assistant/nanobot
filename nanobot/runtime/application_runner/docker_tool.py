"""
Module Purpose: Secure Docker container execution with policy enforcement and resource limits.

Responsibilities:
    - Validate Docker execution requests against security policy
    - Build safe Docker commands with resource constraints
    - Execute containers with output capture
    - Enforce timeout limits
    - Block dangerous Docker flags and shell composition tokens

Dependencies:
    - nanobot.config.settings (configuration: enabled, images, resource limits)
    - subprocess (container execution)
    - shlex (command parsing)
    - pathlib (sandbox path handling)

Why this module exists:
    External tool execution via Docker enables the system to run arbitrary code from GitHub repos.
    This is powerful but dangerous - requires strict policy enforcement to prevent:
    - Privilege escalation (--privileged)
    - Host network access (--network=host)
    - Host filesystem mounts (-v /:/)
    - Shell composition/chaining (&&, ||, ;, |)
    - Unapproved Docker images
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shlex
import subprocess
from typing import Any

from nanobot.config import settings


# ---------- Security Policy Constants ----------

# Docker flags that would compromise container isolation or host security
BLOCKED_DOCKER_FLAGS = (
    "--privileged",  # Grants full host access (dangerous)
    "--network=host",  # Full network access (bypasses isolation)
    "-v /:/",  # Mount entire host filesystem
    "--pid=host",  # Share host process namespace
)

# Shell tokens that enable command chaining, injection, or side effects
BLOCKED_COMMAND_TOKENS = (
    "&&",  # AND chaining (execute second command regardless of first success)
    "||",  # OR chaining (execute second command if first fails)
    ";",  # Sequential execution (classic injection vector)
    "|",  # Pipe chaining (complex command composition)
    "`",  # Command substitution (shell injection)
    "$(",  # Subshell execution (nested command execution)
)


# ---------- Public API: DockerExecuteTool ----------


@dataclass
class DockerExecutionResult:
    """Structured result from Docker container execution."""

    success: bool
    stdout: str
    stderr: str
    exit_code: int
    command: list


class DockerExecuteTool:
    """Run docker containers with strict controls and output capture."""

    # ---------- Execution Entry Point ----------

    def execute(
        self,
        image: str,
        command: str,
        sandbox_dir: Path,
        timeout: int = 60,
    ) -> DockerExecutionResult:
        """
        Execute a Docker container with the given image, command, and sandbox directory.

        Validates request first, then builds safe docker command, executes with timeout,
        and returns structured result including success status, stdout/stderr, and exit code.
        """
        validation_error = self._validate_request(image, command, timeout)
        if validation_error:
            return DockerExecutionResult(
                success=False,
                stdout="",
                stderr=validation_error,
                exit_code=1,
                command=[],
            )

        docker_cmd = self._build_command(
            image=image, command=command, sandbox_dir=sandbox_dir
        )
        try:
            completed = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=min(timeout, settings.app_runner_max_timeout),
            )
            return DockerExecutionResult(
                success=completed.returncode == 0,
                stdout=completed.stdout,
                stderr=completed.stderr,
                exit_code=completed.returncode,
                command=docker_cmd,
            )
        except subprocess.TimeoutExpired as exc:
            # Timeout is an expected condition, not an error
            # Return exit code 124 (standard timeout exit code)
            return DockerExecutionResult(
                success=False,
                stdout=exc.stdout or "",
                stderr=f"Docker execution timeout: {exc}",
                exit_code=124,
                command=docker_cmd,
            )
        except Exception as exc:
            # Unexpected error - return generic failure message
            return DockerExecutionResult(
                success=False,
                stdout="",
                stderr=f"Docker execution failed: {exc}",
                exit_code=1,
                command=docker_cmd,
            )

    # ---------- Request Validation ----------

    def _validate_request(self, image: str, command: str, timeout: int) -> str | None:
        """
        Validate Docker execution request against security policy.

        Checks performed:
        1. Global enable flag (APP_RUNNER_ENABLED)
        2. Phase gate (APP_RUNNER_PHASE)
        3. Timeout value must be positive
        4. No blocked docker flags in command
        5. No blocked shell composition tokens in command
        6. Docker image is allowlisted
        """
        if not settings.app_runner_enabled:
            return "APP_RUNNER_ENABLED is false."
        if settings.app_runner_phase == "disabled":
            return "APP_RUNNER_PHASE is disabled."
        if timeout <= 0:
            return "Timeout must be positive."
        if any(flag in command for flag in BLOCKED_DOCKER_FLAGS):
            return "Blocked docker flag detected in command."
        if any(token in command for token in BLOCKED_COMMAND_TOKENS):
            return "Blocked shell composition token in command."

        # Parse allowlist from config (comma-separated, trim whitespace)
        allowed = {
            item.strip()
            for item in settings.allowed_docker_images.split(",")
            if item.strip()
        }
        if not allowed:
            return "No allowed docker images configured (ALLOWED_DOCKER_IMAGES)."
        if image not in allowed:
            return f"Docker image '{image}' is not allowlisted."
        return None

    # ---------- Command Building ----------

    def _build_command(self, image: str, command: str, sandbox_dir: Path) -> list[str]:
        """
        Build a safe Docker run command with security constraints.

        Security features applied:
        - --rm: Auto-remove container after execution (cleanup)
        - --read-only: Filesystem is read-only (prevents modifications)
        - --pids-limit 128: Limit process creation (prevent fork bombs)
        - --cpus: Enforce CPU limit (prevents CPU exhaustion)
        - --memory: Enforce memory limit (prevents memory exhaustion)
        - --tmpfs: Use in-memory /tmp (prevents disk usage)
        - --workdir /workspace: Set working directory
        - --mount: Bind sandbox directory into container
        - --network none: Disable networking (if configured)

        Finally executes: sh -lc "command" for POSIX compatibility
        """
        sandbox_dir = sandbox_dir.resolve()
        cmd: list[str] = [
            "docker",
            "run",
            "--rm",  # Auto-cleanup
            "--read-only",  # Prevent writes to base filesystem
            "--pids-limit",  # Prevent fork bombs
            "128",
            "--cpus",
            str(settings.app_runner_resource_limit_cpu),  # CPU quota
            "--memory",
            settings.app_runner_resource_limit_memory,  # Memory quota
            "--tmpfs",
            "/tmp:rw,size=64m",  # In-memory temp
            "--workdir",
            "/workspace",
            "--mount",
            f"type=bind,src={sandbox_dir},dst=/workspace",  # Bind sandbox
        ]
        if settings.app_runner_network_isolated:
            cmd.extend(["--network", "none"])
        cmd.append(image)
        cmd.extend(["sh", "-lc", command])  # -l: login shell, -c: execute command
        return cmd
