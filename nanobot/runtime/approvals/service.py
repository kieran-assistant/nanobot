"""
Module Purpose: Approval workflow service for external tool execution governance.

Responsibilities:
    - Manage approval request lifecycle (create, approve, reject, revoke)
    - Track data scope and secret scope grants for security
    - Enforce expiration policies on approved grants
    - Provide query methods for matching existing grants
    - Validate approval states (pending → approved/rejected → active/revoked)

Dependencies:
    - nanobot.db.engine.db (database connection)
    - datetime (for expiration calculations)
    - json (for scope serialization)

Why this module exists:
    External tools (Docker, repo extraction) can access sensitive data or perform
    dangerous operations. This service ensures all such operations are:
    1. Tracked and auditable
    2. Explicitly approved by operators
    3. Scoped to specific data/secrets only
    4. Time-limited with automatic expiration
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from nanobot.db.engine import db


# ---------- Public API: ApprovalService ----------


class ApprovalService:
    """Manages approval request lifecycle and execution authorization checks."""

    # ---------- Schema Management ----------

    async def ensure_schema(self) -> None:
        """
        Create approval workflow tables if they don't exist.

        Creates two tables:
        - approval_requests: Pending and completed requests for tool access
        - approval_grants: Active (approved) grants that can be checked at runtime

        Both tables use JSONB columns for flexible scope storage.
        """
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS approval_requests (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                channel VARCHAR(50) NOT NULL DEFAULT 'cli',
                user_id VARCHAR(255) NOT NULL,
                tool_ref VARCHAR(255) NOT NULL,
                repo_url TEXT NOT NULL,
                requested_data_scopes JSONB DEFAULT '[]'::jsonb,
                requested_secret_scopes JSONB DEFAULT '[]'::jsonb,
                status VARCHAR(50) NOT NULL DEFAULT 'pending',
                requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                decided_at TIMESTAMPTZ,
                decision_note TEXT,
                expires_at TIMESTAMPTZ
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS approval_grants (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                request_id UUID REFERENCES approval_requests(id) ON DELETE SET NULL,
                user_id VARCHAR(255) NOT NULL,
                tool_ref VARCHAR(255) NOT NULL,
                repo_url TEXT NOT NULL,
                approved_data_scopes JSONB DEFAULT '[]'::jsonb,
                approved_secret_scopes JSONB DEFAULT '[]'::jsonb,
                status VARCHAR(50) NOT NULL DEFAULT 'active',
                granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                revoked_at TIMESTAMPTZ,
                expires_at TIMESTAMPTZ
            )
            """
        )

    # ---------- Request Creation ----------

    async def create_request(
        self,
        user_id: str,
        tool_ref: str,
        repo_url: str,
        data_scopes: list[str],
        secret_scopes: list[str],
        channel: str = "cli",
    ) -> str:
        """
        Create a new approval request in 'pending' status.

        Sorts and dedupes scopes to prevent grant scope confusion.
        Returns the new request ID for tracking.
        """
        await self.ensure_schema()
        return await db.fetchval(
            """
            INSERT INTO approval_requests (
                channel, user_id, tool_ref, repo_url, requested_data_scopes, requested_secret_scopes, status
            )
            VALUES ($1, $2, $3, $4, $5, $6, 'pending')
            RETURNING id
            """,
            channel,
            user_id,
            tool_ref,
            repo_url,
            json.dumps(sorted(set(data_scopes))),
            json.dumps(sorted(set(secret_scopes))),
        )

    # ---------- Request Approval ----------

    async def approve_request(
        self,
        request_id: str,
        approver_user_id: str,
        approved_data_scopes: list[str] | None = None,
        approved_secret_scopes: list[str] | None = None,
        expires_hours: int = 24,
        note: str = "",
    ) -> str:
        """
        Approve a pending request, creating an active grant.

        Validates that request is still pending, then:
        1. Creates an approval_grants record with approved scopes
        2. Updates the request status to 'approved'
        3. Sets expiration time (minimum 1 hour, default 24 hours)

        If approver provides no scopes, uses requested scopes as-is.
        """
        await self.ensure_schema()
        row = await db.fetchrow(
            "SELECT * FROM approval_requests WHERE id = $1", request_id
        )
        if not row:
            raise ValueError(f"Approval request not found: {request_id}")
        if row["status"] != "pending":
            raise ValueError(
                f"Approval request {request_id} is not pending (status={row['status']})"
            )

        # Use approved scopes if provided, otherwise fall back to requested scopes
        req_data = self._decode_json(row["requested_data_scopes"])
        req_secret = self._decode_json(row["requested_secret_scopes"])
        data_scopes = (
            approved_data_scopes if approved_data_scopes is not None else req_data
        )
        secret_scopes = (
            approved_secret_scopes if approved_secret_scopes is not None else req_secret
        )

        # Calculate expiration: minimum 1 hour to prevent immediate expiry
        expires_at = datetime.now(timezone.utc) + timedelta(hours=max(1, expires_hours))

        # Create the grant record
        grant_id = await db.fetchval(
            """
            INSERT INTO approval_grants (
                request_id, user_id, tool_ref, repo_url, approved_data_scopes, approved_secret_scopes, status, expires_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, 'active', $7)
            RETURNING id
            """,
            request_id,
            approver_user_id,
            row["tool_ref"],
            row["repo_url"],
            json.dumps(sorted(set(data_scopes))),
            json.dumps(sorted(set(secret_scopes))),
            expires_at,
        )

        # Update the original request with decision details
        await db.execute(
            """
            UPDATE approval_requests
            SET status = 'approved', decided_at = NOW(), decision_note = $2, expires_at = $3
            WHERE id = $1
            """,
            request_id,
            note,
            expires_at,
        )
        return grant_id

    # ---------- Request Rejection ----------

    async def reject_request(self, request_id: str, note: str = "") -> None:
        """
        Reject a pending request without creating a grant.

        Updates the request status to 'rejected' with the rejection note.
        No grant is created, and the request cannot be approved later.
        """
        await self.ensure_schema()
        await db.execute(
            """
            UPDATE approval_requests
            SET status = 'rejected', decided_at = NOW(), decision_note = $2
            WHERE id = $1
            """,
            request_id,
            note,
        )

    # ---------- Grant Revocation ----------

    async def revoke_grant(self, grant_id: str, note: str = "") -> None:
        """
        Revoke an active grant, marking it as 'revoked'.

        Does NOT delete the grant record (preserves audit trail).
        Sets revoked_at timestamp for future reference.
        """
        await self.ensure_schema()
        await db.execute(
            """
            UPDATE approval_grants
            SET status = 'revoked', revoked_at = NOW()
            WHERE id = $1
            """,
            grant_id,
        )

    # ---------- Query Methods ----------

    async def list_requests(
        self, status: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        """
        List approval requests, optionally filtered by status.

        Returns most recent requests first (DESC by requested_at).
        Default limit of 20 prevents excessive memory usage.
        """
        await self.ensure_schema()
        if status:
            rows = await db.fetch(
                """
                SELECT * FROM approval_requests
                WHERE status = $1
                ORDER BY requested_at DESC
                LIMIT $2
                """,
                status,
                limit,
            )
        else:
            rows = await db.fetch(
                """
                SELECT * FROM approval_requests
                ORDER BY requested_at DESC
                LIMIT $1
                """,
                limit,
            )
        return [dict(row) for row in rows]

    async def list_grants(
        self, status: str | None = "active", limit: int = 20
    ) -> list[dict[str, Any]]:
        """
        List approval grants, optionally filtered by status.

        Returns most recent grants first (DESC by granted_at).
        Default limit of 20 prevents excessive memory usage.
        Default status='active' shows currently valid grants only.
        """
        await self.ensure_schema()
        if status:
            rows = await db.fetch(
                """
                SELECT * FROM approval_grants
                WHERE status = $1
                ORDER BY granted_at DESC
                LIMIT $2
                """,
                status,
                limit,
            )
        else:
            rows = await db.fetch(
                """
                SELECT * FROM approval_grants
                ORDER BY granted_at DESC
                LIMIT $1
                """,
                limit,
            )
        return [dict(row) for row in rows]

    # ---------- Grant Matching ----------

    async def find_matching_grant(
        self,
        user_id: str,
        tool_ref: str,
        repo_url: str,
        required_data_scopes: list[str],
        required_secret_scopes: list[str],
    ) -> dict[str, Any] | None:
        """
        Find an existing active grant that matches the required scopes.

        Used by runtime tools to check if a tool execution is already approved.
        Returns the most recently created matching grant, or None if no match.

        Matching logic:
        - Grant must be 'active' (not expired, not revoked)
        - User ID must match (grant is user-specific)
        - Tool reference must match
        - Repository URL must match
        - All required data scopes must be subset of approved data scopes
        - All required secret scopes must be subset of approved secret scopes
        - Grant must not be expired (expires_at > NOW())
        """
        await self.ensure_schema()
        rows = await db.fetch(
            """
            SELECT *
            FROM approval_grants
            WHERE status = 'active'
              AND user_id = $1
              AND tool_ref = $2
              AND repo_url = $3
            ORDER BY granted_at DESC
            """,
            user_id,
            tool_ref,
            repo_url,
        )

        # Check for active, non-expired, scope-matching grant
        now = datetime.now(timezone.utc)
        for row in rows:
            expires_at = row["expires_at"]
            if expires_at and expires_at < now:
                continue

            approved_data = set(self._decode_json(row["approved_data_scopes"]))
            approved_secret = set(self._decode_json(row["approved_secret_scopes"]))

            # Verify all required scopes are covered by approved scopes
            if set(required_data_scopes).issubset(approved_data) and set(
                required_secret_scopes
            ).issubset(approved_secret):
                return dict(row)
        return None

    # ---------- Helper Methods ----------

    def _decode_json(self, value):
        """
        Safely decode JSONB value to Python list.

        Returns empty list [] if parsing fails or value is not a list.
        Used for scope comparison in find_matching_grant.
        """
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else []
            except Exception:
                return []
        return []


# Singleton instance for import
approval_service = ApprovalService()
