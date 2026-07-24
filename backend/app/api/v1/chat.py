"""
Chat completions API: RAG-grounded Q&A with streaming support.

Integrates:
- query expansion (HyDE, keyword expansion)
- vector retrieval
- reranking
- conversation memory (Redis)
- LLM generation with citations
- hallucination detection
"""
from __future__ import annotations
import json
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.core.database import get_db
from app.core.redis_client import get_redis
from app.core.milvus_client import get_milvus_client
from app.models.knowledge_base import KnowledgeBase
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.retrieval_service import search_chunks as retrieval_search
from app.services.retrieval_service import _rerank_results
from app.services.query_expansion import expand_query, hyde_expand
from app.services.conversation_memory import ConversationMemory
from app.services.llm_service import generate_rag_response
from app.schemas.retrieval import SearchRequest
from app.utils.exceptions import NotFoundException
from app.core.auth import get_current_user
from app.models.user import User

logger = logging.getLogger("app.api.chat")

router = APIRouter(prefix="/chat", tags=["Chat Completions"])


@router.post("/completions")
async def chat_completions(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    current_user: User = Depends(get_current_user),
):
    """
    RAG-grounded chat completion with citations.

    If kb_ids is empty, falls back to direct LLM chat without RAG.

    Request body:
        - query: User's question
        - kb_ids: List of knowledge base IDs to search (optional, if empty uses direct LLM)
        - session_id: Optional conversation session ID for multi-turn
        - stream: Whether to stream the response (SSE)
        - top_k: Number of chunks to retrieve
        - enable_rerank: Whether to rerank results
        - enable_expansion: Whether to use query expansion (HyDE)
    """
    kb_ids = request.kb_ids or []
    session_id = request.session_id or "default"
    memory = ConversationMemory(redis, session_id)

    # Step 1: Build conversation context
    conversation_context = ""
    if not await memory.is_first_turn():
        conversation_context = await memory.get_context_window(max_messages=6)

    query = request.query

    # If no kb_ids, use direct LLM chat without RAG
    if not kb_ids:
        logger.info("No KB selected, using direct LLM chat")
        result = await generate_rag_response(
            query=query,
            chunks=[],
            conversation_context=conversation_context,
            stream=request.stream,
            user_id=current_user.id,
            use_rag=False,
        )

        # Handle streaming response
        if result.get("type") == "streaming":
            return StreamingResponse(
                _stream_rag_response(result, memory, current_user.id),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        # Store conversation (non-streaming only)
        await memory.add_user_message(query)
        await memory.add_assistant_message(
            result.get("answer", ""),
            sources=result.get("citations", []),
        )

        return ChatResponse(
            answer=result.get("answer", ""),
            reasoning=result.get("reasoning", ""),
            citations=result.get("citations", []),
            chunks_used=0,
        )

    # Verify KBs exist
    from sqlalchemy import select
    result = await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.id.in_(kb_ids))
    )
    kbs = result.scalars().all()
    if not kbs:
        raise NotFoundException("No valid knowledge bases found")

    milvus = get_milvus_client()

    # Step 2: Query expansion (optional)
    hyde_text = ""
    if request.enable_expansion and request.enable_expansion:
        try:
            expansion = await expand_query(query)
            if expansion.get("hyde_text"):
                hyde_text = expansion["hyde_text"]
                logger.info("Using HyDE expansion for query")
        except Exception as e:
            logger.debug("Query expansion failed: %s", e)

    # Step 3: Retrieve from each KB
    all_chunks = []
    for kb in kbs:
        try:
            search_request = SearchRequest(
                kb_id=kb.id,
                query=hyde_text if hyde_text else query,
                top_k=request.top_k or 10,
                min_score=request.min_score or 0.0,
                enable_hybrid=request.enable_hybrid or False,
                enable_rerank=False,  # We rerank later with merged results
            )
            response = await retrieval_search(db, redis, milvus, search_request)
            all_chunks.extend(response.results)
        except Exception as e:
            logger.warning("Search failed for KB %s: %s", kb.id, e)

    if not all_chunks:
        return ChatResponse(
            answer="No relevant information found.",
            citations=[],
            chunks_used=0,
        )

    # Step 4: Deduplicate and sort
    seen = set()
    unique_chunks = []
    for chunk in all_chunks:
        if chunk.chunk_id not in seen:
            seen.add(chunk.chunk_id)
            unique_chunks.append(chunk)

    # Sort by score descending
    unique_chunks.sort(key=lambda c: c.score, reverse=True)

    # Step 5: Rerank (if enabled)
    if request.enable_rerank and len(unique_chunks) > 1:
        try:
            hits = [
                {
                    "chunk_id": c.chunk_id,
                    "content": c.content,
                    "score": c.score,
                    "metadata": c.metadata,
                }
                for c in unique_chunks[:20]  # Rerank top 20
            ]
            reranked = await _rerank_results(query, hits, top_n=request.top_k or 5)
            # Convert back
            from app.schemas.retrieval import SearchResultItem
            unique_chunks = [
                SearchResultItem(
                    chunk_id=h["chunk_id"],
                    content=h["content"],
                    score=h["score"],
                    metadata=h["metadata"],
                )
                for h in reranked[:request.top_k or 5]
            ]
        except Exception as e:
            logger.warning("Reranking failed: %s", e)
            unique_chunks = unique_chunks[:request.top_k or 5]

    # Step 6: Generate response
    result = await generate_rag_response(
        query=query,
        chunks=unique_chunks[:request.top_k or 5],
        conversation_context=conversation_context,
        stream=request.stream,
        user_id=current_user.id,
    )

    # Step 7: Handle streaming vs non-streaming response
    is_streaming = result.get("type") == "streaming" and result.get("stream") is not None

    if not is_streaming:
        # Store conversation (non-streaming only)
        await memory.add_user_message(query)
        await memory.add_assistant_message(
            result.get("answer", ""),
            sources=result.get("citations", []),
        )

        return ChatResponse(
            answer=result["answer"],
            reasoning=result.get("reasoning", ""),
            citations=[{"index": c["index"], "doc_name": c["doc_name"], "chunk_id": c["chunk_id"]} for c in result.get("citations", [])],
            hallu_score=result.get("hallucination", {}).get("score", 10),
            chunks_used=result.get("chunks_used", 0),
        )
    else:
        # Streaming response - pass user_id for token usage recording
        return StreamingResponse(
            _stream_rag_response(result, memory, current_user.id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )


async def _record_streaming_token_usage(
    user_id: int,
    content: str,
):
    """Record token usage for streaming responses"""
    from app.core.database import async_session_factory
    from app.models.token_usage import TokenUsage
    from app.models.model_config import ModelConfig
    from sqlalchemy import select

    try:
        # Estimate tokens (rough approximation: 4 chars per token for Chinese/English mix)
        output_tokens = max(1, len(content) // 4)

        async with async_session_factory() as session:
            # Get default LLM config
            result = await session.execute(
                select(ModelConfig)
                .where(ModelConfig.model_type == "llm")
                .where(ModelConfig.is_enabled == True)
                .where(ModelConfig.is_default == True)
                .limit(1)
            )
            model = result.scalar_one_or_none()

            if model:
                usage = TokenUsage(
                    user_id=user_id,
                    model_config_id=model.id,
                    model_name=model.name or model.model_id,
                    model_type=model.model_type,
                    provider=model.adapter_type,
                    input_tokens=0,  # Unknown in streaming
                    output_tokens=output_tokens,
                    total_tokens=output_tokens,
                    latency_ms=0,
                    request_type="chat",
                    status="success",
                )
                session.add(usage)
                await session.commit()
    except Exception as e:
        logger.debug("Failed to record streaming token usage: %s", e)


async def _stream_rag_response(result: dict, memory: ConversationMemory, user_id: int | None = None, request: ChatRequest = None):
    """
    SSE streaming generator for RAG response - OpenAI compatible format.

    Emits OpenAI-style chat.completion.chunk events:
    - First chunk: delta.role = "assistant"
    - Reasoning chunks: delta.reasoning_content (for thinking process)
    - Content chunks: delta.content
    - Final chunk: finish_reason = "stop"
    - Citations sent as a custom event before content streaming
    """
    import uuid
    import time

    # Generate OpenAI-compatible response ID
    response_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())

    citations = result.get("citations", [])

    # Send citations as a custom metadata event first
    if citations:
        citation_data = []
        for i, c in enumerate(citations, 1):
            citation_data.append({
                "index": i,
                "doc_name": c.get("doc_name", "") if isinstance(c, dict) else getattr(c, "doc_name", ""),
                "doc_id": c.get("doc_id", "") if isinstance(c, dict) else getattr(c, "doc_id", ""),
            })
        yield f"data: {json.dumps({'type': 'citations', 'citations': citation_data})}\n\n"

    # Stream content - parse LLM's SSE and forward in OpenAI format
    stream = result.get("stream")
    client = result.get("client")  # httpx client for streaming
    accumulated_reasoning = ""
    accumulated_content = ""
    has_sent_role = False
    has_sent_finish = False  # Track if we've sent finish_reason

    # Buffer for incomplete UTF-8 sequences and lines
    byte_buffer = bytearray()
    line_buffer = ""

    if stream and hasattr(stream, "aiter_bytes"):
        try:
            # Use aiter_bytes for true streaming (aiter_lines can buffer)
            async for chunk_bytes in stream.aiter_bytes(chunk_size=256):
                # Accumulate bytes
                byte_buffer.extend(chunk_bytes)

                # Try to decode, handling incomplete UTF-8 sequences
                try:
                    decoded = byte_buffer.decode("utf-8")
                    byte_buffer.clear()
                    line_buffer += decoded
                except UnicodeDecodeError:
                    # Incomplete UTF-8 sequence, wait for more bytes
                    continue

                # Process complete lines
                while "\n" in line_buffer:
                    line, line_buffer = line_buffer.split("\n", 1)
                    line = line.strip()

                    # Skip empty lines
                    if not line:
                        continue

                    # Remove "data: " prefix if present
                    if line.startswith("data: "):
                        line = line[6:]

                    # Skip [DONE] marker
                    if line.strip() == "[DONE]":
                        continue

                    try:
                        chunk = json.loads(line)

                        # Handle LLM's OpenAI-style completion chunks
                        choices = chunk.get("choices", [])
                        if choices and len(choices) > 0:
                            delta = choices[0].get("delta", {})
                            finish_reason = choices[0].get("finish_reason")

                            # Send role on first chunk
                            if not has_sent_role:
                                has_sent_role = True
                                openai_chunk = {
                                    "id": response_id,
                                    "object": "chat.completion.chunk",
                                    "created": created,
                                    "model": chunk.get("model", "unknown"),
                                    "choices": [{
                                        "index": 0,
                                        "delta": {"role": "assistant"},
                                        "logprobs": None,
                                        "finish_reason": None
                                    }]
                                }
                                yield f"data: {json.dumps(openai_chunk)}\n\n"

                            # Handle reasoning_content / reasoning (thinking process)
                            # For Qwen: reasoning contains both thinking AND final answer
                            # We forward reasoning as-is, frontend should parse it
                            if delta.get("reasoning") or delta.get("reasoning_content"):
                                reasoning_chunk = delta.get("reasoning") or delta.get("reasoning_content", "")
                                accumulated_reasoning += reasoning_chunk
                                openai_chunk = {
                                    "id": response_id,
                                    "object": "chat.completion.chunk",
                                    "created": created,
                                    "model": chunk.get("model", "unknown"),
                                    "choices": [{
                                        "index": 0,
                                        "delta": {"reasoning_content": reasoning_chunk},
                                        "logprobs": None,
                                        "finish_reason": None
                                    }]
                                }
                                yield f"data: {json.dumps(openai_chunk)}\n\n"

                            # Handle content (from models that DO emit content natively)
                            if delta.get("content"):
                                content_chunk = delta["content"]
                                accumulated_content += content_chunk
                                openai_chunk = {
                                    "id": response_id,
                                    "object": "chat.completion.chunk",
                                    "created": created,
                                    "model": chunk.get("model", "unknown"),
                                    "choices": [{
                                        "index": 0,
                                        "delta": {"content": content_chunk},
                                        "logprobs": None,
                                        "finish_reason": None
                                    }]
                                }
                                yield f"data: {json.dumps(openai_chunk)}\n\n"

                            # Handle finish_reason - send final chunk (only once!)
                            if finish_reason and not has_sent_finish:
                                has_sent_finish = True
                                openai_chunk = {
                                    "id": response_id,
                                    "object": "chat.completion.chunk",
                                    "created": created,
                                    "model": chunk.get("model", "unknown"),
                                    "choices": [{
                                        "index": 0,
                                        "delta": {},
                                        "logprobs": None,
                                        "finish_reason": finish_reason
                                    }]
                                }
                                yield f"data: {json.dumps(openai_chunk)}\n\n"
                                yield "data: [DONE]\n\n"
                                return

                    except json.JSONDecodeError:
                        # If not valid JSON, skip
                        pass

        finally:
            # Decode any remaining bytes
            if byte_buffer:
                try:
                    line_buffer += byte_buffer.decode("utf-8")
                except UnicodeDecodeError:
                    pass

            # Process any remaining data in line buffer
            if line_buffer.strip():
                line = line_buffer.strip()
                if line.startswith("data: "):
                    line = line[6:]
                if line != "[DONE]":
                    try:
                        chunk = json.loads(line)
                        choices = chunk.get("choices", [])
                        if choices and len(choices) > 0:
                            delta = choices[0].get("delta", {})
                            if delta.get("reasoning") or delta.get("reasoning_content"):
                                reasoning_chunk = delta.get("reasoning") or delta.get("reasoning_content", "")
                                accumulated_reasoning += reasoning_chunk
                                openai_chunk = {
                                    "id": response_id,
                                    "object": "chat.completion.chunk",
                                    "created": created,
                                    "model": chunk.get("model", "unknown"),
                                    "choices": [{
                                        "index": 0,
                                        "delta": {"reasoning_content": reasoning_chunk},
                                        "logprobs": None,
                                        "finish_reason": None
                                    }]
                                }
                                yield f"data: {json.dumps(openai_chunk)}\n\n"
                                # Also stream as content
                                accumulated_content += reasoning_chunk
                                content_evt = {
                                    "id": response_id,
                                    "object": "chat.completion.chunk",
                                    "created": created,
                                    "model": chunk.get("model", "unknown"),
                                    "choices": [{
                                        "index": 0,
                                        "delta": {"content": reasoning_chunk},
                                        "logprobs": None,
                                        "finish_reason": None
                                    }]
                                }
                                yield f"data: {json.dumps(content_evt)}\n\n"
                            if delta.get("content"):
                                content_chunk = delta["content"]
                                accumulated_content += content_chunk
                                openai_chunk = {
                                    "id": response_id,
                                    "object": "chat.completion.chunk",
                                    "created": created,
                                    "model": chunk.get("model", "unknown"),
                                    "choices": [{
                                        "index": 0,
                                        "delta": {"content": content_chunk},
                                        "logprobs": None,
                                        "finish_reason": None
                                    }]
                                }
                                yield f"data: {json.dumps(openai_chunk)}\n\n"
                    except:
                        pass

            # Stream ended - send final chunk ONLY if we haven't sent finish_reason yet
            if has_sent_role and not has_sent_finish:
                has_sent_finish = True
                openai_chunk = {
                    "id": response_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": "unknown",
                    "choices": [{
                        "index": 0,
                        "delta": {},
                        "logprobs": None,
                        "finish_reason": "stop"
                    }]
                }
                yield f"data: {json.dumps(openai_chunk)}\n\n"
                yield "data: [DONE]\n\n"

            # Record token usage after streaming completes
            final_content = accumulated_content if accumulated_content else accumulated_reasoning
            if final_content and user_id:
                await _record_streaming_token_usage(
                    user_id=user_id,
                    content=final_content,
                )

            # Cleanup: close stream and client
            if stream:
                await stream.aclose()
            if client:
                await client.aclose()
    else:
        # Non-streaming fallback - convert to streaming format
        answer = result.get("answer", "")
        reasoning = result.get("reasoning", "")

        # Send role first
        openai_chunk = {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "unknown",
            "choices": [{
                "index": 0,
                "delta": {"role": "assistant"},
                "logprobs": None,
                "finish_reason": None
            }]
        }
        yield f"data: {json.dumps(openai_chunk)}\n\n"

        # Send reasoning if available
        if reasoning:
            openai_chunk = {
                "id": response_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "unknown",
                "choices": [{
                    "index": 0,
                    "delta": {"reasoning_content": reasoning},
                    "logprobs": None,
                    "finish_reason": None
                }]
            }
            yield f"data: {json.dumps(openai_chunk)}\n\n"

        # Send content
        if answer:
            openai_chunk = {
                "id": response_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "unknown",
                "choices": [{
                    "index": 0,
                    "delta": {"content": answer},
                    "logprobs": None,
                    "finish_reason": None
                }]
            }
            yield f"data: {json.dumps(openai_chunk)}\n\n"

        # Send finish
        openai_chunk = {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "unknown",
            "choices": [{
                "index": 0,
                "delta": {},
                "logprobs": None,
                "finish_reason": "stop"
            }]
        }
        yield f"data: {json.dumps(openai_chunk)}\n\n"
        yield "data: [DONE]\n\n"
