"""
沙箱执行环境 - 提供命令执行和文件操作能力
"""
import asyncio
import os
import shutil
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """命令执行结果"""
    stdout: str
    stderr: str
    return_code: int
    sandbox_id: Optional[str] = None
    
    @property
    def success(self) -> bool:
        return self.return_code == 0


class Sandbox(ABC):
    """沙箱基类"""
    
    def __init__(self, sandbox_id: str, workspace_path: Path):
        self.sandbox_id = sandbox_id
        self.workspace_path = workspace_path
        self._closed = False
    
    @abstractmethod
    async def execute_command(self, command: str, timeout: Optional[int] = None) -> CommandResult:
        """执行命令"""
        pass
    
    @abstractmethod
    async def list_directory(self, path: str, depth: int = 2) -> str:
        """列出目录内容（树形格式）"""
        pass
    
    @abstractmethod
    async def read_file(self, path: str) -> bytes:
        """读取文件"""
        pass
    
    @abstractmethod
    async def write_file(self, path: str, content: bytes) -> None:
        """写入文件"""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """关闭沙箱，清理资源"""
        pass
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


class LocalSandbox(Sandbox):
    """
    本地沙箱 - 直接在宿主机执行（开发环境）
    
    特点：
    - 无隔离，性能高
    - 适合开发和测试
    - 生产环境应使用 Docker 沙箱
    """
    
    def __init__(
        self,
        sandbox_id: str,
        workspace_path: Path,
        uploads_path: Optional[Path] = None,
        outputs_path: Optional[Path] = None,
    ):
        super().__init__(sandbox_id, workspace_path)
        self.uploads_path = uploads_path
        self.outputs_path = outputs_path
        
        # 创建工作目录
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        if uploads_path:
            uploads_path.mkdir(parents=True, exist_ok=True)
        if outputs_path:
            outputs_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"[LocalSandbox] Created sandbox {sandbox_id} at {workspace_path}")
    
    async def execute_command(
        self,
        command: str,
        timeout: Optional[int] = 300
    ) -> CommandResult:
        """
        执行命令
        
        Args:
            command: 要执行的命令
            timeout: 超时时间（秒），默认 300 秒
        
        Returns:
            CommandResult: 执行结果
        """
        logger.debug(f"[LocalSandbox:{self.sandbox_id}] Executing: {command}")
        
        try:
            # 创建 subprocess
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workspace_path,
            )
            
            # 等待完成（带超时）
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                # 超时则终止进程
                process.kill()
                await process.wait()
                return CommandResult(
                    stdout="",
                    stderr=f"Command timed out after {timeout} seconds",
                    return_code=-1,
                    sandbox_id=self.sandbox_id,
                )
            
            result = CommandResult(
                stdout=stdout.decode('utf-8', errors='replace'),
                stderr=stderr.decode('utf-8', errors='replace'),
                return_code=process.returncode or 0,
                sandbox_id=self.sandbox_id,
            )
            
            logger.debug(
                f"[LocalSandbox:{self.sandbox_id}] Result: "
                f"code={result.return_code}, stdout={len(result.stdout)} chars"
            )
            
            return result
            
        except Exception as e:
            logger.exception(f"[LocalSandbox:{self.sandbox_id}] Command failed: {e}")
            return CommandResult(
                stdout="",
                stderr=f"Command execution failed: {str(e)}",
                return_code=-1,
                sandbox_id=self.sandbox_id,
            )
    
    async def list_directory(self, path: str, depth: int = 2) -> str:
        """
        列出目录内容（树形格式）
        
        Args:
            path: 目录路径（相对于 workspace）
            depth: 最大深度，默认 2 层
        
        Returns:
            str: 树形格式的目录列表
        """
        try:
            # 解析路径
            full_path = self._resolve_path(path)
            
            if not full_path.exists():
                return f"Directory not found: {path}"
            
            if not full_path.is_dir():
                return f"Not a directory: {path}"
            
            # 生成树形结构
            lines = []
            self._build_tree(full_path, lines, prefix="", depth=0, max_depth=depth)
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.exception(f"[LocalSandbox:{self.sandbox_id}] Failed to list directory: {e}")
            return f"Error listing directory: {str(e)}"
    
    async def read_file(self, path: str) -> bytes:
        """读取文件"""
        try:
            full_path = self._resolve_path(path)
            
            # 安全检查：确保文件在沙箱内
            self._check_path_security(full_path)
            
            return full_path.read_bytes()
            
        except Exception as e:
            logger.exception(f"[LocalSandbox:{self.sandbox_id}] Failed to read file: {e}")
            raise
    
    async def write_file(self, path: str, content: bytes) -> None:
        """写入文件"""
        try:
            full_path = self._resolve_path(path)
            
            # 安全检查：确保文件在沙箱内
            self._check_path_security(full_path)
            
            # 创建父目录
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 写入文件
            full_path.write_bytes(content)
            
            logger.debug(f"[LocalSandbox:{self.sandbox_id}] Wrote file: {path} ({len(content)} bytes)")
            
        except Exception as e:
            logger.exception(f"[LocalSandbox:{self.sandbox_id}] Failed to write file: {e}")
            raise
    
    async def close(self) -> None:
        """关闭沙箱（本地沙箱无需特殊清理）"""
        if not self._closed:
            logger.info(f"[LocalSandbox:{self.sandbox_id}] Closing sandbox")
            self._closed = True
    
    def _resolve_path(self, path: str) -> Path:
        """
        解析路径（支持绝对路径和相对路径）
        
        Args:
            path: 路径（可以是相对路径或虚拟路径）
        
        Returns:
            Path: 解析后的完整路径
        """
        # 处理虚拟路径
        if path.startswith('/mnt/user-data/'):
            # 虚拟路径转换
            if path.startswith('/mnt/user-data/workspace/'):
                rel_path = path[len('/mnt/user-data/workspace/'):]
                return self.workspace_path / rel_path
            elif path.startswith('/mnt/user-data/uploads/'):
                rel_path = path[len('/mnt/user-data/uploads/'):]
                if self.uploads_path:
                    return self.uploads_path / rel_path
                else:
                    raise ValueError(f"Uploads path not configured for sandbox {self.sandbox_id}")
            elif path.startswith('/mnt/user-data/outputs/'):
                rel_path = path[len('/mnt/user-data/outputs/'):]
                if self.outputs_path:
                    return self.outputs_path / rel_path
                else:
                    raise ValueError(f"Outputs path not configured for sandbox {self.sandbox_id}")
            else:
                raise ValueError(f"Invalid virtual path: {path}")
        
        # 绝对路径（安全检查）
        if os.path.isabs(path):
            full_path = Path(path)
            self._check_path_security(full_path)
            return full_path
        
        # 相对路径（相对于 workspace）
        return self.workspace_path / path
    
    def _check_path_security(self, path: Path) -> None:
        """
        安全检查：确保路径在沙箱内
        
        Args:
            path: 要检查的路径
        
        Raises:
            ValueError: 如果路径超出沙箱范围
        """
        try:
            # 解析符号链接和规范化路径
            resolved = path.resolve()
            workspace_resolved = self.workspace_path.resolve()
            
            # 检查是否在 workspace 内
            if not str(resolved).startswith(str(workspace_resolved)):
                # 检查是否在 uploads/outputs 内
                if self.uploads_path:
                    uploads_resolved = self.uploads_path.resolve()
                    if str(resolved).startswith(str(uploads_resolved)):
                        return
                
                if self.outputs_path:
                    outputs_resolved = self.outputs_path.resolve()
                    if str(resolved).startswith(str(outputs_resolved)):
                        return
                
                raise ValueError(f"Path security violation: {path} is outside sandbox boundaries")
                
        except Exception as e:
            if "Path security violation" in str(e):
                raise
            logger.warning(f"[LocalSandbox:{self.sandbox_id}] Path check failed for {path}: {e}")
    
    def _build_tree(
        self,
        path: Path,
        lines: list,
        prefix: str = "",
        depth: int = 0,
        max_depth: int = 2
    ) -> None:
        """构建树形结构"""
        if depth > max_depth:
            return
        
        try:
            entries = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name))
        except PermissionError:
            lines.append(f"{prefix}[Permission Denied]")
            return
        
        for i, entry in enumerate(entries):
            is_last = (i == len(entries) - 1)
            connector = "└── " if is_last else "├── "
            
            if depth == 0:
                lines.append(f"{connector}{entry.name}")
            else:
                lines.append(f"{prefix}{connector}{entry.name}")
            
            if entry.is_dir() and depth < max_depth:
                extension = "    " if is_last else "│   "
                self._build_tree(
                    entry,
                    lines,
                    prefix=prefix + extension,
                    depth=depth + 1,
                    max_depth=max_depth
                )
