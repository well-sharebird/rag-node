from __future__ import annotations
import json
import logging
import time
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.models.knowledge_base import KnowledgeBase
from app.services.embedding_service import get_embedding_service
from app.services.vector_store_service import search_vectors
from app.schemas.retrieval import SearchRequest, SearchResponse, SearchResultItem, SearchHistoryItem, SearchHistoryResponse
from app.utils.exceptions import NotFoundException, ValidationException

logger = logging.getLogger("app.services.retrieval")


async def _resolve_embedding_params() -> dict:
    """Resolve embedding parameters from model_configs or fallback."""
    from app.core.database import async_session_factory
    from app.services.model_config_service import resolve_embedding_config

    try:
        async with async_session_factory() as session:
            model = await resolve_embedding_config(session)
            if model:
                return {
                    "provider": model.adapter_type,
                    "model_name": model.model_id,
                    "api_url": model.api_url or "",
                    "api_key": model.api_key or "",
                    "dim": model.embedding_dim or 1024,
                }
    except Exception as e:
        logger.warning("Failed to resolve embedding from model_configs: %s", e)

    from app.core.rag_config import get_model_config
    config = get_model_config()
    return {
        "provider": config.get("embedding_provider", "local"),
        "model_name": config.get("embedding_model", "BAAI/bge-m3"),
        "api_url": config.get("embedding_api_url", ""),
        "api_key": config.get("embedding_api_key", ""),
        "dim": config.get("embedding_dim", 1024),
    }


async def _rerank_results(
    query: str,
    hits: list[dict],
    top_n: int = 3,
) -> list[dict]:
    """Re-rank search results using the configured rerank model.

    Resolves rerank model from model_configs, falls back to legacy config.
    Returns original hits if no rerank model is available.
    """
    from app.core.database import async_session_factory
    from app.services.model_config_service import resolve_rerank_config
    import httpx

    try:
        async with async_session_factory() as session:
            model = await resolve_rerank_config(session)

            if not model or not model.is_enabled:
                return hits[:top_n]

            if model.adapter_type == "api" and model.api_url:
                base_url = model.api_url.rstrip('/')
                if base_url.endswith('/v1'):
                    rerank_url = f"{base_url}/rerank"
                else:
                    rerank_url = f"{base_url}/v1/rerank"

                documents = [h["content"][:1000] for h in hits]
                async with httpx.AsyncClient(timeout=30) as client:
                    headers = {}
                    if model.api_key:
                        headers["Authorization"] = f"Bearer {model.api_key}"
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
    embed_params = await _resolve_embedding_params()
    embed_service = get_embedding_service(
        provider=embed_params["provider"],
        model_name=embed_params["model_name"],
        api_url=embed_params["api_url"],
        api_key=embed_params["api_key"],
        dim=embed_params["dim"],
    )
    query_embedding = await embed_service.embed_query(data.query)

    # Apply system defaults if not specified in request
    from app.core.rag_config import get_retrieval_config
    defaults = get_retrieval_config()
    top_k = data.top_k if data.top_k != 5 else defaults.get("default_top_k", 10)
    min_score = data.min_score if data.min_score is not None else defaults.get("default_min_score", 0.6)
    enable_rerank = defaults.get("enable_rerank", True)
    rerank_top_n = defaults.get("rerank_top_n", 3)

    # When reranking, use a wider initial recall (min_score=0) since rerank will re-score
    initial_min_score = 0.0 if enable_rerank else min_score
    hits = search_vectors(milvus, kb.collection_name, query_embedding, top_k=top_k, min_score=initial_min_score)

    # Rerank if configured and enabled
    if enable_rerank and len(hits) > 1:
        hits = await _rerank_results(data.query, hits, top_n=rerank_top_n)

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
        SearchResultItem(chunk_id=h["chunk_id"], content=h["content"], score=h["score"], metadata=h["metadata"])
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
