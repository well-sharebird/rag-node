"""
LLM 主备 Fallback 链服务
主模型故障时自动降级到备用模型（如 API→Ollama→本地）
"""
from __future__ import annotations
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import asyncio

logger = logging.getLogger("app.services.llm_fallback")


class ModelTier(Enum):
    """模型优先级"""
    PRIMARY = "primary"       # 主模型（如 GPT-4/Claude）
    SECONDARY = "secondary"   # 次选（如 DeepSeek/Qwen）
    TERTIARY = "tertiary"     # 第三选择（如 Ollama 本地）
    FALLBACK = "fallback"     # 最终 fallback（如随机/规则）


@dataclass
class ModelConfig:
    """模型配置"""
    name: str
    tier: ModelTier
    provider: str  # api, ollama, vllm, local
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    model_id: Optional[str] = None
    timeout: float = 30.0
    max_retries: int = 2
    weight: float = 1.0  # 负载均衡权重


@dataclass
class FallbackResult:
    """Fallback 执行结果"""
    success: bool
    model_used: str
    tier_used: ModelTier
    response: Any
    latency_ms: float
    attempts: int
    error_history: List[str] = field(default_factory=list)


class LLMFallbackChain:
    """
    LLM Fallback 链
    按优先级尝试多个模型，直到成功
    """

    def __init__(self, models: List[ModelConfig]):
        """
        初始化 Fallback 链

        Args:
            models: 模型配置列表（按优先级排序）
        """
        # 按 tier 排序
        tier_order = {
            ModelTier.PRIMARY: 0,
            ModelTier.SECONDARY: 1,
            ModelTier.TERTIARY: 2,
            ModelTier.FALLBACK: 3,
        }
        self.models = sorted(models, key=lambda m: tier_order[m.tier])
        self._model_services: Dict[str, Any] = {}

    def _get_model_service(self, model: ModelConfig):
        """获取或创建模型服务实例"""
        from packages.model_gateway.services.llm_service import LLMService

        if model.name not in self._model_services:
            service = LLMService(
                provider=model.provider,
                model_name=model.model_id,
                api_url=model.api_url,
                api_key=model.api_key,
            )
            self._model_services[model.name] = service

        return self._model_services[model.name]

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        timeout_override: Optional[float] = None,
    ) -> FallbackResult:
        """
        执行带 fallback 的文本生成

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            temperature: 温度参数
            max_tokens: 最大 token 数
            timeout_override: 覆盖默认超时

        Returns:
            FallbackResult 包含结果和元数据
        """
        error_history = []

        for i, model in enumerate(self.models):
            logger.info("Trying model | tier=%s name=%s (attempt %d/%d)",
                       model.tier.value, model.name, i + 1, len(self.models))

            timeout = timeout_override or model.timeout
            start_time = asyncio.get_event_loop().time()

            try:
                service = self._get_model_service(model)

                # 带超时和重试的调用
                response = await self._call_with_retry(
                    service=service,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                    max_retries=model.max_retries,
                )

                latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000

                logger.info("Model succeeded | name=%s latency=%.0fms", model.name, latency_ms)

                return FallbackResult(
                    success=True,
                    model_used=model.name,
                    tier_used=model.tier,
                    response=response,
                    latency_ms=latency_ms,
                    attempts=i + 1,
                    error_history=error_history,
                )

            except asyncio.TimeoutError as e:
                error_history.append(f"{model.name}: Timeout ({timeout}s)")
                logger.warning("Model timeout | name=%s timeout=%.1fs", model.name, timeout)

            except Exception as e:
                error_history.append(f"{model.name}: {type(e).__name__}: {e}")
                logger.warning("Model failed | name=%s error=%s", model.name, e)

        # 所有模型都失败
        logger.error("All models in fallback chain failed | errors=%s", error_history)

        return FallbackResult(
            success=False,
            model_used="",
            tier_used=self.models[-1].tier if self.models else ModelTier.FALLBACK,
            response=None,
            latency_ms=0,
            attempts=len(self.models),
            error_history=error_history,
        )

    async def _call_with_retry(
        self,
        service: Any,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
        timeout: float,
        max_retries: int,
    ) -> str:
        """带重试的模型调用"""
        last_error = None

        for attempt in range(max_retries):
            try:
                # 带超时的调用
                response = await asyncio.wait_for(
                    service.generate(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    ),
                    timeout=timeout,
                )
                return response

            except asyncio.TimeoutError:
                raise  # 超时直接抛出

            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # 指数退避
                    logger.warning("Retry after %.1fs | attempt=%d error=%s", wait_time, attempt + 1, e)
                    await asyncio.sleep(wait_time)
                else:
                    raise last_error

        raise last_error or RuntimeError("Unknown error")

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ):
        """
        执行带 fallback 的流式生成

        注意：流式模式下 fallback 较复杂，这里简化处理
        """
        # 流式模式只使用主模型，不支持 fallback
        if not self.models:
            return

        model = self.models[0]  # 只使用主模型
        service = self._get_model_service(model)

        async for chunk in service.generate_stream(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield chunk


class SmartFallbackChain(LLMFallbackChain):
    """
    智能 Fallback 链
    根据错误类型和历史成功率动态调整优先级
    """

    def __init__(self, models: List[ModelConfig]):
        super().__init__(models)
        self._success_counts: Dict[str, int] = {m.name: 0 for m in models}
        self._failure_counts: Dict[str, int] = {m.name: 0 for m in models}
        self._latencies: Dict[str, List[float]] = {m.name: [] for m in models}

    def _update_stats(self, model_name: str, success: bool, latency_ms: float):
        """更新模型统计信息"""
        if success:
            self._success_counts[model_name] = self._success_counts.get(model_name, 0) + 1
        else:
            self._failure_counts[model_name] = self._failure_counts.get(model_name, 0) + 1

        # 保留最近 100 次延迟
        self._latencies[model_name].append(latency_ms)
        if len(self._latencies[model_name]) > 100:
            self._latencies[model_name] = self._latencies[model_name][-100:]

    def get_model_ranking(self) -> List[str]:
        """
        根据历史成功率获取动态排名
        """
        scores = {}
        for model in self.models:
            name = model.name
            success = self._success_counts.get(name, 0)
            failure = self._failure_counts.get(name, 0)
            total = success + failure

            if total == 0:
                # 没有历史数据，使用默认优先级
                scores[name] = float('-inf') - list(self._success_counts.keys()).index(name)
            else:
                success_rate = success / total
                avg_latency = sum(self._latencies.get(name, [3000])) / max(len(self._latencies.get(name, [1])), 1)
                # 分数 = 成功率 * 100 - 延迟惩罚
                scores[name] = success_rate * 100 - (avg_latency / 1000)

        return sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> FallbackResult:
        """重写 generate 以更新统计信息"""
        result = await super().generate(
            prompt, system_prompt, temperature, max_tokens
        )

        # 更新统计
        self._update_stats(
            result.model_used,
            result.success,
            result.latency_ms,
        )

        return result


# ============================================================
# 预配置的 Fallback 链
# ============================================================

def create_standard_fallback_chain(
    primary_api_url: str = "",
    primary_api_key: str = "",
    primary_model: str = "gpt-4o",
    ollama_url: str = "http://localhost:11434/v1",
    ollama_model: str = "qwen2.5:7b",
    local_model: str = "Qwen/Qwen2.5-7B-Instruct",
) -> SmartFallbackChain:
    """
    创建标准 Fallback 链配置

    优先级:
    1. 主 API (GPT-4/Claude/DeepSeek)
    2. Ollama 本地部署
    3. 本地 Transformers
    """
    models = [
        ModelConfig(
            name="primary_api",
            tier=ModelTier.PRIMARY,
            provider="api",
            api_url=primary_api_url,
            api_key=primary_api_key,
            model_id=primary_model,
            timeout=60.0,
            max_retries=2,
        ),
        ModelConfig(
            name="ollama",
            tier=ModelTier.SECONDARY,
            provider="ollama",
            api_url=ollama_url,
            api_key="ollama",
            model_id=ollama_model,
            timeout=30.0,
            max_retries=1,
        ),
        ModelConfig(
            name="local",
            tier=ModelTier.TERTIARY,
            provider="local",
            model_id=local_model,
            timeout=30.0,
            max_retries=1,
        ),
    ]

    return SmartFallbackChain(models)


# Global instance
_fallback_chain: Optional[SmartFallbackChain] = None


def get_llm_fallback_chain(
    primary_api_url: str = "",
    primary_api_key: str = "",
    primary_model: str = "gpt-4o",
    ollama_url: str = "http://localhost:11434/v1",
    ollama_model: str = "qwen2.5:7b",
) -> SmartFallbackChain:
    """Get or create LLM fallback chain"""
    global _fallback_chain
    if _fallback_chain is None:
        _fallback_chain = create_standard_fallback_chain(
            primary_api_url=primary_api_url,
            primary_api_key=primary_api_key,
            primary_model=primary_model,
            ollama_url=ollama_url,
            ollama_model=ollama_model,
        )
    return _fallback_chain


def reset_llm_fallback_chain():
    """Reset the global fallback chain"""
    global _fallback_chain
    _fallback_chain = None
