from __future__ import annotations
import logging
import time
from datetime import datetime
from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_config import ModelConfig
from app.models.model_gateway import ModelProvider
from app.schemas.model import (
    ModelConfigCreate, ModelConfigUpdate, ModelConfigResponse,
    ModelType, ModelStatus, COMMON_PRESETS
)

logger = logging.getLogger("app.services.model")


async def _validate_provider_exists(db: AsyncSession, provider_code: str) -> None:
    """Validate that a provider exists, raise ValueError if not"""
    provider = await db.execute(
        select(ModelProvider).where(ModelProvider.code == provider_code)
    )
    provider = provider.scalar_one_or_none()
    if not provider:
        raise ValueError(f"Provider '{provider_code}' not found")


async def list_models(
    db: AsyncSession,
    model_type: str | None = None,
    adapter_type: str | None = None,
    enabled_only: bool = False,
) -> list[ModelConfig]:
    """List model configurations with optional filters"""
    stmt = select(ModelConfig).order_by(ModelConfig.created_at.desc())

    if model_type:
        stmt = stmt.where(ModelConfig.model_type == model_type)
    if adapter_type:
        stmt = stmt.where(ModelConfig.adapter_type == adapter_type)
    if enabled_only:
        stmt = stmt.where(ModelConfig.is_enabled == True)

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_model(db: AsyncSession, model_id: int) -> ModelConfig | None:
    """Get a single model configuration by ID"""
    result = await db.execute(select(ModelConfig).where(ModelConfig.id == model_id))
    return result.scalar_one_or_none()


async def create_model(
    db: AsyncSession,
    data: ModelConfigCreate,
) -> ModelConfig:
    """Create a new model configuration"""
    await _validate_provider_exists(db, data.provider)

    # If setting as default, unset other defaults for same type
    if data.is_default:
        await db.execute(
            update(ModelConfig)
            .where(ModelConfig.model_type == data.model_type)
            .values(is_default=False)
        )

    model = ModelConfig(
        name=data.name,
        model_id=data.model_id,
        model_type=data.model_type,
        adapter_type=data.adapter_type,
        provider=data.provider,
        description=data.description,
        api_url=data.api_url,
        api_key=data.api_key,
        max_tokens=data.max_tokens,
        temperature=data.temperature,
        top_p=data.top_p,
        frequency_penalty=data.frequency_penalty,
        presence_penalty=data.presence_penalty,
        embedding_dim=data.embedding_dim,
        normalization=data.normalization,
        batch_size=data.batch_size,
        timeout_ms=data.timeout_ms,
        is_default=data.is_default,
        is_enabled=data.is_enabled,
        tags=",".join(data.tags) if data.tags else None,
        metadata_json=data.metadata if data.metadata else {},
    )

    db.add(model)
    await db.commit()
    await db.refresh(model)

    logger.info("Model config created | id=%d name=%s type=%s", model.id, model.name, model.model_type)
    return model


async def update_model(
    db: AsyncSession,
    model_id: int,
    data: ModelConfigUpdate,
) -> ModelConfig | None:
    """Update a model configuration"""
    model = await get_model(db, model_id)
    if not model:
        return None

    # Validate provider if it's being changed
    if data.provider is not None:
        await _validate_provider_exists(db, data.provider)

    # If setting as default, unset other defaults for same type
    if data.is_default:
        await db.execute(
            update(ModelConfig)
            .where(ModelConfig.model_type == model.model_type)
            .where(ModelConfig.id != model_id)
            .values(is_default=False)
        )

    update_data = data.model_dump(exclude_unset=True)

    # Don't update api_key if it's empty string (user didn't change it)
    if "api_key" in update_data and update_data["api_key"] == "":
        del update_data["api_key"]

    # Handle tags conversion
    if "tags" in update_data and isinstance(update_data["tags"], list):
        update_data["tags"] = ",".join(update_data["tags"])

    for key, value in update_data.items():
        setattr(model, key, value)

    await db.commit()
    await db.refresh(model)

    logger.info("Model config updated | id=%d name=%s", model.id, model.name)
    return model


async def delete_model(db: AsyncSession, model_id: int) -> bool:
    """Delete a model configuration"""
    model = await get_model(db, model_id)
    if not model:
        return False

    await db.delete(model)
    await db.commit()

    logger.info("Model config deleted | id=%d name=%s", model_id, model.name)
    return True


async def get_default_model(db: AsyncSession, model_type: str) -> ModelConfig | None:
    """Get the default model for a specific type"""
    result = await db.execute(
        select(ModelConfig)
        .where(ModelConfig.model_type == model_type)
        .where(ModelConfig.is_default == True)
        .where(ModelConfig.is_enabled == True)
    )
    return result.scalar_one_or_none()


async def test_model_connection(
    db: AsyncSession,
    model_id: int,
    test_input: str | None = None,
) -> dict:
    """Test model connection and return result"""
    model = await get_model(db, model_id)
    if not model:
        return {"success": False, "message": "Model not found", "latency_ms": None}

    start_time = time.time()
    result = {"success": False, "message": "", "latency_ms": None}

    try:
        # Test based on adapter type
        if model.adapter_type == "api":
            result = await _test_api_connection(model, test_input)
        elif model.adapter_type == "ollama":
            result = await _test_ollama_connection(model, test_input)
        elif model.adapter_type == "vllm":
            result = await _test_vllm_connection(model, test_input)
        else:
            result = {"success": True, "message": f"Adapter {model.adapter_type} configured", "latency_ms": None}

        # Update model status
        latency = result.get("latency_ms")
        if latency:
            result["latency_ms"] = round(latency, 2)

        # Update database
        new_status = "active" if result["success"] else "error"
        await db.execute(
            update(ModelConfig)
            .where(ModelConfig.id == model_id)
            .values(
                status=new_status,
                last_tested_at=datetime.utcnow(),
            )
        )
        await db.flush()

    except Exception as e:
        result = {"success": False, "message": str(e), "latency_ms": None}
        await db.execute(
            update(ModelConfig)
            .where(ModelConfig.id == model_id)
            .values(
                status="error",
                last_tested_at=datetime.utcnow(),
            )
        )
        await db.flush()

    return result


async def _test_api_connection(model: ModelConfig, test_input: str | None = None) -> dict:
    """Test API-based model connection"""
    import httpx

    if not model.api_url:
        return {"success": False, "message": "API URL not configured"}

    try:
        async with httpx.AsyncClient(timeout=model.timeout_ms / 1000) as client:
            headers = {"Authorization": f"Bearer {model.api_key}"} if model.api_key else {}

            # Normalize base_url - remove trailing slashes
            base_url = model.api_url.rstrip('/')

            if model.model_type == "embedding":
                # Test embedding endpoint - try /embeddings or /v1/embeddings
                for endpoint in ["/embeddings", "/v1/embeddings"]:
                    try:
                        response = await client.post(
                            f"{base_url}{endpoint}",
                            json={"input": test_input or "test", "model": model.model_id},
                            headers=headers,
                        )
                        if response.status_code == 200:
                            data = response.json()
                            dim = len(data["data"][0]["embedding"])
                            return {
                                "success": True,
                                "message": f"Embedding connection successful, dimension: {dim}",
                                "latency_ms": (response.elapsed.total_seconds() * 1000),
                            }
                    except httpx.HTTPStatusError:
                        continue
                return {"success": False, "message": "Embedding endpoint not found. Try configuring the correct API path."}

            elif model.model_type == "rerank":
                # Test rerank endpoint - try common paths
                for endpoint in ["/rerank", "/v1/rerank", "/rerankings"]:
                    try:
                        response = await client.post(
                            f"{base_url}{endpoint}",
                            json={
                                "model": model.model_id,
                                "query": test_input or "测试查询",
                                "documents": ["文档 1 内容", "文档 2 内容"],
                                "top_n": 2,
                            },
                            headers=headers,
                        )
                        if response.status_code == 200:
                            data = response.json()
                            results = data.get("results", [])
                            return {
                                "success": True,
                                "message": f"Rerank connection successful, got {len(results)} results",
                                "latency_ms": (response.elapsed.total_seconds() * 1000),
                            }
                    except httpx.HTTPStatusError:
                        continue
                return {"success": False, "message": "Rerank endpoint not found. Try configuring the correct API path."}

            elif model.model_type == "llm":
                # Test LLM endpoint (OpenAI-compatible API)
                # Handle various base_url formats:
                # - http://host:port/v1 → /chat/completions
                # - http://host:port/model-id/v1 → /chat/completions
                # - http://host:port → /v1/chat/completions

                # Always try /chat/completions first (when base_url already ends with /v1)
                if base_url.endswith("/v1"):
                    endpoint = "/chat/completions"
                else:
                    endpoint = "/v1/chat/completions"

                url = f"{base_url}{endpoint}"
                try:
                    response = await client.post(
                        url,
                        json={
                            "model": model.model_id,
                            "messages": [{"role": "user", "content": test_input or "Hi"}],
                            "max_tokens": 10,
                        },
                        headers=headers,
                    )
                    if response.status_code == 200:
                        data = response.json()
                        return {
                            "success": True,
                            "message": "LLM connection successful",
                            "latency_ms": (response.elapsed.total_seconds() * 1000),
                        }
                    elif response.status_code == 404:
                        # Try without /v1 prefix if base_url doesn't end with /v1
                        if not base_url.endswith("/v1"):
                            # Try just /chat/completions
                            url = f"{base_url}/chat/completions"
                            response = await client.post(
                                url,
                                json={
                                    "model": model.model_id,
                                    "messages": [{"role": "user", "content": test_input or "Hi"}],
                                    "max_tokens": 10,
                                },
                                headers=headers,
                            )
                            if response.status_code == 200:
                                return {
                                    "success": True,
                                    "message": "LLM connection successful",
                                    "latency_ms": (response.elapsed.total_seconds() * 1000),
                                }
                        return {"success": False, "message": f"LLM endpoint returned 404. Check API URL format."}
                    else:
                        return {"success": False, "message": f"LLM API error: {response.status_code} - {response.text[:200]}"}
                except httpx.RequestError as e:
                    return {"success": False, "message": f"Connection error: {str(e)}"}
                except Exception as e:
                    return {"success": False, "message": f"Error: {str(e)}"}

            else:
                # Generic endpoint test - just check if server responds
                try:
                    response = await client.get(f"{base_url}/models", headers=headers)
                    if response.status_code == 200:
                        return {
                            "success": True,
                            "message": "Connection successful",
                            "latency_ms": (response.elapsed.total_seconds() * 1000),
                        }
                except httpx.HTTPStatusError:
                    pass
                # Fallback: just ping the base URL
                try:
                    response = await client.get(base_url)
                    if response.status_code < 500:
                        return {
                            "success": True,
                            "message": "Server reachable (endpoint test skipped)",
                            "latency_ms": (response.elapsed.total_seconds() * 1000),
                        }
                except:
                    pass
                return {"success": False, "message": "Could not connect to API endpoint"}

    except httpx.RequestError as e:
        return {"success": False, "message": f"Connection failed: {str(e)}"}
    except Exception as e:
        return {"success": False, "message": f"Error: {str(e)}"}


async def _test_ollama_connection(model: ModelConfig, test_input: str | None = None) -> dict:
    """Test Ollama connection"""
    import httpx

    base_url = model.api_url or "http://localhost:11434"

    try:
        async with httpx.AsyncClient(timeout=model.timeout_ms / 1000) as client:
            # Check if model is available
            response = await client.get(f"{base_url}/api/tags")
            response.raise_for_status()
            tags = response.json().get("models", [])

            model_available = any(model.model_id in t.get("name", "") for t in tags)

            if not model_available:
                return {"success": False, "message": f"Model '{model.model_id}' not found in Ollama"}

            # Quick generation test
            response = await client.post(
                f"{base_url}/api/generate",
                json={
                    "model": model.model_id,
                    "prompt": test_input or "Hello",
                    "stream": False,
                    "options": {"num_predict": 10},
                },
            )
            response.raise_for_status()

            return {
                "success": True,
                "message": f"Ollama connection successful",
                "latency_ms": (response.elapsed.total_seconds() * 1000),
            }

    except httpx.HTTPError as e:
        return {"success": False, "message": f"Ollama error: {e}"}
    except Exception as e:
        return {"success": False, "message": f"Connection failed: {e}"}


async def _test_vllm_connection(model: ModelConfig, test_input: str | None = None) -> dict:
    """Test vLLM connection (OpenAI-compatible API)"""
    return await _test_api_connection(model, test_input)




def get_available_presets(model_type: str | None = None) -> list:
    """Get available model presets"""
    if model_type:
        return [p for p in COMMON_PRESETS if p.model_type.value == model_type]
    return list(COMMON_PRESETS)
