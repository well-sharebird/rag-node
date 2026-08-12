"""LangChain 适配器层 - 原子能力封装（设计文档 4.1）

LangChain 只提供原子能力，不负责业务流程、治理逻辑：
- LLM 调用：统一封装 ChatModel 创建与调用
- Tool 定义：工具注册、参数校验
- Memory：记忆读写封装
- Prompt：PromptTemplate 封装

所有能力必须通过 Harness 统一封装入口调用，禁止裸调用 LangChain。
"""
from packages.agent.langchain_adapter.llm_provider import create_llm, get_llm_by_config, invoke_llm
from packages.agent.langchain_adapter.tool_wrapper import ToolWrapper, wrap_tool, wrap_tools

__all__ = [
    "create_llm",
    "get_llm_by_config",
    "invoke_llm",
    "ToolWrapper",
    "wrap_tool",
    "wrap_tools",
]
