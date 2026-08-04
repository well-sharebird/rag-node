"""Embedding service. Model configuration is loaded from model_configs table.

All model settings (embedding, rerank, LLM) are managed via the Model Management UI
and stored in the model_configs database table. This service only handles API calls.
"""
from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from packages.core.tracing import traceable

logger = logging.getLogger("app.services.embedding")


class BaseEmbeddingService(ABC):
    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]: ...
    @abstractmethod
    async def embed_query(self, text: str) -> list[float]: ...
    @property
    @abstractmethod
    def dimension(self) -> int: ...


class APIEmbeddingService(BaseEmbeddingService):
    MAX_CHARS_PER_TEXT = 500

    def __init__(
        self,
        api_url: str,
        api_key: str = "",
        model: str = "text-embedding-3-small",
        dim: int = 1024,
    ):
        self._api_url = api_url.rstrip('/')
        self._api_key = api_key
        self._model = model
        self._dim = dim

    @traceable(node_type='embedding', node_name='embed_texts', capture_input=True, capture_output=True)
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        import httpx
        import asyncio

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        base = self._api_url.rstrip('/')
        if base.endswith('/v1'):
            embed_url = f"{base}/embeddings"
        else:
            embed_url = f"{base}/v1/embeddings"

        truncated = [t[:self.MAX_CHARS_PER_TEXT] for t in texts]
        if any(len(t) > self.MAX_CHARS_PER_TEXT for t in texts):
            logger.warning("Truncated %d texts exceeding %d chars limit",
                          sum(1 for t in texts if len(t) > self.MAX_CHARS_PER_TEXT),
                          self.MAX_CHARS_PER_TEXT)

        payload = {"model": self._model, "input": truncated}
        last_error = None

        async with httpx.AsyncClient(timeout=120.0) as client:
            for attempt in range(3):
                try:
                    response = await client.post(embed_url, json=payload, headers=headers)
                    response.raise_for_status()
                    data = response.json()
                    return [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]
                except httpx.HTTPStatusError as e:
                    last_error = e
                    if e.response.status_code >= 500:
                        logger.warning("Embedding API 5xx (attempt %d/3): %s", attempt + 1, e)
                        await asyncio.sleep(1.0 * (attempt + 1))
                        continue
                    raise
                except httpx.RequestError as e:
                    last_error = e
                    logger.warning("Embedding API connection error (attempt %d/3): %s", attempt + 1, e)
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue

        raise last_error or RuntimeError("Embedding API failed after 3 retries")

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_texts([text]))[0]

    @property
    def dimension(self) -> int:
        return self._dim


_embedding_service: APIEmbeddingService | None = None
_last_model_key: str = ""


def get_embedding_service(
    api_url: str,
    api_key: str,
    model: str,
    dim: int,
) -> APIEmbeddingService:
    """Get embedding service configured with the specified parameters.

    Model configuration should be loaded from model_configs table by the caller.

    Args:
        api_url: Model API base URL (e.g., http://host:port/v1)
        api_key: API key for authentication (optional)
        model: Model ID/name
        dim: Embedding dimension

    Returns:
        Configured APIEmbeddingService instance
    """
    global _embedding_service, _last_model_key

    model_key = f"{model}:{api_url}"

    if _embedding_service is None or model_key != _last_model_key:
        logger.info("Embedding: model=%s url=%s dim=%d", model, api_url, dim)
        _embedding_service = APIEmbeddingService(
            api_url=api_url,
            api_key=api_key,
            model=model,
            dim=dim,
        )
        _last_model_key = model_key

    return _embedding_service


def reset_embedding_service():
    global _embedding_service, _last_model_key
    _embedding_service = None
    _last_model_key = ""
    logger.info("Embedding service reset")
