"""
Full-Text Search Engine - delegates to Elasticsearch (no more SQLite FTS5).
"""
import json
from typing import List, Dict, Any, Optional
import logging

from app.core.elasticsearch_client import ElasticsearchClient, get_elasticsearch_client, initialize_elasticsearch

logger = logging.getLogger("app.core.fts_engine")


class FTSEngine:
    """Full-text search engine backed by Elasticsearch BM25."""

    def __init__(self):
        self._es: ElasticsearchClient = get_elasticsearch_client()
        self._initialized = False
        self._index_name = "rag_default"

    async def initialize(self):
        if self._initialized:
            return
        await self._es.connect()
        if self._es.client:
            # Ensure default index exists
            mappings = {
                "properties": {
                    "title": {"type": "text", "analyzer": "standard"},
                    "content": {"type": "text", "analyzer": "standard"},
                    "metadata": {"type": "object"},
                    "created_at": {"type": "date"},
                }
            }
            await self._es.create_index(self._index_name, mappings)
        self._initialized = True
        logger.info("FTSEngine initialized (Elasticsearch)")

    def configure(self, index_name: str = "rag_default"):
        """Set the ES index name."""
        self._index_name = index_name

    async def index_document(
        self, doc_id: str, title: str, content: str, metadata: Dict[str, Any]
    ):
        await self.initialize()
        await self._es.index_document(
            self._index_name,
            doc_id,
            {
                "doc_id": doc_id,
                "title": title,
                "content": content,
                "metadata": metadata,
                "created_at": metadata.get("created_at"),
            },
        )

    async def remove_document(self, doc_id: str):
        await self.initialize()
        if self._es.client:
            full_index = f"{self._es.index_prefix}_{self._index_name}"
            try:
                await self._es.client.delete(index=full_index, id=doc_id)
            except Exception:
                pass

    async def search(
        self,
        query: str,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        await self.initialize()
        try:
            results = await self._es.search(self._index_name, query, filters=filters, size=limit)
            return [
                {
                    "id": r["id"],
                    "title": r["source"].get("title", ""),
                    "content": r["source"].get("content", ""),
                    "metadata": r["source"].get("metadata", {}),
                    "score": float(r["score"]),
                }
                for r in results
            ]
        except Exception as e:
            logger.warning("ES search failed: %s", e)
            return []

    async def hybrid_search(
        self,
        text_query: str,
        vector_results: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        await self.initialize()
        try:
            results = await self._es.hybrid_search(
                self._index_name, text_query, vector_ids=vector_results, size=limit
            )
            return [
                {
                    "id": r["id"],
                    "title": r["source"].get("title", ""),
                    "content": r["source"].get("content", ""),
                    "metadata": r["source"].get("metadata", {}),
                    "score": float(r["score"]),
                }
                for r in results
            ]
        except Exception as e:
            logger.warning("ES hybrid search failed: %s", e)
            return await self.search(text_query, limit=limit)

    async def get_stats(self) -> Dict[str, Any]:
        await self.initialize()
        try:
            es_stats = await self._es.get_stats()
            es_stats["engine"] = "Elasticsearch (BM25)"
            return es_stats
        except Exception:
            return {"total_documents": 0, "engine": "Elasticsearch (BM25)", "status": "disconnected"}


# Global instance
_fts_engine: Optional[FTSEngine] = None


def get_fts_engine() -> FTSEngine:
    global _fts_engine
    if _fts_engine is None:
        _fts_engine = FTSEngine()
    return _fts_engine


async def initialize_fts():
    engine = get_fts_engine()
    await engine.initialize()
    return engine
