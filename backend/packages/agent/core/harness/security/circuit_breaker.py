"""熔断器 - Harness 安全子系统（设计文档 2.6）

状态机：CLOSED（正常）→ OPEN（熔断）→ HALF_OPEN（半开探测）→ CLOSED/OPEN。

- CLOSED：放行请求；连续失败达到 failure_threshold → 转 OPEN。
- OPEN：拒绝请求（降级）；经过 open_timeout → 转 HALF_OPEN。
- HALF_OPEN：放行一个探测请求；成功 → 复位 CLOSED，失败 → 回到 OPEN。
"""
from __future__ import annotations

import time
from enum import Enum


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, open_timeout: float = 30.0):
        self.failure_threshold = int(failure_threshold)
        self.open_timeout = float(open_timeout)
        self.state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at: float = 0.0

    @property
    def is_open(self) -> bool:
        if self.state == CircuitState.OPEN and time.monotonic() >= self._opened_at + self.open_timeout:
            self.state = CircuitState.HALF_OPEN
        return self.state == CircuitState.OPEN

    def record_success(self) -> None:
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at = 0.0

    def record_failure(self) -> None:
        if self.state == CircuitState.CLOSED:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._open()
        elif self.state == CircuitState.HALF_OPEN:
            self._open()

    def _open(self) -> None:
        self.state = CircuitState.OPEN
        self._opened_at = time.monotonic()
        self._failures = 0
