"""Harness SandboxRuntime - 统一沙箱执行入口（文档 2.2/3.1）

所有代码/工具执行统一提交至 Harness SandboxRuntime：
1. 代码安全检查（危险调用黑名单）
2. 执行：nsjail 优先（真沙箱，工作区绑定），缺失降级受限子进程
3. 产物登记：执行产物自动落用户工作空间（source_type=generated）
4. 审计：log_action 记录执行

LangChain/节点不直接执行，统一经此入口（文档 11.5.2）。
"""
import asyncio
import logging
import os
import re
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
    """Harness 统一沙箱执行运行时。"""

    def __init__(self, db, user_id: int, session_id: Optional[str] = None):
        self.db = db
        self.user_id = user_id
        self.session_id = session_id

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

    async def execute(self, code: str, language: str = "python") -> SandboxResult:
        """统一沙箱执行入口（安全检查 → 沙箱/降级 → 产物登记 → 审计）。"""
        # 1. 安全检查
        reason = check_code_safety(code)
        if reason:
            return SandboxResult(sandbox="blocked", blocked=reason)

        # 2. 获取工作空间
        ws = await self.get_workspace()
        exec_dir = os.path.join(ws.root_path, "exec", str(int(time.time() * 1000)))
        os.makedirs(exec_dir, exist_ok=True)

        interpreter, ext = self._interpreter(language)
        script_path = os.path.join(exec_dir, f"script.{ext}")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(code)

        # 3. 执行
        stdout, stderr, exit_code, sandbox_label, timed_out = "", "", 0, "", False
        try:
            import shutil
            if shutil.which("nsjail"):
                sandbox_label = "nsjail"
                from packages.agent.sandbox.nsjail import NsJailSandboxManager
                cfg = None
                try:
                    from packages.agent.sandbox.nsjail import SandboxConfig
                    cfg = SandboxConfig()
                except Exception:
                    cfg = None
                res = await NsJailSandboxManager().execute_code(
                    code=code, language=language, workspace_path=exec_dir, config=cfg,
                )
                stdout, stderr, exit_code = res.stdout, res.stderr, res.exit_code
            else:
                sandbox_label = "process(降级：nsjail 未安装)"
                proc = await asyncio.create_subprocess_exec(
                    interpreter, script_path, cwd=exec_dir,
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
            return SandboxResult(sandbox="error", stderr=f"执行失败: {e}", exit_code=1)

        # 4. 产物登记（exec 目录内生成文件 → 工作空间 generated）
        from packages.agent.services.workspace_service import WorkspaceService
        ws_svc = WorkspaceService(self.db)
        files = []
        try:
            for name in os.listdir(exec_dir):
                if name.startswith(f"script.{ext}") or name.startswith("."):
                    continue
                p = os.path.join(exec_dir, name)
                if os.path.isfile(p):
                    rel = os.path.join("exec", os.path.basename(exec_dir), name)
                    await ws_svc.register_file(
                        workspace=ws, filename=name, relative_path=rel,
                        file_size=os.path.getsize(p), source_type="generated",
                        session_id=self.session_id or None,
                    )
                    files.append({"filename": name, "relative_path": rel})
            if len(stdout) > 1000:
                out_name = "stdout.txt"
                with open(os.path.join(exec_dir, out_name), "w", encoding="utf-8") as f:
                    f.write(stdout)
                rel = os.path.join("exec", os.path.basename(exec_dir), out_name)
                await ws_svc.register_file(
                    workspace=ws, filename=out_name, relative_path=rel,
                    file_size=len(stdout.encode()), source_type="generated",
                    session_id=self.session_id or None,
                )
                files.append({"filename": out_name, "relative_path": rel})
            await ws_svc.log_action(workspace=ws, action="execute",
                                    file_path="sandbox:execute", user_id=self.user_id,
                                    session_id=self.session_id or None, success=not timed_out)
        except Exception as e:
            logger.warning("[SandboxRuntime] 产物登记失败: %s", e)

        return SandboxResult(sandbox=sandbox_label, stdout=stdout, stderr=stderr,
                             exit_code=exit_code, timed_out=timed_out, files=files)
