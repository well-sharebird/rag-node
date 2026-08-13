"""偏差3：Harness 限流单测"""
import time

import pytest

from packages.agent.core.harness.security.rate_limit import (
    TokenBucket,
    SlidingWindowCounter,
    make_rate_limiter,
)


def test_token_bucket_allows_burst_then_limits():
    # capacity=2：突发允许 2，随后 refill_rate=0 → 不再放行
    bucket = TokenBucket(capacity=2, refill_rate=0.0)
    assert bucket.consume() is True
    assert bucket.consume() is True
    assert bucket.consume() is False  # 容量用尽，无补充


def test_token_bucket_refills_over_time():
    bucket = TokenBucket(capacity=5, refill_rate=1.0)
    assert bucket.consume() is True  # tokens 5->4
    bucket._tokens = 0.0  # 模拟令牌耗尽
    bucket._last_refill = time.monotonic() - 2.0  # 模拟 2 秒后
    assert bucket.consume() is True  # 已补充 2 个令牌


def test_sliding_window_limits_count():
    counter = SlidingWindowCounter(window_seconds=60.0, max_requests=3)
    assert counter.allow() is True
    assert counter.allow() is True
    assert counter.allow() is True
    assert counter.allow() is False  # 超过窗口上限


def test_make_rate_limiter_modes():
    tb = make_rate_limiter("token_bucket", capacity=1, refill_rate=0.0)
    assert isinstance(tb, TokenBucket)
    sw = make_rate_limiter("sliding_window", window_seconds=60, max_requests=1)
    assert isinstance(sw, SlidingWindowCounter)
    with pytest.raises(ValueError):
        make_rate_limiter("bogus")
