"""重试策略 - Harness 韧性/降级机制（与熔断 circuit_breaker.py 同属 resilience）

提供指数退避的异步重试执行器，仅对可重试异常进行重试。
纯函数、无外部依赖。重试（with_retry）+ 熔断（CircuitBreaker）共同构成
Harness 对下游执行调用的降级保护。
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional, Tuple, Type

logger = logging.getLogger(__name__)


@dataclass
class RetryPolicy:
    """重试策略配置"""

    max_retries: int = 3
    delay_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    # 仅对这些异常类型重试；留空表示重试所有 Exception 子类
    retryable_exceptions: Tuple[Type[BaseException], ...] = field(
        default_factory=lambda: (Exception,)
    )
    # 可选：给定异常判断是否重试（返回 False 则不重试）
    should_retry: Optional[Callable[[BaseException], bool]] = None

    def is_retryable(self, exc: BaseException) -> bool:
        """判断异常是否应重试"""
        if self.should_retry is not None:
            try:
                return self.should_retry(exc)
            except Exception:  # noqa: BLE001 - 回调异常不阻断重试冒泡
                return False
        return isinstance(exc, self.retryable_exceptions)


async def with_retry(
    coro_factory: Callable[[], Awaitable[Any]],
    policy: Optional[RetryPolicy] = None,
) -> Any:
    """以重试策略执行一个异步协程工厂。

    Args:
        coro_factory: 返回协程的可调用对象（每次重试新建，避免复用失败的协程）
        policy: 重试策略，默认 max_retries=3

    Returns:
        协程成功执行的结果。

    Raises:
        最后一次尝试的异常（重试耗尽或异常不可重试）。
    """
    policy = policy or RetryPolicy()

    last_exc: Optional[BaseException] = None
    for attempt in range(policy.max_retries + 1):
        try:
            return await coro_factory()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - 需捕获任意异常以判断重试
            last_exc = exc
            if not policy.is_retryable(exc):
                logger.info("非可重试异常，不再重试: %s | exc=%s", exc.__class__.__name__, exc)
                raise
            if attempt >= policy.max_retries:
                logger.warning("重试耗尽 (%d/%d): %s", attempt, policy.max_retries, exc)
                raise
            delay = policy.delay_seconds * (policy.backoff_multiplier ** attempt)
            logger.info("执行失败，%.1fs 后重试 (%d/%d): %s",
                        delay, attempt + 1, policy.max_retries, exc)
            await asyncio.sleep(delay)

    raise last_exc  # pragma: no cover - 理论不可达
