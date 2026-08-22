from packages.agent.llm.factory import create_llm
"""LLM 提供者 - 统一 LLM 创建与调用（设计文档 11.2.2）

统一封装 LangChain ChatModel 的创建与调用，禁止裸调用。
所有 LLM 请求必须通过此入口，由 Harness 注入配置、Token 预算、上下文窗口。
"""
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


def create_llm_sync(
    model_name: str = "gpt-4o",
    temperature: float = 0.3,
    max_tokens: Optional[int] = None,
    top_p: float = 0.9,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    provider: str = "openai",
    **kwargs,
) -> Any:
    """创建 LLM 实例（已废弃，使用 factory.create_llm）

    已迁移到 packages.agent.llm.factory.create_llm
    """
    logger.warning("create_llm_sync is deprecated, use packages.agent.llm.factory.create_llm")
    return create_llm(
        provider=provider,
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        base_url=base_url,
        api_key=api_key,
        **kwargs,
    )


def get_llm_by_config(model_config: Dict[str, Any]) -> Any:
    """从配置字典创建 LLM 实例（使用统一工厂）

    config 格式：
    {
        "provider": "qwen" | "openai" | "anthropic" | "azure" | ...,
        "model": "qwen3.5-397b-a17b" | "gpt-4o" | ...,
        "temperature": 0.3,
        "max_tokens": None,  # None 表示不限制
        "base_url": "...",  # 可选
        "api_key": "...",   # 可选
    }
    """
    # 使用统一工厂函数
    return create_llm(
        provider=model_config.get("provider", "openai"),
        model_name=model_config.get("model", "gpt-4o"),
        temperature=model_config.get("temperature", 0.3),
        max_tokens=model_config.get("max_tokens", None),  # 默认不限制
        top_p=model_config.get("top_p", 0.9),
        base_url=model_config.get("base_url"),
        api_key=model_config.get("api_key"),
    )


async def invoke_llm(
    llm: Any,
    messages: List[Any],
    system_prompt: Optional[str] = None,
) -> Any:
    """统一 LLM 调用入口（带系统提示词注入）

    Args:
        llm: LangChain ChatModel 实例
        messages: 消息列表（HumanMessage/AIMessage/SystemMessage）
        system_prompt: 系统提示词（可选，会自动插入到消息开头）

    Returns:
        LLM 响应（AIMessage）
    """
    from langchain_core.messages import SystemMessage

    # 注入系统提示词
    if system_prompt:
        messages = [SystemMessage(content=system_prompt)] + list(messages)

    return await llm.ainvoke(messages)


async def stream_llm(
    llm: Any,
    messages: List[Any],
    system_prompt: Optional[str] = None,
    on_token: Optional[callable] = None,
) -> str:
    """流式 LLM 调用

    Args:
        llm: LangChain ChatModel 实例
        messages: 消息列表
        system_prompt: 系统提示词
        on_token: token 回调函数 async (chunk) -> None

    Returns:
        完整响应字符串
    """
    from langchain_core.messages import SystemMessage

    if system_prompt:
        messages = [SystemMessage(content=system_prompt)] + list(messages)

    chunks = []
    async for chunk in llm.astream(messages):
        chunks.append(chunk)
        if on_token:
            await on_token(chunk)

    if not chunks:
        return ""

    # 合并所有 chunk
    response = chunks[0]
    for c in chunks[1:]:
        response = response + c

    return str(response.content)
