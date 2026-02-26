"""Central security policy primitives used by evolution and runtime gates.

This module provides one shared source of truth for:
1. Allowlisted shell commands.
2. High-risk shell/file patterns used for release gating.
3. Lightweight policy helpers used by both runtime tools and staging checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shlex
from typing import Iterable


# Only these binaries are allowed for agent-controlled command execution.
ALLOWED_COMMANDS = {
    "echo",
    "ls",
    "pwd",
    "cat",
    "head",
    "tail",
    "grep",
    "wc",
    "date",
    "whoami",
    "uname",
}

# Tokens that indicate command chaining, shell interpolation, or script injection.
BLOCKED_SHELL_TOKENS = ("&&", "||", ";", "|", "$(", "`", "\n")

# Strings that indicate obviously destructive or abuse-oriented behavior.
BLOCKED_SHELL_PATTERNS = (
    "rm -rf /",
    ":(){ :|:& };:",
    "mkfs",
    "dd if=",
    "chmod 777 /",
)

# Strings used for static security scans of generated scripts.
DANGEROUS_CODE_PATTERNS = (
    "os.system(",
    "subprocess.run(",
    "shell=True",
    "eval(",
    "exec(",
    "open('/etc/",
    "open('/root/",
)


@dataclass
class SecurityCheckResult:
    """Result envelope for policy checks."""

    allowed: bool
    reason: str | None = None


def validate_shell_command(command: str) -> SecurityCheckResult:
    """Validate a shell command against policy.

    The command must:
    1. Avoid blocked tokens/patterns.
    2. Parse as shell arguments.
    3. Use an allowlisted binary.
    """

    blocked_patterns = set(BLOCKED_SHELL_PATTERNS) | _parse_csv_env("SECURITY_BLOCKLIST_EXTRA")
    allowed_commands = set(ALLOWED_COMMANDS) | _parse_csv_env("SECURITY_ALLOWLIST_EXTRA")

    if any(pattern in command for pattern in blocked_patterns):
        return SecurityCheckResult(False, "blocked destructive pattern")

    if any(token in command for token in BLOCKED_SHELL_TOKENS):
        return SecurityCheckResult(False, "blocked shell composition token")

    try:
        args = shlex.split(command)
    except ValueError as exc:
        return SecurityCheckResult(False, f"invalid command syntax: {exc}")

    if not args:
        return SecurityCheckResult(False, "empty command")

    if args[0] not in allowed_commands:
        return SecurityCheckResult(False, f"command '{args[0]}' is not allowlisted")

    return SecurityCheckResult(True)


def is_path_within_root(path: str, root: Path) -> bool:
    """Return True when a path resolves inside the configured root directory."""

    try:
        resolved_path = Path(path).expanduser().resolve()
        resolved_root = root.expanduser().resolve()
    except Exception:
        return False
    return str(resolved_path).startswith(str(resolved_root))


def scan_code_for_dangerous_patterns(source: str, patterns: Iterable[str] | None = None) -> list[str]:
    """Return dangerous pattern matches found in source text."""

    checks = tuple(patterns) if patterns is not None else DANGEROUS_CODE_PATTERNS
    return [pattern for pattern in checks if pattern in source]


def _parse_csv_env(name: str) -> set[str]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return set()
    return {item.strip() for item in raw.split(",") if item.strip()}
