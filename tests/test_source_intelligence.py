"""Tests for source-intelligence ranking and synthesis planning."""

from pathlib import Path

import pytest

from nanobot.meta.source_intelligence import SourceIntelligence, SkillCandidate


def test_score_skill_candidate_prefers_relevant_content(tmp_path):
    manager = SourceIntelligence()
    skill_file = tmp_path / "telegram" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(
        """
# Telegram Skill
Security considerations.
Usage example:
```bash
echo hello
```
telegram telegram
""",
        encoding="utf-8",
    )

    score, signals = manager._score_skill_candidate(skill_file, skill_file.read_text(encoding="utf-8"), "telegram")
    assert score > 0.5
    assert signals["query_hits"] >= 2
    assert signals["has_security_section"] is True


def test_build_skill_synthesis_plan_contains_selected_candidates():
    manager = SourceIntelligence()
    candidates = [
        SkillCandidate(
            source_repo="repo_a",
            skill_name="telegram_core",
            skill_path="/tmp/repo_a/telegram_core",
            score=1.2,
            signals={"reason": "best command handling"},
        ),
        SkillCandidate(
            source_repo="repo_b",
            skill_name="telegram_auth",
            skill_path="/tmp/repo_b/telegram_auth",
            score=1.0,
            signals={"reason": "best auth flow"},
        ),
    ]

    plan = manager.build_skill_synthesis_plan("telegram", candidates)
    assert plan["query"] == "telegram"
    assert len(plan["selected_candidates"]) == 2
    assert plan["integration_strategy"] == "extract_interfaces_then_adapt_into_generated_skill"


@pytest.mark.asyncio
async def test_harvest_catalog_snapshot_ranks_candidates(tmp_path):
    manager = SourceIntelligence()
    snapshot = tmp_path / "catalog.json"
    snapshot.write_text(
        """
[
  {"name":"telegram-skill-a","description":"telegram integration","repo":"clawhub","path":"skill/a","rank":9,"downloads":1000,"stars":100},
  {"name":"weather-skill","description":"weather integration","repo":"clawhub","path":"skill/w","rank":10,"downloads":2000,"stars":300}
]
""".strip(),
        encoding="utf-8",
    )

    class _DBStub:
        async def execute(self, *args, **kwargs):
            return None

    # Avoid DB dependency in this unit test.
    from nanobot.meta import source_intelligence as module

    original_db = module.db
    module.db = _DBStub()
    try:
        results = await manager.harvest_catalog_snapshot("telegram", str(snapshot), top_k=4)
    finally:
        module.db = original_db

    assert len(results) == 1
    assert results[0].skill_name == "telegram-skill-a"
