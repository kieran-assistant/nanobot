# nanobot/runtime/graph_manager.py
from nanobot.db.engine import db
from loguru import logger
import json

class GraphManager:
    """Manages the World Model (Context Graph)."""

    async def get_or_create_node(self, node_type: str, external_id: str, properties: dict = None):
        """Ensures a node exists in the graph."""
        query = """
            INSERT INTO context_nodes (node_type, external_id, properties)
            VALUES ($1, $2, $3)
            ON CONFLICT (node_type, external_id) 
            DO UPDATE SET properties = $3, updated_at = NOW()
            RETURNING id
        """
        return await db.fetchval(query, node_type, external_id, json.dumps(properties or {}))

    async def add_edge(self, source_type, source_id, target_type, target_id, relationship, props=None):
        """Creates a relationship between two entities."""
        source = await self.get_or_create_node(source_type, source_id)
        target = await self.get_or_create_node(target_type, target_id)

        query = """
            INSERT INTO context_edges (source_node_id, target_node_id, relationship, properties)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (source_node_id, target_node_id, relationship) DO NOTHING
        """
        await db.execute(query, source, target, relationship, json.dumps(props or {}))
        logger.debug(f"Edge created: {source_type}:{source_id} --[{relationship}]--> {target_type}:{target_id}")

    async def get_neighbors(self, node_type, external_id, relationship_filter=None):
        """Find connected nodes (1-hop traversal)."""
        query = """
            SELECT tn.node_type, tn.external_id, e.relationship, e.properties
            FROM context_nodes src
            JOIN context_edges e ON src.id = e.source_node_id
            JOIN context_nodes tn ON e.target_node_id = tn.id
            WHERE src.node_type = $1 AND src.external_id = $2
            AND ($3::text IS NULL OR e.relationship = $3)
        """
        return await db.fetch(query, node_type, external_id, relationship_filter)

    async def find_path(self, start_type, start_id, end_type, end_id, max_depth=4):
        """Recursive traversal to find a path between entities."""
        query = """
            WITH RECURSIVE search_graph(path, node_id, depth) AS (
                SELECT ARRAY[ARRAY[src.id, tn.id]], tn.id, 1
                FROM context_nodes src
                JOIN context_edges e ON src.id = e.source_node_id
                JOIN context_nodes tn ON e.target_node_id = tn.id
                WHERE src.node_type = $1 AND src.external_id = $2
                
                UNION ALL
                
                SELECT sg.path || ARRAY[e.target_node_id], e.target_node_id, sg.depth + 1
                FROM search_graph sg
                JOIN context_edges e ON sg.node_id = e.source_node_id
                WHERE sg.depth < $5
            )
            SELECT path FROM search_graph sg
            JOIN context_nodes dest ON sg.node_id = dest.id
            WHERE dest.node_type = $3 AND dest.external_id = $4
            LIMIT 1
        """
        return await db.fetch(query, start_type, start_id, end_type, end_id, max_depth)

    async def add_failure_context(self, node_type, node_id, session_id, error_message):
        """Record a failure for later root cause analysis."""
        session_node = await self.get_or_create_node("session", str(session_id))
        node = await self.get_or_create_node(node_type, node_id, {"error": error_message})
        
        await db.execute("""
            INSERT INTO context_edges (source_node_id, target_node_id, relationship, properties)
            VALUES ($1, $2, 'FAILED_IN', $3)
            ON CONFLICT DO NOTHING
        """, node, session_node, json.dumps({"error": error_message}))

graph = GraphManager()
