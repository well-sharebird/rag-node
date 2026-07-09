import logging
from fastapi import APIRouter

from app.core.deps import DBSession, RedisClient, MilvusDep
from app.services.retrieval_service import search_chunks, get_search_history
from app.schemas.retrieval import SearchRequest, SearchResponse, SearchHistoryResponse

logger = logging.getLogger("app.api.retrieval")
router = APIRouter(prefix="/retrieval", tags=["retrieval"])


@router.post("/search", response_model=SearchResponse)
async def search(db: DBSession, redis: RedisClient, milvus: MilvusDep, data: SearchRequest):
    return await search_chunks(db, redis, milvus, data)


@router.get("/history", response_model=SearchHistoryResponse)
async def search_history(redis: RedisClient, limit: int = 20):
    return await get_search_history(redis, limit)
