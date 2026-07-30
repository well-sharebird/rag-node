"""
LLM generation service with RAG-grounded response, citation, and guardrails.

Integrates with the LLM model configured in model management.
"""
from __future__ import annotations
import json
import logging
import re
from typing import Optional, AsyncIterator
import httpx

from app.schemas.retrieval import SearchResultItem

logger = logging.getLogger("app.services.llm")


async def _record_token_usage(
    model_config_id: int,
    model_name: str,
    model_type: str,
    provider: str,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
    latency_ms: float,
    user_id: Optional[int] = None,
    gateway_provider_id: Optional[int] = None,
    gateway_routing_rule_id: Optional[int] = None,
    status: str = "success",
    error_message: Optional[str] = None,
):
    """Record token usage to database (legacy support)"""
    from app.core.database import async_session_factory
    from app.models.token_usage import TokenUsage
    from sqlalchemy import select

    try:
        async with async_session_factory() as session:
            usage = TokenUsage(
                user_id=user_id,
                model_config_id=model_config_id,
                model_name=model_name,
                model_type=model_type,
                provider=provider,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                latency_ms=int(latency_ms),
                request_type="chat",
                status=status,
            )
            session.add(usage)
            await session.commit()
            logger.info("Token usage recorded: user_id=%s, model=%s, %d input, %d output, %d total", user_id, model_name, input_tokens, output_tokens, total_tokens)
    except Exception as e:
        logger.error("Failed to record token usage: %s", e)


async def _record_gateway_call_log(
    provider_id: int,
    model_id: str,
    model_type: str,
    request_id: str,
    status: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency_ms: int = 0,
    error_message: Optional[str] = None,
    error_code: Optional[str] = None,
    cost: Optional[float] = None,
    user_id: Optional[int] = None,
    kb_id: Optional[str] = None,
):
    """Record call log to model gateway"""
    from app.core.database import async_session_factory
    from app.models.model_gateway import ModelCallLog
    import uuid

    try:
        async with async_session_factory() as session:
            log = ModelCallLog(
                request_id=request_id,
                provider_id=provider_id,
                model_id=model_id,
                model_type=model_type,
                status=status,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                latency_ms=latency_ms,
                error_message=error_message,
                error_code=error_code,
                cost=cost,
                user_id=user_id,
                kb_id=kb_id,
            )
            session.add(log)
            await session.commit()
            logger.debug("Gateway call log recorded: request_id=%s, provider_id=%s, status=%s", request_id, provider_id, status)
    except Exception as e:
        logger.error("Failed to record gateway call log: %s", e)

# Default system prompt for RAG-grounded generation
DEFAULT_SYSTEM_PROMPT = """You are an enterprise knowledge assistant. Your answers must be:
1. Based ONLY on the provided reference documents
2. Factual and precise - do not speculate or invent information
3. With citations marked as [1], [2], etc. referencing the sources below
4. Concise but complete

IMPORTANT:
- Think silently in your mind (reasoning), then provide a CLEAR, DIRECT answer (content).
- The reasoning is your internal thought process - do NOT include it in the final answer.
- The content/answer should be a well-structured, standalone response to the user's question.

## Markdown Formatting Support

You MUST use Markdown formatting to make answers more readable and professional:

### Code Blocks
Use fenced code blocks with language identifier for syntax highlighting:
```python
def hello():
    print("Hello, World!")
```

### Mathematical Formulas
Use LaTeX for math formulas:
- Inline: `$E = mc^2$` renders as E = mc²
- Block: `$$\\int_0^\\infty e^{-x} dx = 1$$` for display math

### Diagrams (Mermaid)
Use Mermaid syntax for flowcharts, sequence diagrams, class diagrams, etc:
```mermaid
graph TD
    A[Start] --> B[Process]
    B --> C{Decision}
    C -->|Yes| D[Result 1]
    C -->|No| E[Result 2]
```

### Tables
Use Markdown tables for structured data:
| Column 1 | Column 2 | Column 3 |
|----------|----------|----------|
| Data 1   | Data 2   | Data 3   |

### Admonitions (提示/警告卡片)
Use ::: syntax for callouts:
:::tip
This is a helpful tip for users.
:::

:::warning
Be careful when doing this.
:::

:::note
Additional information to consider.
:::

:::danger
Critical warning about potential issues.
:::

:::info
General information notice.
:::

### JSON Tree View
For complex JSON structures, use json-tree for interactive view:
```json-tree
{"nested": {"data": "structure"}}
```

### Other Formatting
- Use **bold** for emphasis, *italics* for terms
- Use `inline code` for technical terms, commands, APIs
- Use > blockquotes for important notes
- Use bullet/numbered lists for multiple points
- Use ![alt](url) for images when referencing visual content

If the provided documents do not contain enough information to answer, say:
"I could not find sufficient information in the provided documents to answer this question. Please try rephrasing or check other knowledge bases."

If chat history is provided, use it to understand context and follow-up questions."""


class Citation:
    """A citation reference"""
    def __init__(self, index: int, doc_name: str, chunk_id: str, page: Optional[int] = None):
        self.index = index
        self.doc_name = doc_name
        self.chunk_id = chunk_id
        self.page = page

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "doc_name": self.doc_name,
            "chunk_id": self.chunk_id,
            "page": self.page,
        }


async def _get_llm_config_by_id(model_id: str | int) -> Optional[dict]:
    """Get LLM config by specific model ID (supports both numeric ID and model_id string)"""
    from app.core.database import async_session_factory
    from app.models.model_config import ModelConfig
    from sqlalchemy import select

    try:
        async with async_session_factory() as session:
            model = None

            # Try to find by numeric id first if it looks like a number
            if isinstance(model_id, int) or (isinstance(model_id, str) and model_id.isdigit()):
                result = await session.execute(
                    select(ModelConfig)
                    .where(ModelConfig.id == int(model_id))
                    .where(ModelConfig.is_enabled == True)
                    .limit(1)
                )
                model = result.scalar_one_or_none()

            # If not found by numeric id, try to find by model_id string
            if not model:
                result = await session.execute(
                    select(ModelConfig)
                    .where(ModelConfig.model_id == str(model_id))
                    .where(ModelConfig.is_enabled == True)
                    .limit(1)
                )
                model = result.scalar_one_or_none()

            # Also check model_gateway providers if not found in model_configs
            if not model:
                from app.models.model_gateway import ModelProvider
                result = await session.execute(
                    select(ModelProvider)
                    .where(ModelProvider.code == str(model_id))
                    .where(ModelProvider.is_enabled == True)
                    .limit(1)
                )
                provider = result.scalar_one_or_none()
                if provider:
                    return {
                        "id": provider.id,
                        "name": provider.name,
                        "api_url": provider.base_url,
                        "api_key": provider.api_key or "",
                        "model_id": provider.code,
                        "model_type": "llm",
                        "provider": provider.provider_type,
                        "gateway": True,
                    }

            if model:
                return {
                    "id": model.id,
                    "name": model.name,
                    "api_url": model.api_url or "",
                    "api_key": model.api_key or "",
                    "model_id": model.model_id,
                    "model_type": model.model_type,
                    "provider": model.adapter_type,
                    "gateway": False,
                }
    except Exception as e:
        print(f"Error getting model config by id: {e}")
    return None


async def _get_llm_config() -> Optional[dict]:
    """Get LLM config from model_configs (legacy support)"""
    from app.core.database import async_session_factory
    from app.models.model_config import ModelConfig
    from sqlalchemy import select

    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(ModelConfig)
                .where(ModelConfig.model_type == "llm")
                .where(ModelConfig.is_enabled == True)
                .where(ModelConfig.is_default == True)
                .limit(1)
            )
            model = result.scalar_one_or_none()
            if model:
                return {
                    "id": model.id,
                    "name": model.name,
                    "api_url": model.api_url or "",
                    "api_key": model.api_key or "",
                    "model_id": model.model_id,
                    "model_type": model.model_type,
                    "provider": model.adapter_type,
                }
    except Exception:
        pass
    return None


async def _get_llm_config_from_gateway(model_type: str = "llm") -> Optional[dict]:
    """Get LLM config from model gateway (new approach with routing)"""
    from app.core.database import async_session_factory
    from app.models.model_gateway import ModelProvider, ModelRoutingRule
    from app.models.model_config import ModelConfig
    from sqlalchemy import select

    try:
        async with async_session_factory() as session:
            # First try to get default model from model_configs (legacy but reliable)
            # This is the most direct way to get the actual model ID and API config
            default_model_result = await session.execute(
                select(ModelConfig)
                .where(ModelConfig.model_type == model_type)
                .where(ModelConfig.is_enabled == True)
                .where(ModelConfig.is_default == True)
                .limit(1)
            )
            default_model = default_model_result.scalar_one_or_none()

            if default_model and default_model.api_url:
                return {
                    "id": default_model.id,
                    "name": default_model.name,
                    "api_url": default_model.api_url,
                    "api_key": default_model.api_key or "",
                    "model_id": default_model.model_id,  # Use actual model_id from config
                    "model_type": default_model.model_type,
                    "provider": default_model.adapter_type,
                    "gateway": False,  # Use legacy direct API call
                }

            # Fallback: Get default provider from gateway
            default_result = await session.execute(
                select(ModelProvider)
                .where(ModelProvider.is_enabled == True)
                .where(ModelProvider.is_default == True)
                .where(ModelProvider.status == "active")
                .limit(1)
            )
            provider = default_result.scalar_one_or_none()

            if provider:
                return {
                    "id": provider.id,
                    "name": provider.name,
                    "api_url": provider.base_url,
                    "api_key": provider.api_key or "",
                    "model_id": provider.code,
                    "model_type": model_type,
                    "provider": provider.provider_type,
                    "gateway": True,
                }

    except Exception as e:
        logging.debug("Gateway config fetch failed: %s", e)
    return None


def _build_rag_prompt(
    query: str,
    chunks: list[SearchResultItem],
    conversation_context: str = "",
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
) -> tuple[str, list[Citation]]:
    """
    Build RAG-grounded prompt with context and citation markers.

    Returns:
        (formatted_prompt, list_of_citations)
    """
    citations: list[Citation] = []
    context_parts = []

    # Group chunks by content type for structured evidence presentation
    text_chunks = [c for c in chunks if getattr(c, 'content_type', 'text') == 'text']
    table_chunks = [c for c in chunks if getattr(c, 'content_type', 'text') == 'table']
    image_chunks = [c for c in chunks if getattr(c, 'content_type', 'text') == 'image']

    idx = 0

    if text_chunks:
        context_parts.append("[文本证据]")
        for chunk in text_chunks:
            idx += 1
            doc_name = chunk.metadata.get("doc_name", "Unknown")
            page = chunk.metadata.get("page")
            source_info = f"(Source: {doc_name}"
            if page is not None:
                source_info += f", Page: {page}"
            source_info += ")"

            citations.append(Citation(
                index=idx, doc_name=doc_name,
                chunk_id=chunk.chunk_id, page=page,
            ))
            context_parts.append(f"[{idx}] {source_info}\n{chunk.content}")

    if table_chunks:
        context_parts.append("\n[表格数据]")
        for chunk in table_chunks:
            idx += 1
            doc_name = chunk.metadata.get("doc_name", "Unknown")
            page = chunk.metadata.get("page")
            source_info = f"(Source: {doc_name}, Table"
            if page is not None:
                source_info += f", Page: {page}"
            source_info += ")"

            citations.append(Citation(
                index=idx, doc_name=doc_name,
                chunk_id=chunk.chunk_id, page=page,
            ))
            context_parts.append(f"[{idx}] {source_info}\n{chunk.content}\n(请分析此表格中的关键数据和洞察)")

    if image_chunks:
        context_parts.append("\n[图片描述]")
        for chunk in image_chunks:
            idx += 1
            doc_name = chunk.metadata.get("doc_name", "Unknown")
            page = chunk.metadata.get("page")
            source_info = f"(Source: {doc_name}"
            if page is not None:
                source_info += f", Page: {page}"
            source_info += ", Image)"

            citations.append(Citation(
                index=idx, doc_name=doc_name,
                chunk_id=chunk.chunk_id, page=page,
            ))
            context_parts.append(f"[{idx}] {source_info}\n{chunk.content}")

    context_block = "\n\n".join(context_parts)

    prompt = f"""{system_prompt}

[Reference Documents]
{context_block}
[/Reference Documents]"""

    if conversation_context:
        prompt += f"\n\n{conversation_context}"

    prompt += f"\n\n[User Question]\n{query}\n[/User Question]\n\nAnswer:"

    return prompt, citations


def _detect_hallucination(answer: str, chunks: list[SearchResultItem]) -> dict:
    """
    Simple heuristic-based hallucination detection.

    Checks if key claims in the answer can be traced back to source chunks.
    Returns {"score": 0-10, "issues": [...]}
    """
    issues = []
    combined_text = " ".join(c.content.lower() for c in chunks)

    # Check for numeric claims not in sources
    numbers = re.findall(r'\b\d+\.?\d*\s*(?:%|million|billion|thousand)?\b', answer)
    for num in numbers:
        if num.lower() not in combined_text:
            issues.append(f"Potential unverified claim: {num}")

    # Check for categorical statements
    categorical = ["always", "never", "all of", "none of", "the only", "the best"]
    for cat in categorical:
        if cat in answer.lower() and cat not in combined_text:
            issues.append(f"Absolute claim not in sources: '{cat}'")

    score = max(0, 10 - len(issues))
    return {"score": score, "issues": issues}


def _format_streaming_chunk(content: str) -> str:
    """Format a streaming chunk for SSE"""
    return f"data: {json.dumps({'type': 'chunk', 'content': content})}\n\n"


def _format_citation_chunk(citations: list[Citation]) -> str:
    """Format citation data for SSE"""
    return f"data: {json.dumps({'type': 'citation', 'citations': [c.to_dict() for c in citations]})}\n\n"


def _format_done_chunk(
    full_answer: str,
    citations: list[Citation],
    latency_ms: float,
    hallu_check: dict,
) -> str:
    """Format completion event for SSE"""
    data = {
        "type": "done",
        "citations": [c.to_dict() for c in citations],
        "latency_ms": round(latency_ms, 1),
        "hallucination_score": hallu_check.get("score", 10),
    }
    return f"data: {json.dumps(data)}\n\n"


async def generate_rag_response(
    query: str,
    chunks: list[SearchResultItem],
    conversation_context: str = "",
    stream: bool = False,
    temperature: float = 0.3,
    max_tokens: Optional[int] = None,  # None 表示让模型自己决定
    user_id: Optional[int] = None,
    use_rag: bool = True,
    model_id: Optional[str] = None,  # 可选：指定使用的模型 ID
) -> dict:
    """
    Generate a RAG-grounded response using configured LLM.

    Args:
        query: User's question
        chunks: Retrieved context chunks
        conversation_context: Optional conversation history text
        stream: Whether to return SSE stream
        temperature: LLM temperature
        max_tokens: Max output tokens
        use_rag: If False, use direct LLM chat without RAG context
        model_id: Optional model ID to use (overrides default)

    Returns:
        {
            "answer": str,
            "citations": list[Citation],
            "latency_ms": float,
            "hallucination": dict,
            "chunks_used": int,
        }
    """
    import time

    # 优先使用模型网关获取配置（和模型测试接口一致）
    # 如果指定了 model_id，尝试按名称查找；否则使用默认配置
    llm_config = None
    if model_id:
        # 先尝试从 model_configs 按 model_id 查找
        llm_config = await _get_llm_config_by_id(model_id)
        # 如果没找到，使用网关默认配置并覆盖 model_id
        if not llm_config:
            llm_config = await _get_llm_config_from_gateway()
            if llm_config and model_id:
                # 覆盖 model_id 为用户指定的值
                llm_config["model_id"] = model_id

    if not llm_config:
        llm_config = await _get_llm_config_from_gateway()
        if not llm_config:
            llm_config = await _get_llm_config()

    if not llm_config or not llm_config.get("api_url"):
        # No LLM configured
        if chunks:
            chunk_summaries = []
            for c in chunks[:3]:
                doc_name = c.metadata.get("doc_name", "Source")
                chunk_summaries.append(
                    f"**[{doc_name}]** (score: {c.score:.2f})\n{c.content[:300]}..."
                )
            return {
                "answer": (
                    "No LLM configured. Here are the most relevant document excerpts:\n\n"
                    + "\n\n".join(chunk_summaries)
                    + "\n\n*Configure a default LLM model in Model Management to enable AI-generated answers.*"
                ),
                "citations": [],
                "latency_ms": 0,
                "hallucination": {"score": 10, "issues": []},
                "chunks_used": len(chunks),
            }
        else:
            return {
                "answer": "LLM 服务未配置。请在模型管理中配置默认 LLM 模型。",
                "citations": [],
                "latency_ms": 0,
                "hallucination": {"score": 10, "issues": []},
                "chunks_used": 0,
            }

    # If no chunks but use_rag is False, use direct LLM chat
    if not chunks and not use_rag:
        logger.info("Using direct LLM chat without RAG context")
        base_url = llm_config["api_url"].rstrip("/")
        if not base_url.endswith("/v1"):
            api_url = f"{base_url}/v1/chat/completions"
        else:
            api_url = f"{base_url}/chat/completions"

        headers = {"Content-Type": "application/json"}
        if llm_config["api_key"]:
            headers["Authorization"] = f"Bearer {llm_config['api_key']}"

        # Build messages with conversation context
        system_prompt = """You are a helpful AI assistant. Provide clear, accurate, and helpful answers to user questions."""
        messages = [{"role": "system", "content": system_prompt}]

        if conversation_context:
            messages.append({"role": "user", "content": f"Conversation history:\n{conversation_context}"})

        messages.append({"role": "user", "content": query})

        start = time.monotonic()

        try:
            if stream:
                client = httpx.AsyncClient(timeout=60)
                response = await client.send(
                    client.build_request(
                        "POST",
                        api_url,
                        json={
                            "model": llm_config["model_id"],
                            "messages": messages,
                            "temperature": temperature,
                            "max_tokens": max_tokens,
                            "stream": True,
                        },
                        headers=headers,
                    ),
                    stream=True,
                )

                if response.status_code != 200:
                    error_text = await response.aread()
                    logger.error("LLM API error %d: %s | url=%s model=%s", response.status_code, error_text[:300], api_url, llm_config["model_id"])
                    await response.aclose()
                    await client.aclose()
                    return {"answer": f"LLM service error: HTTP {response.status_code}. {error_text.decode()[:200]}", "citations": [], "chunks_used": 0}

                return {
                    "stream": response,
                    "client": client,
                    "type": "streaming",
                    "citations": [],
                }
            else:
                async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0, read=120.0, write=30.0)) as client:
                    response = await client.post(
                        api_url,
                        json={
                            "model": llm_config["model_id"],
                            "messages": messages,
                            "temperature": temperature,
                            "max_tokens": max_tokens,
                            "stream": False,
                        },
                        headers=headers,
                    )

                if response.status_code != 200:
                    logger.error("LLM API error %d: %s", response.status_code, response.text[:300])
                    return {"answer": "LLM service error. Please try again later.", "citations": [], "chunks_used": 0}

                data = response.json()
                message = data["choices"][0]["message"]
                reasoning_text = (message.get("reasoning") or "").strip()
                content = message.get("content")
                answer = content.strip() if content else _extract_answer_from_reasoning(reasoning_text) if reasoning_text else ""

                usage = data.get("usage", {})
                input_tokens = usage.get("prompt_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0)
                total_tokens = usage.get("total_tokens", input_tokens + output_tokens)

                latency = (time.monotonic() - start) * 1000

                # Record to legacy token_usage table
                await _record_token_usage(
                    model_config_id=llm_config.get("id"),
                    model_name=llm_config.get("name", llm_config["model_id"]),
                    model_type=llm_config.get("model_type", "llm"),
                    provider=llm_config.get("provider", "api"),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    latency_ms=latency,
                    user_id=user_id,
                )

                # Record to gateway call log if using gateway
                if llm_config.get("gateway") and llm_config.get("id"):
                    import uuid
                    await _record_gateway_call_log(
                        provider_id=llm_config.get("id"),
                        model_id=llm_config.get("model_id", llm_config.get("code", "unknown")),
                        model_type=llm_config.get("model_type", "llm"),
                        request_id=str(uuid.uuid4()),
                        status="success",
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        latency_ms=int(latency),
                        user_id=user_id,
                        kb_id=None,
                    )

                return {
                    "answer": answer,
                    "reasoning": reasoning_text if reasoning_text != answer else "",
                    "citations": [],
                    "latency_ms": (time.monotonic() - start) * 1000,
                    "hallucination": {"score": 10, "issues": []},
                    "chunks_used": 0,
                }

        except Exception as e:
            logger.exception("Direct LLM chat failed: %s", e)
            return {"answer": "LLM service error. Please try again later.", "citations": [], "chunks_used": 0}

    # For RAG mode with chunks, use the llm_config already fetched at the top
    # No need to fetch again

    if not llm_config or not llm_config.get("api_url"):
        # No LLM configured - return retrieved chunks as citation-only response
        chunk_summaries = []
        for c in chunks[:3]:
            doc_name = c.metadata.get("doc_name", "Source")
            chunk_summaries.append(
                f"**[{doc_name}]** (score: {c.score:.2f})\n{c.content[:300]}..."
            )

        return {
            "answer": (
                "No LLM configured. Here are the most relevant document excerpts:\n\n"
                + "\n\n".join(chunk_summaries)
                + "\n\n*Configure a default LLM model in Model Management to enable AI-generated answers.*"
            ),
            "citations": [],
            "latency_ms": 0,
            "hallucination": {"score": 10, "issues": []},
            "chunks_used": len(chunks),
        }

    base_url = llm_config["api_url"].rstrip("/")
    if not base_url.endswith("/v1"):
        api_url = f"{base_url}/v1/chat/completions"
    else:
        api_url = f"{base_url}/chat/completions"

    prompt, citations = _build_rag_prompt(query, chunks, conversation_context)

    headers = {"Content-Type": "application/json"}
    if llm_config["api_key"]:
        headers["Authorization"] = f"Bearer {llm_config['api_key']}"

    messages = [
        {"role": "user", "content": prompt},
    ]

    start = time.monotonic()

    try:
        # For streaming, we need to use stream=True in httpx to prevent buffering
        if stream:
            client = httpx.AsyncClient(timeout=60)
            # Use stream method for true streaming
            request_body = {
                "model": llm_config["model_id"],
                "messages": messages,
                "temperature": temperature,
                "stream": True,
            }
            # Only add max_tokens if specified (let model decide otherwise)
            if max_tokens is not None:
                request_body["max_tokens"] = max_tokens

            response = await client.send(
                client.build_request(
                    "POST",
                    api_url,
                    json=request_body,
                    headers=headers,
                ),
                stream=True,
            )

            if response.status_code != 200:
                error_text = await response.aread()
                logger.error("LLM API error %d: %s", response.status_code, error_text[:300])
                await response.aclose()
                await client.aclose()
                return _fallback_response(chunks)

            # For streaming, return the response for SSE processing
            # Caller is responsible for closing response and client
            return {
                "stream": response,
                "client": client,
                "type": "streaming",
                "citations": citations,
            }
        else:
            # Use longer timeout for LLM with reasoning
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0, read=120.0, write=30.0)) as client:
                request_body = {
                    "model": llm_config["model_id"],
                    "messages": messages,
                    "temperature": temperature,
                    "stream": False,
                }
                # Only add max_tokens if specified (let model decide otherwise)
                if max_tokens is not None:
                    request_body["max_tokens"] = max_tokens

                response = await client.post(
                    api_url,
                    json=request_body,
                    headers=headers,
                )

                if response.status_code != 200:
                    logger.error("LLM API error %d: %s", response.status_code, response.text[:300])
                    return _fallback_response(chunks)

            data = response.json()
            message = data["choices"][0]["message"]
            reasoning_text = (message.get("reasoning") or "").strip()
            content = message.get("content")

            # 如果 content 有值，直接使用
            if content:
                answer = content.strip()
            # 如果 content 为 null/空，尝试从 reasoning 中提取实际回答
            # Qwen 模型格式："Thinking Process:\n\n1. ...\n2. ...\n\n[实际回答]"
            elif reasoning_text:
                answer = _extract_answer_from_reasoning(reasoning_text)
            else:
                answer = ""

            # Extract token usage if available
            usage = data.get("usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", input_tokens + output_tokens)

            # Record token usage
            await _record_token_usage(
                model_config_id=llm_config.get("id"),
                model_name=llm_config.get("name", llm_config["model_id"]),
                model_type=llm_config.get("model_type", "llm"),
                provider=llm_config.get("provider", "api"),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                latency_ms=(time.monotonic() - start) * 1000,
                user_id=user_id,
            )

    except Exception as e:
        logger.exception("LLM generation failed: %s", e)
        return _fallback_response(chunks)

    elapsed = (time.monotonic() - start) * 1000
    hallucination = _detect_hallucination(answer, chunks)

    return {
        "answer": answer,
        "reasoning": reasoning_text if reasoning_text != answer else "",
        "citations": [c.to_dict() for c in citations],
        "latency_ms": round(elapsed, 1),
        "hallucination": hallucination,
        "chunks_used": len(chunks),
    }


def _extract_answer_from_reasoning(reasoning_text: str) -> str:
    """
    Extract the actual answer from reasoning text for models like Qwen
    that put both thinking and answer in the 'reasoning' field.

    Qwen format:
    "Thinking Process:\n\n1. ...\n2. ...\n\n*Draft:*\n[actual answer]"

    Returns the part after the thinking process ends.
    """
    # Look for common patterns that mark the end of thinking
    # and start of actual answer
    patterns = [
        r"\*Draft:\*\s*\n",           # *Draft:*
        r"\*\*Final Answer\*\*:\s*\n", # **Final Answer**:
        r"\n\n(?:Based on|According to|In summary|综上|因此|所以 | 答案 | 回答)[:：]?\s*\n",
        r"\n\n(?=\d{1,2}\.\s*[A-Z])",  # Numbered list starting with capital (likely answer)
    ]

    for pattern in patterns:
        match = re.search(pattern, reasoning_text, re.IGNORECASE)
        if match:
            # Return everything after the pattern
            answer = reasoning_text[match.end():].strip()
            if answer and len(answer) > 10:
                return answer

    # If no clear separator found, return the last paragraph
    # (often the actual answer in Qwen's format)
    paragraphs = reasoning_text.split('\n\n')
    if len(paragraphs) > 1:
        # Return the last 1-2 paragraphs as the answer
        return '\n\n'.join(paragraphs[-2:]).strip()

    return reasoning_text


def _fallback_response(chunks: list[SearchResultItem]) -> dict:
    """Generate a fallback response when LLM is unavailable"""
    return {
        "answer": (
            "The AI generation service is currently unavailable. "
            "Here are the most relevant document excerpts.\n\n"
            + "\n\n".join(
                f"*{c.metadata.get('doc_name', 'Source')}*: {c.content[:200]}..."
                for c in chunks[:3]
            )
        ),
        "citations": [],
        "latency_ms": 0,
        "hallucination": {"score": 10, "issues": ["LLM unavailable"]},
        "chunks_used": len(chunks),
    }
