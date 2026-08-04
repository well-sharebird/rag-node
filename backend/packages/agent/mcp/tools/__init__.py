"""MCP Tools package."""

from .kb_tools import create_kb_tools, KB_TOOLS, handle_kb_tool
from .model_tools import create_model_tools, MODEL_TOOLS, handle_model_tool
from .prompt_tools import create_prompt_tools, PROMPT_TOOLS, handle_prompt_tool
from .agent_tools import create_agent_tools, AGENT_TOOLS, handle_agent_tool

__all__ = [
    "create_kb_tools",
    "KB_TOOLS",
    "handle_kb_tool",
    "create_model_tools",
    "MODEL_TOOLS",
    "handle_model_tool",
    "create_prompt_tools",
    "PROMPT_TOOLS",
    "handle_prompt_tool",
    "create_agent_tools",
    "AGENT_TOOLS",
    "handle_agent_tool",
]
