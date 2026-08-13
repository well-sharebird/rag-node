"""Harness 中间件层 - 权限护栏与治理（设计文档 2.5 双重安全重点）

提供可独立调用的纯函数工具治理能力：
    - run_tool_permission_check: 白名单/阻断校验
    - clean_tool_params:        工具参数清洗
归属"节点强制 / 中间件观测"分层：此处为强制逻辑，节点直接调用。
"""
from .tool_permission import run_tool_permission_check, clean_tool_params

__all__ = ["run_tool_permission_check", "clean_tool_params"]
