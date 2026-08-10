"""
Agent 沙箱模块

提供代码执行的沙箱环境：
1. NsJail - 轻量级进程隔离
2. Firecracker - 完全隔离的 VM (待实现)
"""

from packages.agent.sandbox.nsjail import (
    NsJailSandboxManager,
    SandboxConfig,
    ExecutionResult,
    execute_code_in_sandbox,
    get_sandbox_manager,
)

__all__ = [
    "NsJailSandboxManager",
    "SandboxConfig",
    "ExecutionResult",
    "execute_code_in_sandbox",
    "get_sandbox_manager",
]
