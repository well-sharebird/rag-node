"""限流原语 - Harness 安全子系统（设计文档 2.6）

提供两种常用限流算法：
- TokenBucket：令牌桶，允许突发，按固定速率补充。
- SlidingWindowCounter：滑动窗口，精确限制窗口内请求数。

纯内存实现，Key 由调用方（ToolExecutionManager）按 user 或 tool 构造。
"""
from __future__ import annotations

import time
from collections import deque
from typing import Deque, Dict, Optional


class TokenBucket:
    """令牌桶限流。

    capacity: 桶容量（最大突发量）
    refill_rate: 每秒补充令牌数
    """

    def __init__(self, capacity: float, refill_rate: float):
        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate)
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()

    def consume(self, tokens: float = 1.0) -> bool:
        """尝试消费 tokens，足额返回 True，否则返回 False。"""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_rate)
        self._last_refill = now
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False


class SlidingWindowCounter:
    """滑动窗口计数器限流。

    window_seconds: 窗口时长
    max_requests:   窗口内允许的最大请求数
    """

    def __init__(self, window_seconds: float, max_requests: int):
        self.window_seconds = float(window_seconds)
        self.max_requests = int(max_requests)
        self._timestamps: Deque[float] = deque()

    def allow(self) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()
        if len(self._timestamps) >= self.max_requests:
            return False
        self._timestamps.append(now)
        return True


def make_rate_limiter(mode: str, **params) -> object:
    """按配置构造限流器。

    mode: "token_bucket" | "sliding_window"
    """
    if mode == "token_bucket":
        return TokenBucket(
            capacity=params.get("capacity", 10),
            refill_rate=params.get("refill_rate", 1.0),
        )
    if mode == "sliding_window":
        return SlidingWindowCounter(
            window_seconds=params.get("window_seconds", 60),
            max_requests=params.get("max_requests", 60),
        )
    raise ValueError(f"未知限流模式: {mode}")


class RateLimiterRegistry:
    """按 key 构造/缓存限流器实例，供工具门按 user/tool 键控。"""

    def __init__(self, mode: str, params: Dict):
        self._mode = mode
        self._params = params
        self._buckets: Dict[str, object] = {}

    def allow(self, key: str) -> bool:
        limiter = self._buckets.get(key)
        if limiter is None:
            limiter = make_rate_limiter(self._mode, **self._params)
            self._buckets[key] = limiter
        if isinstance(limiter, TokenBucket):
            return limiter.consume()
        return limiter.allow()

    def __len__(self) -> int:
        return len(self._buckets)
