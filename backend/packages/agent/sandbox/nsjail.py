"""
NsJail 沙箱管理器

使用 Google nsjail 提供轻量级进程隔离
https://github.com/google/nsjail
"""
import asyncio
import logging
import os
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """代码执行结果"""
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    timed_out: bool = False


@dataclass
class SandboxConfig:
    """沙箱配置"""
    memory_mb: int = 128
    vcpu_count: int = 1
    timeout_seconds: int = 30
    network_enabled: bool = False
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    max_files: int = 100


class NsJailSandboxManager:
    """
    nsjail 沙箱管理器

    提供轻量级的进程隔离，适合代码执行场景
    """

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or "/etc/nsjail/agent.conf"
        self.nsjail_bin = shutil.which("nsjail") or "/usr/local/bin/nsjail"
        self._sandboxes: Dict[str, Any] = {}

        # 确保 nsjail 配置目录存在
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)

    async def execute_code(
        self,
        code: str,
        language: str = "python",
        workspace_path: str = None,
        config: Optional[SandboxConfig] = None,
    ) -> ExecutionResult:
        """
        在 nsjail 沙箱中执行代码

        Args:
            code: 要执行的代码
            language: 语言 (python, node, bash)
            workspace_path: 工作区路径 (隔离的文件系统)
            config: 沙箱配置

        Returns:
            ExecutionResult: 执行结果
        """
        config = config or SandboxConfig()

        with tempfile.TemporaryDirectory() as tmpdir:
            # 准备代码文件
            code_file = await self._write_code_file(
                tmpdir, code, language
            )

            # 构建 nsjail 命令
            cmd = await self._build_nsjail_command(
                tmpdir=tmpdir,
                workspace_path=workspace_path,
                language=language,
                code_file=code_file,
                config=config,
            )

            # 执行
            return await self._execute(cmd, config.timeout_seconds)

    async def execute_command(
        self,
        command: list[str],
        workspace_path: Optional[str] = None,
        config: Optional[SandboxConfig] = None,
    ) -> ExecutionResult:
        """
        在 nsjail 沙箱中执行命令

        Args:
            command: 命令和参数列表
            workspace_path: 工作区路径
            config: 沙箱配置

        Returns:
            ExecutionResult: 执行结果
        """
        config = config or SandboxConfig()

        with tempfile.TemporaryDirectory() as tmpdir:
            cmd = await self._build_nsjail_command(
                tmpdir=tmpdir,
                workspace_path=workspace_path,
                command=command,
                config=config,
            )

            return await self._execute(cmd, config.timeout_seconds)

    async def _write_code_file(
        self,
        tmpdir: str,
        code: str,
        language: str,
    ) -> str:
        """写入代码文件"""
        extensions = {
            "python": ".py",
            "node": ".js",
            "bash": ".sh",
        }
        ext = extensions.get(language, ".txt")
        code_file = os.path.join(tmpdir, f"code{ext}")

        with open(code_file, "w") as f:
            f.write(code)

        # 设置执行权限
        os.chmod(code_file, 0o755)

        return code_file

    async def _build_nsjail_command(
        self,
        tmpdir: str,
        workspace_path: Optional[str] = None,
        language: Optional[str] = None,
        code_file: Optional[str] = None,
        command: Optional[list[str]] = None,
        config: Optional[SandboxConfig] = None,
    ) -> list[str]:
        """
        构建 nsjail 命令

        nsjail 参数说明：
        --mode: 运行模式 (once = 单次执行)
        --uidmap/--gidmap: 用户/组映射到 nobody
        --bindmount: 绑定挂载目录
        --tmpfs: 临时文件系统
        --rlimit_*: 资源限制
        --seccomp_string: 系统调用过滤
        """
        config = config or SandboxConfig()

        # 基础命令
        cmd = [
            self.nsjail_bin,
            "--mode", "once",
            "--daemon",
            "--quiet",

            # 用户/组隔离 (映射到 nobody)
            "--uidmap", "inside_id:1000:outside_id:65534",
            "--gidmap", "inside_id:1000:outside_id:65534",

            # 网络隔离
            "--use_netns",  # 使用独立的 network namespace

            # 资源限制
            "--rlimit_as_type", "HARD",  # 地址空间限制
            "--rlimit_cpu_type", "HARD",  # CPU 时间限制
            "--rlimit_nofile", str(config.max_files),  # 文件描述符限制
            "--rlimit_fsize", str(config.max_file_size),  # 文件大小限制

            # 安全选项
            "--keep_caps", "false",
            "--disable_no_new_privs", "false",
            "--kill_on_exit",  # 父进程退出时终止子进程
        ]

        # 挂载配置
        # 1. 只读挂载系统目录
        cmd.extend(["--robind", "/usr", "/usr"])
        cmd.extend(["--robind", "/lib", "/lib"])
        cmd.extend(["--robind", "/lib64", "/lib64"])
        if os.path.exists("/bin"):
            cmd.extend(["--robind", "/bin", "/bin"])

        # 2. 绑定挂载工作区 (如果有)
        if workspace_path and os.path.exists(workspace_path):
            # 工作区可写
            cmd.extend(["--bind", workspace_path, "/workspace"])
            cmd.extend(["--cwd", "/workspace"])
        else:
            # 使用临时目录作为工作区
            work_dir = os.path.join(tmpdir, "work")
            os.makedirs(work_dir, exist_ok=True)
            cmd.extend(["--bind", work_dir, "/workspace"])
            cmd.extend(["--cwd", "/workspace"])

        # 3. 临时目录
        cmd.extend(["--tmpfs", "/tmp"])
        cmd.extend(["--tmpfs", "/dev"])
        cmd.extend(["--tmpfs", "/var"])

        # 4. 只读 /proc
        cmd.extend(["--proc", "/proc"])

        # seccomp 系统调用过滤
        seccomp_policy = self._build_seccomp_policy(
            network_enabled=config.network_enabled
        )
        cmd.extend(["--seccomp_string", seccomp_policy])

        # 执行命令
        if command:
            # 执行指定命令
            cmd.extend(["--", *command])
        elif language and code_file:
            # 执行代码文件
            interpreter = {
                "python": "python3",
                "node": "node",
                "bash": "bash",
            }.get(language, "python3")

            cmd.extend(["--", interpreter, code_file])
        else:
            raise ValueError("Either command or (language, code_file) must be provided")

        logger.debug(f"NsJail command: {' '.join(cmd)}")

        return cmd

    def _build_seccomp_policy(self, network_enabled: bool = False) -> str:
        """
        构建 seccomp 系统调用过滤策略

        只允许必要的系统调用，禁止危险操作
        """
        # 允许的系统调用
        allowed_syscalls = [
            # 文件操作
            "read", "write", "open", "close",
            "stat", "fstat", "lstat", "newfstatat",
            "access", "faccessat", "faccessat2",

            # 内存操作
            "mmap", "munmap", "mprotect", "brk",

            # 进程控制
            "exit", "exit_group",
            "getuid", "getgid", "geteuid", "getegid",
            "getpid", "getppid", "gettid",
            "getcwd", "getdents", "getdents64",

            # 信号
            "rt_sigaction", "rt_sigprocmask", "rt_sigreturn",

            # 其他必要调用
            "arch_prctl", "prctl",
            "set_tid_address", "set_robust_list",
            "prlimit64", "clock_gettime",
            "getrandom", "getuid32", "getgid32",

            # Python/Node 需要的调用
            "uname", "sysinfo",
            "ioctl", "fcntl", "dup", "dup2", "dup3",
            "pipe", "pipe2",
            "wait4", "waitid",
            "sched_getaffinity", "sched_yield",
            "nanosleep", "clock_nanosleep",
            "futex",
            "readlink", "readlinkat",
            "getxattr", "lgetxattr", "fgetxattr",
            "statx",
        ]

        # 如果允许网络，添加网络相关系统调用
        if network_enabled:
            allowed_syscalls.extend([
                "socket", "connect", "sendto", "sendmsg",
                "recvfrom", "recvmsg", "getsockname",
                "getpeername", "setsockopt", "getsockopt",
                "bind", "listen", "accept", "accept4",
                "shutdown", "sendmmsg",
            ])

        # 构建 seccomp 策略 JSON
        allowed_list = '", "'.join(allowed_syscalls)
        seccomp_policy = f"""{{
    "defaultAction": "SCMP_ACT_ERRNO",
    "syscalls": [
        {{"names": ["{allowed_list}"], "action": "SCMP_ACT_ALLOW"}}
    ]
}}"""
        return seccomp_policy

    async def _execute(
        self,
        cmd: list[str],
        timeout_seconds: int,
    ) -> ExecutionResult:
        """执行命令并捕获结果"""
        import time

        start_time = time.time()
        timed_out = False

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout_seconds,
                )
                exit_code = proc.returncode

            except asyncio.TimeoutError:
                # 超时，终止进程
                proc.kill()
                await proc.wait()
                stdout = b""
                stderr = f"Execution timed out after {timeout_seconds} seconds".encode()
                exit_code = -9
                timed_out = True

        except Exception as e:
            logger.error(f"Execution failed: {e}")
            stdout = b""
            stderr = str(e).encode()
            exit_code = -1

        duration_ms = int((time.time() - start_time) * 1000)

        return ExecutionResult(
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
            exit_code=exit_code,
            duration_ms=duration_ms,
            timed_out=timed_out,
        )


# 全局单例
_sandbox_manager: Optional[NsJailSandboxManager] = None


def get_sandbox_manager() -> NsJailSandboxManager:
    """获取沙箱管理器单例"""
    global _sandbox_manager
    if _sandbox_manager is None:
        _sandbox_manager = NsJailSandboxManager()
    return _sandbox_manager


async def execute_code_in_sandbox(
    code: str,
    language: str = "python",
    workspace_path: Optional[str] = None,
    timeout_seconds: int = 30,
) -> ExecutionResult:
    """
    在沙箱中执行代码的便捷函数

    Args:
        code: 要执行的代码
        language: 语言 (python, node, bash)
        workspace_path: 工作区路径
        timeout_seconds: 超时时间

    Returns:
        ExecutionResult: 执行结果
    """
    manager = get_sandbox_manager()
    config = SandboxConfig(timeout_seconds=timeout_seconds)

    return await manager.execute_code(
        code=code,
        language=language,
        workspace_path=workspace_path,
        config=config,
    )
