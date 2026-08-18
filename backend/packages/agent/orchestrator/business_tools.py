"""业务工具注册 - 供子 Agent 通过 tools_whitelist 调用的真实能力

将系统的领域能力（知识库、沙箱代码执行）封装为 LangChain Tool 并注册进 ToolRegistry，
使子垂直 Agent 能按白名单绑定并真实执行。代码执行遵循 Harness 架构：
沙箱优先（nsjail）、缺失降级受限子进程，产物自动登记进用户工作空间。
"""
import logging
import os
import re
import mimetypes
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 统一沙箱安全检查（复用 Harness SandboxRuntime）
from packages.agent.core.harness.sandbox.runtime import check_code_safety as _check_code_safety  # noqa: E402

# 允许保存的文件扩展名白名单（防写任意/二进制文件）
ALLOWED_FILE_EXTENSIONS = (
    ".py", ".md", ".txt", ".json", ".csv", ".yaml", ".yml",
    ".html", ".js", ".ts", ".sh", ".toml", ".xml",
)
MAX_GENERATED_FILE_SIZE = 1024 * 1024  # 1MB


def _validate_workspace_target(filename: str, folder: str) -> Optional[str]:
    """校验生成文件的文件名/子目录，返回拒绝原因（合法返回 None）。

    - filename 必须是 basename（不允许路径分隔符 / 穿越），且扩展名在白名单内
    - folder 可选，禁止穿越/绝对路径，只允许 [\\w\\-/]+
    """
    name = (filename or "").strip()
    if not name:
        return "文件名不能为空"
    if "/" in name or "\\" in name or ".." in name or os.path.isabs(name):
        return "文件名不能包含路径或 '..'"
    ext = os.path.splitext(name)[1].lower()
    if not ext or ext not in ALLOWED_FILE_EXTENSIONS:
        return f"不支持的扩展名：{name}（允许：{' '.join(ALLOWED_FILE_EXTENSIONS)}）"

    folder = (folder or "").strip()
    if folder:
        if os.path.isabs(folder) or ".." in folder or not re.fullmatch(r"[\w\-/]+", folder):
            return "子目录不合法（禁止穿越或绝对路径）"
    return None


async def ensure_business_tools(db: AsyncSession, user_id: Optional[int] = None) -> None:
    """注册系统业务工具到 ToolRegistry。

    幂等：知识库工具若已注册则复用；execute_code 用当前 user_id 每次覆盖注册，
    使其定位于对应用户的工作空间。
    """
    from packages.agent.tools.registry import get_tool_registry

    reg = get_tool_registry()

    def _register_execute(current_user_id: int):
        from langchain_core.tools import tool

        @tool
        async def execute_code(code: str, language: str = "python", session_id: str = "",
                               requirements: str = "") -> str:
            """在安全沙箱中执行代码，产物保存到你的工作空间。

            当需要运行计算、脚本、生成文件时使用。代码在隔离沙箱执行，
            运行前会自动安装代码 import 的缺失依赖（隔离 venv），
            生成的产物会自动存放到你的工作空间（可查看/下载）。

            Args:
                code: 要执行的代码
                language: 语言，python/ nodejs/ bash
                session_id: 会话 ID（产物关联）
                requirements: 期望额外安装的依赖（可选，如 "pandas numpy"）
            """
            # 统一经 Harness SandboxRuntime（安全检查→沙箱/降级→产物登记→审计）
            from packages.agent.core.harness.sandbox.runtime import SandboxRuntime, check_code_safety

            reqs = [r for r in (requirements or "").replace(",", " ").split() if r]
            try:
                rt = SandboxRuntime(db, user_id=current_user_id, session_id=session_id or None)
                res = await rt.execute(code, language, requirements=reqs or None)
            except Exception as e:
                logger.warning("[SandboxTool] 沙箱执行失败: %s", e)
                return f"[错误] 沙箱执行失败: {e}"

            if res.blocked:
                return f"[安全拦截] {res.blocked}"
            head = res.stdout[:2000]
            err_head = res.stderr[:2000]
            return (f"[{res.sandbox}] exit={res.exit_code} {'(超时)' if res.timed_out else ''}\n"
                    f"stdout:\n{head}\n"
                    f"stderr:\n{err_head}\n"
                    f"工作空间产物: {res.files if res.files else '无'}")

        execute_code.name = "execute_code"

        # Harness 沙箱化：高危 EXECUTE 工具在 ToolExecutionManager 注册沙箱执行器，
        # 执行经独立 SandboxRuntime 工作区（设计文档 2.2/3.1）。
        # （工具为 pydantic StructuredTool 不可附加属性，故按名称键控注册）
        from packages.agent.core.harness.tools import ToolExecutionManager

        async def _sandbox_execute_code(sandbox, tool_input: dict) -> str:
            reqs = [r for r in str(tool_input.get("requirements", "") or "").replace(",", " ").split() if r]
            res = await sandbox.execute(
                tool_input.get("code", ""),
                tool_input.get("language", "python"),
                requirements=reqs or None,
            )
            # 透出产物与执行后端，供 ToolExecutionManager 的 tool_event 前端渲染
            sandbox._last_products = list(res.files) if res.files else []
            sandbox._last_sandbox = res.sandbox or ""
            if res.blocked:
                return f"[安全拦截] {res.blocked}"
            return (f"[{res.sandbox}] exit={res.exit_code} {'(超时)' if res.timed_out else ''}\n"
                    f"stdout:\n{res.stdout[:2000]}\nstderr:\n{res.stderr[:2000]}\n"
                    f"工作空间产物: {res.files if res.files else '无'}")
        ToolExecutionManager.register_sandbox_executor("execute_code", _sandbox_execute_code)

        if reg.get("execute_code"):
            reg.unregister("execute_code")
        reg.register(execute_code, category="business")
        logger.info("[BusinessTools] 注册沙箱执行工具 execute_code (user=%s)", current_user_id)
        return execute_code

    if not reg.get("list_knowledge_bases"):
        from langchain_core.tools import tool

        @tool
        async def list_knowledge_bases() -> str:
            """列出当前系统可用的知识库及其名称、ID。用于了解可检索的知识范围。"""
            from packages.rag.services.kb_service import list_knowledge_bases as _list

            kbs = await _list(db)
            if not kbs:
                return "当前没有知识库。"
            return "\n".join(f"- {kb.name} (id={kb.id})" for kb in kbs)

        @tool
        async def get_knowledge_base_detail(kb_id: str) -> str:
            """获取指定知识库的详情（名称、描述）。参数 kb_id 为知识库 ID。"""
            from packages.rag.services.kb_service import get_knowledge_base as _get

            kb = await _get(db, kb_id)
            if kb is None:
                return f"未找到知识库：{kb_id}"
            return f"名称: {kb.name}\n描述: {kb.description or ''}"

        list_knowledge_bases.name = "list_knowledge_bases"
        get_knowledge_base_detail.name = "get_knowledge_base_detail"
        reg.register(list_knowledge_bases, category="business")
        reg.register(get_knowledge_base_detail, category="business")

    if user_id is not None:
        _register_execute(user_id)
    elif not reg.get("execute_code"):
        # 未提供 user_id 时用默认 1（兼容旧调用）
        _register_execute(1)

    def _register_generate(current_user_id: int):
        from langchain_core.tools import tool

        @tool
        async def save_workspace_file(filename: str, content: str, folder: str = "", session_id: str = "") -> str:
            """把生成的文件内容写入你的工作空间（可查看/下载）。

            当用户要求生成/创建/保存一个文件时使用（如 .py/.md/.json/.csv/.txt
            等文本文件）。文件内容由本工具直接写入用户自己的工作空间，无需执行代码。

            Args:
                filename: 文件名（需含扩展名，如 report.md）
                content: 文件的完整内容
                folder: 可选子目录（相对工作空间，如 docs），默认放 generated 根下
                session_id: 会话 ID（产物关联）
            """
            reason = _validate_workspace_target(filename, folder)
            if reason:
                return f"[参数错误] {reason}"
            if len(content or "") > MAX_GENERATED_FILE_SIZE:
                return f"[参数错误] 内容超过大小上限（{MAX_GENERATED_FILE_SIZE // 1024}KB）"

            from packages.core.system.models.user import User
            from packages.agent.services.workspace_service import WorkspaceService

            try:
                user = await db.get(User, current_user_id)
                if user is None:
                    return "[错误] 用户不存在"
                ws_svc = WorkspaceService(db)
                ws = await ws_svc.get_or_create_workspace(user)
            except Exception as e:
                logger.warning("[FileGenTool] 工作区获取失败: %s", e)
                return f"[错误] 工作区获取失败: {e}"

            folder = (folder or "").strip().strip("/")
            rel_dir = os.path.join("generated", folder) if folder else "generated"
            abs_dir = os.path.join(ws.root_path, rel_dir)
            try:
                os.makedirs(abs_dir, exist_ok=True)
                abs_path = os.path.join(abs_dir, filename)
                with open(abs_path, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception as e:
                logger.warning("[FileGenTool] 写入失败: %s", e)
                return f"[错误] 文件写入失败: {e}"

            rel_path = os.path.join(rel_dir, filename)
            mime, _ = mimetypes.guess_type(filename)
            size = len(content.encode("utf-8"))
            try:
                # 幂等登记：同工作区同路径已存在则更新，避免唯一约束冲突污染共享会话。
                from sqlalchemy import select
                from packages.agent.models.workspace import WorkspaceFile

                existing = (
                    await db.execute(
                        select(WorkspaceFile).where(
                            WorkspaceFile.workspace_id == ws.id,
                            WorkspaceFile.relative_path == rel_path,
                        )
                    )
                ).scalar_one_or_none()
                if existing:
                    existing.file_size = size
                    existing.mime_type = mime
                    existing.session_id = session_id or None
                    file_id = str(existing.id)
                else:
                    wf = await ws_svc.register_file(
                        workspace=ws, filename=filename, relative_path=rel_path,
                        file_size=size, mime_type=mime,
                        source_type="generated", session_id=session_id or None,
                    )
                    file_id = str(getattr(wf, "id", ""))

                await ws_svc.log_action(
                    workspace=ws, action="generate_file", file_path=rel_path,
                    user_id=current_user_id, session_id=session_id or None,
                    file_size=size, success=True,
                )
            except Exception as e:
                # 恢复会话可继续使用，避免一次登记失败拖垮整轮图的后续操作
                try:
                    await db.rollback()
                except Exception:
                    pass
                logger.warning("[FileGenTool] 登记/审计失败(文件已写入): %s", e)
                return f"文件已写入磁盘，但登记失败：{e}（相对路径 {rel_path}）"

            return f"文件已保存：{rel_path}（file_id={file_id}），可在工作空间查看/下载。"

        save_workspace_file.name = "save_workspace_file"
        if reg.get("save_workspace_file"):
            reg.unregister("save_workspace_file")
        reg.register(save_workspace_file, category="business")

        # WRITE 沙箱化（设计文档 3.1）：写原语先落 SandboxScope 隔离 workdir（真沙箱），
        # 再受控提交到用户持久工作区（可查看/下载）。工具本体保留为非沙箱降级路径。
        from packages.agent.core.harness.tools import ToolExecutionManager

        async def _sandbox_save_workspace_file(sandbox, tool_input: dict) -> str:
            d = dict(tool_input or {})
            filename = str(d.get("filename", "")).strip()
            content = d.get("content", "") or ""
            folder = str(d.get("folder", "") or "").strip().strip("/")
            session_id = str(d.get("session_id", "") or "")

            reason = _validate_workspace_target(filename, folder)
            if reason:
                return f"[参数错误] {reason}"
            if len(content) > MAX_GENERATED_FILE_SIZE:
                return f"[参数错误] 内容超过大小上限（{MAX_GENERATED_FILE_SIZE // 1024}KB）"

            # 1. 写原语沙箱化：先落隔离 workdir（随会话销毁，防逃逸/残留）
            if getattr(sandbox, "workdir", None):
                try:
                    sandbox_dir = os.path.join(sandbox.workdir, "generated", folder)
                    os.makedirs(sandbox_dir, exist_ok=True)
                    with open(os.path.join(sandbox_dir, filename), "w", encoding="utf-8") as f:
                        f.write(content)
                except Exception as e:
                    logger.warning("[FileGenTool] 沙箱暂存失败: %s", e)

            # 2. 受控提交：落用户工作区 + 登记 + 审计
            db_ = getattr(sandbox, "db", None)
            user_id_ = getattr(sandbox, "user_id", None) or current_user_id
            from packages.core.system.models.user import User
            from packages.agent.services.workspace_service import WorkspaceService

            try:
                user = await db_.get(User, user_id_)
                if user is None:
                    return "[错误] 用户不存在"
                ws_svc = WorkspaceService(db_)
                ws = await ws_svc.get_or_create_workspace(user)
            except Exception as e:
                return f"[错误] 工作区获取失败: {e}"

            rel_dir = os.path.join("generated", folder) if folder else "generated"
            abs_dir = os.path.join(ws.root_path, rel_dir)
            try:
                os.makedirs(abs_dir, exist_ok=True)
                with open(os.path.join(abs_dir, filename), "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception as e:
                return f"[错误] 文件写入失败: {e}"

            rel_path = os.path.join(rel_dir, filename)
            mime, _ = mimetypes.guess_type(filename)
            size = len(content.encode("utf-8"))
            try:
                from sqlalchemy import select
                from packages.agent.models.workspace import WorkspaceFile

                existing = (
                    await db_.execute(
                        select(WorkspaceFile).where(
                            WorkspaceFile.workspace_id == ws.id,
                            WorkspaceFile.relative_path == rel_path,
                        )
                    )
                ).scalar_one_or_none()
                if existing:
                    existing.file_size = size
                    existing.mime_type = mime
                    existing.session_id = session_id or None
                    file_id = str(existing.id)
                else:
                    wf = await ws_svc.register_file(
                        workspace=ws, filename=filename, relative_path=rel_path,
                        file_size=size, mime_type=mime,
                        source_type="generated", session_id=session_id or None,
                    )
                    file_id = str(getattr(wf, "id", ""))
                await ws_svc.log_action(
                    workspace=ws, action="generate_file", file_path=rel_path,
                    user_id=user_id_, session_id=session_id or None,
                    file_size=size, success=True,
                )
            except Exception as e:
                try:
                    await db_.rollback()
                except Exception:
                    pass
                return f"文件已写入磁盘，但登记失败：{e}（相对路径 {rel_path}）"

            # 透出产物供 tool_event 前端渲染
            sandbox._last_products = [{"filename": filename, "relative_path": rel_path}]
            sandbox._last_sandbox = getattr(sandbox, "_last_sandbox", "") or "workspace"
            return f"文件已保存：{rel_path}（file_id={file_id}），可在工作空间查看/下载。"

        ToolExecutionManager.register_sandbox_executor("save_workspace_file", _sandbox_save_workspace_file)
        logger.info("[BusinessTools] 注册文件生成工具 save_workspace_file (user=%s)", current_user_id)
        return save_workspace_file

    if user_id is not None:
        _register_generate(user_id)
    elif not reg.get("save_workspace_file"):
        _register_generate(1)

    # 工具风险分级注册（Harness 工具治理门面，幂等）
    # EXECUTE/WRITE 高危走沙箱；读取类进程内执行。
    from packages.agent.core.harness.tools import ToolExecutionManager, ToolRisk
    ToolExecutionManager.register_many_risks({
        "execute_code": ToolRisk.EXECUTE,
        "save_workspace_file": ToolRisk.WRITE,
        "list_knowledge_bases": ToolRisk.READ,
        "get_knowledge_base_detail": ToolRisk.READ,
    })
    logger.info("[BusinessTools] 风险分级已注册: %s", dict(ToolExecutionManager._risks))
