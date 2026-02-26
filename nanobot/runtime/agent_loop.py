# nanobot/runtime/agent_loop.py
import json
from loguru import logger
from nanobot.db.engine import db
from nanobot.meta.registry import registry
from nanobot.meta.evolution_engine import evolution_engine
from nanobot.runtime.bus import bus, Event

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
            return f"Processed: {prompt}. (Agent Loop Active)"
        except Exception as e:
            return f"LLM Error: {str(e)}"

    async def detect_capability_gap(self, message: str) -> str:
        if "gmail" in message.lower() and "gmail" not in self.tools:
            return "gmail_integration"
        if "weather" in message.lower() and "weather" not in self.tools:
            return "weather_api"
        return None

    async def trigger_evolution(self):
        logger.info("Manual evolution trigger...")
        await evolution_engine.run_cycle()
        return "Evolution cycle complete. I have checked for updates."

agent = AgentLoop()
