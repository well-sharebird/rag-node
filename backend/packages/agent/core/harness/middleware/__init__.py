"""Harness 中间件层 - 权限护栏与治理（设计文档 2.5 双重安全重点）

1. 纯函数工具治理能力（可独立调用）：
    - run_tool_permission_check: 白名单/阻断校验
    - clean_tool_params:        工具参数清洗
2. LangChain AgentMiddleware 装配（横切拦截）：
    - MiddlewareChain:           节点驱动 middleware 链
    - ContextInit/ToolLogging/AuditLogger/SecurityGuard: 内置横切中间件
"""
from .tool_permission import run_tool_permission_check, clean_tool_params
from .base import MiddlewareChain
from .builtin import (
    AuditLoggerMiddleware,
    ContextInitMiddleware,
    SecurityGuardMiddleware,
    ToolLoggingMiddleware,
)

__all__ = [
    "run_tool_permission_check",
    "clean_tool_params",
    "MiddlewareChain",
    "AuditLoggerMiddleware",
    "ContextInitMiddleware",
    "SecurityGuardMiddleware",
    "ToolLoggingMiddleware",
]
