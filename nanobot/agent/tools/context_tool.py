# nanobot/agent/tools/context_tool.py
from nanobot.meta.metaclasses import ToolMeta
from nanobot.runtime.graph_manager import graph

class ContextQueryTool(metaclass=ToolMeta):
    tool_name = "query_world_model"
    description = "Query the context graph to understand relationships between entities (skills, users, sessions)."
    parameters_schema = {
        "type": "object",
        "properties": {
            "entity_type": {"type": "string", "description": "Type of entity (e.g., 'skill', 'user')"},
            "entity_id": {"type": "string", "description": "ID of the entity"},
            "relationship": {"type": "string", "description": "Relationship to traverse (e.g., 'DEPENDS_ON', 'CREATED_BY')"}
        },
        "required": ["entity_type", "entity_id"]
    }

    async def execute(self, entity_type: str, entity_id: str, relationship: str = None):
        neighbors = await graph.get_neighbors(entity_type, entity_id, relationship)
        
        context = []
        for n in neighbors:
            context.append(f"- {n['relationship']} -> {n['node_type']}:{n['external_id']}")
            
        return {
            "result": "\n".join(context) or "No relationships found.",
            "raw_data": [dict(n) for n in neighbors]
        }
