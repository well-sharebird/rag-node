"""
Agent 包

提供 Agent 运行时和约束系统：
- runtime: 执行引擎（中间件架构/图构建/状态管理）
- services: 服务层（Workspace/Runtime/Session）
- sandbox: 沙箱执行（NsJail/Firecracker）
"""

__all__ = [
    "runtime",
    "services",
    "sandbox",
]
