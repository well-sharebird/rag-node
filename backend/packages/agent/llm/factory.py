"""LLM 工厂 - 统一 LLM 创建与配置（生产级）

所有 LLM 实例必须通过此工厂创建，禁止裸调用 LangChain ChatModel。
由 Harness 注入配置、Token 预算、上下文窗口。
"""
from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)


def create_llm(
    provider: str = "openai",
    model_name: str = "gpt-4o",
    temperature: float = 0.3,
    max_tokens: Optional[int] = None,  # None 表示不限制
    top_p: float = 0.9,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    **kwargs,
) -> Any:
    """创建 LLM 实例的统一工厂函数

    Args:
        provider: 提供商 ("openai", "anthropic", "azure", "qwen", "deepseek", "ollama", "google")
        model_name: 模型名称
        temperature: 温度 (0-2)
        max_tokens: 最大输出 token (None 表示不限制，让模型自由决定)
        top_p: top_p 采样 (0-1)
        base_url: API 基础 URL（可选，用于自定义端点）
        api_key: API Key（可选）
        **kwargs: 其他参数

    Returns:
        LangChain ChatModel 实例或自定义 ChatModel（如 CompatibleChatModel）

    Raises:
        ValueError: 不支持的提供商
    """
    provider = provider.lower()
    
    # 构建通用配置
    common_kwargs = {
        "temperature": temperature,
        "top_p": top_p,
    }
    
    # 只在设置了 max_tokens 时添加（None 表示不限制）
    if max_tokens is not None:
        common_kwargs["max_tokens"] = max_tokens
    
    if api_key:
        common_kwargs["api_key"] = api_key
    
    if base_url:
        # 确保 base_url 以 /v1 结尾（LangChain 内部不再添加）
        base_url = base_url.rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
        common_kwargs["base_url"] = base_url
    
    # 根据提供商创建不同的 LLM
    if provider == "qwen":
        # Qwen3.5 使用自定义 ChatModel（支持 reasoning 字段）
        from packages.agent.llm.compatible_llm import CompatibleChatModel
        
        # 使用默认配置（如果未提供）
        if not base_url:
            base_url = "http://1.181.141.96:6018/qwen3.5-397b-a17b/v1"
        if not api_key:
            api_key = ""
        
        return CompatibleChatModel(
            model_name=model_name or "qwen3.5-397b-a17b",
            base_url=base_url,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,  # None 表示不限制
        )
    
    elif provider in ("openai", "deepseek"):
        from langchain_openai import ChatOpenAI
        
        # DeepSeek 使用 OpenAI 兼容接口
        if provider == "deepseek":
            common_kwargs["model"] = model_name or "deepseek-chat"
            common_kwargs["base_url"] = "https://api.deepseek.com"
            # DeepSeek API Key 从环境变量或参数获取
            if not api_key:
                import os
                api_key = os.environ.get("DEEPSEEK_API_KEY", "")
            common_kwargs["api_key"] = api_key
        else:
            common_kwargs["model"] = model_name or "gpt-4o"
            if api_key:
                common_kwargs["api_key"] = api_key
        
        return ChatOpenAI(**common_kwargs)
    
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        
        if not api_key:
            import os
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        
        return ChatAnthropic(
            model=model_name or "claude-3-5-sonnet-20241022",
            temperature=temperature,
            top_p=top_p,
            api_key=api_key,
            **(common_kwargs if "max_tokens" in common_kwargs else {})
        )
    
    elif provider == "azure":
        from langchain_openai import AzureChatOpenAI
        
        import os
        return AzureChatOpenAI(
            azure_deployment=model_name,
            azure_endpoint=base_url or os.environ.get("AZURE_OPENAI_ENDPOINT", ""),
            api_version=kwargs.get("api_version", "2024-02-15-preview"),
            api_key=api_key or os.environ.get("AZURE_OPENAI_API_KEY", ""),
            temperature=temperature,
            top_p=top_p,
            **(common_kwargs if "max_tokens" in common_kwargs else {})
        )
    
    elif provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        
        if not api_key:
            import os
            api_key = os.environ.get("GOOGLE_API_KEY", "")
        
        return ChatGoogleGenerativeAI(
            model=model_name or "gemini-pro",
            temperature=temperature,
            top_p=top_p,
            google_api_key=api_key,
            **(common_kwargs if "max_tokens" in common_kwargs else {})
        )
    
    elif provider == "ollama":
        from langchain_ollama import ChatOllama
        
        return ChatOllama(
            model=model_name or "llama3.1",
            temperature=temperature,
            top_p=top_p,
            base_url=base_url or "http://localhost:11434",
            num_predict=max_tokens if max_tokens is not None else 2048,
        )
    
    elif provider == "local_qwen":
        # 本地 Qwen 模型，使用 OpenAI 兼容接口
        from langchain_openai import ChatOpenAI
        
        # 本地模型 API Key 处理
        effective_api_key = None if (api_key and api_key.lower() in ["not_required", "not-needed", "none", ""]) else api_key
        
        return ChatOpenAI(
            model=model_name or "qwen",
            temperature=temperature,
            top_p=top_p,
            base_url=base_url,
            api_key=effective_api_key or "not-required",
            **(common_kwargs if "max_tokens" in common_kwargs else {})
        )
    
    else:
        # 降级：使用 OpenAI 兼容模式（将 provider 作为 base_url）
        from langchain_openai import ChatOpenAI
        
        logger.warning(f"未知的提供商 {provider}，降级为 OpenAI 兼容模式")
        return ChatOpenAI(
            model=model_name or "gpt-4o",
            base_url=provider,  # 将 provider 作为 base_url 使用
            api_key=api_key or "sk-no-key",
            temperature=temperature,
            top_p=top_p,
            **(common_kwargs if "max_tokens" in common_kwargs else {})
        )


def create_llm_from_config(model_config: Dict[str, Any]) -> Any:
    """从配置字典创建 LLM 实例

    Args:
        model_config: 配置字典
            {
                "provider": "qwen" | "openai" | "anthropic" | "azure" | ...,
                "model": "qwen3.5-397b-a17b" | "gpt-4o" | ...,
                "temperature": 0.3,
                "max_tokens": None,  # None 表示不限制
                "top_p": 0.9,
                "base_url": "...",  # 可选
                "api_key": "...",   # 可选
            }

    Returns:
        LangChain ChatModel 实例
    """
    return create_llm(
        provider=model_config.get("provider", "openai"),
        model_name=model_config.get("model", "gpt-4o"),
        temperature=model_config.get("temperature", 0.3),
        max_tokens=model_config.get("max_tokens", None),  # 默认不限制
        top_p=model_config.get("top_p", 0.9),
        base_url=model_config.get("base_url"),
        api_key=model_config.get("api_key"),
    )
