"""
OpenAI 兼容接口 ChatModel 包装器（支持 reasoning 字段）

处理 Qwen3.5、DeepSeek 等模型的推理字段：
- Qwen3.5 同时返回 reasoning（思考）和 content（答案）
- reasoning: 思考过程（先输出，约 380 tokens）
- content: 最终答案（后输出，约 10 tokens）
- 两者都需要保留，不能互相覆盖
"""
from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult


class CompatibleChatModel(BaseChatModel):
    """OpenAI 兼容接口 ChatModel（支持 reasoning 字段）包装器"""
    
    model_name: str = "qwen3.5-397b-a17b"
    base_url: str
    api_key: str
    temperature: float = 0.3
    max_tokens: Optional[int] = None  # None 表示不限制，让模型自由决定输出长度
    
    @property
    def _llm_type(self) -> str:
        return "compatible"
    
    def _convert_messages(self, messages: List[BaseMessage]) -> List[Dict[str, Any]]:
        """转换 LangChain 消息为 API 格式"""
        converted = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                converted.append({"role": "system", "content": msg.content})
            elif isinstance(msg, HumanMessage):
                converted.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                converted.append({"role": "assistant", "content": msg.content})
            else:
                converted.append({"role": "user", "content": str(msg.content)})
        return converted
    
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """非流式生成"""
        # 构建请求参数
        payload = {
            "model": self.model_name,
            "messages": self._convert_messages(messages),
            "temperature": self.temperature,
        }
        # 只在设置了 max_tokens 时发送
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens
        
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            )
            response.raise_for_status()
            data = response.json()
        
        # 提取 reasoning 和 content 字段（Qwen3.5 同时返回两者）
        choices = data.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            reasoning = message.get("reasoning")  # 思考过程
            content = message.get("content") or ""  # 最终答案
            
            # ✅ 修复：content 只保存真正的 content 字段，不用 reasoning 填充
            # 这样 graph.py 就可以区分 reasoning chunk 和 content chunk
            final_content = content
        else:
            final_content = ""
            reasoning = None
        
        # 创建 AIMessage，同时保存 reasoning 到多个位置
        ai_message = AIMessage(
            content=final_content,
            additional_kwargs={
                "reasoning": reasoning,  # 供 extract_reasoning 使用
                "original_reasoning": reasoning,  # 保留原始
            },
            response_metadata=data,  # 保存完整响应
        )
        
        return ChatResult(generations=[ChatGeneration(message=ai_message)])
    
    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """异步非流式生成"""
        # 构建请求参数
        payload = {
            "model": self.model_name,
            "messages": self._convert_messages(messages),
            "temperature": self.temperature,
        }
        # 只在设置了 max_tokens 时发送
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            )
            response.raise_for_status()
            data = response.json()
        
        # 提取 reasoning 和 content 字段
        choices = data.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            reasoning = message.get("reasoning")
            content = message.get("content") or ""
            # ✅ 修复：content 只保存真正的 content 字段，不用 reasoning 填充
            final_content = content
        else:
            final_content = ""
            reasoning = None
        
        # 创建 AIMessage，同时保存 reasoning 到多个位置
        ai_message = AIMessage(
            content=final_content,
            additional_kwargs={
                "reasoning": reasoning,
                "original_reasoning": reasoning,
            },
            response_metadata=data,
        )
        
        return ChatResult(generations=[ChatGeneration(message=ai_message)])
    
    async def _astream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        """流式生成 - 同时保留 reasoning 和 content
        
        Qwen3.5 返回模式：
        1. 先输出 reasoning（思考过程，约 380 chunks）
        2. 后输出 content（最终答案，约 10 chunks）
        3. 两者都需要保留，不能互相覆盖
        """
        # 构建请求参数
        payload = {
            "model": self.model_name,
            "messages": self._convert_messages(messages),
            "temperature": self.temperature,
            "stream": True,
        }
        # 只在设置了 max_tokens 时发送
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk_data = json.loads(data)
                            choices = chunk_data.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                # Qwen3.5: reasoning 和 content 是独立的字段，分别在不同阶段返回
                                # reasoning: 思考过程（先输出）
                                # content: 最终答案（后输出）
                                reasoning = delta.get("reasoning")
                                content = delta.get("content")
                                
                                # ✅ 修复：content 只保存真正的 content 字段，不用 reasoning 填充
                                # 这样 graph.py 就可以区分 reasoning chunk 和 content chunk
                                final_content = content or ""
                                
                                # 创建 chunk，同时保存原始 reasoning 到 additional_kwargs
                                chunk_msg = AIMessageChunk(
                                    content=final_content,
                                    additional_kwargs={
                                        "reasoning": reasoning,  # reasoning 字段存在即为 reasoning chunk
                                        "original_reasoning": reasoning,
                                    },
                                    response_metadata=chunk_data,  # 保存完整 chunk 数据
                                )
                                yield ChatGenerationChunk(message=chunk_msg)
                        except json.JSONDecodeError:
                            continue


def create_compatible_llm(
    model_name: str = "qwen3.5-397b-a17b",
    base_url: str = "http://1.181.141.96:6018/qwen3.5-397b-a17b/v1",
    api_key: str = "",
    temperature: float = 0.3,
    max_tokens: Optional[int] = None,  # None 表示不限制
) -> CompatibleChatModel:
    """创建兼容模型实例
    
    Args:
        model_name: 模型名称
        base_url: API 基础 URL
        api_key: API Key
        temperature: 温度
        max_tokens: 最大输出 token（None 表示不限制）
    
    Returns:
        CompatibleChatModel 实例
    """
    return CompatibleChatModel(
        model_name=model_name,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
    )
