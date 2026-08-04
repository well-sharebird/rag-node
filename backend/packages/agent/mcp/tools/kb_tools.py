"""Knowledge Base Management MCP Tools."""

import logging
import json
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from mcp.types import TextContent

from packages.rag.services.kb_service import (
    list_knowledge_bases,
    get_knowledge_base,
    create_knowledge_base,
    update_knowledge_base,
    delete_knowledge_base,
)
from packages.rag.schemas.knowledge_base import KBCreateRequest, KBUpdateRequest

logger = logging.getLogger("app.mcp.kb_tools")

# MCP Tool definitions
KB_TOOLS = [
    {
        "name": "list_knowledge_bases",
        "description": "List all knowledge bases with optional search filter",
        "inputSchema": {
            "type": "object",
            "properties": {
                "search": {"type": "string", "description": "Search keyword for name/description"},
                "limit": {"type": "integer", "description": "Max results to return", "default": 50},
                "offset": {"type": "integer", "description": "Offset for pagination", "default": 0}
            }
        }
    },
    {
        "name": "get_knowledge_base",
        "description": "Get details of a specific knowledge base by ID",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kb_id": {"type": "string", "description": "Knowledge base ID"}
            },
            "required": ["kb_id"]
        }
    },
    {
        "name": "create_knowledge_base",
        "description": "Create a new knowledge base",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Knowledge base name"},
                "description": {"type": "string", "description": "Knowledge base description", "default": ""},
                "permissions": {"type": "string", "description": "Access permissions (read|write|admin)", "default": "write"},
                "top_k": {"type": "integer", "description": "Default top-k for retrieval", "default": 5},
                "min_score": {"type": "number", "description": "Minimum similarity score threshold", "default": 0.7},
                "enable_rerank": {"type": "boolean", "description": "Enable reranking", "default": False}
            },
            "required": ["name"]
        }
    },
    {
        "name": "update_knowledge_base",
        "description": "Update an existing knowledge base",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kb_id": {"type": "string", "description": "Knowledge base ID"},
                "name": {"type": "string", "description": "New name"},
                "description": {"type": "string", "description": "New description"},
                "permissions": {"type": "object", "description": "New permissions config"},
                "top_k": {"type": "integer", "description": "New top-k value"},
                "min_score": {"type": "number", "description": "New min score threshold"},
                "enable_rerank": {"type": "boolean", "description": "Enable/disable reranking"}
            },
            "required": ["kb_id"]
        }
    },
    {
        "name": "delete_knowledge_base",
        "description": "Delete a knowledge base and its associated Milvus collection",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kb_id": {"type": "string", "description": "Knowledge base ID to delete"}
            },
            "required": ["kb_id"]
        }
    },
    {
        "name": "search_knowledge_base",
        "description": "Search content within knowledge bases using vector retrieval",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query text"},
                "kb_ids": {"type": "array", "items": {"type": "string"}, "description": "List of KB IDs to search"},
                "top_k": {"type": "integer", "description": "Number of results to return", "default": 5},
                "min_score": {"type": "number", "description": "Minimum similarity score", "default": 0.7}
            },
            "required": ["query"]
        }
    }
]


async def list_kbs_handler(
    db: AsyncSession,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> Dict[str, Any]:
    """List knowledge bases handler."""
    try:
        kbs = await list_knowledge_bases(db, search or "")
        return {
            "success": True,
            "data": [
                {
                    "id": kb.id,
                    "name": kb.name,
                    "description": kb.description,
                    "document_count": kb.document_count,
                    "vector_count": kb.vector_count,
                    "created_at": str(kb.created_at) if kb.created_at else None,
                }
                for kb in kbs[offset:offset+limit]
            ],
            "total": len(kbs),
        }
    except Exception as e:
        logger.error("Failed to list knowledge bases: %s", e)
        return {"success": False, "error": str(e)}


async def get_kb_handler(db: AsyncSession, kb_id: str) -> Dict[str, Any]:
    """Get knowledge base handler."""
    try:
        kb = await get_knowledge_base(db, kb_id)
        return {
            "success": True,
            "data": {
                "id": kb.id,
                "name": kb.name,
                "description": kb.description,
                "collection_name": kb.collection_name,
                "document_count": kb.document_count,
                "vector_count": kb.vector_count,
                "permissions": kb.permissions,
                "top_k": kb.top_k,
                "min_score": kb.min_score,
                "enable_rerank": kb.enable_rerank,
                "created_at": str(kb.created_at) if kb.created_at else None,
                "updated_at": str(kb.updated_at) if kb.updated_at else None,
            }
        }
    except Exception as e:
        logger.error("Failed to get knowledge base: %s", e)
        return {"success": False, "error": str(e)}


async def create_kb_handler(
    db: AsyncSession,
    milvus=None,
    name: str = None,
    description: Optional[str] = None,
    permissions: Optional[str] = None,
    top_k: int = 5,
    min_score: float = 0.7,
    enable_rerank: bool = False
) -> Dict[str, Any]:
    """Create knowledge base handler."""
    try:
        from packages.core.config import settings
        from pymilvus import MilvusClient
        if milvus is None:
            milvus = MilvusClient(uri=settings.milvus_uri)

        data = KBCreateRequest(
            name=name,
            description=description or "",
            permissions=permissions or "write",
            top_k=top_k,
            min_score=min_score,
            enable_rerank=enable_rerank,
        )
        kb = await create_knowledge_base(db, milvus, data)
        return {
            "success": True,
            "data": {
                "id": kb.id,
                "name": kb.name,
                "collection_name": kb.collection_name,
            }
        }
    except Exception as e:
        logger.error("Failed to create knowledge base: %s", e)
        return {"success": False, "error": str(e)}


async def update_kb_handler(
    db: AsyncSession,
    kb_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    permissions: Optional[Dict] = None,
    top_k: Optional[int] = None,
    min_score: Optional[float] = None,
    enable_rerank: Optional[bool] = None
) -> Dict[str, Any]:
    """Update knowledge base handler."""
    try:
        update_data = {}
        if name is not None:
            update_data["name"] = name
        if description is not None:
            update_data["description"] = description
        if permissions is not None:
            update_data["permissions"] = permissions
        if top_k is not None:
            update_data["top_k"] = top_k
        if min_score is not None:
            update_data["min_score"] = min_score
        if enable_rerank is not None:
            update_data["enable_rerank"] = enable_rerank

        data = KBUpdateRequest(**update_data)
        kb = await update_knowledge_base(db, kb_id, data)
        return {
            "success": True,
            "data": {"id": kb.id, "updated_fields": list(update_data.keys())}
        }
    except Exception as e:
        logger.error("Failed to update knowledge base: %s", e)
        return {"success": False, "error": str(e)}


async def delete_kb_handler(db: AsyncSession, milvus=None, kb_id: str = None) -> Dict[str, Any]:
    """Delete knowledge base handler."""
    try:
        from packages.core.config import settings
        from pymilvus import MilvusClient
        if milvus is None:
            milvus = MilvusClient(uri=settings.milvus_uri)
        await delete_knowledge_base(db, milvus, kb_id)
        return {"success": True, "message": f"Knowledge base {kb_id} deleted"}
    except Exception as e:
        logger.error("Failed to delete knowledge base: %s", e)
        return {"success": False, "error": str(e)}


async def search_kb_handler(
    db: AsyncSession,
    query: str,
    kb_ids: Optional[List[str]] = None,
    top_k: int = 5,
    min_score: float = 0.7
) -> Dict[str, Any]:
    """Search knowledge base handler."""
    try:
        from packages.rag.services.retrieval_service import retrieve

        from packages.core.config import settings
        from pymilvus import MilvusClient
        milvus = MilvusClient(uri=settings.milvus_uri)

        results = await retrieve(
            db=db,
            milvus=milvus,
            query=query,
            kb_ids=kb_ids,
            top_k=top_k,
            min_score=min_score,
        )
        return {
            "success": True,
            "data": {
                "query": query,
                "results": [
                    {
                        "content": r.get("content", ""),
                        "score": r.get("score", 0),
                        "document_id": r.get("document_id"),
                        "kb_id": r.get("kb_id"),
                    }
                    for r in results
                ]
            }
        }
    except Exception as e:
        logger.error("Failed to search knowledge base: %s", e)
        return {"success": False, "error": str(e)}


async def handle_kb_tool(
    name: str,
    arguments: Dict[str, Any],
    db: AsyncSession
) -> List[TextContent]:
    """Handle KB tool calls.

    Args:
        name: Tool name
        arguments: Tool arguments
        db: Database session
    """
    import json

    try:
        if name == "list_knowledge_bases":
            result = await list_kbs_handler(
                db,
                search=arguments.get("search"),
                limit=arguments.get("limit", 50),
                offset=arguments.get("offset", 0)
            )
        elif name == "get_knowledge_base":
            result = await get_kb_handler(db, arguments.get("kb_id"))
        elif name == "create_knowledge_base":
            result = await create_kb_handler(db, **arguments)
        elif name == "update_knowledge_base":
            result = await update_kb_handler(db, **arguments)
        elif name == "delete_knowledge_base":
            result = await delete_kb_handler(db, **arguments)
        elif name == "search_knowledge_base":
            result = await search_kb_handler(db, **arguments)
        else:
            raise ValueError(f"Unknown KB tool: {name}")

        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}, indent=2))]


def create_kb_tools():
    """Return KB tools definitions.

    Returns:
        List of KB tool definitions
    """
    return KB_TOOLS
