"""
Agent Runtime 服务
基于 LangGraph 实现 Agent 的动态加载和运行

v2.0: 整合 AgentGraphFactory，支持 LangGraph 工厂函数模式
- 运行时动态构建图
- 支持 MCP 工具动态加载
- 支持技能渐进式加载
- 支持中间件链
"""
from packages.agent.llm.factory import create_llm
import logging
import time
from typing import Optional, AsyncGenerator, Any
from datetime import datetime
from uuid import uuid4

logger = logging.getLogger(__name__)

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from typing_extensions import TypedDict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from packages.agent.models.agent import AgentConfig, AgentCallLog
from packages.agent.services.agent_memory_service import AgentMemoryService
from packages.agent.schemas.chat import ModelConfig
from packages.core.database import engine, async_session_factory
from sqlalchemy.orm import sessionmaker

# 兼容旧导入 - AgentState 已在本文件定义
# StateGraphBuilder 已废弃，请使用新的 TAO Graph 架构

# 同步 Session factory 用于 LangGraph CheckpointSaver
sync_session_factory = sessionmaker(bind=engine.sync_engine)

def get_sync_db():
    """获取同步数据库 Session"""
    db = sync_session_factory()
    try:
        yield db
    finally:
        db.close()


async def create_langchain_llm(model_config: Any, db: Any = None) -> Any:
    """
    根据模型配置创建 LangChain LLM 实例

    支持主流 LLM 供应商，URL 和 API Key 统一从供应商配置获取

    注意：model_config 可能是：
    1. ModelConfig schema (使用 model, base_url 字段)
    2. ModelConfig ORM 模型 (使用 model_id, api_url 字段)
    """
    from sqlalchemy import select
    from packages.model_gateway.models.model_config import ModelConfig as DBModelConfig
    from packages.model_gateway.models.model_gateway import ModelProvider

    # 兼容 schema 和 ORM 模型的字段名差异
    # schema: model, base_url | ORM: model_id, api_url
    model_name = getattr(model_config, 'model', None) or getattr(model_config, 'model_id', None)
    provider_code = getattr(model_config, 'provider', '').lower()
    temperature = getattr(model_config, 'temperature', 0.7)
    max_tokens = getattr(model_config, 'max_tokens', 4096)
    top_p = getattr(model_config, 'top_p', 1.0)

    # 统一从供应商配置获取 URL 和 API Key
    api_key = None
    api_url = None

    # 前端通常传 model_id（如 qwen3.5-397b-a17b），而 provider_code 可能不匹配
    # 先从 model_configs 表按 model_id 反查真实的 provider code
    resolved_provider = provider_code
    if db and model_name and not provider_code:
        try:
            from sqlalchemy import select as _select
            result = await db.execute(
                _select(DBModelConfig).where(DBModelConfig.model_id == model_name).limit(1)
            )
            mc = result.scalar_one_or_none()
            if mc and mc.provider:
                resolved_provider = mc.provider.lower()
                print(f"[LLM] 从 model_configs 解析 provider | model={model_name} provider={resolved_provider}")
        except Exception as e:
            print(f"Failed to resolve provider from model_configs: {e}")
    elif db and provider_code:
        # provider_code 可能是 model_id，尝试从 model_configs 反查
        try:
            result = await db.execute(
                select(DBModelConfig).where(DBModelConfig.model_id == provider_code).limit(1)
            )
            mc = result.scalar_one_or_none()
            if mc and mc.provider:
                resolved_provider = mc.provider.lower()
                resolved_provider_fallback = True
                print(f"[LLM] provider 实为 model_id，解析为 provider={resolved_provider}")
        except Exception:
            pass

    if db and resolved_provider:
        try:
            # 从 ModelProvider 获取供应商配置
            result = await db.execute(
                select(ModelProvider).where(
                    ModelProvider.code == resolved_provider,
                ).limit(1)
            )
            provider_config = result.scalar_one_or_none()
            if provider_config:
                api_url = provider_config.base_url
                api_key = provider_config.api_key
                print(f"[LLM] 使用供应商配置 | provider={resolved_provider} url={api_url}")
        except Exception as e:
            print(f"Failed to get provider config: {e}")

    if provider_code == "anthropic":
        from langchain_anthropic import ChatAnthropic
        from packages.core.config import settings
        import os
        return ChatAnthropic(
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            anthropic_api_key=api_key or os.environ.get("ANTHROPIC_API_KEY", settings.secret_key),
        )

    elif provider_code == "openai":
        # 使用统一工厂
        return create_llm(
            provider="openai",
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            base_url=api_url,
            api_key=api_key,
        )

    elif provider_code == "azure":
        # 使用统一工厂
        return create_llm(
            provider="azure",
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            api_key=api_key,
        )

    elif provider_code == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        import os
        return ChatGoogleGenerativeAI(
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            google_api_key=api_key or os.environ.get("GOOGLE_API_KEY", ""),
        )

    elif provider_code == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=model_name,
            temperature=temperature,
            num_predict=max_tokens,
            top_p=top_p,
            base_url=api_url or "http://localhost:11434",
        )

    elif provider_code == "local_qwen":
        # 本地 Qwen 模型，使用 OpenAI 兼容接口
        # 使用统一工厂
        return create_llm(
            provider="local_qwen",
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            base_url=api_url,
            api_key=api_key,
        )

    else:
        # 默认使用 OpenAI 兼容接口 - 使用自定义 LLM 类绕过 API Key 验证
        from langchain_core.language_models.chat_models import BaseChatModel
        from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
        from langchain_core.outputs import ChatGeneration, ChatResult
        from pydantic import Field, PrivateAttr
        import httpx

        # 保存参数到闭包
        target_url = api_url
        target_model = model_name
        target_temp = temperature
        target_max_tokens = max_tokens
        target_top_p = top_p

        class SimpleChatHttp(BaseChatModel):
            """简单的 HTTP Chat 模型 - 用于不需要 API Key 的 OpenAI 兼容接口

            支持 OpenAI function calling（bind_tools + tool_calls 解析）。
            """
            base_url: str = Field(default=target_url)
            model_name: str = Field(default=target_model)
            temperature: float = Field(default=target_temp)
            max_tokens: int = Field(default=target_max_tokens)
            top_p: float = Field(default=target_top_p)
            _client: "httpx.AsyncClient" = PrivateAttr()
            _bound_tools: list = PrivateAttr(default_factory=list)

            def model_post_init(self, __context) -> None:
                self._client = httpx.AsyncClient(timeout=180.0)

            @property
            def _llm_type(self) -> str:
                return "simple_chat_http"

            @property
            def _identifying_params(self):
                return {"base_url": self.base_url, "model_name": self.model_name}

            def bind_tools(self, tools, **kwargs):
                """绑定工具（OpenAI function calling schema）。返回独立副本，避免污染。"""
                from langchain_core.utils.function_calling import convert_to_openai_tool

                bound = self.__class__(
                    base_url=self.base_url,
                    model_name=self.model_name,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    top_p=self.top_p,
                )
                bound._client = self._client
                bound._bound_tools = [convert_to_openai_tool(t) for t in tools]
                return bound

            def _to_openai_messages(self, messages: list[BaseMessage]) -> list:
                """将 LangChain 消息转换为 OpenAI 格式"""
                openai_messages = []
                for msg in messages:
                    if isinstance(msg, SystemMessage):
                        openai_messages.append({"role": "system", "content": msg.content})
                    elif isinstance(msg, HumanMessage):
                        openai_messages.append({"role": "user", "content": msg.content})
                    elif isinstance(msg, AIMessage):
                        openai_messages.append({"role": "assistant", "content": msg.content})
                    else:
                        openai_messages.append({"role": "user", "content": str(msg)})
                return openai_messages

            async def _agenerate(
                self,
                messages: list[BaseMessage],
                stop: list[str] | None = None,
                **kwargs,
            ) -> ChatResult:
                """异步生成响应（非流式，支持 function calling）"""
                import json as _json

                openai_messages = self._to_openai_messages(messages)

                payload = {
                    "model": self.model_name,
                    "messages": openai_messages,
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                    "top_p": self.top_p,
                    "stream": False,
                }
                if self._bound_tools:
                    payload["tools"] = self._bound_tools
                    payload["tool_choice"] = "auto"

                # 发送请求 - 不发送 Authorization header
                response = await self._client.post(
                    f"{self.base_url}/chat/completions", json=payload,
                )
                response.raise_for_status()
                data = response.json()
                msg = data["choices"][0]["message"]

                content = msg.get("content") or ""
                tool_calls = msg.get("tool_calls") or []

                if tool_calls:
                    # 解析 OpenAI tool_calls → LangChain AIMessage.tool_calls
                    lc_tool_calls = []
                    for tc in tool_calls:
                        fn = tc.get("function", {})
                        lc_tool_calls.append({
                            "name": fn.get("name", ""),
                            "args": _json.loads(fn.get("arguments") or "{}"),
                            "id": tc.get("id", ""),
                        })
                    return ChatResult(generations=[ChatGeneration(
                        message=AIMessage(content=content, tool_calls=lc_tool_calls))])

                # Qwen 等推理模型可能把输出放 reasoning 而 content 为空/None，需兜底
                if not content:
                    content = msg.get("reasoning") or ""
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])

            async def _astream(
                self,
                messages: list[BaseMessage],
                stop: list[str] | None = None,
                **kwargs,
            ):
                """异步流式生成响应 - 逐 token 解析 OpenAI SSE 流"""
                import json
                from langchain_core.messages import AIMessageChunk
                from langchain_core.outputs import ChatGenerationChunk

                # 模型先输出 reasoning，然后切换到 content，不会交叉
                # 直接按字段区分即可，不需要额外的状态追踪

                openai_messages = self._to_openai_messages(messages)

                payload = {
                    "model": self.model_name,
                    "messages": openai_messages,
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                    "top_p": self.top_p,
                    "stream": True,
                }
                if self._bound_tools:
                    payload["tools"] = self._bound_tools
                    payload["tool_choice"] = "auto"

                logger.info("=" * 80)
                logger.info("[_astream] START - Model: %s", self.model_name)
                logger.info("=" * 80)

                chunk_idx = 0
                async with self._client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        data = line[6:].strip()
                        if data == "[DONE]":
                            logger.info("[_astream] END - [DONE] received")
                            break
                        try:
                            obj = json.loads(data)
                            choices = obj.get("choices") or []
                            if not choices:
                                continue
                            delta = choices[0].get("delta") or {}
                            # 标准 OpenAI 流用 content 字段（最终答案）；推理模型
                            # （如 Qwen/deepseek-reasoner）把思考放在 reasoning_content
                            # / reasoning 字段。两类分开产出并打标，使前端能把"思考过程"
                            # 与"最终答案"分开渲染（思考块走独立 reasoning 事件）。
                            reason_text = delta.get("reasoning_content") or delta.get("reasoning")
                            answer_text = delta.get("content")
                            
                            # 🔍 打印模型原始输出（用 WARNING 确保能看到）
                            logger.warning("[_astream] RAW DELTA (chunk #%d):", chunk_idx)
                            if reason_text:
                                logger.warning("  [reasoning] %s", reason_text[:200] if len(reason_text) > 200 else reason_text)
                            if answer_text:
                                logger.warning("  [content] %s", answer_text[:200] if len(answer_text) > 200 else answer_text)
                            
                            # 🐛 SWITCHING POINT 监控
                            if reason_text and answer_text:
                                logger.warning("[_astream] ⚠️ SWITCHING POINT DETECTED (chunk #%d):", chunk_idx)
                                logger.warning("  reasoning: %s", repr(reason_text))
                                logger.warning("  content: %s", repr(answer_text))
                            
                            # 模型先输出 reasoning，然后切换到 content，不会交叉
                            # 使用两个独立的 if，确保 reasoning 和 content 都能正确输出
                            # 注意：即使同一个 delta 同时包含，也会分别 yield 两个 Chunk
                            # 但由于模型特性，这不会导致混淆（reasoning 总是在前）
                            
                            if reason_text:
                                logger.warning("[_astream] YIELD reasoning chunk #%d (len=%d)", chunk_idx, len(reason_text))
                                yield ChatGenerationChunk(
                                    message=AIMessageChunk(
                                        content=reason_text,
                                        additional_kwargs={"reasoning": True},
                                    )
                                )
                            
                            if answer_text:
                                logger.warning("[_astream] YIELD content chunk #%d (len=%d)", chunk_idx, len(answer_text))
                                yield ChatGenerationChunk(
                                    message=AIMessageChunk(content=answer_text)
                                )
                            # 工具调用片段（SSE 按 index 分片）：转成 langchain tool_call_chunks，
                            # think 节点合并 chunk 后 .tool_calls 即可得到完整调用并被 ToolNode 执行。
                            tool_deltas = delta.get("tool_calls") or []
                            for tc in tool_deltas:
                                fn = tc.get("function") or {}
                                yield ChatGenerationChunk(
                                    message=AIMessageChunk(
                                        content="",
                                        tool_call_chunks=[{
                                            "name": fn.get("name", ""),
                                            "args": fn.get("arguments", "") or "",
                                            "id": tc.get("id", ""),
                                            "index": tc.get("index", 0),
                                        }],
                                    )
                                )
                            chunk_idx += 1
                        except Exception as e:
                            logger.error("[_astream] Error parsing SSE data: %s", e)
                            continue
                
                logger.info("[_astream] TOTAL CHUNKS PROCESSED: %d", chunk_idx)
                logger.info("[_astream] " + "=" * 80)

            def _generate(
                self,
                messages: list[BaseMessage],
                stop: list[str] | None = None,
                **kwargs,
            ) -> ChatResult:
                """同步生成响应 - 用于非流式调用"""
                import asyncio
                loop = asyncio.get_event_loop()
                return loop.run_until_complete(self._agenerate(messages, stop, **kwargs))

        return SimpleChatHttp()


