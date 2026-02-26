# nanobot/meta/planner.py
from loguru import logger
from nanobot.db.engine import db
from nanobot.meta.schemas import SkillDefinition, ToolDefinition, ParameterSchema, ExecutorType
from nanobot.config import settings
import json
from typing import Any, Dict
import re

class Planner:
    async def identify_gaps(self):
        logger.info("Analyzing system for evolution gaps...")
        
        existing_tools = await db.fetch("SELECT component_name FROM system_model WHERE component_type = 'tool'")
        existing_names = {t['component_name'] for t in existing_tools}
        existing_skills = await db.fetch("SELECT component_name FROM system_model WHERE component_type = 'skill'")
        existing_skill_names = {s["component_name"] for s in existing_skills}
        reserved_skill_names = set(existing_skill_names)
        
        references = await db.fetch("SELECT * FROM reference_patterns")
        
        proposals = []
        
        for ref in references:
            ref_name = ref['pattern_name']
            ref_def = self._decode_jsonb(ref['definition'])
            tool_name = self._normalize_tool_name(ref_name or "")
            
            if tool_name not in existing_names:
                logger.info(f"Gap found: Missing capability '{tool_name}'")

                score = await self._score_proposal(tool_name, ref_def)
                skill_name = self._build_unique_skill_name(f"gen-{tool_name}", reserved_skill_names)
                delivery_plan = self._build_delivery_plan(tool_name, skill_name, ref_def, score)
                proposal = self._create_proposal(
                    tool_name,
                    skill_name,
                    ref_def,
                    score,
                    delivery_plan,
                    ref.get("source_repo", "reference"),
                )
                proposals.append(proposal)
                
        return proposals

    def _create_proposal(
        self,
        name: str,
        skill_name: str,
        ref_def: dict,
        score: dict,
        delivery_plan: dict,
        proposal_source: str,
    ) -> dict:
        params = []
        for arg in ref_def.get('args', []):
            if arg == 'self': continue
            params.append(ParameterSchema(
                name=arg,
                type="string",
                description=f"Parameter {arg}",
                required=True
            ))

        tool = ToolDefinition(
            name=name,
            description=ref_def.get('docstring', 'Generated from reference'),
            parameters=params,
            executor_type=ExecutorType.SCRIPT,
            executor_config={"command": f"echo 'Implementation required for {name}'"}
        )
        
        return {
            "action": "CREATE",
            "target": name,
            "proposal_source": proposal_source,
            "score": score,
            "delivery_plan": delivery_plan,
            "spec": SkillDefinition(
                name=skill_name,
                description=f"Auto-generated skill for {name}",
                tools=[tool]
            ).model_dump()
        }

    async def _score_proposal(self, name: str, ref_def: Dict[str, Any]) -> Dict[str, Any]:
        """Score a proposal using AST, dependency, usage, failure, and operator-priority signals."""

        dependency_impact = len(ref_def.get("imports", [])) + len(ref_def.get("called_functions", []))
        ast_signature = ref_def.get("signature_hash", "")
        signature_status = "present" if ast_signature else "missing"
        # Missing signatures are treated as neutral (not automatically low novelty).
        signature_novelty = 1.0 if signature_status == "present" else 0.8

        usage_frequency = await self._usage_frequency(name)
        failure_history = await self._failure_history(name)
        operator_priority = await self._operator_priority(name)

        blast_radius = min(1.0, dependency_impact / 10.0)
        risk = min(1.0, (blast_radius * 0.5) + (failure_history * 0.3) + ((1.0 - signature_novelty) * 0.2))
        confidence = max(0.0, min(1.0, (usage_frequency * 0.4) + (signature_novelty * 0.3) + (operator_priority * 0.3) - (failure_history * 0.2)))

        return {
            "risk": round(risk, 4),
            "blast_radius": round(blast_radius, 4),
            "confidence": round(confidence, 4),
            "dependency_impact": dependency_impact,
            "signals": {
                "ast_signature": ast_signature,
                "ast_signature_status": signature_status,
                "usage_frequency": usage_frequency,
                "failure_history": failure_history,
                "operator_priority": operator_priority,
            },
        }

    def _build_delivery_plan(self, name: str, skill_name: str, ref_def: Dict[str, Any], score: Dict[str, Any]) -> Dict[str, Any]:
        """Produce structured artifacts expected for high-quality generated changes."""

        parameters = [arg for arg in ref_def.get("args", []) if arg != "self"]
        return {
            "patch_plan": [
                {
                    "path": f"nanobot/skills/{skill_name}/tool_{name}.py",
                    "change": "Create generated tool module from schema template.",
                },
                {
                    "path": "nanobot/meta/registry.py",
                    "change": "Register generated capability metadata and maturity state.",
                },
            ],
            "test_plan": [
                {
                    "test_name": f"test_generated_{name}_execution",
                    "target": "tests/test_evolution.py",
                    "coverage": f"Validate execution and parameter behavior for {name}({', '.join(parameters)}).",
                },
                {
                    "test_name": f"test_generated_{name}_security_gate",
                    "target": "tests/test_security_release_gate.py",
                    "coverage": "Validate shell/file policy constraints before promotion.",
                },
            ],
            "migration_plan": [
                {
                    "required": False,
                    "description": "No schema migration required for simple generated skill.",
                }
            ],
            "validation_plan": [
                "Run syntax compile for generated files.",
                "Run security gate checks (threat model + red-team rules).",
                "Run targeted unit tests and evolution regression tests.",
                f"Require review if score.risk={score['risk']} is above policy threshold.",
            ],
        }

    async def _usage_frequency(self, component_name: str) -> float:
        try:
            count = await db.fetchval("SELECT COUNT(*) FROM messages WHERE content ILIKE $1", f"%{component_name}%")
            cap = max(1, int(settings.planner_usage_cap))
            capped = min(float(count or 0), float(cap))
            return round(capped / float(cap), 4)
        except Exception:
            return 0.0

    async def _failure_history(self, component_name: str) -> float:
        try:
            failures = await db.fetchval(
                "SELECT COUNT(*) FROM evolution_queue WHERE target_component = $1 AND status IN ('failed', 'error')",
                component_name,
            )
            capped = min(float(failures or 0), 10.0)
            return round(capped / 10.0, 4)
        except Exception:
            return 0.0

    async def _operator_priority(self, component_name: str) -> float:
        """Read operator priorities if configured; otherwise default neutral priority."""

        try:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS operator_priorities (
                    component_name VARCHAR(255) PRIMARY KEY,
                    priority NUMERIC NOT NULL DEFAULT 0.5
                )
                """
            )
            priority = await db.fetchval(
                "SELECT priority FROM operator_priorities WHERE component_name = $1",
                component_name,
            )
            if priority is None:
                return 0.5
            return max(0.0, min(1.0, float(priority)))
        except Exception:
            return 0.5

    def _decode_jsonb(self, value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            return json.loads(value)
        return {}

    def _normalize_tool_name(self, raw_name: str) -> str:
        """Normalize arbitrary discovered names into ToolDefinition-compatible format."""

        value = (raw_name or "").strip().lower()
        value = re.sub(r"[^a-z0-9_]+", "_", value)
        value = re.sub(r"_+", "_", value).strip("_")
        if not value:
            value = "generated_tool"
        if not re.match(r"^[a-z_]", value):
            value = f"t_{value}"
        return value

    def _normalize_skill_name(self, raw_name: str) -> str:
        """Normalize arbitrary names into SkillDefinition-compatible format."""

        value = (raw_name or "").strip().lower()
        value = value.replace("_", "-")
        value = re.sub(r"[^a-z0-9-]+", "-", value)
        value = re.sub(r"-+", "-", value).strip("-")
        if not value:
            value = "generated-skill"
        if not re.match(r"^[a-z]", value):
            value = f"s-{value}"
        return value

    def _build_unique_skill_name(self, raw_name: str, reserved_skill_names: set[str]) -> str:
        """Generate a collision-safe skill name."""

        base = self._normalize_skill_name(raw_name)
        if base not in reserved_skill_names:
            reserved_skill_names.add(base)
            return base

        counter = 2
        while True:
            candidate = f"{base}-v{counter}"
            if candidate not in reserved_skill_names:
                reserved_skill_names.add(candidate)
                return candidate
            counter += 1

planner = Planner()
