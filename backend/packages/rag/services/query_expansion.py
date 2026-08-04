"""
Query expansion and rewriting service.

Strategies:
- HyDE: Hypothetical Document Embedding - LLM generates a hypothetical answer,
  then we use that answer's embedding to search (improves semantic matching).
- Keyword expansion: extract and expand domain-specific keywords.
- Query decomposition: break complex queries into sub-queries.
"""
from __future__ import annotations
import logging
from typing import Optional
import httpx

logger = logging.getLogger("app.services.query_expansion")


async def _get_llm_client() -> Optional[dict]:
    """Get LLM config from model_configs"""
    from packages.core.database import async_session_factory
    from packages.model_gateway.models.model_config import ModelConfig
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
                    "api_url": model.api_url or "",
                    "api_key": model.api_key or "",
                    "model_id": model.model_id,
                }
    except Exception as e:
        logger.warning("Failed to get LLM config: %s", e)
    return None


async def _call_llm(
    prompt: str,
    system_prompt: str = "You are a helpful assistant.",
    temperature: float = 0.7,
    max_tokens: int = 512,
) -> str:
    """Call LLM for query expansion tasks"""
    llm_config = await _get_llm_client()

    if not llm_config or not llm_config["api_url"]:
        logger.debug("No LLM configured, returning empty expansion")
        return ""

    base_url = llm_config["api_url"].rstrip("/")
    if not base_url.endswith("/v1"):
        api_url = f"{base_url}/v1/chat/completions"
    else:
        api_url = f"{base_url}/chat/completions"

    headers = {"Content-Type": "application/json"}
    if llm_config["api_key"]:
        headers["Authorization"] = f"Bearer {llm_config['api_key']}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                api_url,
                json={
                    "model": llm_config["model_id"],
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                headers=headers,
            )
            if response.status_code == 200:
                data = response.json()
                message = data["choices"][0]["message"]
                return (message.get("content") or message.get("reasoning") or "").strip()
            logger.warning("LLM API returned %d", response.status_code)
            return ""
    except Exception as e:
        logger.warning("LLM call failed: %s", e)
        return ""


async def hyde_expand(query: str) -> str:
    """
    HyDE: Hypothetical Document Embedding.

    Generates a hypothetical answer to the query, then uses that answer's
    embedding for vector search (better semantic matching than the raw query).

    Args:
        query: The user's original question

    Returns:
        A hypothetical answer text, or empty string if no LLM available
    """
    system_prompt = (
        "You are a knowledgeable assistant. Given a question, write a brief, "
        "factual passage that answers it (1-3 paragraphs). Be specific and "
        "include likely details, keywords, and context. Write in the same "
        "language as the question."
    )

    prompt = f"Question: {query}\n\nWrite a brief passage that answers this question:"

    hyde_text = await _call_llm(prompt, system_prompt, temperature=0.3, max_tokens=256)
    if hyde_text:
        logger.info("HyDE expansion generated | query_len=%d hyde_len=%d", len(query), len(hyde_text))
    return hyde_text


async def expand_keywords(query: str) -> list[str]:
    """
    Keyword expansion: generate alternative search queries with synonyms and related terms.

    Returns up to 3 expanded query variants.
    """
    system_prompt = (
        "You are a search query optimizer. Given a search query, generate "
        "2-3 alternative phrasings that would help find relevant documents. "
        "Include synonyms, related terminology, and different ways to express "
        "the same information need. Return only the queries, one per line. "
        "Do NOT add numbers, bullets, or explanations."
    )

    prompt = f"Original query: {query}\n\nGenerate alternative search queries:"

    result = await _call_llm(prompt, system_prompt, temperature=0.5, max_tokens=200)
    if result:
        variants = [line.strip().lstrip("- ").lstrip("0123456789. ") for line in result.split("\n") if line.strip()]
        variants = [v for v in variants if v != query and len(v) > 3][:3]
        logger.info("Query expansion | variants=%d", len(variants))
        return variants
    return []


async def decompose_query(query: str) -> list[str]:
    """
    Decompose a complex multi-faceted query into simpler sub-queries.

    Example:
        "Compare the performance and cost of GPU A vs GPU B"
        -> ["GPU A performance metrics", "GPU B performance metrics",
            "GPU A cost", "GPU B cost"]
    """
    system_prompt = (
        "You are a query analyzer. Break down complex, multi-faceted questions "
        "into simpler, independent sub-questions that can each be answered "
        "separately. Return only the sub-questions, one per line. "
        "If the question is already simple, return the original question."
    )

    prompt = f"Complex question: {query}\n\nBreak this down into simpler sub-questions:"

    result = await _call_llm(prompt, system_prompt, temperature=0.3, max_tokens=200)
    if result:
        sub_queries = [line.strip().lstrip("- ").lstrip("0123456789. ") for line in result.split("\n") if line.strip()]
        sub_queries = [q for q in sub_queries if len(q) > 3]
        if len(sub_queries) <= 1:
            return [query]
        logger.info("Query decomposition | sub_queries=%d", len(sub_queries))
        return sub_queries
    return [query]


async def expand_query(query: str) -> dict:
    """
    Full query expansion pipeline.

    Returns:
        dict with:
        - original_query: str
        - hyde_text: str (for HyDE embedding)
        - expanded_queries: list[str]
        - sub_queries: list[str]
    """
    result = {
        "original_query": query,
        "hyde_text": "",
        "expanded_queries": [],
        "sub_queries": [query],
    }

    # Try HyDE expansion
    hyde_text = await hyde_expand(query)
    if hyde_text:
        result["hyde_text"] = hyde_text

    # Try keyword expansion
    expanded = await expand_keywords(query)
    if expanded:
        result["expanded_queries"] = expanded

    # Try decomposition
    sub_queries = await decompose_query(query)
    if len(sub_queries) > 1:
        result["sub_queries"] = sub_queries

    return result
