"""Red-team regression tests for release-gate security controls."""

from pathlib import Path

import pytest

from nanobot.meta.schemas import SkillDefinition, ToolDefinition, ExecutorType
from nanobot.meta.security_gate import security_gate
from nanobot.security.policy import validate_shell_command, is_path_within_root


def test_block_shell_composition_tokens():
    result = validate_shell_command("echo hi && whoami")
    assert result.allowed is False
    assert "shell composition token" in (result.reason or "")


def test_block_non_allowlisted_binary():
    result = validate_shell_command("python3 -V")
    assert result.allowed is False
    assert "not allowlisted" in (result.reason or "")


def test_allow_safe_command():
    result = validate_shell_command("echo hello")
    assert result.allowed is True


def test_workspace_path_boundary():
    root = Path.cwd()
    assert is_path_within_root(str(root / "README.md"), root) is True
    assert is_path_within_root("/etc/passwd", root) is False


def test_security_gate_blocks_dangerous_executor_command():
    skill = SkillDefinition(
        name="gen-dangerous",
        description="Dangerous command test",
        tools=[
            ToolDefinition(
                name="dangerous_tool",
                description="Attempt non-allowlisted command",
                executor_type=ExecutorType.SCRIPT,
                executor_config={"command": "python3 -V"},
            )
        ],
    )
    result = security_gate.validate_skill_definition(skill)
    assert result.passed is False
    assert any("not allowlisted" in reason for reason in result.reasons)


def test_red_team_scan_blocks_shell_true(tmp_path):
    staged = tmp_path / "gen-skill"
    staged.mkdir()
    (staged / "tool_x.py").write_text("import subprocess\nsubprocess.run('ls', shell=True)\n", encoding="utf-8")
    result = security_gate.scan_generated_directory(staged)
    assert result.passed is False
    assert any("shell=True" in reason for reason in result.reasons)
