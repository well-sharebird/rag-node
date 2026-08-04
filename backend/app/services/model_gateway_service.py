"""
模型网关服务层
提供供应商管理、路由决策、调用日志记录等功能
支持：流式调用、重试机制、熔断器、缓存
"""
import json
import hashlib
import uuid
import time
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, AsyncIterator, Callable, TypeVar, Union
from dataclasses import dataclass, field
from enum import Enum
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
import httpx

from app.models.model_gateway import ModelProvider, ModelRoutingRule, ModelCallLog, ModelCache
from app.models.model_config import ModelConfig

logger = logging.getLogger(__name__)


class ModelGatewayError(Exception):
    """模型网关基础异常"""
    pass


class CircuitBreakerOpenError(ModelGatewayError):
    """熔断器打开异常"""
    pass


class ProviderUnavailableError(ModelGatewayError):
    """供应商不可用异常"""
    pass


class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"      # 正常状态
    OPEN = "open"          # 熔断状态，拒绝请求
    HALF_OPEN = "half_open"  # 半开状态，尝试恢复


@dataclass
class CircuitBreaker:
    """
    熔断器实现
    当连续失败达到阈值时打开电路，拒绝后续请求
    经过一段时间后尝试恢复
    """
    failure_threshold: int = 5          # 失败阈值
    recovery_timeout: float = 60.0      # 恢复超时（秒）
    half_open_max_calls: int = 3        # 半开状态最大调用数

    state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    failure_count: int = field(default=0, init=False)
    last_failure_time: Optional[float] = field(default=None, init=False)
    half_open_calls: int = field(default=0, init=False)

    def record_success(self) -> None:
        """记录成功调用"""
        self.failure_count = 0
        self.state = CircuitState.CLOSED
        self.half_open_calls = 0

    def record_failure(self) -> None:
        """记录失败调用"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning("Circuit breaker opened after %d failures", self.failure_count)

    def can_execute(self) -> bool:
        """检查是否可以执行调用"""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # 检查是否过了恢复超时
            if self.last_failure_time is None:
                return True
            elapsed = time.time() - self.last_failure_time
            if elapsed >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                return True
            return False

        # HALF_OPEN 状态
        if self.half_open_calls < self.half_open_max_calls:
            self.half_open_calls += 1
            return True
        return False

    def get_state(self) -> str:
        """获取当前状态"""
        return self.state.value


@dataclass
class RetryConfig:
    """重试配置"""
    max_attempts: int = 3
    initial_delay_ms: int = 100
    max_delay_ms: int = 10000
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_exceptions: tuple = (httpx.RequestError, httpx.TimeoutException)


T = TypeVar('T')


async def retry_with_backoff(
    func: Callable[..., Any],
    config: RetryConfig,
    *args,
    **kwargs,
) -> T:
    """
    带指数退避的重试机制

    Args:
        func: 要执行的异步函数
        config: 重试配置
        *args: 函数参数
        **kwargs: 函数关键字参数

    Returns:
        函数执行结果

    Raises:
        最后一次尝试的异常
    """
    last_exception = None

    for attempt in range(1, config.max_attempts + 1):
        try:
            return await func(*args, **kwargs)
        except config.retryable_exceptions as e:
            last_exception = e
            logger.warning("Attempt %d/%d failed: %s", attempt, config.max_attempts, e)

            if attempt < config.max_attempts:
                # 计算延迟时间（指数退避 + jitter）
                delay_ms = min(
                    config.initial_delay_ms * (config.exponential_base ** (attempt - 1)),
                    config.max_delay_ms
                )

                if config.jitter:
                    import random
                    delay_ms = delay_ms * (0.5 + random.random() * 0.5)

                await asyncio.sleep(delay_ms / 1000)

    # 所有重试都失败了
    logger.error("All %d attempts failed", config.max_attempts)
    if last_exception:
        raise last_exception
    raise Exception("All retry attempts failed")


class ModelGatewayService:
    """模型网关服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ========== 供应商管理 ==========

    async def get_providers(
        self,
        provider_type: Optional[str] = None,
        is_enabled: Optional[bool] = None,
        status: Optional[str] = None,
    ) -> List[ModelProvider]:
        """获取供应商列表"""
        query = select(ModelProvider)

        if provider_type:
            query = query.where(ModelProvider.provider_type == provider_type)
        if is_enabled is not None:
            query = query.where(ModelProvider.is_enabled == is_enabled)
        if status:
            query = query.where(ModelProvider.status == status)

        query = query.order_by(ModelProvider.name)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_provider_by_id(self, provider_id: int) -> Optional[ModelProvider]:
        """根据 ID 获取供应商"""
        query = select(ModelProvider).where(ModelProvider.id == provider_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_provider_by_code(self, code: str) -> Optional[ModelProvider]:
        """根据代码获取供应商"""
        query = select(ModelProvider).where(ModelProvider.code == code)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_model_by_name(self, model_name: str) -> Optional[ModelConfig]:
        """根据模型名称获取模型配置"""
        query = select(ModelConfig).where(
            ModelConfig.model_id == model_name,
            ModelConfig.is_enabled == True
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def create_provider(self, data: Dict[str, Any]) -> ModelProvider:
        """创建供应商"""
        provider = ModelProvider(**data)
        self.db.add(provider)
        await self.db.commit()
        await self.db.refresh(provider)
        return provider

    async def update_provider(self, provider_id: int, data: Dict[str, Any]) -> Optional[ModelProvider]:
        """更新供应商"""
        provider = await self.get_provider_by_id(provider_id)
        if not provider:
            return None

        for key, value in data.items():
            if hasattr(provider, key):
                setattr(provider, key, value)

        await self.db.commit()
        await self.db.refresh(provider)
        return provider

    async def delete_provider(self, provider_id: int) -> bool:
        """删除供应商

        删除前检查是否有关联的模型，如有则抛出异常
        """
        provider = await self.get_provider_by_id(provider_id)
        if not provider:
            return False

        # 检查是否有关联的模型
        models_query = select(ModelConfig).where(ModelConfig.provider == provider.code)
        models_result = await self.db.execute(models_query)
        related_models = list(models_result.scalars().all())

        if related_models:
            model_names = ", ".join([m.name for m in related_models])
            raise ValueError(
                f"无法删除供应商 '{provider.name}'：该供应商下存在 {len(related_models)} 个模型配置（{model_names}），"
                f"请先删除或迁移这些模型"
            )

        await self.db.delete(provider)
        await self.db.commit()
        return True

    async def update_provider_health(
        self,
        provider_id: int,
        health_status: str,
        is_success: bool
    ) -> None:
        """更新供应商健康状态"""
        provider = await self.get_provider_by_id(provider_id)
        if not provider:
            return

        provider.health_status = health_status
        provider.last_health_check = datetime.utcnow()

        if is_success:
            provider.consecutive_failures = 0
            if provider.status == "error":
                provider.status = "active"
        else:
            provider.consecutive_failures += 1
            if provider.consecutive_failures >= 5:
                provider.status = "error"

        await self.db.flush()

    # ========== 路由规则管理 ==========

    async def get_routing_rules(
        self,
        model_type: Optional[str] = None,
        is_enabled: Optional[bool] = None,
    ) -> List[ModelRoutingRule]:
        """获取路由规则列表"""
        query = select(ModelRoutingRule).order_by(ModelRoutingRule.priority)

        if model_type:
            query = query.where(ModelRoutingRule.model_type == model_type)
        if is_enabled is not None:
            query = query.where(ModelRoutingRule.is_enabled == is_enabled)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_routing_rule_by_id(self, rule_id: int) -> Optional[ModelRoutingRule]:
        """根据 ID 获取路由规则"""
        query = select(ModelRoutingRule).where(ModelRoutingRule.id == rule_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def create_routing_rule(self, data: Dict[str, Any]) -> ModelRoutingRule:
        """创建路由规则"""
        rule = ModelRoutingRule(**data)
        self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)
        return rule

    async def update_routing_rule(self, rule_id: int, data: Dict[str, Any]) -> Optional[ModelRoutingRule]:
        """更新路由规则"""
        rule = await self.get_routing_rule_by_id(rule_id)
        if not rule:
            return None

        for key, value in data.items():
            if hasattr(rule, key):
                setattr(rule, key, value)

        await self.db.commit()
        await self.db.refresh(rule)
        return rule

    async def delete_routing_rule(self, rule_id: int) -> bool:
        """删除路由规则"""
        rule = await self.get_routing_rule_by_id(rule_id)
        if not rule:
            return False

        await self.db.delete(rule)
        await self.db.commit()
        return True

    # ========== 路由决策 ==========

    async def get_best_provider(
        self,
        model_type: str,
        model_id: Optional[str] = None,
        user_id: Optional[int] = None,
        tags: Optional[List[str]] = None,
        request_id: Optional[str] = None,
    ) -> Optional[ModelProvider]:
        """
        根据路由规则获取最佳供应商
        支持：优先级、流量权重、故障转移、标签匹配

        Args:
            model_type: 模型类型（llm, embedding, rerank 等）
            model_id: 具体模型 ID
            user_id: 用户 ID（用于用户级别路由）
            tags: 标签列表（用于特殊路由，如 premium）
            request_id: 请求 ID（用于流量权重的一致性哈希）

        Returns:
            最佳供应商，如果没有可用供应商则返回 None
        """
        # 获取所有启用的路由规则，按优先级排序
        rules = await self.get_routing_rules(model_type=model_type, is_enabled=True)

        if not rules:
            # 没有路由规则，返回默认供应商
            return await self._get_default_provider()

        # 收集所有匹配的供应商及其规则
        matched_providers = []

        for rule in rules:
            # 检查规则匹配条件
            if not self._match_rule_conditions(rule, model_id, user_id, tags):
                continue

            # 获取供应商
            provider = await self.get_provider_by_id(rule.provider_id)
            if not provider or not provider.is_enabled:
                continue

            # 检查供应商健康状态
            if provider.status != "active":
                continue

            # 计算综合得分（优先级 + 流量权重）
            score = self._calculate_provider_score(rule, provider)

            matched_providers.append({
                "provider": provider,
                "rule": rule,
                "score": score,
            })

        if not matched_providers:
            # 没有匹配的供应商，返回默认供应商
            return await self._get_default_provider()

        # 按优先级分组
        priority_groups = {}
        for item in matched_providers:
            priority = item["rule"].priority
            if priority not in priority_groups:
                priority_groups[priority] = []
            priority_groups[priority].append(item)

        # 从最高优先级（数字最小）开始选择
        for priority in sorted(priority_groups.keys()):
            group = priority_groups[priority]

            if len(group) == 1:
                # 只有一个供应商，直接返回
                return group[0]["provider"]

            # 多个供应商，按流量权重分配
            selected = self._weighted_select(group, request_id)
            if selected:
                return selected["provider"]

        return await self._get_default_provider()

    def _match_rule_conditions(
        self,
        rule: ModelRoutingRule,
        model_id: Optional[str],
        user_id: Optional[int],
        tags: Optional[List[str]],
    ) -> bool:
        """检查请求是否匹配路由规则条件"""
        if not rule.match_conditions:
            return True  # 没有条件，默认匹配

        conditions = rule.match_conditions

        # 检查模型 ID 匹配
        if "models" in conditions and model_id:
            if model_id not in conditions["models"]:
                return False

        # 检查用户匹配
        if "users" in conditions and user_id:
            if user_id not in conditions["users"]:
                return False

        # 检查标签匹配（任意匹配即可）
        if "tags" in conditions and tags:
            if not any(tag in conditions["tags"] for tag in tags):
                return False

        # 检查是否排除特定用户
        if "exclude_users" in conditions and user_id:
            if user_id in conditions["exclude_users"]:
                return False

        return True

    def _calculate_provider_score(
        self,
        rule: ModelRoutingRule,
        provider: ModelProvider,
    ) -> float:
        """
        计算供应商综合得分
        得分 = 优先级得分 + 健康得分 + 成本得分
        """
        # 优先级得分（优先级越高，得分越高）
        priority_score = 1000 - rule.priority

        # 健康得分
        health_score = 100
        if provider.health_status == "degraded":
            health_score = 50
        elif provider.health_status == "error":
            health_score = 0

        # 连续失败惩罚
        health_score -= provider.consecutive_failures * 10

        # 成本得分（成本越低，得分越高）
        cost_score = 0
        if provider.cost_input is not None and provider.cost_output is not None:
            avg_cost = (float(provider.cost_input) + float(provider.cost_output)) / 2
            cost_score = max(0, 100 - avg_cost * 1000)  # 成本越低得分越高

        return priority_score + health_score + cost_score

    def _weighted_select(
        self,
        providers: List[Dict],
        request_id: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        根据流量权重选择供应商
        使用一致性哈希确保同一请求总是路由到同一供应商
        """
        total_weight = sum(p["rule"].traffic_weight for p in providers)

        if total_weight == 0:
            return providers[0] if providers else None

        # 生成 0-1 之间的哈希值
        if request_id:
            hash_value = int(hashlib.md5(request_id.encode()).hexdigest(), 16) / (2 ** 128)
        else:
            hash_value = hash(str(time.time())) % 10000 / 10000

        # 按权重累积选择
        cumulative = 0
        for item in providers:
            weight = item["rule"].traffic_weight / total_weight
            cumulative += weight
            if hash_value < cumulative:
                return item

        return providers[-1]

    async def _get_default_provider(self) -> Optional[ModelProvider]:
        """获取第一个启用的供应商"""
        query = select(ModelProvider).where(
            ModelProvider.is_enabled == True,
            ModelProvider.status == "active"
        ).order_by(ModelProvider.id).limit(1)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    def _extract_answer_from_reasoning(reasoning_text: str) -> str:
        """
        从 reasoning 文本中提取实际回答（用于 Qwen 等模型）

        Qwen 格式："Thinking Process:\n\n1. ...\n2. ...\n\n*Draft:*\n[实际回答]"
        """
        import re

        # 查找标记思考结束和实际回答开始的模式
        patterns = [
            r"\*Draft:\*\s*\n",           # *Draft:*
            r"\*\*Final Answer\*\*:\s*\n", # **Final Answer**:
            r"\n\n(?:Based on|According to|In summary|综上|因此|所以 | 答案 | 回答 | 你好 | 您好)[:：]?\s*\n",
        ]

        for pattern in patterns:
            match = re.search(pattern, reasoning_text, re.IGNORECASE)
            if match:
                answer = reasoning_text[match.end():].strip()
                if answer and len(answer) > 10:
                    return answer

        # 如果没有找到明确分隔符，返回最后一段
        paragraphs = reasoning_text.split('\n\n')
        if len(paragraphs) > 1:
            last_para = paragraphs[-1].strip()
            if last_para and len(last_para) > 10:
                return last_para

        # 否则返回原文
        return reasoning_text

    async def get_provider_with_failover(
        self,
        primary_provider_id: int,
        model_type: str,
        model_id: Optional[str] = None,
    ) -> Optional[ModelProvider]:
        """
        获取供应商，支持故障转移
        如果主供应商不可用，自动切换到备用供应商
        """
        primary = await self.get_provider_by_id(primary_provider_id)

        if primary and primary.is_enabled and primary.status == "active":
            return primary

        # 主供应商不可用，查找故障转移目标
        if primary and primary.status != "active":
            # 查找有故障转移配置的规则
            rules = await self.get_routing_rules(model_type=model_type, is_enabled=True)
            for rule in rules:
                if rule.provider_id == primary_provider_id and rule.failover_enabled:
                    failover_provider = await self.get_provider_by_id(rule.failover_provider_id)
                    if failover_provider and failover_provider.is_enabled and failover_provider.status == "active":
                        return failover_provider

        # 没有故障转移配置，返回最佳可用供应商
        return await self.get_best_provider(model_type=model_type, model_id=model_id)

    # ========== 调用日志 ==========

    async def log_call(
        self,
        provider_id: int,
        model_id: str,
        model_type: str,
        request_id: str,
        status: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: int = 0,
        first_token_latency_ms: Optional[int] = None,
        error_message: Optional[str] = None,
        error_code: Optional[str] = None,
        cost: Optional[float] = None,
        cached: bool = False,
        user_id: Optional[int] = None,
        app_id: Optional[str] = None,
        kb_id: Optional[str] = None,
        request_summary: Optional[Dict] = None,
        response_summary: Optional[Dict] = None,
    ) -> ModelCallLog:
        """记录模型调用日志"""
        log = ModelCallLog(
            request_id=request_id,
            provider_id=provider_id,
            model_id=model_id,
            model_type=model_type,
            status=status,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            latency_ms=latency_ms,
            first_token_latency_ms=first_token_latency_ms,
            error_message=error_message,
            error_code=error_code,
            cost=cost,
            cached=cached,
            user_id=user_id,
            app_id=app_id,
            kb_id=kb_id,
            request_summary=request_summary,
            response_summary=response_summary,
        )
        self.db.add(log)
        await self.db.flush()
        await self.db.refresh(log)
        return log

    async def get_call_logs(
        self,
        provider_id: Optional[int] = None,
        model_type: Optional[str] = None,
        user_id: Optional[int] = None,
        kb_id: Optional[str] = None,
        status: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ModelCallLog]:
        """获取调用日志列表"""
        query = select(ModelCallLog)

        if provider_id:
            query = query.where(ModelCallLog.provider_id == provider_id)
        if model_type:
            query = query.where(ModelCallLog.model_type == model_type)
        if user_id:
            query = query.where(ModelCallLog.user_id == user_id)
        if kb_id:
            query = query.where(ModelCallLog.kb_id == kb_id)
        if status:
            query = query.where(ModelCallLog.status == status)
        if start_time:
            query = query.where(ModelCallLog.created_at >= start_time)
        if end_time:
            query = query.where(ModelCallLog.created_at <= end_time)

        query = query.order_by(ModelCallLog.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_call_statistics(
        self,
        provider_id: Optional[int] = None,
        model_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """获取调用统计信息"""
        # 基础查询条件
        base_conditions = []
        if provider_id:
            base_conditions.append(ModelCallLog.provider_id == provider_id)
        if model_type:
            base_conditions.append(ModelCallLog.model_type == model_type)
        if start_time:
            base_conditions.append(ModelCallLog.created_at >= start_time)
        if end_time:
            base_conditions.append(ModelCallLog.created_at <= end_time)

        # 总调用次数
        total_query = select(func.count()).select_from(ModelCallLog)
        if base_conditions:
            total_query = total_query.where(and_(*base_conditions))
        total_result = await self.db.execute(total_query)
        total_calls = total_result.scalar() or 0

        # 成功调用次数
        success_query = select(func.count()).select_from(ModelCallLog).where(
            ModelCallLog.status == "success"
        )
        if base_conditions:
            success_query = success_query.where(and_(*base_conditions))
        success_result = await self.db.execute(success_query)
        success_calls = success_result.scalar() or 0

        # 总 Token 数
        tokens_query = select(
            func.sum(ModelCallLog.input_tokens),
            func.sum(ModelCallLog.output_tokens),
            func.sum(ModelCallLog.total_tokens),
        ).select_from(ModelCallLog)
        if base_conditions:
            tokens_query = tokens_query.where(and_(*base_conditions))
        tokens_result = await self.db.execute(tokens_query)
        tokens_row = tokens_result.first()
        input_tokens = tokens_row[0] or 0
        output_tokens = tokens_row[1] or 0
        total_tokens = tokens_row[2] or 0

        # 总成本
        cost_query = select(func.sum(ModelCallLog.cost)).select_from(ModelCallLog)
        if base_conditions:
            cost_query = cost_query.where(and_(*base_conditions))
        cost_result = await self.db.execute(cost_query)
        total_cost = float(cost_result.scalar() or 0)

        # 平均延迟
        latency_query = select(func.avg(ModelCallLog.latency_ms)).select_from(ModelCallLog)
        if base_conditions:
            latency_query = latency_query.where(and_(*base_conditions))
        latency_result = await self.db.execute(latency_query)
        avg_latency = float(latency_result.scalar() or 0)

        # 缓存命中率
        cache_query = select(func.count()).select_from(ModelCallLog).where(
            ModelCallLog.cached == True
        )
        if base_conditions:
            cache_query = cache_query.where(and_(*base_conditions))
        cache_result = await self.db.execute(cache_query)
        cache_hits = cache_result.scalar() or 0
        cache_hit_rate = (cache_hits / total_calls * 100) if total_calls > 0 else 0

        return {
            "total_calls": total_calls,
            "success_calls": success_calls,
            "error_calls": total_calls - success_calls,
            "success_rate": (success_calls / total_calls * 100) if total_calls > 0 else 0,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "total_cost": total_cost,
            "avg_latency_ms": round(avg_latency, 2),
            "cache_hits": cache_hits,
            "cache_hit_rate": round(cache_hit_rate, 2),
        }

    # ========== 缓存管理 ==========

    def _generate_cache_key(
        self,
        model_type: str,
        model_id: str,
        input_content: str,
        params: Optional[Dict] = None,
    ) -> str:
        """生成缓存键"""
        key_data = {
            "model_type": model_type,
            "model_id": model_id,
            "input": input_content,
            "params": params or {},
        }
        key_string = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_string.encode()).hexdigest()

    async def get_cached_response(
        self,
        model_type: str,
        model_id: str,
        input_content: str,
        params: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """获取缓存的响应"""
        cache_key = self._generate_cache_key(model_type, model_id, input_content, params)

        query = select(ModelCache).where(
            ModelCache.cache_key == cache_key,
            ModelCache.expires_at > datetime.utcnow()
        )
        result = await self.db.execute(query)
        cache = result.scalar_one_or_none()

        if cache:
            cache.hit_count += 1
            cache.last_hit_at = datetime.utcnow()
            await self.db.flush()
            return cache.response_data

        return None

    async def cache_response(
        self,
        model_type: str,
        model_id: str,
        input_content: str,
        response_data: Dict,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: int = 0,
        ttl_seconds: int = 3600,
        params: Optional[Dict] = None,
    ) -> ModelCache:
        """缓存响应"""
        cache_key = self._generate_cache_key(model_type, model_id, input_content, params)

        # 检查是否已存在
        existing_query = select(ModelCache).where(ModelCache.cache_key == cache_key)
        existing_result = await self.db.execute(existing_query)
        existing = existing_result.scalar_one_or_none()

        if existing:
            # 更新现有缓存
            existing.response_data = response_data
            existing.expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
            existing.input_tokens = input_tokens
            existing.output_tokens = output_tokens
            existing.latency_ms = latency_ms
            await self.db.flush()
            await self.db.refresh(existing)
            return existing

        # 创建新缓存
        cache = ModelCache(
            cache_key=cache_key,
            model_type=model_type,
            model_id=model_id,
            response_data=response_data,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            ttl_seconds=ttl_seconds,
            expires_at=datetime.utcnow() + timedelta(seconds=ttl_seconds),
        )
        self.db.add(cache)
        await self.db.flush()
        await self.db.refresh(cache)
        return cache

    async def clear_expired_cache(self) -> int:
        """清理过期缓存"""
        query = select(ModelCache).where(ModelCache.expires_at <= datetime.utcnow())
        result = await self.db.execute(query)
        caches = list(result.scalars().all())

        deleted_count = 0
        for cache in caches:
            await self.db.delete(cache)
            deleted_count += 1

        await self.db.flush()
        return deleted_count

    async def get_cache_statistics(self) -> Dict[str, Any]:
        """获取缓存统计"""
        # 总缓存数
        total_query = select(func.count()).select_from(ModelCache)
        total_result = await self.db.execute(total_query)
        total_caches = total_result.scalar() or 0

        # 即将过期的缓存 (5 分钟内)
        expiring_query = select(func.count()).select_from(ModelCache).where(
            ModelCache.expires_at <= datetime.utcnow() + timedelta(minutes=5)
        )
        expiring_result = await self.db.execute(expiring_query)
        expiring_caches = expiring_result.scalar() or 0

        # 总命中次数
        hits_query = select(func.sum(ModelCache.hit_count)).select_from(ModelCache)
        hits_result = await self.db.execute(hits_query)
        total_hits = hits_result.scalar() or 0

        return {
            "total_caches": total_caches,
            "expiring_caches": expiring_caches,
            "total_hits": total_hits,
        }

    # ========== 统一 LLM 调用（支持流式） ==========

    async def call_llm(
        self,
        provider: ModelProvider,
        model_id: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        user_id: Optional[int] = None,
        kb_id: Optional[str] = None,
        model_type: str = "llm",
    ) -> Dict[str, Any]:
        """
        统一 LLM 调用接口
        支持流式和非流式调用，自动记录调用日志

        Args:
            provider: 供应商实例
            model_id: 模型 ID
            messages: OpenAI 格式的消息列表
            temperature: 温度参数
            max_tokens: 最大输出 token 数
            stream: 是否流式输出
            user_id: 用户 ID
            kb_id: 知识库 ID
            model_type: 模型类型 (llm, embedding, rerank, etc.)

        Returns:
            非流式：{"content": str, "usage": dict, "latency_ms": float}
            流式：{"stream": AsyncIterator, "client": httpx.AsyncClient}
        """
        import time
        request_id = str(uuid.uuid4())
        start_time = time.monotonic()

        # 构建 API 请求 - 统一使用供应商的 base_url
        base_url = provider.base_url.rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"

        # 根据模型类型选择不同的 API 端点
        if model_type == "embedding":
            api_url = f"{base_url}/embeddings"
        elif model_type == "rerank":
            api_url = f"{base_url}/rerank"
        else:
            api_url = f"{base_url}/chat/completions"

        logger.info(f"模型调用 | type={model_type}, model={model_id}, url={api_url}")

        headers = {
            "Content-Type": "application/json",
        }

        # 根据认证类型设置认证头
        if provider.auth_type == "api_key" and provider.api_key:
            if provider.api_key_name and provider.api_key_name.lower() != "authorization":
                headers[provider.api_key_name] = provider.api_key
            else:
                headers["Authorization"] = f"Bearer {provider.api_key}"

        # 根据模型类型构建不同的请求体
        if model_type == "embedding":
            # Embedding 请求格式
            request_body = {
                "model": model_id,
                "input": messages[0].get("content", "") if messages else "",
            }
        elif model_type == "rerank":
            # Rerank 请求格式
            request_body = {
                "model": model_id,
                "query": messages[0].get("content", "") if messages else "",
                "documents": messages[0].get("documents", []) if messages else [],
            }
        else:
            # LLM / Chat 请求格式
            request_body = {
                "model": model_id,
                "messages": messages,
                "temperature": temperature,
                "stream": stream,
            }
            if max_tokens is not None:
                request_body["max_tokens"] = max_tokens

        try:
            if stream:
                # Embedding 和 Rerank 模型不支持流式
                if model_type in ("embedding", "rerank"):
                    raise Exception(f"模型类型 '{model_type}' 不支持流式输出，请使用非流式模式")

                # 流式调用 - 使用 Limits 禁用缓冲
                limits = httpx.Limits(
                    max_keepalive_connections=10,
                    max_connections=10,
                    keepalive_expiry=30.0
                )
                client = httpx.AsyncClient(
                    timeout=httpx.Timeout(
                        connect=30.0,
                        read=120.0,
                        write=30.0,
                        pool=10.0
                    ),
                    limits=limits,
                )

                response = await client.send(
                    client.build_request(
                        "POST",
                        api_url,
                        json=request_body,
                        headers=headers,
                    ),
                    stream=True,
                )

                if response.status_code != 200:
                    error_text = await response.aread()
                    await response.aclose()
                    await client.aclose()

                    # 记录错误日志
                    await self.log_call(
                        provider_id=provider.id,
                        model_id=model_id,
                        model_type=model_type,
                        request_id=request_id,
                        status="error",
                        error_message=error_text.decode()[:500],
                        error_code=f"HTTP_{response.status_code}",
                        user_id=user_id,
                        kb_id=kb_id,
                    )

                    raise Exception(f"LLM API error {response.status_code}: {error_text.decode()[:200]}")

                # 返回流式响应
                return {
                    "type": "streaming",
                    "stream": response,
                    "client": client,
                    "request_id": request_id,
                    "provider_id": provider.id,
                    "model_id": model_id,
                    "user_id": user_id,
                    "kb_id": kb_id,
                }

            else:
                # 非流式调用
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(
                        connect=30.0,
                        read=120.0,
                        write=30.0,
                        pool=10.0
                    )
                ) as client:
                    response = await client.post(
                        api_url,
                        json=request_body,
                        headers=headers,
                    )

                    latency_ms = int((time.monotonic() - start_time) * 1000)

                    if response.status_code != 200:
                        # 记录错误日志
                        await self.log_call(
                            provider_id=provider.id,
                            model_id=model_id,
                            model_type=model_type,
                            request_id=request_id,
                            status="error",
                            error_message=response.text[:500],
                            error_code=f"HTTP_{response.status_code}",
                            latency_ms=latency_ms,
                            user_id=user_id,
                            kb_id=kb_id,
                        )

                        raise Exception(f"API error {response.status_code}: {response.text[:200]}")

                    data = response.json()

                    # 根据模型类型解析不同的响应格式
                    if model_type == "embedding":
                        # Embedding 响应格式：{"data": [{"embedding": [...], "index": 0}], "usage": {...}}
                        embedding_data = data.get("data", [])
                        embedding_vector = embedding_data[0].get("embedding", []) if embedding_data else []
                        usage = data.get("usage", {})
                        input_tokens = usage.get("prompt_tokens", 0)

                        await self.log_call(
                            provider_id=provider.id,
                            model_id=model_id,
                            model_type="embedding",
                            request_id=request_id,
                            status="success",
                            input_tokens=input_tokens,
                            output_tokens=0,
                            latency_ms=latency_ms,
                            user_id=user_id,
                            kb_id=kb_id,
                            request_summary={"input_length": len(messages[0].get("content", "")) if messages else 0},
                            response_summary={"embedding_dim": len(embedding_vector)},
                        )

                        return {
                            "type": "complete",
                            "embedding": embedding_vector,
                            "usage": usage,
                            "latency_ms": latency_ms,
                            "request_id": request_id,
                        }

                    elif model_type == "rerank":
                        # Rerank 响应格式：{"results": [{"index": 0, "score": 0.95}] 或 [{"index": 0, "relevance_score": 0.95}]}
                        results = data.get("results", [])
                        usage = data.get("usage", {})

                        # 标准化字段名：relevance_score -> score
                        normalized_results = []
                        for r in results:
                            normalized = dict(r)
                            if "relevance_score" in r and "score" not in r:
                                normalized["score"] = r["relevance_score"]
                            normalized_results.append(normalized)

                        await self.log_call(
                            provider_id=provider.id,
                            model_id=model_id,
                            model_type="rerank",
                            request_id=request_id,
                            status="success",
                            latency_ms=latency_ms,
                            user_id=user_id,
                            kb_id=kb_id,
                            request_summary={"documents_count": len(messages[0].get("documents", [])) if messages else 0},
                            response_summary={"results_count": len(normalized_results)},
                        )

                        return {
                            "type": "complete",
                            "results": normalized_results,
                            "usage": usage,
                            "latency_ms": latency_ms,
                            "request_id": request_id,
                        }

                    else:
                        # LLM / Chat 响应格式
                        message = data["choices"][0]["message"]
                        content = message.get("content") or ""  # 处理 content 为 null 的情况
                        reasoning = message.get("reasoning", "")

                        # 如果 content 为空但 reasoning 有值，从 reasoning 中提取答案
                        # Qwen 模型格式："Thinking Process:\n\n1. ...\n2. ...\n\n[实际回答]"
                        if not content and reasoning:
                            content = self._extract_answer_from_reasoning(reasoning)

                        # 提取 token 使用
                        usage = data.get("usage", {})
                        input_tokens = usage.get("prompt_tokens", 0)
                        output_tokens = usage.get("completion_tokens", 0)
                        total_tokens = usage.get("total_tokens", input_tokens + output_tokens)

                        # 计算成本
                        cost = None
                        if provider.cost_input is not None and provider.cost_output is not None:
                            cost = (float(provider.cost_input) * input_tokens / 1000 +
                                    float(provider.cost_output) * output_tokens / 1000)

                        # 记录调用日志
                        await self.log_call(
                            provider_id=provider.id,
                            model_id=model_id,
                            model_type="llm",
                            request_id=request_id,
                            status="success",
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            latency_ms=latency_ms,
                            cost=cost,
                            user_id=user_id,
                            kb_id=kb_id,
                            request_summary={"messages_count": len(messages), "temperature": temperature},
                            response_summary={"content_length": len(content)},
                        )

                        return {
                            "type": "complete",
                            "content": content,
                            "reasoning": reasoning,
                            "usage": usage,
                            "latency_ms": latency_ms,
                            "cost": cost,
                            "request_id": request_id,
                        }

        except httpx.RequestError as e:
            latency_ms = int((time.monotonic() - start_time) * 1000)
            await self.log_call(
                provider_id=provider.id,
                model_id=model_id,
                model_type=model_type,
                request_id=request_id,
                status="error",
                error_message=str(e),
                error_code="REQUEST_ERROR",
                latency_ms=latency_ms,
                user_id=user_id,
                kb_id=kb_id,
            )
            raise

    async def stream_llm_response(
        self,
        request_data: Dict[str, Any],
    ) -> AsyncIterator[str]:
        """
        处理流式 LLM 响应，直接转发原始 OpenAI 格式 SSE 数据

        Args:
            request_data: call_llm 返回的流式响应数据

        Yields:
            SSE 格式的事件字符串（OpenAI 兼容格式）
        """
        stream = request_data.get("stream")
        client = request_data.get("client")
        provider_id = request_data.get("provider_id")
        model_id = request_data.get("model_id")
        request_id = request_data.get("request_id")
        user_id = request_data.get("user_id")
        kb_id = request_data.get("kb_id")

        if not stream or not client:
            return

        content_buffer = ""
        reasoning_buffer = ""
        input_tokens = 0
        output_tokens = 0
        start_time = time.monotonic()

        try:
            # 使用 aiter_lines 按行读取，避免 UTF-8 字符被切断
            # 上游返回的已经是完整的 SSE 格式，直接转发，确保每个事件以 \n\n 结尾
            done_received = False
            chunk_count = 0
            chunk_start_time = time.monotonic()
            async for line in stream.aiter_lines():
                chunk_count += 1
                chunk_current_time = time.monotonic()
                chunk_elapsed_ms = int((chunk_current_time - chunk_start_time) * 1000)
                total_elapsed_ms = int((chunk_current_time - start_time) * 1000)

                if line.strip():
                    # 打印模型原生层的流式数据返回日志
                    logger.info(
                        "[Stream Chunk #%d] +%dms (总计：%dms) | provider_id=%s model_id=%s | data: %.80s...",
                        chunk_count, chunk_elapsed_ms, total_elapsed_ms,
                        provider_id, model_id, line.strip()
                    )
                    yield line + '\n\n'

                    if line.strip() == 'data: [DONE]':
                        done_received = True
                        break

            if not done_received:
                yield 'data: [DONE]\n\n'

            # 读取完成后记录日志
            latency_ms = int((time.monotonic() - start_time) * 1000)
            await self.log_call(
                provider_id=provider_id,
                model_id=model_id,
                model_type=model_type,
                request_id=request_id,
                status="success",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                user_id=user_id,
                kb_id=kb_id,
                request_summary={"streaming": True},
                response_summary={"content_length": len(content_buffer)},
            )

        except Exception as e:
            logger.exception("Stream processing error: %s", e)
            # OpenAI 格式错误响应
            yield f"data: {json.dumps({'error': {'message': str(e)}})}\n\n"
            yield 'data: [DONE]\n\n'
        finally:
            # 清理资源 - 确保连接关闭
            try:
                await stream.aclose()
            except Exception:
                pass
            try:
                await client.aclose()
            except Exception:
                pass

    # ========== 熔断器管理 ==========

    def __init__(self, db: AsyncSession):
        self.db = db
        self._circuit_breakers: Dict[int, CircuitBreaker] = {}

    def get_circuit_breaker(self, provider_id: int) -> CircuitBreaker:
        """获取或创建供应商的熔断器"""
        if provider_id not in self._circuit_breakers:
            self._circuit_breakers[provider_id] = CircuitBreaker()
        return self._circuit_breakers[provider_id]

    def reset_circuit_breaker(self, provider_id: int) -> None:
        """重置供应商的熔断器"""
        if provider_id in self._circuit_breakers:
            self._circuit_breakers[provider_id] = CircuitBreaker()

    async def call_llm_with_retry(
        self,
        provider: ModelProvider,
        model_id: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        user_id: Optional[int] = None,
        kb_id: Optional[str] = None,
        model_type: str = "llm",
        retry_config: Optional[RetryConfig] = None,
    ) -> Dict[str, Any]:
        """
        带重试和熔断器的 LLM 调用

        Args:
            provider: 供应商实例
            model_id: 模型 ID
            messages: OpenAI 格式的消息列表
            temperature: 温度参数
            max_tokens: 最大输出 token 数
            stream: 是否流式输出
            user_id: 用户 ID
            kb_id: 知识库 ID
            model_type: 模型类型 (llm, embedding, rerank, etc.)
            retry_config: 重试配置，None 则使用默认配置

        Returns:
            同 call_llm

        Raises:
            CircuitBreakerOpenError: 熔断器打开
            Exception: 所有重试失败
        """
        # 检查熔断器
        circuit_breaker = self.get_circuit_breaker(provider.id)

        if not circuit_breaker.can_execute():
            logger.warning("Circuit breaker open for provider %s", provider.name)
            await self.log_call(
                provider_id=provider.id,
                model_id=model_id,
                model_type=model_type,
                request_id=str(uuid.uuid4()),
                status="error",
                error_message="Circuit breaker open",
                error_code="CIRCUIT_BREAKER_OPEN",
                user_id=user_id,
                kb_id=kb_id,
            )
            raise Exception(f"Circuit breaker open for provider {provider.name}")

        # 流式调用不使用 retry_with_backoff（会缓冲整个响应）
        # 直接调用 call_llm，让 StreamingResponse 逐行返回
        if stream:
            try:
                result = await self.call_llm(
                    provider=provider,
                    model_id=model_id,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=stream,
                    user_id=user_id,
                    kb_id=kb_id,
                    model_type=model_type,
                )
                circuit_breaker.record_success()
                return result
            except Exception as e:
                circuit_breaker.record_failure()
                raise

        # 非流式调用使用完整重试机制
        if retry_config is None:
            retry_config = RetryConfig(
                max_attempts=3,
                initial_delay_ms=100,
                max_delay_ms=5000,
                exponential_base=2.0,
                jitter=True,
            )

        async def _call():
            result = await self.call_llm(
                provider=provider,
                model_id=model_id,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream,
                user_id=user_id,
                kb_id=kb_id,
                model_type=model_type,
            )
            # 成功调用，重置熔断器
            circuit_breaker.record_success()
            return result

        try:
            return await retry_with_backoff(_call, retry_config)
        except Exception as e:
            # 失败调用，记录熔断器
            circuit_breaker.record_failure()
            raise

    async def get_provider_health(self, provider_id: int) -> Dict[str, Any]:
        """获取供应商健康状态（包括熔断器状态）"""
        provider = await self.get_provider_by_id(provider_id)
        if not provider:
            raise Exception("Provider not found")

        circuit_breaker = self.get_circuit_breaker(provider_id)

        return {
            "provider_id": provider_id,
            "provider_name": provider.name,
            "status": provider.status,
            "health_status": provider.health_status,
            "consecutive_failures": provider.consecutive_failures,
            "last_health_check": provider.last_health_check,
            "circuit_breaker_state": circuit_breaker.get_state(),
            "circuit_breaker_failures": circuit_breaker.failure_count,
        }

    # ========== 健康检查 ==========

    async def check_provider_health(
        self,
        provider: ModelProvider,
        timeout_ms: int = 5000,
    ) -> Dict[str, Any]:
        """
        检查供应商健康状态

        Args:
            provider: 供应商实例
            timeout_ms: 超时时间（毫秒）

        Returns:
            {"healthy": bool, "latency_ms": int, "error": Optional[str]}
        """
        import time

        # 构建健康检查请求
        base_url = provider.base_url.rstrip("/")

        # 不同供应商的健康检查端点
        if provider.provider_type == "openai" or provider.code == "openai":
            health_url = f"{base_url}/v1/models"
        elif provider.provider_type == "anthropic" or provider.code == "anthropic":
            health_url = f"{base_url}/v1/models"
        elif provider.provider_type == "google" or provider.code == "google":
            health_url = f"{base_url}/models"
        elif provider.code == "ollama":
            health_url = f"{base_url}/api/tags"
        elif provider.code == "vllm":
            health_url = f"{base_url}/v1/models"
        else:
            # 默认使用 /v1/models 作为健康检查端点
            if not base_url.endswith("/v1"):
                health_url = f"{base_url}/v1/models"
            else:
                health_url = f"{base_url}/models"

        headers = {"Content-Type": "application/json"}
        if provider.api_key:
            if provider.api_key_name and provider.api_key_name.lower() != "authorization":
                headers[provider.api_key_name] = provider.api_key
            else:
                headers["Authorization"] = f"Bearer {provider.api_key}"

        start_time = time.monotonic()

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout_ms / 1000)
            ) as client:
                response = await client.get(health_url, headers=headers)

                latency_ms = int((time.monotonic() - start_time) * 1000)

                if response.status_code == 200:
                    return {
                        "healthy": True,
                        "latency_ms": latency_ms,
                        "status_code": response.status_code,
                    }
                else:
                    return {
                        "healthy": False,
                        "latency_ms": latency_ms,
                        "status_code": response.status_code,
                        "error": response.text[:200],
                    }

        except httpx.TimeoutException:
            return {
                "healthy": False,
                "latency_ms": int((time.monotonic() - start_time) * 1000),
                "error": "Timeout",
            }
        except httpx.RequestError as e:
            return {
                "healthy": False,
                "latency_ms": int((time.monotonic() - start_time) * 1000),
                "error": str(e),
            }

    async def update_provider_health_from_check(
        self,
        provider_id: int,
        check_result: Dict[str, Any],
    ) -> None:
        """
        根据健康检查结果更新供应商状态

        Args:
            provider_id: 供应商 ID
            check_result: 健康检查结果
        """
        provider = await self.get_provider_by_id(provider_id)
        if not provider:
            return

        if check_result.get("healthy"):
            provider.health_status = "healthy"
            provider.consecutive_failures = 0
            if provider.status == "error":
                provider.status = "active"
        else:
            provider.consecutive_failures += 1
            error = check_result.get("error", "Unknown error")

            if "Timeout" in error:
                provider.health_status = "timeout"
            else:
                provider.health_status = "error"

            if provider.consecutive_failures >= 5:
                provider.status = "error"

        provider.last_health_check = datetime.utcnow()
        await self.db.flush()

    async def run_health_check_all_providers(
        self,
        timeout_ms: int = 5000,
    ) -> Dict[str, Any]:
        """
        运行所有供应商的健康检查

        Args:
            timeout_ms: 每个供应商的超时时间

        Returns:
            健康检查结果汇总
        """
        providers = await self.get_providers()

        results = []
        healthy_count = 0
        unhealthy_count = 0

        for provider in providers:
            if not provider.is_enabled:
                continue

            check_result = await self.check_provider_health(provider, timeout_ms)
            await self.update_provider_health_from_check(provider.id, check_result)

            result = {
                "provider_id": provider.id,
                "provider_name": provider.name,
                "provider_code": provider.code,
                **check_result,
            }
            results.append(result)

            if check_result.get("healthy"):
                healthy_count += 1
            else:
                unhealthy_count += 1

        return {
            "total_checked": len(results),
            "healthy": healthy_count,
            "unhealthy": unhealthy_count,
            "results": results,
            "checked_at": datetime.utcnow().isoformat(),
        }

    # ========== 限流和配额管理 ==========

    async def check_rate_limit(
        self,
        user_id: Optional[int] = None,
        kb_id: Optional[str] = None,
        provider_id: Optional[int] = None,
        model_type: str = "llm",
    ) -> Dict[str, Any]:
        """
        检查调用限流

        Args:
            user_id: 用户 ID
            kb_id: 知识库 ID
            provider_id: 供应商 ID
            model_type: 模型类型

        Returns:
            {"allowed": bool, "remaining": int, "reset_at": str, "retry_after": int}
        """
        from app.core.database import async_session_factory
        from app.models.token_usage import TokenUsage
        from sqlalchemy import select, func

        # 获取限流配置（从供应商或系统配置）
        provider = None
        if provider_id:
            provider = await self.get_provider_by_id(provider_id)

        rate_limit_enabled = provider.rate_limit_enabled if provider else False
        rate_limit_requests = provider.rate_limit_requests if provider else None
        rate_limit_tokens = provider.rate_limit_tokens if provider else None

        if not rate_limit_enabled:
            return {"allowed": True, "remaining": -1, "reset_at": None, "retry_after": 0}

        # 计算当前分钟的开始时间
        now = datetime.utcnow()
        minute_start = now.replace(second=0, microsecond=0)

        # 查询当前分钟内的调用次数
        conditions = [
            TokenUsage.created_at >= minute_start,
        ]

        if user_id:
            conditions.append(TokenUsage.user_id == user_id)

        if provider_id:
            # 通过 model_config 关联 provider
            from app.models.model_config import ModelConfig
            conditions.append(TokenUsage.model_config_id == ModelConfig.id)
            conditions.append(ModelConfig.provider == provider.code)

        query = select(func.count()).select_from(TokenUsage)
        if len(conditions) > 1:
            from sqlalchemy import and_
            query = query.where(and_(*conditions))
        elif len(conditions) == 1:
            query = query.where(conditions[0])

        async with async_session_factory() as session:
            result = await session.execute(query)
            call_count = result.scalar() or 0

        # 检查是否超过限制
        if rate_limit_requests and call_count >= rate_limit_requests:
            reset_at = minute_start.replace(minute=minute_start.minute + 1)
            retry_after = int((reset_at - now).total_seconds())

            return {
                "allowed": False,
                "remaining": 0,
                "reset_at": reset_at.isoformat(),
                "retry_after": max(1, retry_after),
            }

        remaining = rate_limit_requests - call_count if rate_limit_requests else -1

        return {
            "allowed": True,
            "remaining": remaining,
            "reset_at": minute_start.replace(minute=minute_start.minute + 1).isoformat(),
            "retry_after": 0,
        }

    async def check_quota(
        self,
        user_id: Optional[int] = None,
        kb_id: Optional[str] = None,
        model_type: str = "llm",
        requested_tokens: int = 1000,
    ) -> Dict[str, Any]:
        """
        检查配额

        Args:
            user_id: 用户 ID
            kb_id: 知识库 ID
            model_type: 模型类型
            requested_tokens: 请求的 token 数

        Returns:
            {"allowed": bool, "remaining_quota": int, "quota_limit": int, "period": str}
        """
        from app.core.database import async_session_factory
        from app.models.token_usage import TokenUsage
        from sqlalchemy import select, func

        # 获取配额配置（这里使用默认配置，实际可以从数据库或配置中心获取）
        # 默认配额：每用户每天 100K tokens
        default_quota_limit = 100000
        period = "daily"

        # 计算今天的开始时间
        now = datetime.utcnow()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # 查询今天已使用的 tokens
        conditions = [
            TokenUsage.created_at >= day_start,
        ]

        if user_id:
            conditions.append(TokenUsage.user_id == user_id)

        from sqlalchemy import and_
        query = select(func.sum(TokenUsage.total_tokens)).select_from(TokenUsage)
        if len(conditions) > 1:
            query = query.where(and_(*conditions))
        elif len(conditions) == 1:
            query = query.where(conditions[0])

        async with async_session_factory() as session:
            result = await session.execute(query)
            used_tokens = result.scalar() or 0

        remaining_quota = default_quota_limit - used_tokens

        if requested_tokens > remaining_quota:
            return {
                "allowed": False,
                "remaining_quota": remaining_quota,
                "quota_limit": default_quota_limit,
                "used_quota": used_tokens,
                "period": period,
            }

        return {
            "allowed": True,
            "remaining_quota": remaining_quota,
            "quota_limit": default_quota_limit,
            "used_quota": used_tokens,
            "period": period,
        }

    async def record_usage_with_quota(
        self,
        user_id: int,
        total_tokens: int,
        model_type: str = "llm",
        provider_code: Optional[str] = None,
        request_type: str = "chat",
    ) -> bool:
        """
        记录使用量并更新配额

        Args:
            user_id: 用户 ID
            total_tokens: 使用的 token 数
            model_type: 模型类型
            provider_code: 供应商代码
            request_type: 请求类型

        Returns:
            是否记录成功
        """
        from app.core.database import async_session_factory
        from app.models.token_usage import TokenUsage

        try:
            async with async_session_factory() as session:
                usage = TokenUsage(
                    user_id=user_id,
                    model_config_id=None,
                    model_name=provider_code or "unknown",
                    model_type=model_type,
                    provider=provider_code or "unknown",
                    input_tokens=0,
                    output_tokens=total_tokens,
                    total_tokens=total_tokens,
                    latency_ms=0,
                    request_type=request_type,
                    status="success",
                )
                session.add(usage)
                await session.commit()
                return True
        except Exception as e:
            logger.error("Failed to record usage with quota: %s", e)
            return False
