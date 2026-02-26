# nanobot/runtime/agent_loop.py
import json
import re
from loguru import logger
from nanobot.db.engine import db
from nanobot.meta.registry import registry
from nanobot.meta.evolution_engine import evolution_engine
from nanobot.runtime.bus import bus, Event
from nanobot.config import settings

class AgentLoop:
    def __init__(self):
        self.history = []
        self.tools = registry.tools
        
    async def process_event(self, event: Event):
        user_message = event.payload.get("content")
        session_id = event.payload.get("session_id", "default")
        
        logger.info(f"Agent received message: {user_message}")
        
        if "update yourself" in user_message.lower() or "check for updates" in user_message.lower():
            response = await self.trigger_evolution()
            await bus.publish("agent.response", {"content": response, "session_id": session_id})
            return

        missing_capability = await self.detect_capability_gap(user_message)
        
        if missing_capability:
            response = f"I don't currently support '{missing_capability}'. Let me check if I can learn that..."
            await bus.publish("agent.response", {"content": response, "session_id": session_id})
            
            await evolution_engine.run_cycle()
            
            return

        response = await self.generate_llm_response(user_message)
        
        await bus.publish("agent.response", {"content": response, "session_id": session_id})

    async def generate_llm_response(self, prompt: str) -> str:
        try:
            if not settings.llm_api_key:
                return "LLM is not configured. Set LLM_API_KEY (and optionally LLM_PROVIDER/LLM_MODEL)."

            if settings.llm_provider.lower() == "openai":
                try:
                    from openai import AsyncOpenAI

                    client_kwargs = {"api_key": settings.llm_api_key}
                    if settings.llm_base_url:
                        client_kwargs["base_url"] = settings.llm_base_url

                    client = AsyncOpenAI(**client_kwargs)
                    response = await client.chat.completions.create(
                        model=settings.llm_model,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=200,
                    )
                    content = response.choices[0].message.content if response.choices else ""
                    return content or "LLM returned an empty response."
                except Exception as exc:
                    return f"LLM Error: {exc}"

            return f"LLM provider '{settings.llm_provider}' is not implemented yet."
        except Exception as e:
            return f"LLM Error: {str(e)}"

    async def detect_capability_gap(self, message: str) -> str:
        available_capabilities = await self._production_ready_capabilities()
        message_terms = self._terms(message)

        # First, detect direct missing references from known production/runtime capabilities.
        for capability in sorted(available_capabilities):
            capability_terms = self._terms(capability)
            if capability_terms and capability_terms.issubset(message_terms):
                return None

        # Then, detect missing capabilities from reference patterns not yet available.
        refs = await db.fetch("SELECT DISTINCT pattern_name FROM reference_patterns WHERE pattern_name IS NOT NULL")
        for row in refs:
            pattern_name = row["pattern_name"]
            if not pattern_name:
                continue
            normalized = self._normalize_capability_name(pattern_name)
            if normalized in available_capabilities:
                continue

            pattern_terms = self._terms(pattern_name)
            if pattern_terms and pattern_terms.issubset(message_terms):
                return normalized
        return None

    async def _production_ready_capabilities(self) -> set[str]:
        """Return runtime-callable capabilities based on maturity policy."""

        capabilities = set(self.tools.keys())
        if not settings.live_mode:
            return capabilities

        rows = await db.fetch(
            """
            SELECT component_name, definition_json
            FROM system_model
            WHERE component_type = 'skill'
            """
        )
        production_ready = set(capabilities)
        for row in rows:
            definition = row["definition_json"] or {}
            if isinstance(definition, str):
                try:
                    definition = json.loads(definition)
                except Exception:
                    definition = {}

            if definition.get("maturity") == "production-approved":
                production_ready.add(row["component_name"])

        return production_ready

    def _terms(self, text: str) -> set[str]:
        return {token for token in re.split(r"[^a-z0-9]+", text.lower()) if token}

    def _normalize_capability_name(self, name: str) -> str:
        value = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")
        if not value:
            value = "unknown_capability"
        if not re.match(r"^[a-z_]", value):
            value = f"cap_{value}"
        return value

    async def trigger_evolution(self):
        logger.info("Manual evolution trigger...")
        await evolution_engine.run_cycle()
        return "Evolution cycle complete. I have checked for updates."

agent = AgentLoop()
