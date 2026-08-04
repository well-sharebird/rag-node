"""
Skills 包
包含可被 Agent 调用的工具函数

## 可用工具集
- knowledge_base_tools: 知识库管理工具
- model_tools: 模型管理工具
- prompt_tools: 提示词工程管理工具
- agent_tools: 智能体管理工具
- create_agent_skill: 智能体创建技能
"""

from app.skills.knowledge_base_tools import get_kb_tools, KB_TOOL_PROMPT
from app.skills.model_tools import get_model_tools, MODEL_TOOL_PROMPT
from app.skills.prompt_tools import get_prompt_tools, PROMPT_TOOL_PROMPT
from app.skills.agent_tools import get_agent_tools, AGENT_TOOL_PROMPT
from app.skills.create_agent_skill import create_agent_skill, get_create_agent_tool

__all__ = [
    # 工具集获取函数
    "get_kb_tools",
    "get_model_tools",
    "get_prompt_tools",
    "get_agent_tools",
    "get_create_agent_tool",
    # 技能函数
    "create_agent_skill",
    # 系统提示词
    "KB_TOOL_PROMPT",
    "MODEL_TOOL_PROMPT",
    "PROMPT_TOOL_PROMPT",
    "AGENT_TOOL_PROMPT",
]
