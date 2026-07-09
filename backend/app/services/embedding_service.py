"""Embedding service. Model choice comes from model_configs table via model_config_service."""
from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

logger = logging.getLogger("app.services.embedding")


class BaseEmbeddingService(ABC):
    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]: ...
    @abstractmethod
    async def embed_query(self, text: str) -> list[float]: ...
    @property
    @abstractmethod
    def dimension(self) -> int: ...


class SentenceTransformerService(BaseEmbeddingService):
    def __init__(self, model_name: str = "BAAI/bge-m3"):
        self._model_name = model_name
        self._model = None

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading embedding model: %s", self._model_name)
            self._model = SentenceTransformer(self._model_name)
        return self._model

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        import asyncio
        model = self._load_model()
        return await asyncio.to_thread(lambda: model.encode(texts, normalize_embeddings=True).tolist())

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_texts([text]))[0]

    @property
    def dimension(self) -> int:
        return self._load_model().get_sentence_embedding_dimension()


class APIEmbeddingService(BaseEmbeddingService):
    def __init__(self, api_url: str, api_key: str = "", model: str = "text-embedding-3-small"):
        self._api_url = api_url.rstrip('/')
        self._api_key = api_key
        self._model = model

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        import httpx
        import asyncio

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        # Build correct embedding URL: normalize base_url paths
        base = self._api_url.rstrip('/')
        if base.endswith('/v1'):
            embed_url = f"{base}/embeddings"
        else:
            embed_url = f"{base}/v1/embeddings"

        payload = {"model": self._model, "input": texts}
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
        from app.core.rag_config import get_model_config
        return get_model_config().get("embedding_dim", 1024)


class RandomEmbeddingService(BaseEmbeddingService):
    def __init__(self, dim: int = 1024):
        self._dim = dim

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        import hashlib
        result = []
        for text in texts:
            seed = int(hashlib.md5(text.encode()).hexdigest()[:16], 16)
            rng = __import__('random').Random(seed)
            vec = [rng.uniform(-1, 1) for _ in range(self._dim)]
            norm = sum(x * x for x in vec) ** 0.5
            result.append([x / norm for x in vec])
        return result

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_texts([text]))[0]

    @property
    def dimension(self) -> int:
        return self._dim


_embedding_service: BaseEmbeddingService | None = None
_last_model_key: str = ""


def get_embedding_service(
    provider: str = None,
    model_name: str = None,
    api_url: str = None,
    api_key: str = None,
    dim: int = None,
) -> BaseEmbeddingService:
    """Return a cached embedding service.

    Args:
        provider: 'local', 'api', 'ollama', 'vllm', or None for auto from config
        model_name: Model name/path
        api_url: API endpoint URL
        api_key: API key
        dim: Embedding dimension

    If no parameters provided, falls back to legacy rag_config.
    """
    global _embedding_service, _last_model_key

    from app.config import settings as app_settings

    # Use provided params or fall back to legacy config
    if provider is None:
        from app.core.rag_config import get_model_config
        model = get_model_config()
        provider = model.get("embedding_provider", "local")
        model_name = model.get("embedding_model", "BAAI/bge-m3")
        dim = dim or model.get("embedding_dim", 1024)
        api_url = api_url or model.get("embedding_api_url", "")
        api_key = api_key or model.get("embedding_api_key", "")

    model_key = f"{provider}:{model_name}"

    if _embedding_service is None or model_key != _last_model_key:
        if provider == "api":
            logger.info("Embedding: API provider=%s model=%s", api_url, model_name)
            _embedding_service = APIEmbeddingService(api_url=api_url, api_key=api_key, model=model_name)
        elif provider == "ollama":
            logger.info("Embedding: Ollama model=%s", model_name)
            _embedding_service = APIEmbeddingService(
                api_url=api_url or "http://localhost:11434/v1",
                api_key=api_key or "ollama",
                model=model_name
            )
        elif provider == "vllm":
            logger.info("Embedding: vLLM model=%s", model_name)
            _embedding_service = APIEmbeddingService(
                api_url=api_url,
                api_key=api_key or "ollama",
                model=model_name
            )
        else:
            logger.info("Embedding: local model=%s", model_name)
            _embedding_service = SentenceTransformerService(model_name=model_name)
        _last_model_key = model_key

    return _embedding_service


def reset_embedding_service():
    """Force reload of embedding service on next get_embedding_service() call."""
    global _embedding_service, _last_model_key
    _embedding_service = None
    _last_model_key = ""
    logger.info("Embedding service reset — will reload on next use")
