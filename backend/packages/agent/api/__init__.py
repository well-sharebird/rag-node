"""
Agent API 模块

导出所有 API 路由
"""

from packages.agent.api.agents import router as agents_router
# chat.py 已废弃，不再导入
# from packages.agent.api.chat import router as chat_router
from packages.agent.api.conversations import router as conversations_router
from packages.agent.api.conversation_history import router as conversation_history_router
from packages.agent.api.skills import router as skills_router
from packages.agent.api.feedback import router as feedback_router
from packages.agent.api.tracing import router as tracing_router

from packages.agent.api.workspaces import router as workspaces_router

__all__ = [
    "agents_router",
    # "chat_router",  # 已废弃
    "conversations_router",
    "conversation_history_router",
    "skills_router",
    "feedback_router",
    "tracing_router",
    "workspaces_router",
]
