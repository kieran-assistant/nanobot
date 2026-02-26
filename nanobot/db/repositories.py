# nanobot/db/repositories.py
from datetime import datetime
from nanobot.db.engine import db
from typing import Optional, Dict, Any
import json

class SystemModelRepository:
    """Manages the system's self-knowledge."""

    @staticmethod
    async def register_component(comp_type: str, name: str, definition: Dict, layer: str, file_hash: str = None):
        query = """
            INSERT INTO system_model (component_type, component_name, definition_json, source_layer, implementation_hash)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (component_type, component_name) 
            DO UPDATE SET definition_json = $3, implementation_hash = $5, updated_at = NOW()
        """
        await db.execute(query, comp_type, name, json.dumps(definition), layer, file_hash)

    @staticmethod
    async def get_component(comp_type: str, name: str) -> Optional[Dict]:
        query = "SELECT * FROM system_model WHERE component_type = $1 AND component_name = $2"
        row = await db.fetchrow(query, comp_type, name)
        return dict(row) if row else None

class EvolutionQueueRepository:
    """Manages the evolution tasks."""

    @staticmethod
    async def create_task(action: str, target: str, spec: Dict):
        query = """
            INSERT INTO evolution_queue (action, target_component, spec_definition, status)
            VALUES ($1, $2, $3, 'pending')
            RETURNING id
        """
        return await db.fetchval(query, action, target, json.dumps(spec))

    @staticmethod
    async def get_pending_tasks():
        query = "SELECT * FROM evolution_queue WHERE status = 'pending' ORDER BY created_at ASC"
        rows = await db.fetch(query)
        return [dict(row) for row in rows]

    @staticmethod
    async def update_task_status(task_id: str, status: str, output: str = None):
        query = """
            UPDATE evolution_queue SET status = $2, test_output = $3, updated_at = NOW()
            WHERE id = $1
        """
        await db.execute(query, task_id, status, output)
