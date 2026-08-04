"""Multi-modal retrieval: parallel search across content types with result merging."""
from __future__ import annotations
import asyncio
import logging
from typing import Optional

from pymilvus import MilvusClient

logger = logging.getLogger("app.services.multi_modal_retrieval")


class MultiModalRetrievalService:
    """Parallel search across text/table/image content types with score-based merge."""

    def __init__(
        self,
        milvus: MilvusClient,
        text_embed_service,
        content_types: list[str] | None = None,
    ):
        self.milvus = milvus
        self.text_embed = text_embed_service
        self.content_types = content_types or ["text", "table", "image"]

    async def multi_modal_search(
        self,
        collection_name: str,
        query: str,
        top_k: int = 10,
    ) -> list[dict]:
        """Search across content types in parallel, merge and deduplicate results.

        Falls back to unfiltered search if content_type field doesn't exist in collection.
        """
        query_emb = await self.text_embed.embed_query(query)

        # Parallel type-filtered searches with fallback on filter error
        tasks = []
        for ct in self.content_types:
            tasks.append(self._search_typed(collection_name, query_emb, ct, top_k * 2))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect and deduplicate
        seen_ids = set()
        all_hits = []
        for result in results:
            if isinstance(result, list):
                for hit in result:
                    cid = hit.get("chunk_id", "")
                    if cid and cid not in seen_ids:
                        seen_ids.add(cid)
                        all_hits.append(hit)
            elif isinstance(result, Exception):
                logger.warning("Multi-modal search task failed: %s", result)

        # Sort by score descending
        all_hits.sort(key=lambda h: h.get("score", 0), reverse=True)
        return all_hits[:top_k]

    async def _search_typed(
        self, collection_name: str, query_emb: list[float],
        content_type: str, top_k: int,
    ) -> list[dict]:
        """Search with content_type filter, fallback to unfiltered on error."""
        from packages.rag.services.vector_store_service import search_vectors

        try:
            hits = search_vectors(
                self.milvus, collection_name, query_emb,
                top_k=top_k, content_type_filter=content_type,
            )
        except Exception:
            logger.debug("Content type filter failed for [%s], using unfiltered search", content_type)
            hits = search_vectors(
                self.milvus, collection_name, query_emb,
                top_k=top_k,
            )

        for h in hits:
            h["content_type"] = h.get("content_type", content_type)
        logger.debug("Multi-modal [%s]: %d hits", content_type, len(hits))
        return hits


_mm_service: Optional[MultiModalRetrievalService] = None


def get_multi_modal_retrieval_service(
    milvus: MilvusClient,
    text_embed_service,
) -> MultiModalRetrievalService:
    global _mm_service
    if _mm_service is None:
        _mm_service = MultiModalRetrievalService(
            milvus=milvus,
            text_embed_service=text_embed_service,
        )
    return _mm_service


def reset_multi_modal_service():
    global _mm_service
    _mm_service = None
