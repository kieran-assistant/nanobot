"""End-to-end evolution integration test with observability validation."""

from pathlib import Path
import shutil
import uuid

import pytest

from nanobot.config import settings
from nanobot.db.engine import db
from nanobot.meta.evolution_engine import evolution_engine
from nanobot.meta.introspector import introspector
from nanobot.meta.source_intelligence import source_intelligence


@pytest.mark.asyncio
async def test_full_evolution_cycle_records_observability(require_db, monkeypatch):
    suffix = uuid.uuid4().hex[:8]
    tool_name = f"integration_dummy_feature_{suffix}"
    expected_skill_prefix = f"gen-{tool_name.replace('_', '-')}"
    previous_phase = settings.evolution_phase

    async def no_scan(*args, **kwargs):
        return None

    async def no_refresh(*args, **kwargs):
        return {
            "discovered_repositories": 0,
            "synced_repositories": 0,
            "failed_syncs": 0,
            "new_patterns_ingested": 0,
        }

    monkeypatch.setattr(introspector, "scan_reference_repo", no_scan)
    monkeypatch.setattr(source_intelligence, "refresh_sources", no_refresh)
    settings.evolution_phase = "phase3"

    await db.execute("DELETE FROM reference_patterns WHERE source_repo = 'integration_test'")
    await db.execute("DELETE FROM evolution_queue WHERE target_component = $1", tool_name)
    await db.execute("DELETE FROM evolution_attempts WHERE target_component = $1", tool_name)

    await db.execute(
        """
        INSERT INTO reference_patterns (source_repo, pattern_name, pattern_type, definition)
        VALUES ($1, $2, 'function', $3)
        """,
        "integration_test",
        tool_name,
        f'{{"name":"{tool_name}","args":[],"docstring":"Integration test capability"}}',
    )

    try:
        await evolution_engine.run_cycle()

        queue_status = await db.fetchval(
            "SELECT status FROM evolution_queue WHERE target_component = $1 ORDER BY created_at DESC LIMIT 1",
            tool_name,
        )
        assert queue_status == "deployed"

        skill_name = await db.fetchval(
            """
            SELECT component_name
            FROM system_model
            WHERE component_type = 'skill'
              AND component_name LIKE $1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            f"{expected_skill_prefix}%",
        )
        assert skill_name is not None

        maturity = await db.fetchval(
            """
            SELECT definition_json->>'maturity'
            FROM system_model
            WHERE component_type = 'skill' AND component_name = $1
            """,
            skill_name,
        )
        assert maturity == "production-approved"

        attempt_status = await db.fetchval(
            """
            SELECT status
            FROM evolution_attempts
            WHERE target_component = $1
            ORDER BY started_at DESC
            LIMIT 1
            """,
            tool_name,
        )
        assert attempt_status == "deployed"
    finally:
        settings.evolution_phase = previous_phase
        await db.execute("DELETE FROM reference_patterns WHERE source_repo = 'integration_test' AND pattern_name = $1", tool_name)
        await db.execute("DELETE FROM evolution_queue WHERE target_component = $1", tool_name)
        await db.execute("DELETE FROM evolution_attempts WHERE target_component = $1", tool_name)
        await db.execute("DELETE FROM system_model WHERE component_type = 'skill' AND component_name LIKE $1", f"{expected_skill_prefix}%")
        skill_dir_root = Path("nanobot/skills")
        for path in skill_dir_root.glob(f"{expected_skill_prefix}*"):
            if path.is_dir():
                shutil.rmtree(path)
