# tests/test_cli.py
from typer.testing import CliRunner
from nanobot.cli.commands import app
from nanobot.db.engine import db
from nanobot.meta.evolution_engine import evolution_engine

runner = CliRunner()

def test_status_command(monkeypatch):
    async def fake_connect():
        return None

    async def fake_fetch(query, *args):
        if "FROM system_model" in query:
            return [{"component_name": "shell_exec", "source_layer": "primitive_kernel"}]
        return [{"count": 0}]

    async def fake_disconnect():
        return None

    monkeypatch.setattr(db, "connect", fake_connect)
    monkeypatch.setattr(db, "fetch", fake_fetch)
    monkeypatch.setattr(db, "disconnect", fake_disconnect)

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "Registered Tools" in result.stdout

def test_evolve_command(monkeypatch):
    async def fake_connect():
        return None

    async def fake_disconnect():
        return None

    async def fake_run_cycle():
        return None

    monkeypatch.setattr(db, "connect", fake_connect)
    monkeypatch.setattr(db, "disconnect", fake_disconnect)
    monkeypatch.setattr(evolution_engine, "run_cycle", fake_run_cycle)

    result = runner.invoke(app, ["evolve"])
    assert result.exit_code == 0
    assert "Evolution Cycle Finished" in result.stdout
