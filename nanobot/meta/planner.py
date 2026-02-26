# nanobot/meta/planner.py
from loguru import logger
from nanobot.db.engine import db
from nanobot.meta.schemas import SkillDefinition, ToolDefinition, ParameterSchema, ExecutorType
import json

class Planner:
    async def identify_gaps(self):
        logger.info("Analyzing system for evolution gaps...")
        
        existing_tools = await db.fetch("SELECT component_name FROM system_model WHERE component_type = 'tool'")
        existing_names = {t['component_name'] for t in existing_tools}
        
        references = await db.fetch("SELECT * FROM reference_patterns")
        
        proposals = []
        
        for ref in references:
            ref_name = ref['pattern_name']
            ref_def = json.loads(ref['definition'])
            
            if ref_name not in existing_names:
                logger.info(f"Gap found: Missing capability '{ref_name}'")
                
                proposal = self._create_proposal(ref_name, ref_def)
                proposals.append(proposal)
                
        return proposals

    def _create_proposal(self, name: str, ref_def: dict) -> dict:
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
            "spec": SkillDefinition(
                name=f"gen_{name}",
                description=f"Auto-generated skill for {name}",
                tools=[tool]
            ).model_dump()
        }

planner = Planner()
