"""业务工具注册 - 供子 Agent 通过 tools_whitelist 调用的真实能力

将系统的领域能力（知识库、沙箱代码执行）封装为 LangChain Tool 并注册进 ToolRegistry，
使子垂直 Agent 能按白名单绑定并真实执行。代码执行遵循 Harness 架构：
沙箱优先（nsjail）、缺失降级受限子进程，产物自动登记进用户工作空间。
"""
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 统一沙箱安全检查（复用 Harness SandboxRuntime）
from packages.agent.harness.sandbox.runtime import check_code_safety as _check_code_safety  # noqa: E402


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
        async def execute_code(code: str, language: str = "python", session_id: str = "") -> str:
            """在安全沙箱中执行代码，产物保存到你的工作空间。

            当需要运行计算、脚本、生成文件时使用。代码在隔离沙箱执行，
            生成的产物会自动存放到你的工作空间（可查看/下载）。

            Args:
                code: 要执行的代码
                language: 语言，python/ nodejs/ bash
                session_id: 会话 ID（产物关联）
            """
            # 统一经 Harness SandboxRuntime（安全检查→沙箱/降级→产物登记→审计）
            from packages.agent.harness.sandbox.runtime import SandboxRuntime, check_code_safety

            try:
                rt = SandboxRuntime(db, user_id=current_user_id, session_id=session_id or None)
                res = await rt.execute(code, language)
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
