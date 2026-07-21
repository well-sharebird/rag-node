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
):
    """Record token usage to database"""
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
                status="success",
            )
            session.add(usage)
            await session.commit()
            logger.info("Token usage recorded: user_id=%s, model=%s, %d input, %d output, %d total", user_id, model_name, input_tokens, output_tokens, total_tokens)
    except Exception as e:
        logger.error("Failed to record token usage: %s", e)

# Default system prompt for RAG-grounded generation
DEFAULT_SYSTEM_PROMPT = """You are an enterprise knowledge assistant. Your answers must be:
1. Based ONLY on the provided reference documents
2. Factual and precise - do not speculate or invent information
3. With citations marked as [1], [2], etc. referencing the sources below
4. Concise but complete

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


async def _get_llm_config() -> Optional[dict]:
    """Get LLM config from model_configs"""
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
    max_tokens: int = 1024,
    user_id: Optional[int] = None,
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

    if not chunks:
        return {
            "answer": "I could not find relevant information to answer your question. Please try rephrasing or check if the relevant documents have been indexed.",
            "citations": [],
            "latency_ms": 0,
            "hallucination": {"score": 10, "issues": []},
            "chunks_used": 0,
        }

    llm_config = await _get_llm_config()

    if not llm_config or not llm_config["api_url"]:
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
                    return _fallback_response(chunks)

            data = response.json()
            message = data["choices"][0]["message"]
            reasoning_text = (message.get("reasoning") or "").strip()
            answer = (message.get("content") or reasoning_text or "").strip()

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
