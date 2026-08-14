"""Harness SandboxRuntime - 统一沙箱执行入口（文档 2.2/3.1）

所有代码/工具执行统一提交至 Harness SandboxRuntime：
1. 代码安全检查（危险调用黑名单）
2. Python 一律在**隔离 venv** 解释器执行（自动安装缺失依赖；禁用宿主 Python）
3. 产物提升：执行产物落用户工作空间 generated/（source_type=generated），
   随 sandbox 整树销毁（venv+临时目录）——运行时销毁、产物保留
4. 审计：log_action 记录执行

LangChain/节点不直接执行，统一经此入口（文档 11.5.2）。
"""
import asyncio
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

DANGEROUS_PATTERNS = [
    r"os\.system\s*\(",
    r"subprocess\s*[\.\[]",
    r"shutil\.rmtree\s*\(",
    r"shutil\.move\s*\(",
    r"os\.remove\s*\(",
    r"os\.unlink\s*\(",
    r"rm\s+-rf",
    r"eval\s*\(",
    r"exec\s*\(",
    r"__import__\s*\(",
    r"open\s*\(['\"]/etc",
]


def check_code_safety(code: str) -> Optional[str]:
    """代码安全检查：命中危险调用则返回拒绝原因。"""
    for pat in DANGEROUS_PATTERNS:
        if re.search(pat, code):
            return f"检测到危险操作（{pat}），已拒绝执行"
    return None


@dataclass
class SandboxResult:
    """沙箱执行结果"""
    sandbox: str                      # nsjail / process(降级)
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    timed_out: bool = False
    files: List[dict] = field(default_factory=list)   # 工作空间产物
    blocked: Optional[str] = None     # 安全检查拦截原因


class SandboxRuntime:
    """Harness 统一沙箱执行运行时。

    执行模型（用户约定：代码只能在沙箱中运行，不使用宿主 Python）：
    - Python 一律跑在**隔离 venv** 解释器（`python -m venv`），绝不落到后端/宿主的
      `sys.executable`；
    - 运行前自动解析 import 需求并用 <venv>/pip 安装缺失依赖（见 `deps.py`）；
    - 执行结束（含超时/异常）在 finally 中整体销毁 sandbox_root（venv+临时目录），
      产物在销毁前已提升到用户持久工作区 generated/。
    """

    def __init__(self, db, user_id: int, session_id: Optional[str] = None,
                 workdir: Optional[str] = None,
                 sandbox_policy: Optional[dict] = None):
        self.db = db
        self.user_id = user_id
        self.session_id = session_id
        self.workdir = workdir  # 任务级沙箱工作目录（SandboxScope 提供），None 用默认工作区
        policy = sandbox_policy or {}
        self.auto_install = bool(policy.get("auto_install", True))
        self.install_index = policy.get("install_index") or None
        self.install_timeout = float(policy.get("install_timeout_seconds", 180))

    @staticmethod
    def _interpreter(language: str) -> tuple[str, str]:
        lang = (language or "python").lower()
        if lang in ("node", "nodejs"):
            return "node", "js"
        if lang in ("bash", "sh"):
            return "bash", "sh"
        return "python", "py"

    async def get_workspace(self):
        """获取当前用户工作空间（不存在自动创建）。"""
        from packages.core.system.models.user import User
        user = await self.db.get(User, self.user_id)
        if user is None:
            raise ValueError("用户不存在")
        from packages.agent.services.workspace_service import WorkspaceService
        return await WorkspaceService(self.db).get_or_create_workspace(user)

    async def _make_venv(self, env_dir: str) -> Optional[str]:
        """创建隔离 venv，返回其 python 解释器路径；失败返回 None。"""
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "venv", env_dir,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            _, err = await asyncio.wait_for(proc.communicate(), timeout=self.install_timeout)
            if proc.returncode != 0:
                logger.warning("[SandboxRuntime] venv 创建失败: %s", (err or b"").decode(errors="replace")[:500])
                return None
            py = os.path.join(env_dir, "bin", "python")
            py = py if os.path.exists(py) else os.path.join(env_dir, "Scripts", "python.exe")
            return py if os.path.exists(py) else None
        except Exception as e:
            logger.warning("[SandboxRuntime] venv 创建异常: %s", e)
            return None

    async def _install_deps(self, env_python: str, deps: List[str]) -> None:
        """在 venv 内安装依赖（best-effort：单个失败仅记日志，不中断执行）。"""
        cmd = [env_python, "-m", "pip", "install", "--quiet", "--no-input"]
        if self.install_index:
            cmd += ["--index-url", self.install_index]
        cmd += deps
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            _, err = await asyncio.wait_for(proc.communicate(), timeout=self.install_timeout)
            if proc.returncode != 0:
                logger.warning("[SandboxRuntime] 依赖安装部分失败(%s): %s",
                               deps, (err or b"").decode(errors="replace")[:600])
        except asyncio.TimeoutError:
            logger.warning("[SandboxRuntime] 依赖安装超时: %s", deps)
            try:
                proc.kill()
            except Exception:
                pass
        except Exception as e:
            logger.warning("[SandboxRuntime] 依赖安装异常: %s", e)

    async def _promote_products(self, ws, work_dir: str, ext: str, run_id: str,
                                stdout: str) -> List[dict]:
        """把 work_dir 内产物移动到用户持久工作区 generated/exec/<run_id>/ 并登记。

        在销毁 venv/临时目录前调用，保证"生成的产物保留、运行时销毁"。
        """
        import shutil
        from packages.agent.services.workspace_service import WorkspaceService
        ws_svc = WorkspaceService(self.db)
        products = []
        target_dir = os.path.join(ws.root_path, "generated", "exec", run_id)
        try:
            names = [n for n in os.listdir(work_dir)
                     if not n.startswith(f"script.{ext}") and not n.startswith(".")]
            if len(stdout) > 1000:
                with open(os.path.join(work_dir, "stdout.txt"), "w", encoding="utf-8") as f:
                    f.write(stdout)
                names.append("stdout.txt")
            if names:
                os.makedirs(target_dir, exist_ok=True)
            for name in names:
                src = os.path.join(work_dir, name)
                if not os.path.isfile(src):
                    continue
                dst = os.path.join(target_dir, name)
                shutil.move(src, dst)
                rel = os.path.join("generated", "exec", run_id, name).replace(os.sep, "/")
                await ws_svc.register_file(
                    workspace=ws, filename=name, relative_path=rel,
                    file_size=os.path.getsize(dst), source_type="generated",
                    session_id=self.session_id or None,
                )
                products.append({"filename": name, "relative_path": rel})
            return products
        except Exception as e:
            logger.warning("[SandboxRuntime] 产物提升/登记失败: %s", e)
            return products

    async def execute(self, code: str, language: str = "python",
                      requirements: Optional[List[str]] = None) -> SandboxResult:
        """统一沙箱执行（安全检查 → venv 隔离+自动装依赖 → 执行 → 产物提升 → 销毁）。

        Python 只跑隔离 venv 解释器；node/bash 走各自独立解释器子进程（非后端 Python）。
        无论成功/超时/异常，sandbox_root 都在 finally 中销毁。
        """
        # 1. 安全检查
        reason = check_code_safety(code)
        if reason:
            return SandboxResult(sandbox="blocked", blocked=reason)

        # 2. 工作区与沙箱根目录（venv + 执行目录均在 sandbox_root 下，整树销毁）
        ws = await self.get_workspace()
        ts = str(int(time.time() * 1000))
        sandbox_root = self.workdir or os.path.join(ws.root_path, "sandbox", f"task_{ts}")
        env_dir = os.path.join(sandbox_root, "env")
        work_dir = os.path.join(sandbox_root, "work")
        os.makedirs(work_dir, exist_ok=True)
        os.makedirs(env_dir, exist_ok=True)

        stdout, stderr, exit_code, sandbox_label, timed_out = "", "", 0, "", False
        files: List[dict] = []
        interpreter, ext = self._interpreter(language)
        script_path = os.path.join(work_dir, f"script.{ext}")
        try:
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(code)

            # 3. 执行体（python 一律隔离 venv；venv 失败则拒绝执行，绝不回退宿主解释器）
            env_python = None
            if language in ("python", "py"):
                env_python = await self._make_venv(env_dir)
                if not env_python:
                    stderr = "无法创建隔离 venv，已拒绝在宿主解释器上执行"
                    exit_code = 1
                    sandbox_label = "error"
                elif self.auto_install:
                    from packages.agent.core.harness.sandbox.deps import plan_dependencies
                    deps = plan_dependencies(code, requirements)
                    if deps:
                        await self._install_deps(env_python, deps)
                    sandbox_label = "venv"
                else:
                    sandbox_label = "venv"

            py_ready = not (language in ("python", "py") and env_python is None)
            try:
                if py_ready:
                    import shutil
                    if env_python is not None and shutil.which("nsjail"):
                        sandbox_label = "nsjail"
                        from packages.agent.sandbox.nsjail import NsJailSandboxManager
                        cfg = None
                        try:
                            from packages.agent.sandbox.nsjail import SandboxConfig
                            cfg = SandboxConfig()
                        except Exception:
                            cfg = None
                        res = await NsJailSandboxManager().execute_code(
                            code=code, language=language, workspace_path=work_dir, config=cfg,
                        )
                        stdout, stderr, exit_code = res.stdout, res.stderr, res.exit_code
                    else:
                        cmd = env_python if env_python is not None else interpreter
                        proc = await asyncio.create_subprocess_exec(
                            cmd, script_path, cwd=work_dir,
                            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                        )
                        try:
                            out, err = await asyncio.wait_for(proc.communicate(), timeout=60)
                            stdout = (out or b"").decode(errors="replace")
                            stderr = (err or b"").decode(errors="replace")
                            exit_code = proc.returncode if proc.returncode is not None else 0
                        except asyncio.TimeoutError:
                            proc.kill()
                            timed_out = True
                            stderr = "执行超时"
            except Exception as e:
                logger.warning("[SandboxRuntime] 执行异常: %s", e)
                stderr = f"执行失败: {e}"
                exit_code = 1

            # 4. 产物提升到持久工作区（sandbox 销毁前）
            files = await self._promote_products(ws, work_dir, ext, ts, stdout)

            # 5. 审计
            try:
                from packages.agent.services.workspace_service import WorkspaceService
                await WorkspaceService(self.db).log_action(
                    workspace=ws, action="execute", file_path="sandbox:execute",
                    user_id=self.user_id, session_id=self.session_id or None,
                    success=not timed_out,
                )
            except Exception as e:
                logger.warning("[SandboxRuntime] 审计失败: %s", e)
        finally:
            # 6. 确定性销毁：venv + 临时执行目录整树清理（幂等，SandboxScope 双清安全）
            try:
                if os.path.exists(sandbox_root):
                    import shutil
                    shutil.rmtree(sandbox_root, ignore_errors=True)
            except Exception as e:
                logger.warning("[SandboxRuntime] 销毁失败: %s", e)

        return SandboxResult(sandbox=sandbox_label or interpreter, stdout=stdout,
                             stderr=stderr, exit_code=exit_code, timed_out=timed_out,
                             files=files)


class SandboxScope:
    """任务/会话级沙箱生命周期（Phase 3：加载→执行→销毁）。

    为子 Agent 执行（_exec_sub_task）与主 Agent 直答（_direct_answer_stream）
    提供隔离工作区：进入创建独立 workdir，退出 best-effort 销毁（防逃逸/残留）。

    Usage:
        async with SandboxScope(db, user_id, session_id, policy) as scope:
            # 将 scope.workdir 注入工具治理门面，高危工具执行落于该目录
            ...execute...
        # 退出后 scope.workdir 已被清理
    """

    def __init__(self, db, user_id: int, session_id: Optional[str] = None,
                 policy: Optional[dict] = None):
        self.db = db
        self.user_id = user_id
        self.session_id = session_id
        self.policy = policy or {}
        self.workdir: Optional[str] = None

    async def get_workspace(self):
        from packages.core.system.models.user import User
        user = await self.db.get(User, self.user_id)
        if user is None:
            raise ValueError("用户不存在")
        from packages.agent.services.workspace_service import WorkspaceService
        return await WorkspaceService(self.db).get_or_create_workspace(user)

    async def __aenter__(self):
        ws = await self.get_workspace()
        self.workdir = os.path.join(
            ws.root_path, "sandbox", f"task_{int(time.time() * 1000)}"
        )
        os.makedirs(self.workdir, exist_ok=True)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.workdir:
            import shutil
            try:
                shutil.rmtree(self.workdir, ignore_errors=True)
            except Exception as e:
                logger.warning("[SandboxScope] 清理失败: %s", e)
        return False
