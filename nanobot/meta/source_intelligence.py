"""Source intelligence services for repo sync, ingestion, and skill harvesting.

This module enables real-world source workflows:
1. Discover/sync local git repositories under ``repos/``.
2. Ingest changed Python patterns into ``reference_patterns``.
3. Rank candidate skills for a query (e.g. "telegram") across sources.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any

from loguru import logger

from nanobot.db.engine import db
from nanobot.meta.introspector import introspector


@dataclass
class SkillCandidate:
    """Normalized candidate structure used by ranking and synthesis logic."""

    source_repo: str
    skill_name: str
    skill_path: str
    score: float
    signals: dict[str, Any]


class SourceIntelligence:
    """Coordinates repository synchronization and skill candidate analysis."""

    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent
        self.repos_root = self.project_root / "repos"
        self.github_root = self.repos_root / "github"
        self.skills_root = self.repos_root / "skills"

    def ensure_source_layout(self) -> dict[str, str]:
        """Create recommended source folders for real-world ingestion workflows."""

        self.repos_root.mkdir(parents=True, exist_ok=True)
        self.github_root.mkdir(parents=True, exist_ok=True)
        self.skills_root.mkdir(parents=True, exist_ok=True)

        github_readme = self.github_root / "README.md"
        if not github_readme.exists():
            github_readme.write_text(
                "# GitHub Sources\n\n"
                "Place cloned repositories here (one directory per repository).\n"
                "Example: repos/github/my-valuable-repo\n",
                encoding="utf-8",
            )

        skills_readme = self.skills_root / "README.md"
        if not skills_readme.exists():
            skills_readme.write_text(
                "# Skill Sources\n\n"
                "Place standalone skill packs here.\n"
                "Each pack should contain one or more SKILL.md files.\n"
                "Example: repos/skills/telegram-bundle/SKILL.md\n",
                encoding="utf-8",
            )

        return {
            "repos_root": str(self.repos_root),
            "github_root": str(self.github_root),
            "skills_root": str(self.skills_root),
        }

    async def ensure_schema(self) -> None:
        """Create source-intelligence tables if they do not exist."""

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS source_repositories (
                name VARCHAR(255) PRIMARY KEY,
                repo_path TEXT NOT NULL,
                source_type VARCHAR(50) NOT NULL DEFAULT 'local_git',
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                last_commit VARCHAR(128),
                last_synced_at TIMESTAMPTZ
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS source_sync_runs (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                repo_name VARCHAR(255) NOT NULL,
                started_at TIMESTAMPTZ NOT NULL,
                ended_at TIMESTAMPTZ,
                status VARCHAR(50) NOT NULL,
                changed_files JSONB DEFAULT '[]'::jsonb,
                error_message TEXT
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS harvested_skills (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                query VARCHAR(255) NOT NULL,
                source_repo VARCHAR(255) NOT NULL,
                skill_name VARCHAR(255) NOT NULL,
                skill_path TEXT NOT NULL,
                score NUMERIC NOT NULL,
                signals JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

    async def refresh_sources(self) -> dict[str, Any]:
        """Discover repos, sync available git repos, and ingest Python patterns.

        Returns a summary payload suitable for CLI/reporting.
        """

        await self.ensure_schema()
        repos = self._discover_repositories()
        synced = 0
        failed = 0
        ingested_patterns = 0

        for source in repos:
            repo_name = source["name"]
            repo_path = source["path"]
            source_type = source["source_type"]
            await self._upsert_repository(repo_name, str(repo_path), source_type)
            if source["syncable"]:
                result = await self._sync_repository(repo_name, repo_path)
                if result["status"] == "ok":
                    synced += 1
                else:
                    failed += 1

            before = await db.fetchval(
                "SELECT COUNT(*) FROM reference_patterns WHERE source_repo = $1",
                repo_name,
            )
            await introspector.scan_reference_repo(str(repo_path), repo_name)
            after = await db.fetchval(
                "SELECT COUNT(*) FROM reference_patterns WHERE source_repo = $1",
                repo_name,
            )
            ingested_patterns += int((after or 0) - (before or 0))

            await self._update_repo_commit(repo_name, repo_path)

        return {
            "discovered_repositories": len(repos),
            "synced_repositories": synced,
            "failed_syncs": failed,
            "new_patterns_ingested": ingested_patterns,
        }

    async def harvest_skill_candidates(self, query: str, top_k: int = 4) -> list[SkillCandidate]:
        """Search source repos for skills related to query and return ranked candidates."""

        await self.ensure_schema()
        candidates = self._collect_skill_candidates(query)
        ranked = sorted(candidates, key=lambda item: item.score, reverse=True)[:top_k]

        for item in ranked:
            await db.execute(
                """
                INSERT INTO harvested_skills (query, source_repo, skill_name, skill_path, score, signals)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                query,
                item.source_repo,
                item.skill_name,
                item.skill_path,
                item.score,
                json.dumps(item.signals),
            )

        return ranked

    async def harvest_catalog_snapshot(self, query: str, snapshot_path: str, top_k: int = 4) -> list[SkillCandidate]:
        """Rank candidates from an external catalog snapshot file.

        The snapshot is expected to be a JSON list of objects with optional fields:
        - name
        - description
        - repo
        - path
        - rank
        - downloads
        - stars
        """

        data = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
        ranked: list[SkillCandidate] = []
        for item in data:
            description = str(item.get("description", ""))
            name = str(item.get("name", "unknown_skill"))
            combined = f"{name}\n{description}"
            if query.lower() not in combined.lower():
                continue

            rank = float(item.get("rank", 0))
            downloads = float(item.get("downloads", 0))
            stars = float(item.get("stars", 0))
            relevance = combined.lower().count(query.lower())
            score = (rank * 0.5) + (min(downloads, 100000) / 100000 * 0.2) + (min(stars, 10000) / 10000 * 0.2) + (
                min(relevance, 10) * 0.1
            )

            ranked.append(
                SkillCandidate(
                    source_repo=str(item.get("repo", "catalog")),
                    skill_name=name,
                    skill_path=str(item.get("path", "")),
                    score=round(score, 4),
                    signals={
                        "catalog_rank": rank,
                        "downloads": downloads,
                        "stars": stars,
                        "relevance_hits": relevance,
                        "reason": "catalog ranking + relevance",
                    },
                )
            )

        ranked = sorted(ranked, key=lambda candidate: candidate.score, reverse=True)[:top_k]
        for item in ranked:
            await db.execute(
                """
                INSERT INTO harvested_skills (query, source_repo, skill_name, skill_path, score, signals)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                query,
                item.source_repo,
                item.skill_name,
                item.skill_path,
                item.score,
                json.dumps(item.signals),
            )
        return ranked

    def build_skill_synthesis_plan(self, query: str, candidates: list[SkillCandidate]) -> dict[str, Any]:
        """Build a controlled "best of sources" implementation plan.

        The result is intentionally plan-oriented (not blind code merge):
        - Which sources to pull from.
        - Why each source was selected.
        - What validation gates must pass before promotion.
        """

        patch_plan = []
        for candidate in candidates:
            patch_plan.append(
                {
                    "source_repo": candidate.source_repo,
                    "skill_name": candidate.skill_name,
                    "source_path": candidate.skill_path,
                    "selection_reason": candidate.signals.get("reason", "high ranking candidate"),
                }
            )

        return {
            "query": query,
            "selected_candidates": [candidate.__dict__ for candidate in candidates],
            "integration_strategy": "extract_interfaces_then_adapt_into_generated_skill",
            "patch_plan": patch_plan,
            "validation_plan": [
                "Run security release gate (threat-model + red-team checks).",
                "Run syntax and targeted unit tests for selected segments.",
                "Require policy-phase approval before production promotion.",
            ],
        }

    def _discover_repositories(self) -> list[dict[str, Any]]:
        """Find candidate repositories in ``repos/`` including github/skills partitions."""

        self.ensure_source_layout()
        discovered: dict[str, dict[str, Any]] = {}

        # Keep compatibility with existing direct repos/ children.
        for child in sorted(self.repos_root.iterdir()):
            if not child.is_dir():
                continue
            if child.name in {"github", "skills"}:
                continue
            name = child.name
            discovered[name] = {
                "name": name,
                "path": child,
                "source_type": "local_repo",
                "syncable": (child / ".git").exists(),
            }

        # GitHub-style repositories: repos/github/<repo_name>
        for repo in sorted(self.github_root.iterdir()):
            if not repo.is_dir():
                continue
            name = f"github/{repo.name}"
            discovered[name] = {
                "name": name,
                "path": repo,
                "source_type": "github_repo" if (repo / ".git").exists() else "github_snapshot",
                "syncable": (repo / ".git").exists(),
            }

        # Standalone skill packs: repos/skills/<pack_name>
        for pack in sorted(self.skills_root.iterdir()):
            if not pack.is_dir():
                continue
            name = f"skills/{pack.name}"
            discovered[name] = {
                "name": name,
                "path": pack,
                "source_type": "skill_bundle",
                "syncable": (pack / ".git").exists(),
            }

        return list(discovered.values())

    async def _upsert_repository(self, repo_name: str, repo_path: str, source_type: str) -> None:
        await db.execute(
            """
            INSERT INTO source_repositories (name, repo_path, source_type, enabled, last_synced_at)
            VALUES ($1, $2, $3, TRUE, NOW())
            ON CONFLICT (name)
            DO UPDATE SET repo_path = EXCLUDED.repo_path,
                          source_type = EXCLUDED.source_type,
                          enabled = TRUE,
                          last_synced_at = NOW()
            """,
            repo_name,
            repo_path,
            source_type,
        )

    async def _sync_repository(self, repo_name: str, repo_path: Path) -> dict[str, Any]:
        """Run git fetch/pull for a repo and capture changed files."""

        started_at = datetime.now(timezone.utc)
        run_id = await db.fetchval(
            """
            INSERT INTO source_sync_runs (repo_name, started_at, status, changed_files)
            VALUES ($1, $2, 'running', '[]'::jsonb)
            RETURNING id
            """,
            repo_name,
            started_at,
        )

        try:
            self._run_git(repo_path, ["fetch", "--all", "--prune"])
            self._run_git(repo_path, ["pull", "--ff-only"])
            changed_files = self._git_changed_files(repo_path)
            await db.execute(
                """
                UPDATE source_sync_runs
                SET ended_at = NOW(), status = 'ok', changed_files = $2
                WHERE id = $1
                """,
                run_id,
                json.dumps(changed_files),
            )
            return {"status": "ok", "changed_files": changed_files}
        except Exception as exc:
            await db.execute(
                """
                UPDATE source_sync_runs
                SET ended_at = NOW(), status = 'failed', error_message = $2
                WHERE id = $1
                """,
                run_id,
                str(exc),
            )
            logger.warning(f"Repository sync failed for {repo_name}: {exc}")
            return {"status": "failed", "error": str(exc)}

    async def _update_repo_commit(self, repo_name: str, repo_path: Path) -> None:
        if not (repo_path / ".git").exists():
            return
        try:
            commit = self._run_git(repo_path, ["rev-parse", "HEAD"]).strip()
            await db.execute(
                """
                UPDATE source_repositories
                SET last_commit = $2, last_synced_at = NOW()
                WHERE name = $1
                """,
                repo_name,
                commit,
            )
        except Exception as exc:
            logger.warning(f"Unable to store commit hash for {repo_name}: {exc}")

    def _collect_skill_candidates(self, query: str) -> list[SkillCandidate]:
        """Collect and score skill candidates from source repos."""

        q = query.lower()
        candidates: list[SkillCandidate] = []
        for source in self._discover_repositories():
            repo_name = source["name"]
            repo_path = source["path"]
            for skill_file in repo_path.rglob("SKILL.md"):
                content = skill_file.read_text(encoding="utf-8", errors="ignore")
                if q not in content.lower() and q not in skill_file.as_posix().lower():
                    continue
                score, signals = self._score_skill_candidate(skill_file, content, query)
                candidates.append(
                    SkillCandidate(
                        source_repo=repo_name,
                        skill_name=skill_file.parent.name,
                        skill_path=str(skill_file.parent),
                        score=score,
                        signals=signals,
                    )
                )
        return candidates

    def _score_skill_candidate(self, skill_file: Path, content: str, query: str) -> tuple[float, dict[str, Any]]:
        """Heuristic candidate scoring with transparent signals."""

        lower = content.lower()
        query_hits = lower.count(query.lower())
        code_block_count = content.count("```")
        has_security_section = "security" in lower
        has_examples = "example" in lower or "usage" in lower
        recency_signal = 0.3 if "2026" in content or "2025" in content else 0.1

        score = (
            min(query_hits, 10) * 0.4
            + min(code_block_count, 10) * 0.2
            + (0.2 if has_security_section else 0.0)
            + (0.2 if has_examples else 0.0)
            + recency_signal
        )
        reason = "high relevance and implementation detail density"
        return round(score, 4), {
            "query_hits": query_hits,
            "code_blocks": code_block_count,
            "has_security_section": has_security_section,
            "has_examples": has_examples,
            "recency_signal": recency_signal,
            "reason": reason,
            "source_file": str(skill_file),
        }

    def _run_git(self, repo_path: Path, args: list[str]) -> str:
        process = subprocess.run(
            ["git", "-C", str(repo_path), *args],
            check=True,
            capture_output=True,
            text=True,
        )
        return process.stdout

    def _git_changed_files(self, repo_path: Path) -> list[str]:
        try:
            output = self._run_git(repo_path, ["diff", "--name-only", "HEAD@{1}", "HEAD"])
            return [line.strip() for line in output.splitlines() if line.strip()]
        except Exception:
            return []


source_intelligence = SourceIntelligence()
