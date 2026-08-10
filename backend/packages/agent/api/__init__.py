"""
Agent API 模块

导出所有 API 路由
"""

from packages.agent.api.agents import router as agents_router
from packages.agent.api.agent_runtime import router as agent_runtime_router
# chat.py 已废弃，不再导入
# from packages.agent.api.chat import router as chat_router
from packages.agent.api.conversations import router as conversations_router
from packages.agent.api.conversation_history import router as conversation_history_router
from packages.agent.api.skills import router as skills_router
from packages.agent.api.feedback import router as feedback_router
from packages.agent.api.tracing import router as tracing_router

# 新增的 Runtime 和 Workspace API
from packages.agent.api.workspaces import router as workspaces_router
from packages.agent.api.runtimes import router as runtimes_router
from packages.agent.api.sessions import router as sessions_router
from packages.agent.api.code_execution import router as code_execution_router

__all__ = [
    "agents_router",
    "agent_runtime_router",
    # "chat_router",  # 已废弃
    "conversations_router",
    "conversation_history_router",
    "skills_router",
    "feedback_router",
    "tracing_router",
    "workspaces_router",
    "runtimes_router",
    "sessions_router",
    "code_execution_router",
]
