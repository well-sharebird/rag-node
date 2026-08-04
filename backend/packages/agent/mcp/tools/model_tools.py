"""Model Management MCP Tools."""

import logging
import json
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from mcp.types import TextContent

from packages.model_gateway.services.model_service import (
    list_models,
    get_model,
    create_model,
    update_model,
    delete_model,
    get_default_model,
    test_model_connection,
)
from packages.model_gateway.schemas.model import ModelConfigCreate, ModelConfigUpdate, ModelTestRequest

logger = logging.getLogger("app.mcp.model_tools")

MODEL_TOOLS = [
    {
        "name": "list_models",
        "description": "List model configurations with optional filters",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model_type": {"type": "string", "enum": ["LLM", "EMBEDDING", "RERANK", "VISION", "SPEECH_TO_TEXT", "TEXT_TO_SPEECH"], "description": "Filter by model type"},
                "adapter_type": {"type": "string", "enum": ["API", "OLLAMA", "VLLM", "TRITON", "CUSTOM"], "description": "Filter by adapter type"},
                "enabled_only": {"type": "boolean", "description": "Only return enabled models", "default": False}
            }
        }
    },
    {
        "name": "get_model",
        "description": "Get details of a specific model configuration",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model_id": {"type": "integer", "description": "Model configuration ID"}
            },
            "required": ["model_id"]
        }
    },
    {
        "name": "create_model",
        "description": "Create a new model configuration",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Model name"},
                "model_id": {"type": "string", "description": "Provider model ID (e.g., gpt-4, qwen-2.5-72b)"},
                "model_type": {"type": "string", "enum": ["LLM", "EMBEDDING", "RERANK", "VISION"], "description": "Model type"},
                "adapter_type": {"type": "string", "enum": ["API", "OLLAMA", "VLLM", "TRITON", "CUSTOM"], "description": "Adapter type"},
                "provider": {"type": "string", "description": "Provider name (e.g., openai, azure, gemini)"},
                "api_url": {"type": "string", "description": "API endpoint URL"},
                "api_key": {"type": "string", "description": "API key for authentication"},
                "max_tokens": {"type": "integer", "description": "Max tokens for generation"},
                "temperature": {"type": "number", "description": "Temperature for sampling"},
                "embedding_dim": {"type": "integer", "description": "Embedding dimension (for EMBEDDING type)"}
            },
            "required": ["name", "model_id", "model_type", "adapter_type"]
        }
    },
    {
        "name": "update_model",
        "description": "Update an existing model configuration",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model_id": {"type": "integer", "description": "Model ID to update"},
                "name": {"type": "string", "description": "New name"},
                "api_url": {"type": "string", "description": "New API URL"},
                "api_key": {"type": "string", "description": "New API key"},
                "max_tokens": {"type": "integer", "description": "New max tokens"},
                "temperature": {"type": "number", "description": "New temperature"},
                "is_enabled": {"type": "boolean", "description": "Enable/disable model"},
                "is_default": {"type": "boolean", "description": "Set as default for type"}
            },
            "required": ["model_id"]
        }
    },
    {
        "name": "delete_model",
        "description": "Delete a model configuration",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model_id": {"type": "integer", "description": "Model ID to delete"}
            },
            "required": ["model_id"]
        }
    },
    {
        "name": "test_model",
        "description": "Test model connection and functionality",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model_id": {"type": "integer", "description": "Model ID to test"},
                "test_input": {"type": "string", "description": "Test input for the model"}
            },
            "required": ["model_id"]
        }
    },
    {
        "name": "get_default_model",
        "description": "Get the default model for a specific type",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model_type": {"type": "string", "enum": ["LLM", "EMBEDDING", "RERANK"], "description": "Model type"}
            },
            "required": ["model_type"]
        }
    }
]


async def list_models_handler(
    db: AsyncSession,
    model_type: Optional[str] = None,
    adapter_type: Optional[str] = None,
    enabled_only: bool = False
) -> Dict[str, Any]:
    """List models handler."""
    try:
        models = await list_models(db, model_type, adapter_type, enabled_only)
        return {
            "success": True,
            "data": [
                {
                    "id": m.id,
                    "name": m.name,
                    "model_id": m.model_id,
                    "model_type": m.model_type,
                    "adapter_type": m.adapter_type,
                    "provider": m.provider,
                    "is_enabled": m.is_enabled,
                    "is_default": m.is_default,
                    "created_at": str(m.created_at) if m.created_at else None,
                }
                for m in models
            ],
            "total": len(models),
        }
    except Exception as e:
        logger.error("Failed to list models: %s", e)
        return {"success": False, "error": str(e)}


async def get_model_handler(db: AsyncSession, model_id: int) -> Dict[str, Any]:
    """Get model handler."""
    try:
        model = await get_model(db, model_id)
        return {
            "success": True,
            "data": {
                "id": model.id,
                "name": model.name,
                "model_id": model.model_id,
                "model_type": model.model_type,
                "adapter_type": model.adapter_type,
                "provider": model.provider,
                "api_url": model.api_url,
                "max_tokens": model.max_tokens,
                "temperature": model.temperature,
                "embedding_dim": model.embedding_dim,
                "is_enabled": model.is_enabled,
                "is_default": model.is_default,
                "config": model.config,
            }
        }
    except Exception as e:
        logger.error("Failed to get model: %s", e)
        return {"success": False, "error": str(e)}


async def create_model_handler(db: AsyncSession, **kwargs) -> Dict[str, Any]:
    """Create model handler."""
    try:
        data = ModelConfigCreate(**kwargs)
        model = await create_model(db, data)
        return {
            "success": True,
            "data": {
                "id": model.id,
                "name": model.name,
                "model_type": model.model_type,
            }
        }
    except Exception as e:
        logger.error("Failed to create model: %s", e)
        return {"success": False, "error": str(e)}


async def update_model_handler(db: AsyncSession, model_id: int, **kwargs) -> Dict[str, Any]:
    """Update model handler."""
    try:
        data = ModelConfigUpdate(**kwargs)
        model = await update_model(db, model_id, data)
        return {
            "success": True,
            "data": {"id": model.id, "updated_fields": list(kwargs.keys())}
        }
    except Exception as e:
        logger.error("Failed to update model: %s", e)
        return {"success": False, "error": str(e)}


async def delete_model_handler(db: AsyncSession, model_id: int) -> Dict[str, Any]:
    """Delete model handler."""
    try:
        result = await delete_model(db, model_id)
        return {"success": result, "message": f"Model {model_id} deleted" if result else "Delete failed"}
    except Exception as e:
        logger.error("Failed to delete model: %s", e)
        return {"success": False, "error": str(e)}


async def test_model_handler(db: AsyncSession, model_id: int, test_input: Optional[str] = None) -> Dict[str, Any]:
    """Test model handler."""
    try:
        result = await test_model_connection(db, model_id, test_input)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error("Failed to test model: %s", e)
        return {"success": False, "error": str(e)}


async def get_default_model_handler(db: AsyncSession, model_type: str) -> Dict[str, Any]:
    """Get default model handler."""
    try:
        model = await get_default_model(db, model_type)
        return {
            "success": True,
            "data": {
                "id": model.id,
                "name": model.name,
                "model_id": model.model_id,
                "provider": model.provider,
            }
        }
    except Exception as e:
        logger.error("Failed to get default model: %s", e)
        return {"success": False, "error": str(e)}


async def handle_model_tool(
    name: str,
    arguments: Dict[str, Any],
    db: AsyncSession
) -> List[TextContent]:
    """Handle Model tool calls.

    Args:
        name: Tool name
        arguments: Tool arguments
        db: Database session
    """
    import json

    try:
        if name == "list_models":
            result = await list_models_handler(
                db,
                model_type=arguments.get("model_type"),
                adapter_type=arguments.get("adapter_type"),
                enabled_only=arguments.get("enabled_only", False)
            )
        elif name == "get_model":
            result = await get_model_handler(db, arguments.get("model_id"))
        elif name == "create_model":
            result = await create_model_handler(db, **arguments)
        elif name == "update_model":
            model_id = arguments.pop("model_id")
            result = await update_model_handler(db, model_id, **arguments)
        elif name == "delete_model":
            result = await delete_model_handler(db, arguments.get("model_id"))
        elif name == "test_model":
            result = await test_model_handler(db, arguments.get("model_id"), arguments.get("test_input"))
        elif name == "get_default_model":
            result = await get_default_model_handler(db, arguments.get("model_type"))
        else:
            raise ValueError(f"Unknown model tool: {name}")

        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}, indent=2))]


def create_model_tools():
    """Return Model tools definitions."""
    return MODEL_TOOLS
