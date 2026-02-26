# nanobot/cli/commands.py
import asyncio
from pathlib import Path
from typing import Dict

import typer
from nanobot.runtime.bus import bus
from nanobot.runtime.agent_loop import agent

app = typer.Typer(help="Nanobot-DB CLI")

def run_async(coro):
    return asyncio.run(coro)


def _parse_env_file(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    values: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _write_env_atomic(path: Path, values: Dict[str, str]) -> None:
    """Write `.env` atomically to avoid partial writes."""

    ordered_lines = [f"{key}={value}" for key, value in sorted(values.items())]
    payload = "\n".join(ordered_lines) + "\n"
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(payload, encoding="utf-8")
    temp_path.replace(path)


async def _test_db_connection(values: Dict[str, str]) -> tuple[bool, str]:
    """Test raw DB connectivity using user-supplied settings."""

    try:
        import asyncpg

        conn = await asyncpg.connect(
            host=values["DB_HOST"],
            port=int(values["DB_PORT"]),
            user=values["DB_USER"],
            password=values["DB_PASSWORD"],
            database=values["DATABASE_NAME"],
        )
        await conn.fetchval("SELECT 1")
        await conn.close()
        return True, "Connection successful."
    except Exception as exc:
        return False, str(exc)


async def _bootstrap_schema(values: Dict[str, str]) -> tuple[bool, str]:
    """Apply sql/schema.sql against supplied DB settings."""

    try:
        import asyncpg
        from nanobot.db.schema_utils import split_sql_statements

        schema_path = Path(__file__).resolve().parents[2] / "sql" / "schema.sql"
        if not schema_path.exists():
            return False, f"Schema file not found: {schema_path}"

        conn = await asyncpg.connect(
            host=values["DB_HOST"],
            port=int(values["DB_PORT"]),
            user=values["DB_USER"],
            password=values["DB_PASSWORD"],
            database=values["DATABASE_NAME"],
        )
        statements = split_sql_statements(schema_path.read_text(encoding="utf-8"))
        for statement in statements:
            await conn.execute(statement)
        await conn.close()
        return True, "Schema initialized."
    except Exception as exc:
        return False, str(exc)

async def initialize_system():
    from nanobot.db.engine import db
    from nanobot.core.adapter import initialize_kernel

    await db.connect()
    await initialize_kernel()

    def print_response(event):
        typer.echo(f"Agent: {event.payload['content']}")
    bus.subscribe("agent.response", print_response)

@app.command()
def start():
    """
    Start the interactive CLI chat.
    """
    async def _run_start():
        from nanobot.db.engine import db

        typer.echo("Initializing Nanobot-DB...")
        await initialize_system()
        bus.subscribe("user.message", agent.process_event)

        typer.echo("System ready. Type 'exit' to quit.")

        try:
            while True:
                user_input = await asyncio.to_thread(typer.prompt, "You")
                if user_input.lower() == "exit":
                    typer.echo("Shutting down...")
                    break

                await bus.publish("user.message", {"content": user_input})
        except KeyboardInterrupt:
            pass
        finally:
            await db.disconnect()

    run_async(_run_start())

@app.command()
def evolve():
    """
    Manually trigger the evolution engine.
    """
    typer.echo("Triggering Evolution Cycle...")
    async def run_evolve():
        from nanobot.db.engine import db
        from nanobot.meta.evolution_engine import evolution_engine
        await db.connect()
        try:
            await evolution_engine.run_cycle()
        finally:
            await db.disconnect()
    run_async(run_evolve())
    typer.echo("Evolution Cycle Finished.")

@app.command()
def status():
    """
    Display current system status.
    """
    async def check_status():
        from nanobot.db.engine import db
        await db.connect()
        try:
            tools = await db.fetch("SELECT component_name, source_layer FROM system_model WHERE component_type = 'tool'")

            typer.echo("\n--- Registered Tools ---")
            for tool in tools:
                typer.echo(f"- {tool['component_name']} ({tool['source_layer']})")

            queue = await db.fetch("SELECT count(*) FROM evolution_queue WHERE status = 'pending'")
            typer.echo(f"\nPending Evolution Tasks: {queue[0]['count']}")
        finally:
            await db.disconnect()
        
    run_async(check_status())


@app.command("evolution-report")
def evolution_report(days: int = typer.Option(7, help="Number of trailing days to include in report.")):
    """Render a weekly evolution health report from structured observability metrics."""

    async def run_report():
        from nanobot.db.engine import db
        from nanobot.meta.observability import observability

        await db.connect()
        try:
            report = await observability.weekly_health_report(days=days)
            typer.echo("\n--- Evolution Health Report ---")
            typer.echo(f"Window (days): {report['window_days']}")
            typer.echo(f"Attempts: {report['attempts_total']}")
            typer.echo(f"Deployed: {report['deployed']}")
            typer.echo(f"Failed: {report['failed']}")
            typer.echo(f"Review Required: {report['review_required']}")
            typer.echo(f"Success Rate: {report['success_rate']:.2%}")
            typer.echo(f"Rollback Count: {report['rollback_count']}")
            typer.echo(f"Mean Time To Recover (s): {report['mean_time_to_recover_seconds']:.2f}")
            typer.echo(f"Generated At: {report['generated_at']}")
        finally:
            await db.disconnect()

    run_async(run_report())


@app.command("approve-skill")
def approve_skill(
    skill_name: str = typer.Argument(..., help="Skill component_name to approve."),
    maturity: str = typer.Option(
        "production-approved",
        help="Target maturity level (experimental | staging-approved | production-approved).",
    ),
):
    """Manually set skill maturity level to support assisted-adoption phases."""

    async def run_approval():
        from nanobot.db.engine import db

        await db.connect()
        try:
            import json

            row = await db.fetchrow(
                "SELECT definition_json FROM system_model WHERE component_type = 'skill' AND component_name = $1",
                skill_name,
            )
            if not row:
                typer.echo(f"Skill not found: {skill_name}")
                return

            definition = row["definition_json"] or {}
            if isinstance(definition, str):
                definition = json.loads(definition)

            definition["maturity"] = maturity
            await db.execute(
                """
                UPDATE system_model
                SET definition_json = $2, updated_at = NOW()
                WHERE component_type = 'skill' AND component_name = $1
                """,
                skill_name,
                json.dumps(definition),
            )
            typer.echo(f"Updated {skill_name} maturity -> {maturity}")
        finally:
            await db.disconnect()

    run_async(run_approval())


@app.command("ingest-sources")
def ingest_sources():
    """Discover/sync source repositories and ingest updated patterns."""

    async def run_ingest():
        from nanobot.db.engine import db
        from nanobot.meta.source_intelligence import source_intelligence

        await db.connect()
        try:
            summary = await source_intelligence.refresh_sources()
            typer.echo("\n--- Source Ingestion Summary ---")
            typer.echo(f"Discovered Repositories: {summary['discovered_repositories']}")
            typer.echo(f"Synced Repositories: {summary['synced_repositories']}")
            typer.echo(f"Failed Syncs: {summary['failed_syncs']}")
            typer.echo(f"New Patterns Ingested: {summary['new_patterns_ingested']}")
        finally:
            await db.disconnect()

    run_async(run_ingest())


@app.command("prepare-sources")
def prepare_sources():
    """Create recommended source layout directories for manual repo/skill drops."""

    def run_prepare():
        from nanobot.meta.source_intelligence import source_intelligence

        layout = source_intelligence.ensure_source_layout()
        typer.echo("\n--- Source Layout Ready ---")
        typer.echo(f"repos root: {layout['repos_root']}")
        typer.echo(f"github repos: {layout['github_root']}")
        typer.echo(f"skill bundles: {layout['skills_root']}")
        typer.echo("\nNext steps:")
        typer.echo("1) Clone repos into repos/github/<repo-name>")
        typer.echo("2) Add SKILL.md bundles into repos/skills/<bundle-name>")
        typer.echo("3) Run: python -m nanobot ingest-sources")
        typer.echo("4) Run: python -m nanobot harvest-skill <query> --top-k 4")

    run_prepare()


@app.command("harvest-skill")
def harvest_skill(
    query: str = typer.Argument(..., help="Skill query (for example: telegram)."),
    top_k: int = typer.Option(4, help="Number of top candidates to select."),
    catalog_snapshot: str = typer.Option(
        "",
        help="Optional JSON snapshot path from an external catalog (for example ClawHub export).",
    ),
):
    """Rank top candidate skills from source repos and produce synthesis plan."""

    async def run_harvest():
        import json

        from nanobot.db.engine import db
        from nanobot.meta.source_intelligence import source_intelligence

        await db.connect()
        try:
            candidates = await source_intelligence.harvest_skill_candidates(query=query, top_k=top_k)
            if catalog_snapshot:
                catalog_candidates = await source_intelligence.harvest_catalog_snapshot(
                    query=query,
                    snapshot_path=catalog_snapshot,
                    top_k=top_k,
                )
                candidates = sorted(candidates + catalog_candidates, key=lambda c: c.score, reverse=True)[:top_k]
            plan = source_intelligence.build_skill_synthesis_plan(query=query, candidates=candidates)

            typer.echo("\n--- Skill Harvest Candidates ---")
            if not candidates:
                typer.echo("No matching candidates found.")
                return

            for idx, candidate in enumerate(candidates, start=1):
                typer.echo(
                    f"{idx}. {candidate.skill_name} [{candidate.source_repo}] score={candidate.score} path={candidate.skill_path}"
                )

            typer.echo("\n--- Synthesis Plan ---")
            typer.echo(json.dumps(plan, indent=2))
        finally:
            await db.disconnect()

    run_async(run_harvest())


@app.command()
def onboard(
    yes: bool = typer.Option(False, "--yes", help="Accept prompts defaults and confirmation when possible."),
    from_file: str = typer.Option("", help="Optional YAML file path with onboarding values."),
):
    """Interactive onboarding wizard for first-time setup and reconfiguration."""

    async def run_onboard():
        import json

        env_path = Path(".env")
        existing = _parse_env_file(env_path)
        updates = dict(existing)

        if from_file:
            import yaml

            raw = yaml.safe_load(Path(from_file).read_text(encoding="utf-8")) or {}
            for key, value in raw.items():
                updates[str(key)] = str(value)

        typer.echo("\n--- Nanobot Onboarding ---")
        if existing:
            typer.echo("Existing .env detected.")
            if not yes:
                mode = typer.prompt(
                    "Choose mode [update/new/cancel]",
                    default="update",
                ).strip().lower()
                if mode == "cancel":
                    typer.echo("Onboarding cancelled.")
                    return
                if mode == "new":
                    updates = {}

        # 1) Deployment mode.
        deploy_mode = updates.get("DEPLOY_MODE", "docker")
        if not yes:
            deploy_mode = typer.prompt("Database mode [docker/external]", default=deploy_mode).strip().lower()
        updates["DEPLOY_MODE"] = deploy_mode

        # 2) Database settings + connection test.
        updates["DB_HOST"] = updates.get("DB_HOST", "localhost")
        updates["DB_PORT"] = updates.get("DB_PORT", "5432")
        updates["DB_USER"] = updates.get("DB_USER", "postgres")
        updates["DB_PASSWORD"] = updates.get("DB_PASSWORD", "password")
        updates["DATABASE_NAME"] = updates.get("DATABASE_NAME", "nanobot_prod")
        updates["DATABASE_URL"] = updates.get(
            "DATABASE_URL",
            f"postgres://{updates['DB_USER']}:{updates['DB_PASSWORD']}@{updates['DB_HOST']}:{updates['DB_PORT']}/{updates['DATABASE_NAME']}",
        )

        if not yes:
            updates["DB_HOST"] = typer.prompt("DB host", default=updates["DB_HOST"])
            updates["DB_PORT"] = typer.prompt("DB port", default=updates["DB_PORT"])
            updates["DB_USER"] = typer.prompt("DB user", default=updates["DB_USER"])
            updates["DB_PASSWORD"] = typer.prompt("DB password", default=updates["DB_PASSWORD"], hide_input=True)
            updates["DATABASE_NAME"] = typer.prompt("DB name", default=updates["DATABASE_NAME"])
            updates["DATABASE_URL"] = typer.prompt(
                "DATABASE_URL",
                default=f"postgres://{updates['DB_USER']}:{updates['DB_PASSWORD']}@{updates['DB_HOST']}:{updates['DB_PORT']}/{updates['DATABASE_NAME']}",
            )

        ok, message = await _test_db_connection(updates)
        typer.echo(f"DB connection test: {'ok' if ok else 'failed'} - {message}")
        if not ok and not yes:
            retry = typer.confirm("Connection failed. Continue anyway?", default=False)
            if not retry:
                typer.echo("Onboarding stopped due to DB validation failure.")
                return

        # 3) Schema init.
        init_schema = yes or typer.confirm("Initialize/verify database schema now?", default=True)
        if init_schema:
            schema_ok, schema_msg = await _bootstrap_schema(updates)
            typer.echo(f"Schema bootstrap: {'ok' if schema_ok else 'failed'} - {schema_msg}")
            if not schema_ok and not yes:
                cont = typer.confirm("Schema bootstrap failed. Continue anyway?", default=False)
                if not cont:
                    return

        # 4) LLM provider settings.
        updates["LLM_PROVIDER"] = updates.get("LLM_PROVIDER", "openai")
        updates["LLM_MODEL"] = updates.get("LLM_MODEL", "gpt-4o-mini")
        updates["LLM_API_KEY"] = updates.get("LLM_API_KEY", "")
        updates["LLM_BASE_URL"] = updates.get("LLM_BASE_URL", "")
        if not yes:
            updates["LLM_PROVIDER"] = typer.prompt("LLM provider", default=updates["LLM_PROVIDER"])
            updates["LLM_MODEL"] = typer.prompt("LLM model", default=updates["LLM_MODEL"])
            if not updates["LLM_API_KEY"]:
                updates["LLM_API_KEY"] = typer.prompt("LLM API key", hide_input=True, default="")
            updates["LLM_BASE_URL"] = typer.prompt("LLM base URL (optional)", default=updates["LLM_BASE_URL"])

        # 5) Security/workspace policy.
        updates["WORKSPACE_ROOT"] = updates.get("WORKSPACE_ROOT", str(Path.cwd()))
        updates["SECURITY_ALLOWLIST_EXTRA"] = updates.get("SECURITY_ALLOWLIST_EXTRA", "")
        updates["SECURITY_BLOCKLIST_EXTRA"] = updates.get("SECURITY_BLOCKLIST_EXTRA", "")
        if not yes:
            updates["WORKSPACE_ROOT"] = typer.prompt("Workspace root", default=updates["WORKSPACE_ROOT"])
            updates["SECURITY_ALLOWLIST_EXTRA"] = typer.prompt(
                "Extra allowlisted commands (comma-separated, optional)",
                default=updates["SECURITY_ALLOWLIST_EXTRA"],
            )
            updates["SECURITY_BLOCKLIST_EXTRA"] = typer.prompt(
                "Extra blocked patterns (comma-separated, optional)",
                default=updates["SECURITY_BLOCKLIST_EXTRA"],
            )

        # 6) Evolution policy.
        updates["EVOLUTION_PHASE"] = updates.get("EVOLUTION_PHASE", "phase1")
        updates["LIVE_MODE"] = updates.get("LIVE_MODE", "true")
        updates["PLANNER_USAGE_CAP"] = updates.get("PLANNER_USAGE_CAP", "50")
        if not yes:
            updates["EVOLUTION_PHASE"] = typer.prompt(
                "Evolution phase [phase1/phase2/phase3]",
                default=updates["EVOLUTION_PHASE"],
            )
            updates["LIVE_MODE"] = str(typer.confirm("Enable live mode?", default=str(updates["LIVE_MODE"]).lower() == "true")).lower()
            updates["PLANNER_USAGE_CAP"] = typer.prompt("Planner usage cap", default=updates["PLANNER_USAGE_CAP"])

        # 7) Observability settings.
        updates["HEALTH_REPORT_FREQUENCY_DAYS"] = updates.get("HEALTH_REPORT_FREQUENCY_DAYS", "7")
        updates["METRICS_RETENTION_DAYS"] = updates.get("METRICS_RETENTION_DAYS", "30")
        if not yes:
            updates["HEALTH_REPORT_FREQUENCY_DAYS"] = typer.prompt(
                "Health report frequency (days)",
                default=updates["HEALTH_REPORT_FREQUENCY_DAYS"],
            )
            updates["METRICS_RETENTION_DAYS"] = typer.prompt(
                "Metrics retention (days)",
                default=updates["METRICS_RETENTION_DAYS"],
            )

        summary = {
            "DEPLOY_MODE": updates.get("DEPLOY_MODE"),
            "DB_HOST": updates.get("DB_HOST"),
            "DB_PORT": updates.get("DB_PORT"),
            "DB_USER": updates.get("DB_USER"),
            "DATABASE_NAME": updates.get("DATABASE_NAME"),
            "LLM_PROVIDER": updates.get("LLM_PROVIDER"),
            "LLM_MODEL": updates.get("LLM_MODEL"),
            "WORKSPACE_ROOT": updates.get("WORKSPACE_ROOT"),
            "EVOLUTION_PHASE": updates.get("EVOLUTION_PHASE"),
            "LIVE_MODE": updates.get("LIVE_MODE"),
            "PLANNER_USAGE_CAP": updates.get("PLANNER_USAGE_CAP"),
            "HEALTH_REPORT_FREQUENCY_DAYS": updates.get("HEALTH_REPORT_FREQUENCY_DAYS"),
            "METRICS_RETENTION_DAYS": updates.get("METRICS_RETENTION_DAYS"),
        }
        typer.echo("\n--- Onboarding Summary ---")
        typer.echo(json.dumps(summary, indent=2))

        if not yes:
            confirm = typer.confirm("Write these settings to .env?", default=True)
            if not confirm:
                typer.echo("Onboarding cancelled before write.")
                return

        _write_env_atomic(env_path, updates)
        typer.echo(".env updated successfully.")
        typer.echo("Next steps:")
        typer.echo("1) Restart the process so new settings are loaded.")
        typer.echo("2) Run: python -m nanobot ingest-sources")
        typer.echo("3) Run: python -m nanobot evolve")

    run_async(run_onboard())

if __name__ == "__main__":
    app()
