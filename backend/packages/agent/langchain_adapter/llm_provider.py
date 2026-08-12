"""LLM 提供者 - 统一 LLM 创建与调用（设计文档 11.2.2）

统一封装 LangChain ChatModel 的创建与调用，禁止裸调用。
所有 LLM 请求必须通过此入口，由 Harness 注入配置、Token 预算、上下文窗口。
"""
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


async def create_llm(
    model_name: str = "qwen3.5-397b-a17b",
    temperature: float = 0.3,
    max_tokens: int = 2048,
    top_p: float = 0.9,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    **kwargs,
) -> Any:
    """创建 LLM 实例

    Args:
        model_name: 模型名称
        temperature: 温度
        max_tokens: 最大输出 token
        top_p: top_p 采样
        base_url: API 基础 URL（可选，用于自定义端点）
        api_key: API Key（可选）
        **kwargs: 其他参数

    Returns:
        LangChain ChatModel 实例
    """
    from langchain_openai import ChatOpenAI

    # 默认配置
    config = {
        "model": model_name,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "top_p": top_p,
    }

    # 如果有自定义 base_url，使用兼容模式
    if base_url:
        config["base_url"] = base_url
    if api_key:
        config["api_key"] = api_key

    try:
        llm = ChatOpenAI(**config)
        logger.info(f"LLM 创建成功：{model_name}")
        return llm
    except Exception as e:
        logger.error(f"LLM 创建失败：{e}")
        raise


def get_llm_by_config(model_config: Dict[str, Any]) -> Any:
    """从配置字典创建 LLM 实例

    config 格式：
    {
        "provider": "openai" | "anthropic" | "azure",
        "model": "gpt-4o" | "claude-3-5-sonnet" | ...,
        "temperature": 0.3,
        "max_tokens": 2048,
        "base_url": "...",  # 可选
        "api_key": "...",   # 可选
    }
    """
    provider = model_config.get("provider", "openai").lower()

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model_config.get("model", "gpt-4o"),
            temperature=model_config.get("temperature", 0.3),
            max_tokens=model_config.get("max_tokens", 2048),
            base_url=model_config.get("base_url"),
            api_key=model_config.get("api_key"),
        )
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=model_config.get("model", "claude-3-5-sonnet-20241022"),
            temperature=model_config.get("temperature", 0.3),
            max_tokens=model_config.get("max_tokens", 2048),
            api_key=model_config.get("api_key"),
        )
    elif provider == "azure":
        from langchain_openai import AzureChatOpenAI
        return AzureChatOpenAI(
            azure_deployment=model_config.get("deployment_name"),
            azure_endpoint=model_config.get("azure_endpoint"),
            api_version=model_config.get("api_version", "2024-02-15-preview"),
            api_key=model_config.get("api_key"),
            temperature=model_config.get("temperature", 0.3),
            max_tokens=model_config.get("max_tokens", 2048),
        )
    else:
        # 降级：使用 OpenAI 兼容模式
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model_config.get("model", "gpt-4o"),
            base_url=provider,  # 将 provider 作为 base_url 使用
            api_key=model_config.get("api_key", "sk-no-key"),
            temperature=model_config.get("temperature", 0.3),
            max_tokens=model_config.get("max_tokens", 2048),
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
