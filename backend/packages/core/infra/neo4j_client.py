"""
Neo4j client for Knowledge Graph
"""
from neo4j import AsyncGraphDatabase, GraphDatabase
from typing import List, Dict, Any, Optional
import logging
import asyncio

logger = logging.getLogger(__name__)


class Neo4jClient:
    """Neo4j client for Knowledge Graph operations"""

    def __init__(
        self,
        uri: str = None,
        user: str = None,
        password: str = None,
    ):
        from packages.core.config import settings
        self.uri = uri or settings.neo4j_uri
        self.user = user or settings.neo4j_user
        self.password = password or settings.neo4j_password
        self._driver = None

    async def connect(self):
        """Connect to Neo4j"""
        if self._driver is None:
            try:
                self._driver = AsyncGraphDatabase.driver(
                    self.uri,
                    auth=(self.user, self.password)
                )
                # Verify connection
                await self._driver.verify_connectivity()
                logger.info(f"Connected to Neo4j: {self.uri}")
            except Exception as e:
                logger.warning(f"Neo4j connection failed: {e}")
                self._driver = None

    async def close(self):
        """Close Neo4j connection"""
        if self._driver:
            await self._driver.close()
            self._driver = None

    @property
    def driver(self):
        return self._driver

    async def create_entity(
        self,
        entity_id: str,
        label: str,
        properties: Dict[str, Any]
    ):
        """Create a node (entity)"""
        if not self._driver:
            return

        async with self._driver.session() as session:
            props_str = ", ".join(f"{k}: ${k}" for k in properties.keys())
            query = f"""
                MERGE (n:{label} {{id: $id}})
                SET n.{props_str}
                RETURN n
            """
            await session.run(query, id=entity_id, **properties)

    async def create_relationship(
        self,
        source_id: str,
        target_id: str,
        relation: str,
        source_label: str = "Entity",
        target_label: str = "Entity",
        properties: Optional[Dict[str, Any]] = None
    ):
        """Create a relationship between entities"""
        if not self._driver:
            return

        async with self._driver.session() as session:
            props_set = ""
            if properties:
                props_set = "SET r " + ", ".join(f"r.{k} = ${k}" for k in properties.keys())

            query = f"""
                MATCH (a:{source_label} {{id: $source_id}})
                MATCH (b:{target_label} {{id: $target_id}})
                MERGE (a)-[r:{relation}]->(b)
                {props_set}
                RETURN r
            """
            params = {"source_id": source_id, "target_id": target_id}
            if properties:
                params.update(properties)
            await session.run(query, **params)

    async def find_entities(
        self,
        label: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Find entities by label and/or properties"""
        if not self._driver:
            return []

        async with self._driver.session() as session:
            label_str = f":{label}" if label else ""
            where_clause = ""
            params = {"limit": limit}

            if properties:
                where_conditions = " AND ".join(f"n.{k} = ${k}" for k in properties.keys())
                where_clause = f"WHERE {where_conditions}"
                params.update(properties)

            query = f"""
                MATCH (n{label_str})
                {where_clause}
                RETURN n
                LIMIT $limit
            """
            result = await session.run(query, **params)
            return [dict(record["n"]) async for record in result]

    async def find_relationships(
        self,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        relation: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Find relationships"""
        if not self._driver:
            return []

        async with self._driver.session() as session:
            conditions = []
            params = {"limit": limit}

            if source_id:
                conditions.append("a.id = $source_id")
                params["source_id"] = source_id
            if target_id:
                conditions.append("b.id = $target_id")
                params["target_id"] = target_id
            if relation:
                conditions.append("type(r) = $relation")
                params["relation"] = relation

            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

            query = f"""
                MATCH (a)-[r]->(b)
                {where_clause}
                RETURN a, r, b
                LIMIT $limit
            """
            result = await session.run(query, **params)
            return [
                {
                    "source": dict(record["a"]),
                    "relation": record["r"].type,
                    "target": dict(record["b"]),
                    "properties": dict(record["r"])
                }
                async for record in result
            ]

    async def get_neighbors(
        self,
        entity_id: str,
        direction: str = "both",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get neighboring entities

        Args:
            entity_id: Center entity ID
            direction: 'outgoing', 'incoming', or 'both'
            limit: Max results
        """
        if not self._driver:
            return []

        async with self._driver.session() as session:
            if direction == "outgoing":
                query = """
                    MATCH (a {id: $id})-[r]->(b)
                    RETURN a, r, b
                    LIMIT $limit
                """
            elif direction == "incoming":
                query = """
                    MATCH (a)<-[r]-(b {id: $id})
                    RETURN a, r, b
                    LIMIT $limit
                """
            else:  # both
                query = """
                    MATCH (a)-[r]-(b {id: $id})
                    RETURN a, r, b
                    LIMIT $limit
                """

            result = await session.run(query, id=entity_id, limit=limit)
            return [
                {
                    "source": dict(record["a"]),
                    "relation": record["r"].type,
                    "target": dict(record["b"]),
                    "properties": dict(record["r"])
                }
                async for record in result
            ]

    async def delete_entity(self, entity_id: str, label: str = "Entity"):
        """Delete an entity and its relationships"""
        if not self._driver:
            return

        async with self._driver.session() as session:
            await session.run(f"""
                MATCH (n:{label} {{id: $id}})
                DETACH DELETE n
            """, id=entity_id)

    async def run_query(self, query: str, params: Optional[Dict[str, Any]] = None):
        """Run a custom Cypher query"""
        if not self._driver:
            return []

        async with self._driver.session() as session:
            result = await session.run(query, **(params or {}))
            return [dict(record) async for record in result]

    async def get_stats(self) -> Dict[str, Any]:
        """Get graph statistics"""
        if not self._driver:
            return {"status": "disconnected"}

        try:
            async with self._driver.session() as session:
                # Count nodes
                node_result = await session.run("MATCH (n) RETURN count(n) as count")
                node_count = (await node_result.single())["count"]

                # Count relationships
                rel_result = await session.run("MATCH ()-[r]->() RETURN count(r) as count")
                rel_count = (await rel_result.single())["count"]

                # Get labels
                label_result = await session.run("CALL db.labels()")
                labels = [record["label"] async for record in label_result]

                # Get relationship types
                type_result = await session.run("CALL db.relationshipTypes()")
                rel_types = [record["relationshipType"] async for record in type_result]

                return {
                    "status": "connected",
                    "total_nodes": node_count,
                    "total_relationships": rel_count,
                    "labels": labels,
                    "relationship_types": rel_types
                }
        except Exception as e:
            return {"status": "error", "error": str(e)}


# Global instance
_neo4j_client: Optional[Neo4jClient] = None


def get_neo4j_client() -> Neo4jClient:
    """Get or create Neo4j client"""
    global _neo4j_client
    if _neo4j_client is None:
        _neo4j_client = Neo4jClient()
    return _neo4j_client


async def initialize_neo4j():
    """Initialize Neo4j client"""
    client = get_neo4j_client()
    await client.connect()
    return client
