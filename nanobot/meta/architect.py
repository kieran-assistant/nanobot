# nanobot/meta/architect.py
from loguru import logger
from nanobot.db.engine import db
from nanobot.meta.schemas import ToolDefinition, SkillDefinition, ParameterSchema, ExecutorType

class Architect:
    """
    Analyzes proposed tools to find shared requirements (e.g., Auth).
    Refactors existing tools to use shared capabilities.
    """

    async def analyze_for_refactoring(self, proposed_tool: ToolDefinition) -> dict:
        keywords = ['auth', 'login', 'connect', 'database', 'db']
        
        required_caps = []
        for kw in keywords:
            if kw in proposed_tool.name or kw in proposed_tool.description:
                required_caps.append(kw)
        
        if not required_caps:
            return {"action": "create_new"}

        for cap in required_caps:
            existing = await db.fetchrow(
                "SELECT provider_skill FROM capability_graph WHERE capability_tag = $1 LIMIT 1",
                cap
            )
            
            if existing:
                logger.info(f"Found existing capability provider for {cap}: {existing['provider_skill']}")
                return {"action": "link_existing", "provider": existing['provider_skill']}
        
        logger.info(f"New shared capability detected: {required_caps}. Proposing extraction.")
        return {"action": "create_shared", "capability": required_caps[0]}

    async def register_capability(self, provider_skill: str, capability_tag: str):
        await db.execute("""
            INSERT INTO capability_graph (provider_skill, capability_tag, consumer_skill)
            VALUES ($1, $2, $1)
            ON CONFLICT DO NOTHING
        """, provider_skill, capability_tag)
        logger.info(f"Registered capability: {provider_skill} provides {capability_tag}")

architect = Architect()
