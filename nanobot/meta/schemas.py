# nanobot/meta/schemas.py
from pydantic import BaseModel, Field, field_validator
from typing import Literal, List, Dict, Any, Optional
from enum import Enum

class ExecutorType(str, Enum):
    SCRIPT = "script"
    HTTP = "http"
    INTERNAL = "internal"

class ParameterSchema(BaseModel):
    name: str
    type: Literal["string", "integer", "number", "boolean", "array", "object"]
    description: str
    required: bool = True
    default: Any = None

class ToolDefinition(BaseModel):
    name: str = Field(..., pattern=r'^[a-z_][a-z0-9_]*$')
    description: str
    parameters: List[ParameterSchema] = []
    executor_type: ExecutorType = ExecutorType.SCRIPT
    executor_config: Dict[str, Any] = {}

    class Config:
        extra = "forbid"

class SkillDefinition(BaseModel):
    name: str = Field(..., pattern=r'^[a-z][a-z0-9-]*$')
    version: str = "0.1.0"
    description: str
    tools: List[ToolDefinition] = []
    prompts: Dict[str, str] = {}

    class Config:
        extra = "forbid"
