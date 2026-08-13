"""Harness 核心层 - 生产治理管控（设计文档 2）——统一治理层

三层铁律：治理归 Harness、编排归 LangGraph、能力归 LangChain。
本包承载全部治理职责：

- 上下文工程  - context/
- 工具治理    - tools/ + middleware/tool_permission.py
- 权限/限流/熔断 - security/（permission.py / rate_limit.py / circuit_breaker.py）
- 沙箱与工作区隔离 - sandbox/
- Agent 加载  - agent/loader.py
- 横切中间件  - middleware/（base.py + builtin.py）
- 配置        - config.py（HarnessConfig）

LangGraph 层（图构建）在 runtime_engine.tao_graph；LangChain 能力层在 langchain 生态。
"""
from packages.agent.core.harness.context import PromptAssembler, ContextCompressor
from packages.agent.core.harness.config import RuntimeConfig, HarnessConfig, CollaborationMode
from packages.agent.core.harness.agent.loader import AgentLoader, LoadedAgentConfig
from packages.agent.core.harness.security.permission import (
    PermissionEngine,
    PermissionLevel,
)
from packages.agent.core.harness.security.rate_limit import (
    TokenBucket,
    SlidingWindowCounter,
    RateLimiterRegistry,
    make_rate_limiter,
)
from packages.agent.core.harness.security.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
)
from packages.agent.core.harness.security.retry import RetryPolicy, with_retry
from packages.agent.core.harness.sandbox.runtime import (
    SandboxRuntime,
    SandboxResult,
    SandboxScope,
    check_code_safety,
)
from packages.agent.core.harness.tools import ToolExecutionManager, ToolRisk
from packages.agent.core.harness.middleware import (
    MiddlewareChain,
    AuditLoggerMiddleware,
    ContextInitMiddleware,
    SecurityGuardMiddleware,
    ToolLoggingMiddleware,
    clean_tool_params,
    run_tool_permission_check,
)

__all__ = [
    # context
    "PromptAssembler",
    "ContextCompressor",
    # config
    "RuntimeConfig",
    "HarnessConfig",
    "CollaborationMode",
    # agent 加载
    "AgentLoader",
    "LoadedAgentConfig",
    # security
    "PermissionEngine",
    "PermissionLevel",
    "TokenBucket",
    "SlidingWindowCounter",
    "RateLimiterRegistry",
    "make_rate_limiter",
    "CircuitBreaker",
    "CircuitState",
    "RetryPolicy",
    "with_retry",
    # sandbox
    "SandboxRuntime",
    "SandboxResult",
    "SandboxScope",
    "check_code_safety",
    # tools
    "ToolExecutionManager",
    "ToolRisk",
    # middleware
    "MiddlewareChain",
    "AuditLoggerMiddleware",
    "ContextInitMiddleware",
    "SecurityGuardMiddleware",
    "ToolLoggingMiddleware",
    "clean_tool_params",
    "run_tool_permission_check",
]
