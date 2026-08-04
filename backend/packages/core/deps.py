from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from packages.core.database import get_db
from packages.core.infra.redis_client import get_redis
from packages.core.infra.milvus_client import get_milvus_client

DBSession = Annotated[AsyncSession, Depends(get_db)]
RedisClient = Annotated[aioredis.Redis, Depends(get_redis)]


def get_milvus():
    return get_milvus_client()


MilvusDep = Annotated[object, Depends(get_milvus)]
