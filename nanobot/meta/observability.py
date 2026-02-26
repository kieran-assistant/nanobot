"""Evolution observability and reporting services.

This module records structured attempt metrics and generates weekly health reports.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import Any

from nanobot.db.engine import db


class EvolutionObservability:
    """Tracks evolution attempts and emits aggregated health reports."""

    async def ensure_schema(self) -> None:
        """Create observability tables when missing."""

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS evolution_attempts (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                proposal_source VARCHAR(100) NOT NULL,
                target_component VARCHAR(255) NOT NULL,
                proposal_payload JSONB DEFAULT '{}'::jsonb,
                score JSONB DEFAULT '{}'::jsonb,
                checks_run JSONB DEFAULT '[]'::jsonb,
                stage VARCHAR(50) NOT NULL,
                status VARCHAR(50) NOT NULL,
                failure_reason TEXT,
                rollback_count INT DEFAULT 0,
                started_at TIMESTAMPTZ NOT NULL,
                ended_at TIMESTAMPTZ,
                duration_seconds DOUBLE PRECISION
            )
            """
        )

    async def start_attempt(
        self,
        proposal_source: str,
        target_component: str,
        proposal_payload: dict[str, Any],
        score: dict[str, Any],
    ) -> str:
        """Create a new evolution attempt row and return attempt id."""

        await self.ensure_schema()
        started_at = datetime.now(timezone.utc)
        return await db.fetchval(
            """
            INSERT INTO evolution_attempts (
                proposal_source, target_component, proposal_payload, score, checks_run, stage, status, started_at
            )
            VALUES ($1, $2, $3, $4, '[]'::jsonb, 'ingest', 'started', $5)
            RETURNING id
            """,
            proposal_source,
            target_component,
            json.dumps(proposal_payload),
            json.dumps(score),
            started_at,
        )

    async def mark_stage(
        self,
        attempt_id: str,
        stage: str,
        status: str,
        check_name: str | None = None,
        failure_reason: str | None = None,
        rollback_delta: int = 0,
    ) -> None:
        """Update the stage/status and append check metadata for an attempt."""

        checks_to_append = []
        if check_name:
            checks_to_append.append(
                {
                    "name": check_name,
                    "status": status,
                    "stage": stage,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

        await db.execute(
            """
            UPDATE evolution_attempts
            SET stage = $2,
                status = $3,
                checks_run = checks_run || $4::jsonb,
                failure_reason = COALESCE($5, failure_reason),
                rollback_count = rollback_count + $6
            WHERE id = $1
            """,
            attempt_id,
            stage,
            status,
            json.dumps(checks_to_append),
            failure_reason,
            rollback_delta,
        )

    async def finish_attempt(self, attempt_id: str, status: str, failure_reason: str | None = None) -> None:
        """Finalize timing and terminal status for an attempt."""

        await db.execute(
            """
            UPDATE evolution_attempts
            SET status = $2,
                ended_at = NOW(),
                duration_seconds = EXTRACT(EPOCH FROM (NOW() - started_at)),
                failure_reason = COALESCE($3, failure_reason)
            WHERE id = $1
            """,
            attempt_id,
            status,
            failure_reason,
        )

    async def weekly_health_report(self, days: int = 7) -> dict[str, Any]:
        """Aggregate health metrics for recent attempts."""

        await self.ensure_schema()
        since = datetime.now(timezone.utc) - timedelta(days=days)
        rows = await db.fetch(
            """
            SELECT status, stage, failure_reason, rollback_count, duration_seconds, started_at
            FROM evolution_attempts
            WHERE started_at >= $1
            ORDER BY started_at DESC
            """,
            since,
        )

        total = len(rows)
        deployed = sum(1 for row in rows if row["status"] == "deployed")
        failed = sum(1 for row in rows if row["status"] in {"failed", "error"})
        review_required = sum(1 for row in rows if row["status"] == "review_required")
        rollback_count = sum(int(row["rollback_count"] or 0) for row in rows)
        durations = [float(row["duration_seconds"]) for row in rows if row["duration_seconds"] is not None]
        mean_recovery = (sum(durations) / len(durations)) if durations else 0.0

        return {
            "window_days": days,
            "attempts_total": total,
            "deployed": deployed,
            "failed": failed,
            "review_required": review_required,
            "success_rate": (deployed / total) if total else 0.0,
            "rollback_count": rollback_count,
            "mean_time_to_recover_seconds": mean_recovery,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


observability = EvolutionObservability()
