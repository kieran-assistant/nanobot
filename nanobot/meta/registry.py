# nanobot/meta/registry.py
from nanobot.meta.metaclasses import ToolMeta
from nanobot.db.repositories import SystemModelRepository
from loguru import logger
import hashlib

class Registry:
    def __init__(self):
        self.tools = ToolMeta.get_registry()

    async def sync_to_database(self):
        """
        Iterates through all registered tools and syncs their definitions
        to the system_model table.
        """
        logger.info("Syncing tool registry to database...")
        for tool_name, tool_cls in self.tools.items():
            # Create a hash of the class name/module to detect changes
            impl_hash = hashlib.sha256(f"{tool_cls.__module__}.{tool_name}".encode()).hexdigest()
            
            definition = {
                "name": tool_name,
                "description": getattr(tool_cls, 'description', 'N/A'),
                "parameters": getattr(tool_cls, 'parameters_schema', {})
            }
            
            await SystemModelRepository.register_component(
                comp_type="tool",
                name=tool_name,
                definition=definition,
                layer="primitive_kernel", # Identifying this as core code
                file_hash=impl_hash
            )
        logger.info(f"Registry sync complete. {len(self.tools)} tools registered.")

# Global Registry Instance
registry = Registry()
