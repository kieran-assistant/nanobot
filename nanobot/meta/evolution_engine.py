# nanobot/meta/evolution_engine.py
from nanobot.meta.introspector import introspector
from nanobot.meta.planner import planner
from nanobot.meta.staging_manager import staging_manager
from nanobot.meta.schemas import SkillDefinition, ToolDefinition
from nanobot.meta.architect import architect
from nanobot.meta.observability import observability
from nanobot.meta.security_gate import security_gate
from nanobot.meta.source_intelligence import source_intelligence
from nanobot.db.engine import db
from nanobot.config import settings
from loguru import logger
import json


MATURITY_EXPERIMENTAL = "experimental"
MATURITY_STAGING_APPROVED = "staging-approved"
MATURITY_PRODUCTION_APPROVED = "production-approved"


class EvolutionEngine:
    async def run_cycle(self):
        logger.info("------- Starting Evolution Cycle -------")

        await introspector.scan_reference_repo("repos/reference", "GitNexus")
        source_summary = await source_intelligence.refresh_sources()
        logger.info(f"Source refresh summary: {source_summary}")

        proposals = await planner.identify_gaps()

        if not proposals:
            logger.success("System is up to date. No evolution required.")
            return

        ordered = sorted(
            proposals,
            key=lambda p: p.get("score", {}).get("confidence", 0.0),
            reverse=True,
        )
        for proposal in ordered:
            await self._process_proposal(proposal)

        logger.info("------- Evolution Cycle Complete -------")

    async def _process_proposal(self, proposal: dict):
        action = proposal["action"]
        target = proposal["target"]
        spec = proposal["spec"]
        score = proposal.get("score", {})
        proposal_source = proposal.get("proposal_source", "reference")

        logger.info(f"Processing proposal: {action} {target}")

        query = """
            INSERT INTO evolution_queue (action, target_component, spec_definition, status)
            VALUES ($1, $2, $3, 'pending')
            RETURNING id
        """
        task_id = await db.fetchval(query, action, target, json.dumps(spec))
        await db.execute(
            "UPDATE evolution_queue SET test_output = $1 WHERE id = $2",
            json.dumps({"maturity": MATURITY_EXPERIMENTAL}),
            task_id,
        )
        attempt_id = await observability.start_attempt(
            proposal_source, target, proposal, score
        )

        try:
            await observability.mark_stage(
                attempt_id, "plan", "ok", check_name="planner.scorecard"
            )
            skill_def = SkillDefinition(**spec)
            security_definition_gate = security_gate.validate_skill_definition(
                skill_def
            )
            if not security_definition_gate.passed:
                reason = "; ".join(security_definition_gate.reasons)
                await db.execute(
                    "UPDATE evolution_queue SET status = 'failed', error_message = $1 WHERE id = $2",
                    reason,
                    task_id,
                )
                await observability.mark_stage(
                    attempt_id,
                    "security_definition",
                    "failed",
                    check_name="security.command_policy",
                    failure_reason=reason,
                )
                await observability.finish_attempt(attempt_id, "failed", reason)
                return

            tool_capabilities = {}
            for tool_def in skill_def.tools:
                arch_decision = await architect.analyze_for_refactoring(tool_def)

                if arch_decision["action"] == "link_existing":
                    tool_def.executor_config["dependency"] = arch_decision["provider"]
                    logger.info(
                        f"Linking {tool_def.name} to existing provider {arch_decision['provider']}"
                    )
                    if arch_decision.get("capability"):
                        tool_capabilities[tool_def.name] = arch_decision["capability"]
                elif arch_decision["action"] == "create_shared":
                    core_skill = self._generate_core_skill(arch_decision["capability"])
                    await staging_manager.propose_skill(core_skill)
                    tool_def.executor_config["dependency"] = core_skill.name
                    tool_capabilities[tool_def.name] = arch_decision["capability"]

            should_autopromote, adoption_reason = self._should_autopromote(score)
            if not should_autopromote:
                await db.execute(
                    """
                    UPDATE evolution_queue
                    SET status = 'review_required',
                        error_message = $1,
                        test_output = $2,
                        updated_at = NOW()
                    WHERE id = $3
                    """,
                    adoption_reason,
                    json.dumps({"maturity": MATURITY_STAGING_APPROVED, "score": score}),
                    task_id,
                )
                await observability.mark_stage(
                    attempt_id,
                    "adoption_policy",
                    "review_required",
                    check_name="policy.phase_gate",
                    failure_reason=adoption_reason,
                )
                await observability.finish_attempt(
                    attempt_id, "review_required", adoption_reason
                )
                return

            await db.execute(
                "UPDATE evolution_queue SET status = 'staging' WHERE id = $1", task_id
            )
            await observability.mark_stage(
                attempt_id, "staging", "started", check_name="staging.begin"
            )

            result = await staging_manager.propose_skill(
                skill_def,
                pre_promote_check=self._run_pre_promote_security_checks,
            )

            if result["status"] == "deployed":
                await observability.mark_stage(
                    attempt_id,
                    "staging",
                    "ok",
                    check_name="staging.syntax_and_security",
                )
                async with db.pool.acquire() as connection:
                    async with connection.transaction():
                        await connection.execute(
                            """
                            UPDATE evolution_queue SET status = 'deployed', test_output = $1 WHERE id = $2
                        """,
                            "Successfully deployed.",
                            task_id,
                        )

                        record_definition = skill_def.model_dump()
                        record_definition["maturity"] = MATURITY_PRODUCTION_APPROVED
                        record_definition["score"] = score
                        record_definition["delivery_plan"] = proposal.get(
                            "delivery_plan", {}
                        )

                        await connection.execute(
                            """
                            INSERT INTO system_model (component_type, component_name, definition_json, source_layer)
                            VALUES ('skill', $1, $2, 'generated')
                            ON CONFLICT (component_type, component_name)
                            DO UPDATE SET definition_json = $2,
                                          source_layer = 'generated',
                                          updated_at = NOW()
                        """,
                            skill_def.name,
                            json.dumps(record_definition),
                        )

                        await self._wire_capability_graph(connection, skill_def)

                        for tool_def in skill_def.tools:
                            dependency = tool_def.executor_config.get("dependency")
                            if dependency:
                                capability_tag = tool_capabilities.get(
                                    tool_def.name, "shared"
                                )
                                await connection.execute(
                                    """
                                    INSERT INTO capability_graph (provider_skill, capability_tag, consumer_skill)
                                    VALUES ($1, $2, $1)
                                    ON CONFLICT DO NOTHING
                                """,
                                    dependency,
                                    capability_tag,
                                )
                await observability.finish_attempt(attempt_id, "deployed")
            else:
                await db.execute(
                    """
                    UPDATE evolution_queue SET status = 'failed', error_message = $1 WHERE id = $2
                """,
                    result.get("reason", "Unknown error"),
                    task_id,
                )
                await observability.mark_stage(
                    attempt_id,
                    "staging",
                    "failed",
                    check_name="staging.syntax_and_security",
                    failure_reason=result.get("reason", "Unknown error"),
                )
                await observability.finish_attempt(
                    attempt_id, "failed", result.get("reason", "Unknown error")
                )

        except Exception as e:
            logger.error(f"Evolution task failed: {e}")
            await db.execute(
                "UPDATE evolution_queue SET status = 'error', error_message = $1 WHERE id = $2",
                str(e),
                task_id,
            )
            await observability.finish_attempt(attempt_id, "error", str(e))

    def _should_autopromote(self, score: dict) -> tuple[bool, str]:
        """Apply staged-adoption policy gates by configured phase."""

        phase = (settings.evolution_phase or "phase1").lower()
        risk = float(score.get("risk", 1.0))
        confidence = float(score.get("confidence", 0.0))

        if phase == "phase1":
            return False, "Phase 1 requires human review for all proposals."
        if phase == "phase2":
            if risk <= 0.35 and confidence >= 0.60:
                return True, "Low-risk proposal approved for autonomous promotion."
            return (
                False,
                f"Phase 2 blocks promotion (risk={risk}, confidence={confidence}).",
            )
        if phase == "phase3":
            if risk <= 0.80 and confidence >= 0.30:
                return True, "Phase 3 policy gate passed."
            return (
                False,
                f"Phase 3 policy denied promotion (risk={risk}, confidence={confidence}).",
            )
        return False, f"Unknown evolution phase '{phase}'."

    async def _run_pre_promote_security_checks(self, generated_skill_path):
        """Execute red-team static checks on staged generated code."""

        gate_result = security_gate.scan_generated_directory(generated_skill_path)
        return {
            "passed": gate_result.passed,
            "reasons": gate_result.reasons,
            "checks_run": gate_result.checks_run,
        }

    def _generate_core_skill(self, capability: str) -> SkillDefinition:
        from nanobot.meta.schemas import ExecutorType
        import re

        normalized_capability = (
            re.sub(r"[^a-z0-9]+", "-", capability.lower()).strip("-") or "shared"
        )
        skill_name = f"core-{normalized_capability}"
        tool_name = f"{normalized_capability.replace('-', '_')}_handler"
        return SkillDefinition(
            name=skill_name,
            description=f"Shared {capability} capability",
            tools=[
                ToolDefinition(
                    name=tool_name,
                    description=f"Handles {capability} operations",
                    executor_type=ExecutorType.INTERNAL,
                    executor_config={},
                )
            ],
        )

    async def _wire_capability_graph(self, connection, skill_def: SkillDefinition):
        """
        Updates the Context Graph to reflect the new skill's dependencies.
        """
        skill_node_id = await self._get_or_create_node(
            connection, "skill", skill_def.name, {"desc": skill_def.description}
        )

        for tool in skill_def.tools:
            tool_node_id = await self._get_or_create_node(
                connection, "tool", tool.name, {"executor": tool.executor_type.value}
            )
            await self._add_edge(connection, skill_node_id, tool_node_id, "OWNS")

            if "dependency" in tool.executor_config:
                dep = tool.executor_config["dependency"]
                dep_node_id = await self._get_or_create_node(
                    connection, "skill", dep, {}
                )
                await self._add_edge(
                    connection, tool_node_id, dep_node_id, "DEPENDS_ON"
                )
                logger.info(f"Graph wired: {tool.name} DEPENDS_ON {dep}")

    async def _get_or_create_node(
        self, connection, node_type: str, external_id: str, properties: dict
    ):
        return await connection.fetchval(
            """
            INSERT INTO context_nodes (node_type, external_id, properties)
            VALUES ($1, $2, $3)
            ON CONFLICT (node_type, external_id)
            DO UPDATE SET properties = EXCLUDED.properties, updated_at = NOW()
            RETURNING id
            """,
            node_type,
            external_id,
            json.dumps(properties or {}),
        )

    async def _add_edge(
        self, connection, source_node_id: int, target_node_id: int, relationship: str
    ):
        await connection.execute(
            """
            INSERT INTO context_edges (source_node_id, target_node_id, relationship, properties)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (source_node_id, target_node_id, relationship) DO NOTHING
            """,
            source_node_id,
            target_node_id,
            relationship,
            json.dumps({}),
        )


evolution_engine = EvolutionEngine()
