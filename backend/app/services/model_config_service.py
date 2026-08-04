"""Model Config Service - Bridge between model management and RAG processing.

This service provides the integration layer between:
1. Model Management (model_configs table) - User configures models via UI
2. RAG Processing Pipeline - Document embedding, reranking, LLM generation

The system settings store references (IDs) to the default models,
and this service resolves those references to actual model configurations.
"""
from __future__ import annotations
import logging
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_config import ModelConfig
from app.schemas.model import ModelType

logger = logging.getLogger("app.services.model_config")


async def get_default_model(db: AsyncSession, model_type: str) -> Optional[ModelConfig]:
    """Get the default model configuration for a given type.

    Args:
        db: Database session
        model_type: One of 'llm', 'embedding', 'rerank', 'vision', etc.

    Returns:
        ModelConfig if found, None otherwise
    """
    result = await db.execute(
        select(ModelConfig)
        .where(ModelConfig.model_type == model_type)
        .where(ModelConfig.is_default == True)
        .where(ModelConfig.is_enabled == True)
        .order_by(ModelConfig.updated_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_model_by_id(db: AsyncSession, model_id: int) -> Optional[ModelConfig]:
    """Get model configuration by ID."""
    result = await db.execute(
        select(ModelConfig).where(ModelConfig.id == model_id)
    )
    return result.scalar_one_or_none()


async def resolve_embedding_config(db: AsyncSession) -> Optional[ModelConfig]:
    """Resolve the active embedding model configuration.

    Priority:
    1. Default embedding model from model_configs (is_default=True)
    2. Fallback to legacy system_settings config
    """
    # Try to get default embedding model
    model = await get_default_model(db, ModelType.EMBEDDING.value)
    if model:
        logger.info("Using embedding model from model_configs: %s", model.name)
        return model

    logger.warning("No default embedding model found in model_configs")
    return None


async def get_provider_config(db: AsyncSession, provider_code: str) -> Optional[dict]:
    """Get provider configuration (base_url, api_key) by provider code.

    Args:
        db: Database session
        provider_code: Provider code (e.g., 'openai', 'xinference')

    Returns:
        Dict with base_url, api_key, api_key_name; None if not found
    """
    from app.models.model_gateway import ModelProvider

    result = await db.execute(
        select(ModelProvider)
        .where(ModelProvider.code == provider_code)
        .where(ModelProvider.is_enabled == True)
        .limit(1)
    )
    provider = result.scalar_one_or_none()
    if provider:
        return {
            "base_url": provider.base_url,
            "api_key": provider.api_key,
            "api_key_name": provider.api_key_name,
        }
    return None


async def resolve_rerank_config(db: AsyncSession) -> Optional[ModelConfig]:
    """Resolve the active rerank model configuration."""
    model = await get_default_model(db, ModelType.RERANK.value)
    if model:
        logger.info("Using rerank model from model_configs: %s", model.name)
        return model

    logger.info("No rerank model configured in model_configs")
    return None


async def resolve_llm_config(db: AsyncSession) -> Optional[ModelConfig]:
    """Resolve the active LLM model configuration."""
    model = await get_default_model(db, ModelType.LLM.value)
    if model:
        logger.info("Using LLM model from model_configs: %s", model.name)
        return model

    logger.info("No LLM model configured in model_configs")
    return None


async def model_config_to_embedding_params(db: AsyncSession, model: ModelConfig) -> dict:
    """Convert ModelConfig to embedding service parameters.

    Args:
        db: Database session
        model: ModelConfig with model_type='embedding'

    Returns:
        Dict with provider, model_name, api_url, api_key, dim
    """
    config = model.metadata_json or {}

    # Get provider config for base_url and api_key
    provider_config = await get_provider_config(db, model.provider)
    base_url = provider_config["base_url"] if provider_config else ""
    api_key = provider_config["api_key"] if provider_config else ""

    # All providers (api, ollama, vllm) use the same API interface
    return {
        "provider": model.adapter_type,
        "model_name": model.model_id,
        "api_url": base_url,
        "api_key": api_key,
        "dim": model.embedding_dim or config.get("embedding_dim", 1024),
    }


async def model_config_to_rerank_params(db: AsyncSession, model: ModelConfig) -> dict:
    """Convert ModelConfig to rerank service parameters."""
    config = model.metadata_json or {}

    # Get provider config for base_url and api_key
    provider_config = await get_provider_config(db, model.provider)
    base_url = provider_config["base_url"] if provider_config else ""
    api_key = provider_config["api_key"] if provider_config else ""

    if model.adapter_type == "api":
        return {
            "provider": "api",
            "model_name": model.model_id,
            "api_url": base_url,
            "api_key": api_key,
        }
    else:  # local
        return {
            "provider": "local",
            "model_name": model.model_id,
            "api_url": base_url,
            "api_key": api_key,
        }


async def model_config_to_llm_params(db: AsyncSession, model: ModelConfig) -> dict:
    """Convert ModelConfig to LLM service parameters."""
    config = model.metadata_json or {}

    # Get provider config for base_url and api_key
    provider_config = await get_provider_config(db, model.provider)
    base_url = provider_config["base_url"] if provider_config else ""
    api_key = provider_config["api_key"] if provider_config else ""

    return {
        "provider": model.adapter_type,
        "model_name": model.model_id,
        "api_url": base_url,
        "api_key": api_key,
        "max_tokens": model.max_tokens or config.get("max_tokens", 4096),
        "temperature": model.temperature or config.get("temperature", 0.7),
        "top_p": model.top_p or config.get("top_p", 0.9),
    }
