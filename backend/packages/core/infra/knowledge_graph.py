"""
Knowledge Graph - delegates to Neo4j (no more SQLite).
Thin wrapper around neo4j_client.py to preserve the existing public API.
"""
from typing import List, Dict, Any, Optional
import logging

from packages.core.infra.neo4j_client import Neo4jClient, get_neo4j_client, initialize_neo4j

logger = logging.getLogger("app.core.knowledge_graph")


class KnowledgeGraph:
    """Knowledge graph backed by Neo4j. Delegates to Neo4jClient."""

    def __init__(self):
        self._neo4j: Neo4jClient = get_neo4j_client()
        self._initialized = False

    async def initialize(self):
        if self._initialized:
            return
        await self._neo4j.connect()
        self._initialized = True
        logger.info("KnowledgeGraph initialized (Neo4j)")

    # ==================== Node Operations ====================

    async def create_node(
        self,
        node_id: str,
        label: str,
        properties: Dict[str, Any],
        embedding: Optional[List[float]] = None,
    ) -> str:
        await self.initialize()
        props = {**properties}
        if embedding:
            props["embedding"] = embedding
        await self._neo4j.create_entity(entity_id=node_id, label=label, properties=props)
        return node_id

    async def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        await self.initialize()
        entities = await self._neo4j.find_entities(properties={"id": node_id}, limit=1)
        if entities:
            e = entities[0]
            return {"id": node_id, "label": list(e.labels)[0] if hasattr(e, 'labels') else "Entity", "properties": dict(e)}
        return None

    async def delete_node(self, node_id: str):
        await self.initialize()
        await self._neo4j.delete_entity(node_id)

    async def find_nodes(
        self,
        label: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        await self.initialize()
        entities = await self._neo4j.find_entities(label=label, properties=properties, limit=limit)
        return [{"id": e.get("id", ""), "label": label or "Entity", "properties": e} for e in entities]

    # ==================== Edge Operations ====================

    async def create_edge(
        self,
        edge_id: str,
        source_id: str,
        target_id: str,
        relation: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> str:
        await self.initialize()
        await self._neo4j.create_relationship(
            source_id=source_id, target_id=target_id, relation=relation, properties=properties,
        )
        return edge_id

    async def get_edges(
        self,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        relation: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        await self.initialize()
        results = await self._neo4j.find_relationships(
            source_id=source_id, target_id=target_id, relation=relation,
        )
        return [
            {
                "id": f"{r['source'].get('id','')}_{r['target'].get('id','')}",
                "source_id": r["source"].get("id", ""),
                "target_id": r["target"].get("id", ""),
                "relation": r["relation"],
                "properties": r.get("properties", {}),
            }
            for r in results
        ]

    async def delete_edge(self, edge_id: str):
        await self.initialize()
        # Neo4j doesn't have edge IDs; edges are identified by source-relation-target
        # For compatibility, run raw query to delete by matching id property
        try:
            await self._neo4j.run_query(
                "MATCH ()-[r {id: $id}]->() DELETE r", {"id": edge_id}
            )
        except Exception:
            pass

    # ==================== Graph Queries ====================

    async def get_neighbors(
        self,
        node_id: str,
        direction: str = "both",
        relation: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        await self.initialize()
        neo_direction = "outgoing" if direction == "outgoing" else ("incoming" if direction == "incoming" else "both")
        results = await self._neo4j.get_neighbors(node_id, direction=neo_direction, limit=limit)

        neighbors = []
        for r in results:
            if relation and r.get("relation") != relation:
                continue
            neighbors.append({
                "id": r["target"].get("id", "") if direction != "incoming" else r["source"].get("id", ""),
                "label": "Entity",
                "properties": r["target"] if direction != "incoming" else r["source"],
                "relation": r["relation"],
            })
        return neighbors

    async def find_path(
        self,
        start_id: str,
        end_id: str,
        max_depth: int = 5,
    ) -> Optional[List[Dict[str, Any]]]:
        await self.initialize()
        query = f"""
            MATCH path = shortestPath((a {{id: $start_id}})-[*1..{max_depth}]-(b {{id: $end_id}}))
            RETURN path LIMIT 1
        """
        results = await self._neo4j.run_query(query, {"start_id": start_id, "end_id": end_id})
        if results and results[0]:
            path = results[0].get("path", [])
            return list(path) if path else []
        return None

    async def get_stats(self) -> Dict[str, Any]:
        await self.initialize()
        return await self._neo4j.get_stats()


# Global instance
_kg: Optional[KnowledgeGraph] = None


def get_knowledge_graph() -> KnowledgeGraph:
    global _kg
    if _kg is None:
        _kg = KnowledgeGraph()
    return _kg


async def initialize_knowledge_graph():
    kg = get_knowledge_graph()
    await kg.initialize()
    return kg
