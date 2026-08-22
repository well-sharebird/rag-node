"""
沙箱系统 - 提供安全的工具执行环境

核心设计：
1. 沙箱提供者模式（本地/Docker）
2. 虚拟路径映射（/mnt/user-data/* → 实际路径）
3. 生命周期管理（acquire/release）
4. 线程隔离（每个 thread_id 独立沙箱）
"""

from .provider import SandboxProvider, LocalSandboxProvider
from .sandbox import Sandbox, LocalSandbox
from .paths import VirtualPathMapper, get_thread_data_paths

__all__ = [
    "SandboxProvider",
    "LocalSandboxProvider",
    "Sandbox",
    "LocalSandbox",
    "VirtualPathMapper",
    "get_thread_data_paths",
]
