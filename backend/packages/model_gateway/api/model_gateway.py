"""
模型网关 API 端点
支持供应商管理、路由配置、调用日志查询、统一 LLM 调用
"""
import logging
from typing import Optional, List, Any, Dict
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from packages.core.database import get_db
from packages.model_gateway.models.model_gateway import ModelProvider, ModelRoutingRule, ModelCallLog
from packages.model_gateway.models.model_config import ModelConfig
from packages.model_gateway.services.model_gateway_service import ModelGatewayService
from packages.model_gateway.schemas.model_gateway import (
    # Provider schemas
    ModelProviderBase, ModelProviderCreate, ModelProviderUpdate, ModelProviderResponse,
    ModelProviderListResponse,
    # Routing schemas
    ModelRoutingRuleBase, ModelRoutingRuleCreate, ModelRoutingRuleUpdate, ModelRoutingRuleResponse,
    ModelRoutingRuleListResponse,
    # Call log schemas
    ModelCallLogResponse, ModelCallLogListResponse, ModelCallStatistics,
    # Cache schemas
    ModelCacheStatistics,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/model-gateway", tags=["model-gateway"])


def _mask_api_key(api_key: Optional[str]) -> Optional[str]:
    """对 API Key 做掩码，仅保留首尾少量字符，中间打码。

    完整密钥不出后端；前端据此确认 key 是否存在、大致是哪个。
    - None/空 → None（前端显示"未配置"）
    - 长度 <= 8 → 全部打码，保留长度感知
    - 否则 → 前 4 + •••••• + 后 4
    """
    if not api_key:
        return None
    if len(api_key) <= 8:
        return "•" * len(api_key)
    return f"{api_key[:4]}{'•' * 6}{api_key[-4:]}"


def _provider_to_response(p) -> ModelProviderBase:
    """把 ORM 供应商转为响应 Schema，并对 api_key 做掩码。"""
    item = ModelProviderBase.model_validate(p, from_attributes=True)
    item.api_key = _mask_api_key(p.api_key)
    return item


# ========== 供应商管理 ==========

@router.get("/providers", response_model=ModelProviderListResponse)
async def list_providers(
    provider_type: Optional[str] = Query(None, description="供应商类型"),
    is_enabled: Optional[bool] = Query(None, description="是否启用"),
    status: Optional[str] = Query(None, description="状态"),
    db: AsyncSession = Depends(get_db),
):
    """获取供应商列表"""
    service = ModelGatewayService(db)
    providers = await service.get_providers(
        provider_type=provider_type,
        is_enabled=is_enabled,
        status=status,
    )
    return ModelProviderListResponse(items=[_provider_to_response(p) for p in providers], total=len(providers))


@router.get("/providers/{provider_id}", response_model=ModelProviderResponse)
async def get_provider(
    provider_id: int,
    db: AsyncSession = Depends(get_db),
):
    """获取供应商详情"""
    service = ModelGatewayService(db)
    provider = await service.get_provider_by_id(provider_id)

    if not provider:
        raise HTTPException(status_code=404, detail="供应商不存在")

    return ModelProviderResponse(item=_provider_to_response(provider))


@router.post("/providers", response_model=ModelProviderResponse, status_code=201)
async def create_provider(
    data: ModelProviderCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建供应商"""
    service = ModelGatewayService(db)

    # 检查代码是否已存在
    existing = await service.get_provider_by_code(data.code)
    if existing:
        raise HTTPException(status_code=400, detail="供应商代码已存在")

    provider_data = data.model_dump()
    provider = await service.create_provider(provider_data)

    return ModelProviderResponse(item=_provider_to_response(provider))


@router.put("/providers/{provider_id}", response_model=ModelProviderResponse)
async def update_provider(
    provider_id: int,
    data: ModelProviderUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新供应商"""
    service = ModelGatewayService(db)

    provider = await service.update_provider(provider_id, data.model_dump(exclude_unset=True))

    if not provider:
        raise HTTPException(status_code=404, detail="供应商不存在")

    return ModelProviderResponse(item=_provider_to_response(provider))


@router.delete("/providers/{provider_id}")
async def delete_provider(
    provider_id: int,
    db: AsyncSession = Depends(get_db),
):
    """删除供应商"""
    service = ModelGatewayService(db)

    try:
        success = await service.delete_provider(provider_id)
        if not success:
            raise HTTPException(status_code=404, detail="供应商不存在")
        return {"message": "供应商已删除"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/providers/{provider_id}/health")
async def update_provider_health(
    provider_id: int,
    health_status: str = Query(..., description="健康状态"),
    success: bool = Query(..., description="是否成功"),
    db: AsyncSession = Depends(get_db),
):
    """更新供应商健康状态（手动）"""
    service = ModelGatewayService(db)
    await service.update_provider_health(provider_id, health_status, success)
    return {"message": "健康状态已更新"}


@router.get("/providers/{provider_id}/health/check")
async def check_provider_health(
    provider_id: int,
    timeout_ms: int = Query(5000, description="超时时间（毫秒）"),
    db: AsyncSession = Depends(get_db),
):
    """检查供应商健康状态（实时检测）"""
    service = ModelGatewayService(db)
    provider = await service.get_provider_by_id(provider_id)

    if not provider:
        raise HTTPException(status_code=404, detail="供应商不存在")

    check_result = await service.check_provider_health(provider, timeout_ms)
    await service.update_provider_health_from_check(provider_id, check_result)

    return check_result


@router.post("/providers/health/check-all")
async def check_all_providers_health(
    timeout_ms: int = Query(5000, description="超时时间（毫秒）"),
    db: AsyncSession = Depends(get_db),
):
    """批量检查所有供应商健康状态"""
    service = ModelGatewayService(db)
    results = await service.run_health_check_all_providers(timeout_ms)
    return results


@router.get("/providers/{provider_id}/circuit-breaker")
async def get_circuit_breaker_status(
    provider_id: int,
    db: AsyncSession = Depends(get_db),
):
    """获取熔断器状态"""
    service = ModelGatewayService(db)
    health = await service.get_provider_health(provider_id)
    return {
        "circuit_breaker_state": health["circuit_breaker_state"],
        "circuit_breaker_failures": health["circuit_breaker_failures"],
        "provider_status": health["status"],
        "health_status": health["health_status"],
    }


@router.post("/providers/{provider_id}/circuit-breaker/reset")
async def reset_circuit_breaker(
    provider_id: int,
    db: AsyncSession = Depends(get_db),
):
    """重置熔断器"""
    service = ModelGatewayService(db)
    service.reset_circuit_breaker(provider_id)
    return {"message": "熔断器已重置"}


# ========== 路由规则管理 ==========

@router.get("/routing-rules", response_model=ModelRoutingRuleListResponse)
async def list_routing_rules(
    model_type: Optional[str] = Query(None, description="模型类型"),
    is_enabled: Optional[bool] = Query(None, description="是否启用"),
    db: AsyncSession = Depends(get_db),
):
    """获取路由规则列表"""
    service = ModelGatewayService(db)
    rules = await service.get_routing_rules(
        model_type=model_type,
        is_enabled=is_enabled,
    )
    return ModelRoutingRuleListResponse(items=[ModelRoutingRuleBase.model_validate(r, from_attributes=True) for r in rules], total=len(rules))


@router.get("/routing-rules/{rule_id}", response_model=ModelRoutingRuleResponse)
async def get_routing_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
):
    """获取路由规则详情"""
    service = ModelGatewayService(db)
    rule = await service.get_routing_rule_by_id(rule_id)

    if not rule:
        raise HTTPException(status_code=404, detail="路由规则不存在")

    return ModelRoutingRuleResponse(item=ModelRoutingRuleBase.model_validate(rule, from_attributes=True))


@router.post("/routing-rules", response_model=ModelRoutingRuleResponse, status_code=201)
async def create_routing_rule(
    data: ModelRoutingRuleCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建路由规则"""
    service = ModelGatewayService(db)

    rule_data = data.model_dump()
    rule = await service.create_routing_rule(rule_data)

    return ModelRoutingRuleResponse(item=ModelRoutingRuleBase.model_validate(rule, from_attributes=True))


@router.put("/routing-rules/{rule_id}", response_model=ModelRoutingRuleResponse)
async def update_routing_rule(
    rule_id: int,
    data: ModelRoutingRuleUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新路由规则"""
    service = ModelGatewayService(db)

    rule = await service.update_routing_rule(rule_id, data.model_dump(exclude_unset=True))

    if not rule:
        raise HTTPException(status_code=404, detail="路由规则不存在")

    return ModelRoutingRuleResponse(item=ModelRoutingRuleBase.model_validate(rule, from_attributes=True))


@router.delete("/routing-rules/{rule_id}")
async def delete_routing_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
):
    """删除路由规则"""
    service = ModelGatewayService(db)
    success = await service.delete_routing_rule(rule_id)

    if not success:
        raise HTTPException(status_code=404, detail="路由规则不存在")

    return {"message": "路由规则已删除"}


# ========== 调用日志 ==========

@router.get("/call-logs", response_model=ModelCallLogListResponse)
async def list_call_logs(
    provider_id: Optional[int] = Query(None, description="供应商 ID"),
    model_type: Optional[str] = Query(None, description="模型类型"),
    user_id: Optional[int] = Query(None, description="用户 ID"),
    kb_id: Optional[str] = Query(None, description="知识库 ID"),
    status: Optional[str] = Query(None, description="状态"),
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    limit: int = Query(100, ge=1, le=1000, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    db: AsyncSession = Depends(get_db),
):
    """获取调用日志列表"""
    service = ModelGatewayService(db)
    logs = await service.get_call_logs(
        provider_id=provider_id,
        model_type=model_type,
        user_id=user_id,
        kb_id=kb_id,
        status=status,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )

    total_query = await db.execute(
        ModelGatewayService(db).get_call_logs.__code__,
    )

    return ModelCallLogListResponse(items=logs, total=len(logs))


@router.get("/statistics", response_model=ModelCallStatistics)
async def get_statistics(
    provider_id: Optional[int] = Query(None, description="供应商 ID"),
    model_type: Optional[str] = Query(None, description="模型类型"),
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    db: AsyncSession = Depends(get_db),
):
    """获取调用统计信息"""
    service = ModelGatewayService(db)
    stats = await service.get_call_statistics(
        provider_id=provider_id,
        model_type=model_type,
        start_time=start_time,
        end_time=end_time,
    )
    return ModelCallStatistics(**stats)


@router.get("/cache/statistics", response_model=ModelCacheStatistics)
async def get_cache_statistics(
    db: AsyncSession = Depends(get_db),
):
    """获取缓存统计"""
    service = ModelGatewayService(db)
    stats = await service.get_cache_statistics()
    return ModelCacheStatistics(**stats)


@router.post("/cache/clear")
async def clear_expired_cache(
    db: AsyncSession = Depends(get_db),
):
    """清理过期缓存"""
    service = ModelGatewayService(db)
    deleted_count = await service.clear_expired_cache()
    return {"message": f"已清理 {deleted_count} 条过期缓存"}


# ========== 统一 LLM 调用 ==========


class LLMChatRequest(BaseModel):
    """LLM 聊天请求"""
    model_type: str = Field(default="llm", description="模型类型")
    model_id: Optional[str] = Field(default=None, description="具体模型 ID")
    messages: List[Dict[str, str]] = Field(..., description="OpenAI 格式的消息列表")
    temperature: float = Field(default=0.7, description="温度参数", ge=0, le=2)
    max_tokens: Optional[int] = Field(default=None, description="最大输出 token 数")
    stream: bool = Field(default=False, description="是否流式输出")
    use_routing: bool = Field(default=True, description="是否使用路由")
    user_id: Optional[int] = Field(default=None, description="用户 ID")
    kb_id: Optional[str] = Field(default=None, description="知识库 ID")


class LLMChatResponse(BaseModel):
    """LLM 聊天响应"""
    content: str
    reasoning: Optional[str] = None
    usage: Dict[str, Any]  # Can be int or nested dict (new OpenAI format)
    latency_ms: float
    provider_name: str
    model_id: str


class RateLimitResponse(BaseModel):
    """限流检查响应"""
    allowed: bool
    remaining: int
    reset_at: Optional[str] = None
    retry_after: int = 0


class QuotaResponse(BaseModel):
    """配额检查响应"""
    allowed: bool
    remaining_quota: int
    quota_limit: int
    used_quota: int
    period: str


@router.post("/chat/completions")
async def chat_completions(
    request: LLMChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    统一 LLM 聊天接口
    支持路由选择、重试、流式响应
    """
    service = ModelGatewayService(db)

    # 选择供应商
    if request.use_routing:
        provider = await service.get_best_provider(
            model_type=request.model_type,
            model_id=request.model_id,
            user_id=request.user_id,
        )
    else:
        # 使用默认供应商
        provider = await service._get_default_provider()

    if not provider:
        raise HTTPException(status_code=503, detail="No available LLM provider")

    try:
        # 调用 LLM
        result = await service.call_llm_with_retry(
            provider=provider,
            model_id=request.model_id or provider.code,
            messages=request.messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=request.stream,
            user_id=request.user_id,
            kb_id=request.kb_id,
            model_type=request.model_type,
        )

        if request.stream and result.get("type") == "streaming":
            # 流式响应
            return StreamingResponse(
                service.stream_llm_response(result),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        else:
            # 非流式响应
            return LLMChatResponse(
                content=result.get("content", ""),
                reasoning=result.get("reasoning"),
                usage=result.get("usage", {}),
                latency_ms=result.get("latency_ms", 0),
                provider_name=provider.name,
                model_id=request.model_id or provider.code,
            )

    except Exception as e:
        logger.exception("LLM chat completion failed")
        raise HTTPException(status_code=500, detail=str(e))


# ========== 限流和配额 ==========

@router.get("/rate-limit/check", response_model=RateLimitResponse)
async def check_rate_limit(
    user_id: Optional[int] = Query(None, description="用户 ID"),
    kb_id: Optional[str] = Query(None, description="知识库 ID"),
    provider_id: Optional[int] = Query(None, description="供应商 ID"),
    model_type: str = Query(default="llm", description="模型类型"),
    db: AsyncSession = Depends(get_db),
):
    """检查调用限流"""
    service = ModelGatewayService(db)
    result = await service.check_rate_limit(
        user_id=user_id,
        kb_id=kb_id,
        provider_id=provider_id,
        model_type=model_type,
    )
    return RateLimitResponse(**result)


@router.get("/quota/check", response_model=QuotaResponse)
async def check_quota(
    user_id: Optional[int] = Query(None, description="用户 ID"),
    kb_id: Optional[str] = Query(None, description="知识库 ID"),
    model_type: str = Query(default="llm", description="模型类型"),
    requested_tokens: int = Query(default=1000, description="请求的 token 数"),
    db: AsyncSession = Depends(get_db),
):
    """检查配额"""
    service = ModelGatewayService(db)
    result = await service.check_quota(
        user_id=user_id,
        kb_id=kb_id,
        model_type=model_type,
        requested_tokens=requested_tokens,
    )
    return QuotaResponse(**result)


# ========== 模型测试接口 ==========

class EmbeddingTestRequest(BaseModel):
    """Embedding 测试请求"""
    model_config_id: int = Field(..., description="模型配置 ID")
    input: str = Field(..., description="输入文本")


class EmbeddingTestResponse(BaseModel):
    """Embedding 测试响应"""
    embedding: list[float]
    dimension: int
    latency_ms: float
    provider_name: str
    model_id: str


class RerankTestRequest(BaseModel):
    """Rerank 测试请求"""
    model_config_id: int = Field(..., description="模型配置 ID")
    query: str = Field(..., description="查询文本")
    documents: list[str] = Field(..., description="待排序的文档列表")


class RerankResult(BaseModel):
    """Rerank 结果"""
    index: int
    score: float
    document: str


class RerankTestResponse(BaseModel):
    """Rerank 测试响应"""
    results: list[RerankResult]
    latency_ms: float
    provider_name: str
    model_id: str


@router.post("/test/embedding", response_model=EmbeddingTestResponse)
async def test_embedding(
    data: EmbeddingTestRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    测试 Embedding 模型

    调用指定的 Embedding 模型生成向量
    """
    service = ModelGatewayService(db)

    # 使用模型配置 ID 精确查询
    from sqlalchemy import select
    model_config_result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.id == data.model_config_id,
        )
    )
    model_config = model_config_result.scalar_one_or_none()

    if not model_config:
        raise HTTPException(status_code=404, detail=f"模型配置未找到：{data.model_config_id}")

    # 获取供应商
    provider = await service.get_provider_by_code(model_config.provider)
    if not provider:
        raise HTTPException(status_code=404, detail=f"供应商未找到：{model_config.provider}")

    try:
        result = await service.call_llm(
            provider=provider,
            model_id=model_config.model_id,
            messages=[{"content": data.input}],
            model_type="embedding",
        )

        return EmbeddingTestResponse(
            embedding=result["embedding"],
            dimension=len(result["embedding"]),
            latency_ms=result.get("latency_ms", 0),
            provider_name=provider.name,
            model_id=model_config.model_id,
        )

    except Exception as e:
        logger.exception("Embedding test failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test/rerank", response_model=RerankTestResponse)
async def test_rerank(
    data: RerankTestRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    测试 Rerank 模型

    对文档列表进行相关性排序
    """
    service = ModelGatewayService(db)

    # 使用模型配置 ID 精确查询
    from sqlalchemy import select
    model_config_result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.id == data.model_config_id,
        )
    )
    model_config = model_config_result.scalar_one_or_none()

    if not model_config:
        raise HTTPException(status_code=404, detail=f"模型配置未找到：{data.model_config_id}")

    # 获取供应商
    provider = await service.get_provider_by_code(model_config.provider)
    if not provider:
        raise HTTPException(status_code=404, detail=f"供应商未找到：{model_config.provider}")

    try:
        result = await service.call_llm(
            provider=provider,
            model_id=model_config.model_id,
            messages=[{
                "content": data.query,
                "documents": data.documents,
            }],
            model_type="rerank",
        )

        # 构建结果
        rerank_results = [
            RerankResult(
                index=r["index"],
                score=r["score"],
                document=data.documents[r["index"]] if r["index"] < len(data.documents) else "",
            )
            for r in result["results"]
        ]

        return RerankTestResponse(
            results=rerank_results,
            latency_ms=result.get("latency_ms", 0),
            provider_name=provider.name,
            model_id=model_config.model_id,
        )

    except Exception as e:
        logger.exception("Rerank test failed")
        raise HTTPException(status_code=500, detail=str(e))
