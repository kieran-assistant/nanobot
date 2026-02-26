# nanobot/meta/evolution_engine.py
from nanobot.meta.introspector import introspector
from nanobot.meta.planner import planner
from nanobot.meta.staging_manager import staging_manager
from nanobot.meta.schemas import SkillDefinition, ToolDefinition
from nanobot.meta.architect import architect
from nanobot.runtime.graph_manager import graph
from nanobot.db.engine import db
from loguru import logger
import json

class EvolutionEngine:
    async def run_cycle(self):
        logger.info("------- Starting Evolution Cycle -------")

        await introspector.scan_reference_repo("repos/reference", "GitNexus")

        proposals = await planner.identify_gaps()

        if not proposals:
            logger.success("System is up to date. No evolution required.")
            return

        for proposal in proposals:
            await self._process_proposal(proposal)

        logger.info("------- Evolution Cycle Complete -------")

    async def _process_proposal(self, proposal: dict):
        action = proposal['action']
        target = proposal['target']
        spec = proposal['spec']

        logger.info(f"Processing proposal: {action} {target}")

        query = """
            INSERT INTO evolution_queue (action, target_component, spec_definition, status)
            VALUES ($1, $2, $3, 'pending')
            RETURNING id
        """
        task_id = await db.fetchval(query, action, target, json.dumps(spec))

        try:
            skill_def = SkillDefinition(**spec)
            
            for tool_def in skill_def.tools:
                arch_decision = await architect.analyze_for_refactoring(tool_def)
                
                if arch_decision["action"] == "link_existing":
                    tool_def.executor_config["dependency"] = arch_decision["provider"]
                    logger.info(f"Linking {tool_def.name} to existing provider {arch_decision['provider']}")
                    
                elif arch_decision["action"] == "create_shared":
                    core_skill = self._generate_core_skill(arch_decision["capability"])
                    await staging_manager.propose_skill(core_skill)
                    tool_def.executor_config["dependency"] = core_skill.name
            
            await db.execute("UPDATE evolution_queue SET status = 'staging' WHERE id = $1", task_id)
            
            result = await staging_manager.propose_skill(skill_def)

            if result['status'] == 'deployed':
                await db.execute("""
                    UPDATE evolution_queue SET status = 'deployed', test_output = $1 WHERE id = $2
                """, "Successfully deployed.", task_id)
                
                await db.execute("""
                    INSERT INTO system_model (component_type, component_name, definition_json, source_layer)
                    VALUES ('skill', $1, $2, 'generated')
                """, skill_def.name, json.dumps(skill_def.model_dump()))
                
                # Wire the Context Graph
                await self._wire_capability_graph(skill_def)
                
                for tool_def in skill_def.tools:
                    if tool_def.executor_config.get("dependency"):
                        await architect.register_capability(tool_def.executor_config["dependency"], arch_decision.get("capability", "shared"))
                
            else:
                await db.execute("""
                    UPDATE evolution_queue SET status = 'failed', error_message = $1 WHERE id = $2
                """, result.get('reason', 'Unknown error'), task_id)

        except Exception as e:
            logger.error(f"Evolution task failed: {e}")
            await db.execute("UPDATE evolution_queue SET status = 'error', error_message = $1 WHERE id = $2", str(e), task_id)

    def _generate_core_skill(self, capability: str) -> SkillDefinition:
        from nanobot.meta.schemas import ExecutorType
        return SkillDefinition(
            name=f"core_{capability}",
            description=f"Shared {capability} capability",
            tools=[
                ToolDefinition(
                    name=f"{capability}_handler",
                    description=f"Handles {capability} operations",
                    executor_type=ExecutorType.INTERNAL,
                    executor_config={}
                )
            ]
        )

    async def _wire_capability_graph(self, skill_def: SkillDefinition):
        """
        Updates the Context Graph to reflect the new skill's dependencies.
        """
        for tool in skill_def.tools:
            await graph.get_or_create_node("skill", skill_def.name, {"desc": skill_def.description})
            await graph.get_or_create_node("tool", tool.name, {"executor": tool.executor_type.value})
            await graph.add_edge("skill", skill_def.name, "tool", tool.name, "OWNS")
            
            if "dependency" in tool.executor_config:
                dep = tool.executor_config["dependency"]
                await graph.add_edge("tool", tool.name, "skill", dep, "DEPENDS_ON")
                logger.info(f"Graph wired: {tool.name} DEPENDS_ON {dep}")

evolution_engine = EvolutionEngine()
