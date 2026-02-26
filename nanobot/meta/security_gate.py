"""Release-gate security checks for generated evolution proposals."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from nanobot.meta.schemas import SkillDefinition
from nanobot.security.policy import (
    scan_code_for_dangerous_patterns,
    validate_shell_command,
)


@dataclass
class GateResult:
    """Security gate result payload."""

    passed: bool
    reasons: List[str]
    checks_run: List[str]


class SecurityGate:
    """Implements threat-model checks and red-team style static checks."""

    THREAT_MODEL = {
        "sandbox_escape": "Generated tools must not use shell=True or dynamic exec/eval.",
        "filesystem_traversal": "Generated tools must not read sensitive system paths.",
        "command_injection": "Commands must pass allowlist and token checks.",
    }

    RED_TEAM_PATTERNS = (
        "shell=True",
        "eval(",
        "exec(",
        "subprocess.Popen(",
        "open('/etc/",
        "open('/root/",
    )

    def validate_skill_definition(self, skill_def: SkillDefinition) -> GateResult:
        """Validate tool commands declared in schema before code generation."""

        reasons: List[str] = []
        checks = ["threat_model.command_policy"]
        for tool in skill_def.tools:
            command = tool.executor_config.get("command")
            if not command:
                continue
            validation = validate_shell_command(command)
            if not validation.allowed:
                reasons.append(f"{tool.name}: {validation.reason}")
        return GateResult(passed=not reasons, reasons=reasons, checks_run=checks)

    def scan_generated_directory(self, path: Path) -> GateResult:
        """Run red-team static checks against generated scripts."""

        reasons: List[str] = []
        checks = ["red_team.static_pattern_scan"]
        for file in path.rglob("*.py"):
            content = file.read_text(encoding="utf-8")
            matches = scan_code_for_dangerous_patterns(content, self.RED_TEAM_PATTERNS)
            if matches:
                reasons.append(f"{file.name}: blocked patterns {matches}")
        return GateResult(passed=not reasons, reasons=reasons, checks_run=checks)


security_gate = SecurityGate()
