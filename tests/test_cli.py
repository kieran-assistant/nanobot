# tests/test_cli.py
import pytest
from typer.testing import CliRunner
from nanobot.cli.commands import app

runner = CliRunner()

def test_status_command():
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "Registered Tools" in result.stdout

def test_evolve_command():
    result = runner.invoke(app, ["evolve"])
    assert result.exit_code == 0
    assert "Evolution Cycle Finished" in result.stdout
