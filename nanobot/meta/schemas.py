# nanobot/meta/schemas.py
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal, List, Dict, Any
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
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., pattern=r'^[a-z_][a-z0-9_]*$')
    description: str
    parameters: List[ParameterSchema] = Field(default_factory=list)
    executor_type: ExecutorType = ExecutorType.SCRIPT
    executor_config: Dict[str, Any] = Field(default_factory=dict)

class SkillDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., pattern=r'^[a-z][a-z0-9-]*$')
    version: str = "0.1.0"
    description: str
    tools: List[ToolDefinition] = Field(default_factory=list)
    prompts: Dict[str, str] = Field(default_factory=dict)
