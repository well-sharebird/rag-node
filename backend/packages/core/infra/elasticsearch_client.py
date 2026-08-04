"""
Elasticsearch client for full-text search (BM25)
"""
from elasticsearch import AsyncElasticsearch
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class ElasticsearchClient:
    """Elasticsearch client for BM25 full-text search"""

    def __init__(
        self,
        host: str = None,
        port: int = None,
        index_prefix: str = None,
    ):
        from packages.core.config import settings
        self.host = host or settings.es_host
        self.port = port or settings.es_port
        self.index_prefix = index_prefix or settings.es_index_prefix
        self._client: Optional[AsyncElasticsearch] = None

    async def connect(self):
        """Connect to Elasticsearch"""
        if self._client is None:
            self._client = AsyncElasticsearch(
                hosts=[f"http://{self.host}:{self.port}"],
                request_timeout=30
            )
            # Test connection
            try:
                info = await self._client.info()
                logger.info(f"Connected to Elasticsearch: {info['version']['number']}")
            except Exception as e:
                logger.warning(f"Elasticsearch connection failed: {e}")
                self._client = None

    async def close(self):
        """Close Elasticsearch connection"""
        if self._client:
            await self._client.close()
            self._client = None

    @property
    def client(self) -> Optional[AsyncElasticsearch]:
        return self._client

    async def create_index(self, index_name: str, mappings: Dict[str, Any]):
        """Create an index with mappings"""
        if not self._client:
            await self.connect()
        if not self._client:
            return

        full_index_name = f"{self.index_prefix}_{index_name}"
        try:
            if not await self._client.indices.exists(index=full_index_name):
                await self._client.indices.create(
                    index=full_index_name,
                    mappings=mappings
                )
                logger.info(f"Created index: {full_index_name}")
        except Exception as e:
            logger.error(f"Failed to create index {full_index_name}: {e}")

    async def index_document(
        self,
        index_name: str,
        doc_id: str,
        document: Dict[str, Any]
    ):
        """Index a document"""
        if not self._client:
            return
        full_index_name = f"{self.index_prefix}_{index_name}"
        try:
            await self._client.index(
                index=full_index_name,
                id=doc_id,
                document=document
            )
        except Exception as e:
            logger.error(f"Failed to index document: {e}")

    async def search(
        self,
        index_name: str,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        size: int = 10
    ) -> List[Dict[str, Any]]:
        """
        BM25 full-text search

        Args:
            index_name: Index name
            query: Search query
            filters: Optional filters
            size: Result size

        Returns:
            List of matching documents
        """
        if not self._client:
            return []

        full_index_name = f"{self.index_prefix}_{index_name}"

        # Build BM25 query
        es_query = {
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": ["title^2", "content", "keywords"],
                    "type": "best_fields"
                }
            },
            "size": size
        }

        # Add filters
        if filters:
            es_query["query"] = {
                "bool": {
                    "must": es_query["query"],
                    "filter": [{"term": {k: v}} for k, v in filters.items()]
                }
            }

        try:
            response = await self._client.search(
                index=full_index_name,
                body=es_query
            )
            return [
                {
                    "id": hit["_id"],
                    "score": hit["_score"],
                    "source": hit["_source"]
                }
                for hit in response["hits"]["hits"]
            ]
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    async def hybrid_search(
        self,
        index_name: str,
        query: str,
        vector_ids: Optional[List[str]] = None,
        size: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search: BM25 + vector boost

        Args:
            index_name: Index name
            query: Text query
            vector_ids: Optional list of IDs from vector search
            size: Result size

        Returns:
            Reranked results
        """
        results = await self.search(index_name, query, size=size * 2)

        if vector_ids:
            # Boost documents that appear in both results
            vector_set = set(vector_ids)
            for doc in results:
                if doc["id"] in vector_set:
                    doc["score"] *= 1.5

            # Sort by boosted score
            results.sort(key=lambda x: x["score"], reverse=True)

        return results[:size]

    async def delete_index(self, index_name: str):
        """Delete an index"""
        if not self._client:
            return
        full_index_name = f"{self.index_prefix}_{index_name}"
        try:
            await self._client.indices.delete(index=full_index_name)
        except Exception:
            pass

    async def get_stats(self) -> Dict[str, Any]:
        """Get Elasticsearch stats"""
        if not self._client:
            return {"status": "disconnected"}
        try:
            health = await self._client.cluster.health()
            stats = await self._client.indices.stats()
            return {
                "status": health.get("status", "unknown"),
                "cluster": health.get("cluster_name", ""),
                "active_shards": health.get("active_shards", 0),
                "docs_count": stats.get("_all", {}).get("total", {}).get("docs", {}).get("count", 0)
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}


# Global instance
_es_client: Optional[ElasticsearchClient] = None


def get_elasticsearch_client() -> ElasticsearchClient:
    """Get or create Elasticsearch client"""
    global _es_client
    if _es_client is None:
        _es_client = ElasticsearchClient()
    return _es_client


async def initialize_elasticsearch():
    """Initialize Elasticsearch client"""
    client = get_elasticsearch_client()
    await client.connect()
    return client
