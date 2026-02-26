# Evolution Governance

This document describes how Nanobot-DB governs autonomous evolution.

## 1. Proposal Quality Bar

The planner now emits:
- `score`: risk, blast radius, confidence, dependency impact, and signal breakdown.
- `delivery_plan`: structured patch/test/migration/validation plan.

Signals used in scoring:
- AST signature hash novelty.
- Dependency impact (imports + called functions).
- Usage frequency from `messages`.
- Failure history from `evolution_queue`.
- Operator priority overrides from `operator_priorities`.

## 2. Security Release Gates

Security is blocking, not advisory.

Release gates:
- Definition-time policy checks for executor commands.
- Pre-promotion red-team static scans for dangerous patterns.
- Runtime command/file policy enforcement.

See: `SECURITY_THREAT_MODEL.md`.

## 3. Capability Maturity Levels

Generated capabilities are governed by maturity tags:
- `experimental`
- `staging-approved`
- `production-approved`

In live mode, only `production-approved` skills are callable.
Use:
- `python -m nanobot approve-skill <skill-name> --maturity production-approved`

## 4. Staged Adoption Phases

Set via `EVOLUTION_PHASE`:
- `phase1`: human review required for all proposals.
- `phase2`: auto-promote only low-risk/high-confidence proposals.
- `phase3`: broader autonomous promotions with policy guardrails.

## 5. Observability & Weekly Health

Each attempt is recorded in `evolution_attempts`:
- Proposal source/payload.
- Checks run.
- Stage/status transitions.
- Failure reasons.
- Rollback count.
- Time-to-recover.

Generate report:
- `python -m nanobot evolution-report --days 7`

## 6. Multi-Source Skill Harvesting

To avoid reinventing common capabilities:
- `python -m nanobot ingest-sources`
  - Discovers and syncs repositories under `repos/`.
  - Ingests pattern updates into reference intelligence.
- `python -m nanobot harvest-skill <query> --top-k 4`
  - Ranks top candidate skills for the query.
  - Produces a synthesis plan selecting best segments from one or more candidates.
- `python -m nanobot harvest-skill <query> --catalog-snapshot <skills.json>`
  - Merges catalog-sourced candidates (for example exported from ClawHub) with local source candidates.

All resulting integrations must still pass security gates and staged-adoption policy.

## 7. Onboarding Order

The recommended onboarding order is implemented in `python -m nanobot onboard`:
1. Detect existing config and choose update/new mode.
2. Choose deployment mode (`docker` or external DB).
3. Collect DB settings and validate connection.
4. Initialize/verify schema.
5. Collect LLM provider/model/key settings.
6. Collect security/workspace policy.
7. Collect evolution/adoption policy settings.
8. Collect observability settings.
9. Show summary and confirm.
10. Persist `.env` atomically.
