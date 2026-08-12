"""Middleware 中间件层（基于 LangChain AgentMiddleware）

统一承载 Harness 的横切管控：日志、审计、上下文注入等。
替代自研 hooks 系统，中间件为官方 AgentMiddleware 对象，由节点驱动。
"""
from packages.agent.middlewares.base import MiddlewareChain
from packages.agent.middlewares.builtin import (
    AuditLoggerMiddleware,
    ContextInitMiddleware,
    SecurityGuardMiddleware,
    ToolLoggingMiddleware,
)

__all__ = [
    "MiddlewareChain",
    "AuditLoggerMiddleware",
    "ContextInitMiddleware",
    "SecurityGuardMiddleware",
    "ToolLoggingMiddleware",
]
