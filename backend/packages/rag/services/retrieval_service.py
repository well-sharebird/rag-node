from __future__ import annotations
import json
import logging
import time
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from packages.rag.models.knowledge_base import KnowledgeBase
from packages.rag.models.document import Document
from packages.rag.services.embedding_service import get_embedding_service
from packages.rag.services.vector_store_service import search_vectors
from packages.rag.schemas.retrieval import SearchRequest, SearchResponse, SearchResultItem, SearchHistoryItem, SearchHistoryResponse
from packages.core.exceptions import NotFoundException, ValidationException

logger = logging.getLogger("app.services.retrieval")


async def _resolve_embedding_params(db: AsyncSession) -> dict | None:
    """Resolve embedding parameters from model_configs.

    Args:
        db: Database session

    Returns:
        Dict with provider, model_name, api_url, api_key, dim; or None if not configured
    """
    from packages.model_gateway.services.model_config_service import resolve_embedding_config, model_config_to_embedding_params

    model = await resolve_embedding_config(db)
    if model:
        return await model_config_to_embedding_params(db, model)

    logger.warning("No embedding model configured in model_configs")
    return None


async def _rerank_results(
    db: AsyncSession,
    query: str,
    hits: list[dict],
    top_n: int = 3,
) -> list[dict]:
    """Re-rank search results using the configured rerank model.

    Resolves rerank model from model_configs, falls back to legacy config.
    Returns original hits if no rerank model is available.
    """
    from packages.core.database import async_session_factory
    from packages.model_gateway.services.model_config_service import resolve_rerank_config, get_provider_config
    import httpx

    try:
        model = await resolve_rerank_config(db)

        if not model or not model.is_enabled:
            return hits[:top_n]

        # Get provider config for base_url and api_key
        provider_config = await get_provider_config(db, model.provider)
        base_url = provider_config["base_url"] if provider_config else ""
        api_key = provider_config["api_key"] if provider_config else ""

        if not base_url:
            logger.warning("Rerank model has no base_url configured")
            return hits[:top_n]

        # Build rerank URL
        base_url = base_url.rstrip('/')
        if base_url.endswith('/v1'):
            rerank_url = f"{base_url}/rerank"
        else:
            rerank_url = f"{base_url}/v1/rerank"

        documents = [h["content"][:1000] for h in hits]
        async with httpx.AsyncClient(timeout=30) as client:
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            response = await client.post(
                rerank_url,
                json={
                    "model": model.model_id,
                    "query": query,
                    "documents": documents,
                    "top_n": top_n,
                },
                headers=headers,
            )
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                reordered = []
                for r in results:
                    idx = r.get("index", 0)
                    if idx < len(hits):
                        hits[idx]["score"] = r.get("relevance_score", hits[idx]["score"])
                        reordered.append(hits[idx])
                logger.info("Reranked results from %d to %d", len(hits), len(reordered))
                return reordered[:top_n]
            else:
                logger.warning("Rerank API returned %d: %s", response.status_code, response.text[:200])
                return hits[:top_n]

    except Exception as e:
        logger.warning("Rerank failed, using original results: %s", e)
        return hits[:top_n]


async def search_chunks(db: AsyncSession, redis: aioredis.Redis, milvus, data: SearchRequest) -> SearchResponse:
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == data.kb_id))
    kb = result.scalar_one_or_none()
    if kb is None:
        raise NotFoundException("Knowledge base not found")
    if not milvus.has_collection(kb.collection_name):
        raise ValidationException("Collection not found. Re-index may be required.")

    logger.info("Search | kb=%s query='%s' top_k=%d", kb.name, data.query[:80], data.top_k)

    start = time.monotonic()

    # Resolve embedding model from model_configs
    embed_params = await _resolve_embedding_params(db)
    if embed_params is None:
        raise ValidationException("No embedding model configured. Please configure a default embedding model in Model Management.")

    embed_service = get_embedding_service(
        api_url=embed_params["api_url"],
        api_key=embed_params["api_key"],
        model=embed_params["model_name"],
        dim=embed_params["dim"],
    )
    query_embedding = await embed_service.embed_query(data.query)

    # Apply KB-level config if set, otherwise use system defaults
    from packages.rag.config import get_retrieval_config
    defaults = get_retrieval_config()

    # Priority: Request > KB config > System default
    top_k = (
        data.top_k
        if data.top_k and data.top_k != 5
        else (kb.top_k if kb.top_k else defaults.get("default_top_k", 10))
    )
    min_score = (
        data.min_score
        if data.min_score is not None
        else (kb.min_score if kb.min_score is not None else defaults.get("default_min_score", 0.6))
    )
    enable_rerank = (
        data.enable_rerank
        if data.enable_rerank is not None
        else (kb.enable_rerank if kb.enable_rerank is not None else defaults.get("enable_rerank", True))
    )
    rerank_top_n = defaults.get("rerank_top_n", 3)

    # When reranking, use a wider initial recall (min_score=0) since rerank will re-score
    initial_min_score = 0.0 if enable_rerank else min_score

    # Build Milvus filter expression from metadata filters
    filter_parts = []

    # Tag filtering: find documents with matching tags, then filter by doc_id
    if data.tags:
        tag_conditions = []
        for tag in data.tags:
            tag_conditions.append(f"tags LIKE '%{tag}%'")
        tag_filter = " OR ".join(tag_conditions)
        tag_docs_result = await db.execute(
            select(Document.id).where(
                Document.kb_id == data.kb_id,
                Document.tags.isnot(None),
            )
        )
        tag_doc_ids = [str(d.id) for d in tag_docs_result.scalars().all()]
        # Filter documents that match any of the tags
        matching_doc_ids = []
        for doc_id in tag_doc_ids:
            doc_result = await db.execute(select(Document.tags).where(Document.id == doc_id))
            doc_tags_raw = doc_result.scalar_one_or_none()
            if doc_tags_raw:
                try:
                    doc_tags = json.loads(doc_tags_raw) if isinstance(doc_tags_raw, str) else doc_tags_raw
                    if any(t in doc_tags for t in data.tags):
                        matching_doc_ids.append(doc_id)
                except:
                    pass
        if matching_doc_ids:
            doc_ids_str = ", ".join(f'"{id}"' for id in matching_doc_ids)
            filter_parts.append(f'doc_id in [{doc_ids_str}]')
        else:
            # No documents match tags, return empty results
            logger.info("No documents match tags: %s", data.tags)
            return SearchResponse(results=[], query=data.query, search_time_ms=0, total_recalled=0)

    # Direct doc_id filtering
    if data.doc_ids:
        doc_ids_str = ", ".join(f'"{id}"' for id in data.doc_ids)
        filter_parts.append(f'doc_id in [{doc_ids_str}]')

    # Content type filtering
    if data.content_type:
        filter_parts.append(f'content_type == "{data.content_type}"')

    # Combine all filter parts
    filter_expr = " AND ".join(filter_parts) if filter_parts else None

    if data.enable_multimodal:
        from packages.rag.services.multi_modal_retrieval import get_multi_modal_retrieval_service
        mm_svc = get_multi_modal_retrieval_service(milvus, embed_service)
        hits = await mm_svc.multi_modal_search(
            kb.collection_name, data.query, top_k=top_k * 2,
            content_type_filter=data.content_type,
        )
    else:
        hits = search_vectors(milvus, kb.collection_name, query_embedding, top_k=top_k, min_score=initial_min_score, filter=filter_expr)

    # Rerank if configured and enabled
    if enable_rerank and len(hits) > 1:
        hits = await _rerank_results(db, data.query, hits, top_n=rerank_top_n)

    # Apply user's min_score filter to final (reranked) results
    hits = [h for h in hits if h.get("score", h.get("distance", 0)) >= min_score]

    elapsed = (time.monotonic() - start) * 1000

    # Record metrics
    try:
        await redis.lpush("rag:latency:recent", str(round(elapsed, 1)))
        await redis.ltrim("rag:latency:recent", 0, 99)

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        pipe = redis.pipeline()
        pipe.hincrby(f"rag:stats:{today}", "searches", 1)
        pipe.hincrbyfloat(f"rag:stats:{today}", "total_score", sum(h["score"] for h in hits))
        pipe.hincrbyfloat(f"rag:stats:{today}", "total_latency", elapsed)
        if len(hits) == 0:
            pipe.hincrby(f"rag:stats:{today}", "zero_results", 1)
        await pipe.execute()

        # Record search history
        entry = json.dumps({
            "query": data.query, "kb_name": kb.name,
            "result_count": len(hits), "latency_ms": round(elapsed, 1),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        await redis.lpush("rag:search_history", entry)
        await redis.ltrim("rag:search_history", 0, 199)

        # Track top docs
        for h in hits:
            doc_id = h["metadata"].get("doc_id", "")
            if doc_id:
                await redis.zincrby("rag:top_docs", 1, f"{doc_id}:{h['metadata'].get('doc_name', '')}")
                await redis.hincrbyfloat(f"rag:doc_score:{doc_id}", "total_score", h["score"])
                await redis.hincrby(f"rag:doc_score:{doc_id}", "count", 1)
                new_avg = await redis.hget(f"rag:doc_score:{doc_id}", "total_score") or "0"
                new_cnt = await redis.hget(f"rag:doc_score:{doc_id}", "count") or "1"
                # Compute avg score
    except Exception as e:
        logger.debug("Redis metrics recording failed: %s", e)

    items = [
        SearchResultItem(chunk_id=h["chunk_id"], content=h["content"], score=h["score"], metadata=h["metadata"],
                         content_type=h.get("content_type", "text"))
        for h in hits
    ]
    logger.info("Search done | results=%d time=%.1fms", len(items), elapsed)
    return SearchResponse(results=items, query=data.query, search_time_ms=round(elapsed, 1), total_recalled=len(items))


async def get_search_history(redis: aioredis.Redis, limit: int = 20) -> SearchHistoryResponse:
    try:
        raw_entries = await redis.lrange("rag:search_history", 0, limit - 1)
        total = await redis.llen("rag:search_history")
    except Exception as e:
        logger.debug("Failed to read search history: %s", e)
        return SearchHistoryResponse(items=[], total=0)

    items = []
    for entry in raw_entries:
        try:
            data = json.loads(entry)
            items.append(SearchHistoryItem(**data))
        except Exception:
            pass
    return SearchHistoryResponse(items=items, total=total)
