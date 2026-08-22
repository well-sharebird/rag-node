"""
沙箱提供者 - 管理沙箱的生命周期

核心设计：
1. 提供者模式（本地/Docker）
2. 线程隔离（每个 thread_id 独立沙箱）
3. 懒加载（首次工具调用时创建）
4. 复用机制（同一次线程执行中复用沙箱）
"""
import asyncio
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional, Any
from datetime import datetime, timedelta

from .sandbox import Sandbox, LocalSandbox

logger = logging.getLogger(__name__)


class SandboxProvider(ABC):
    """沙箱提供者基类"""
    
    @abstractmethod
    async def acquire(self, thread_id: str) -> str:
        """
        获取沙箱
        
        Args:
            thread_id: 线程 ID
        
        Returns:
            str: 沙箱 ID
        """
        pass
    
    @abstractmethod
    async def get(self, sandbox_id: str) -> Optional[Sandbox]:
        """
        获取沙箱实例
        
        Args:
            sandbox_id: 沙箱 ID
        
        Returns:
            Sandbox: 沙箱实例，如果不存在则返回 None
        """
        pass
    
    @abstractmethod
    async def release(self, sandbox_id: str) -> None:
        """
        释放沙箱
        
        Args:
            sandbox_id: 沙箱 ID
        """
        pass
    
    @abstractmethod
    async def cleanup(self) -> None:
        """清理所有沙箱"""
        pass


class LocalSandboxProvider(SandboxProvider):
    """
    本地沙箱提供者
    
    特点：
    - 单例模式（全局共享）
    - 懒加载（首次 acquire 时创建目录）
    - 自动清理（应用关闭时）
    """
    
    def __init__(
        self,
        base_path: Optional[Path] = None,
        cleanup_on_exit: bool = True,
    ):
        """
        初始化本地沙箱提供者
        
        Args:
            base_path: 基础路径，默认为 backend/.harness/sandboxes
            cleanup_on_exit: 是否在退出时清理
        """
        self.base_path = base_path or Path(__file__).parent.parent.parent / ".harness" / "sandboxes"
        self.cleanup_on_exit = cleanup_on_exit
        
        # 沙箱缓存
        self._sandboxes: Dict[str, LocalSandbox] = {}
        self._thread_to_sandbox: Dict[str, str] = {}
        self._lock = asyncio.Lock()
        
        # 懒加载标志
        self._initialized = False
        
        logger.info(f"[LocalSandboxProvider] Initialized with base_path: {self.base_path}")
    
    async def _ensure_initialized(self) -> None:
        """确保初始化（懒加载）"""
        if not self._initialized:
            async with self._lock:
                if not self._initialized:
                    # 创建基础目录
                    self.base_path.mkdir(parents=True, exist_ok=True)
                    logger.info(f"[LocalSandboxProvider] Created base directory: {self.base_path}")
                    self._initialized = True
    
    async def acquire(self, thread_id: str) -> str:
        """
        获取沙箱（懒加载 + 复用）
        
        Args:
            thread_id: 线程 ID
        
        Returns:
            str: 沙箱 ID
        """
        await self._ensure_initialized()
        
        async with self._lock:
            # 检查是否已有沙箱
            if thread_id in self._thread_to_sandbox:
                sandbox_id = self._thread_to_sandbox[thread_id]
                logger.debug(f"[LocalSandboxProvider] Reusing sandbox {sandbox_id} for thread {thread_id}")
                return sandbox_id
            
            # 创建新沙箱
            sandbox_id = f"sandbox_{thread_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            thread_path = self.base_path / thread_id
            
            # 创建目录结构
            workspace_path = thread_path / "workspace"
            uploads_path = thread_path / "uploads"
            outputs_path = thread_path / "outputs"
            
            # 创建沙箱实例
            sandbox = LocalSandbox(
                sandbox_id=sandbox_id,
                workspace_path=workspace_path,
                uploads_path=uploads_path,
                outputs_path=outputs_path,
            )
            
            # 缓存
            self._sandboxes[sandbox_id] = sandbox
            self._thread_to_sandbox[thread_id] = sandbox_id
            
            logger.info(f"[LocalSandboxProvider] Acquired sandbox {sandbox_id} for thread {thread_id}")
            
            return sandbox_id
    
    async def get(self, sandbox_id: str) -> Optional[LocalSandbox]:
        """获取沙箱实例"""
        return self._sandboxes.get(sandbox_id)
    
    async def release(self, sandbox_id: str) -> None:
        """
        释放沙箱（不立即清理，等待复用）
        
        Args:
            sandbox_id: 沙箱 ID
        """
        async with self._lock:
            if sandbox_id in self._sandboxes:
                # 关闭沙箱
                await self._sandboxes[sandbox_id].close()
                
                # 从 thread 映射中移除
                thread_id = None
                for tid, sid in self._thread_to_sandbox.items():
                    if sid == sandbox_id:
                        thread_id = tid
                        break
                
                if thread_id and thread_id in self._thread_to_sandbox:
                    del self._thread_to_sandbox[thread_id]
                
                logger.info(f"[LocalSandboxProvider] Released sandbox {sandbox_id}")
    
    async def cleanup(self) -> None:
        """清理所有沙箱"""
        async with self._lock:
            logger.info(f"[LocalSandboxProvider] Cleaning up {len(self._sandboxes)} sandboxes")
            
            # 关闭所有沙箱
            for sandbox_id, sandbox in list(self._sandboxes.items()):
                try:
                    await sandbox.close()
                except Exception as e:
                    logger.error(f"[LocalSandboxProvider] Failed to close sandbox {sandbox_id}: {e}")
            
            # 清空缓存
            self._sandboxes.clear()
            self._thread_to_sandbox.clear()
            
            # 清理目录（可选）
            if self.cleanup_on_exit:
                try:
                    import shutil
                    if self.base_path.exists():
                        shutil.rmtree(self.base_path)
                        logger.info(f"[LocalSandboxProvider] Cleaned up base directory: {self.base_path}")
                except Exception as e:
                    logger.error(f"[LocalSandboxProvider] Failed to cleanup base directory: {e}")
    
    async def __aenter__(self):
        await self._ensure_initialized()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()


# 全局提供者实例（单例）
_global_provider: Optional[LocalSandboxProvider] = None


def get_sandbox_provider() -> LocalSandboxProvider:
    """获取全局沙箱提供者实例"""
    global _global_provider
    if _global_provider is None:
        _global_provider = LocalSandboxProvider()
    return _global_provider


async def create_sandbox_provider(
    base_path: Optional[Path] = None,
    cleanup_on_exit: bool = True,
) -> LocalSandboxProvider:
    """创建沙箱提供者实例"""
    provider = LocalSandboxProvider(
        base_path=base_path,
        cleanup_on_exit=cleanup_on_exit,
    )
    await provider._ensure_initialized()
    return provider
