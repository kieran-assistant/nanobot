# nanobot/meta/metaclasses.py
from abc import ABCMeta
from typing import Dict, Type
from pydantic import BaseModel, Field
from loguru import logger

class ToolSchema(BaseModel):
    """Schema definition for a tool, used for validation and DB storage."""
    name: str
    description: str = "No description provided."
    parameters: Dict = Field(default_factory=dict)

class ToolMeta(ABCMeta):
    """
    Metaclass for automatically registering tools.
    Ensures every tool has a 'tool_name', 'schema', and 'execute' method.
    """
    _registry: Dict[str, Type] = {}

    def __new__(mcs, name, bases, namespace):
        cls = super().__new__(mcs, name, bases, namespace)
        
        # Do not register the base class itself
        if name == "BaseTool" or not namespace.get('tool_name'):
            return cls
            
        tool_name = namespace.get('tool_name')
        
        # Validation
        if not hasattr(cls, 'execute'):
            raise TypeError(f"Tool '{name}' must implement an 'execute' method.")
            
        # Auto-generate schema if not present
        if not hasattr(cls, 'schema'):
             cls.schema = ToolSchema(name=tool_name)
        
        # Register in local memory (Global registry accessible via ToolMeta._registry)
        mcs._registry[tool_name] = cls
        logger.debug(f"[Meta] Registered Tool: {tool_name}")
        
        return cls

    @classmethod
    def get_registry(mcs):
        return mcs._registry
