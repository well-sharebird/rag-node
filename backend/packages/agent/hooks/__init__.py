"""Hook 系统 - 统一中间件机制"""
from packages.agent.hooks.registry import HookPoint, HookRegistry, get_hook_registry, hook
from packages.agent.hooks.builtin import *

__all__ = [
    "HookPoint",
    "HookRegistry",
    "get_hook_registry",
    "hook",
]
