"""Agent Hub MCP Tools."""

import logging
import json
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from mcp.types import TextContent

logger = logging.getLogger("app.mcp.agent_tools")

AGENT_TOOLS = [
    {
        "name": "list_agents",
        "description": "List agent configurations with optional filters",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["draft", "published", "archived"], "description": "Filter by status"},
                "agent_type": {"type": "string", "description": "Filter by agent type"},
                "limit": {"type": "integer", "description": "Max results", "default": 50},
                "offset": {"type": "integer", "description": "Offset", "default": 0}
            }
        }
    },
    {
        "name": "list_public_agents",
        "description": "List public agents from the agent marketplace",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max results", "default": 50},
                "offset": {"type": "integer", "description": "Offset", "default": 0}
            }
        }
    },
    {
        "name": "get_agent",
        "description": "Get details of a specific agent by ID",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Agent ID"}
            },
            "required": ["agent_id"]
        }
    },
    {
        "name": "create_agent",
        "description": "Create a new agent configuration",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Agent name"},
                "description": {"type": "string", "description": "Agent description"},
                "agent_type": {"type": "string", "description": "Agent type (e.g., langgraph, workflow)"},
                "config": {"type": "object", "description": "Agent configuration JSON"},
                "is_public": {"type": "boolean", "description": "Make agent public (visible in marketplace)", "default": False}
            },
            "required": ["name"]
        }
    },
    {
        "name": "update_agent",
        "description": "Update an existing agent configuration",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Agent ID to update"},
                "name": {"type": "string", "description": "New name"},
                "description": {"type": "string", "description": "New description"},
                "config": {"type": "object", "description": "New configuration"},
                "is_public": {"type": "boolean", "description": "Set public visibility"}
            },
            "required": ["agent_id"]
        }
    },
    {
        "name": "delete_agent",
        "description": "Delete an agent configuration",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Agent ID to delete"}
            },
            "required": ["agent_id"]
        }
    },
    {
        "name": "execute_agent",
        "description": "Execute an agent with a given query",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Agent ID to execute"},
                "query": {"type": "string", "description": "Input query for the agent"},
                "session_id": {"type": "string", "description": "Session ID for conversation context"}
            },
            "required": ["agent_id", "query"]
        }
    },
    {
        "name": "publish_agent",
        "description": "Publish an agent to the public marketplace",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Agent ID to publish"}
            },
            "required": ["agent_id"]
        }
    }
]


async def list_agents_handler(
    db: AsyncSession,
    user_id: int,
    status: Optional[str] = None,
    agent_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> Dict[str, Any]:
    """List agents handler."""
    try:
        from packages.agent.services.agent_config_service import AgentConfigService
        svc = AgentConfigService(db)
        agents, total = await svc.list(
            user_id=user_id,
            status=status,
            agent_type=agent_type,
            skip=offset,
            limit=limit
        )
        return {
            "success": True,
            "data": [
                {
                    "id": a.id,
                    "name": a.name,
                    "description": a.description,
                    "agent_type": a.agent_type,
                    "status": a.status,
                    "is_public": a.is_public,
                    "created_at": str(a.created_at) if a.created_at else None,
                }
                for a in agents
            ],
            "total": total,
        }
    except Exception as e:
        logger.error("Failed to list agents: %s", e)
        return {"success": False, "error": str(e)}


async def list_public_agents_handler(
    db: AsyncSession,
    limit: int = 50,
    offset: int = 0
) -> Dict[str, Any]:
    """List public agents handler."""
    try:
        from packages.agent.services.agent_config_service import AgentConfigService
        svc = AgentConfigService(db)
        # Get public agents (is_public=True, status=published)
        agents, total = await svc.list(
            user_id=None,
            status="published",
            agent_type=None,
            skip=offset,
            limit=limit
        )
        # Filter to only public ones
        public_agents = [a for a in agents if a.is_public]
        return {
            "success": True,
            "data": [
                {
                    "id": a.id,
                    "name": a.name,
                    "description": a.description,
                    "agent_type": a.agent_type,
                    "author": a.owner,
                    "created_at": str(a.created_at) if a.created_at else None,
                }
                for a in public_agents
            ],
            "total": len(public_agents),
        }
    except Exception as e:
        logger.error("Failed to list public agents: %s", e)
        return {"success": False, "error": str(e)}


async def get_agent_handler(db: AsyncSession, agent_id: str) -> Dict[str, Any]:
    """Get agent handler."""
    try:
        from packages.agent.services.agent_config_service import AgentConfigService
        svc = AgentConfigService(db)
        agent = await svc.get_by_id(agent_id)
        if not agent:
            return {"success": False, "error": f"Agent not found: {agent_id}"}

        return {
            "success": True,
            "data": {
                "id": agent.id,
                "name": agent.name,
                "description": agent.description,
                "agent_type": agent.agent_type,
                "config": agent.config,
                "status": agent.status,
                "is_public": agent.is_public,
                "owner": agent.owner,
            }
        }
    except Exception as e:
        logger.error("Failed to get agent: %s", e)
        return {"success": False, "error": str(e)}


async def create_agent_handler(db: AsyncSession, user_id: int, **kwargs) -> Dict[str, Any]:
    """Create agent handler."""
    try:
        from packages.agent.services.agent_config_service import AgentConfigService
        from packages.agent.schemas.chat import AgentCreate

        # Extract fields for AgentCreate schema
        create_data = {}
        for field in ["name", "description", "agent_type", "config", "is_public"]:
            if field in kwargs:
                create_data[field] = kwargs[field]

        data = AgentCreate(**create_data)
        svc = AgentConfigService(db)
        agent = await svc.create(user_id=user_id, tenant_id="default", data=data)
        return {
            "success": True,
            "data": {"id": agent.id, "name": agent.name}
        }
    except Exception as e:
        logger.error("Failed to create agent: %s", e)
        return {"success": False, "error": str(e)}


async def update_agent_handler(db: AsyncSession, agent_id: str, user_id: int, **kwargs) -> Dict[str, Any]:
    """Update agent handler."""
    try:
        from packages.agent.services.agent_config_service import AgentConfigService
        from packages.agent.schemas.chat import AgentUpdate

        # Filter out agent_id from kwargs
        kwargs.pop("agent_id", None)
        data = AgentUpdate(**kwargs)
        svc = AgentConfigService(db)
        agent = await svc.update(agent_id=agent_id, user_id=user_id, data=data)
        return {
            "success": True,
            "data": {"id": agent.id, "updated_fields": list(kwargs.keys())}
        }
    except Exception as e:
        logger.error("Failed to update agent: %s", e)
        return {"success": False, "error": str(e)}


async def delete_agent_handler(db: AsyncSession, agent_id: str, user_id: int) -> Dict[str, Any]:
    """Delete agent handler."""
    try:
        from packages.agent.services.agent_config_service import AgentConfigService
        svc = AgentConfigService(db)
        result = await svc.delete(agent_id=agent_id, user_id=user_id)
        return {"success": result, "message": f"Agent {agent_id} deleted" if result else "Delete failed"}
    except Exception as e:
        logger.error("Failed to delete agent: %s", e)
        return {"success": False, "error": str(e)}


async def execute_agent_handler(
    db: AsyncSession,
    agent_id: str,
    user_id: int,
    query: str,
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    """Execute agent handler."""
    try:
        from packages.agent.services.agent_service import AgentService, AgentExecuteRequest, ExecutionMode
        from packages.model_gateway.services.model_gateway_service import ModelGatewayService
        from packages.agent.services.skill_registry import RegistryService as SkillRegistryService

        model_gateway = ModelGatewayService(db)
        skill_registry = SkillRegistryService(db)
        agent_service = AgentService(db, model_gateway, skill_registry)

        request = AgentExecuteRequest(
            query=query,
            user_id=user_id,
            tenant_id="default",
            agent_id=agent_id,
            session_id=session_id,
            execution_mode=ExecutionMode.SINGLE,
        )

        result = await agent_service.execute(request)

        return {
            "success": True,
            "data": result.to_dict()
        }
    except Exception as e:
        logger.error("Failed to execute agent: %s", e)
        return {"success": False, "error": str(e)}


async def publish_agent_handler(db: AsyncSession, agent_id: str, user_id: int) -> Dict[str, Any]:
    """Publish agent handler."""
    try:
        from packages.agent.services.agent_config_service import AgentConfigService
        svc = AgentConfigService(db)
        agent = await svc.publish(agent_id=agent_id, user_id=user_id)
        return {
            "success": True,
            "data": {"id": agent.id, "name": agent.name, "status": agent.status}
        }
    except Exception as e:
        logger.error("Failed to publish agent: %s", e)
        return {"success": False, "error": str(e)}


async def handle_agent_tool(
    name: str,
    arguments: Dict[str, Any],
    db: AsyncSession
) -> List[TextContent]:
    """Handle Agent tool calls.

    Args:
        name: Tool name
        arguments: Tool arguments
        db: Database session
    """
    import json

    # Default user ID for MCP context - in production should come from auth
    user_id = arguments.get("user_id", 1)

    try:
        if name == "list_agents":
            result = await list_agents_handler(
                db,
                user_id=user_id,
                status=arguments.get("status"),
                agent_type=arguments.get("agent_type"),
                limit=arguments.get("limit", 50),
                offset=arguments.get("offset", 0)
            )
        elif name == "list_public_agents":
            result = await list_public_agents_handler(
                db,
                limit=arguments.get("limit", 50),
                offset=arguments.get("offset", 0)
            )
        elif name == "get_agent":
            result = await get_agent_handler(db, arguments.get("agent_id"))
        elif name == "create_agent":
            result = await create_agent_handler(db, user_id=user_id, **arguments)
        elif name == "update_agent":
            agent_id = arguments.pop("agent_id")
            result = await update_agent_handler(db, agent_id, user_id=user_id, **arguments)
        elif name == "delete_agent":
            result = await delete_agent_handler(db, arguments.get("agent_id"), user_id=user_id)
        elif name == "execute_agent":
            result = await execute_agent_handler(
                db=db,
                agent_id=arguments.get("agent_id"),
                user_id=user_id,
                query=arguments.get("query"),
                session_id=arguments.get("session_id")
            )
        elif name == "publish_agent":
            result = await publish_agent_handler(db, arguments.get("agent_id"), user_id=user_id)
        else:
            raise ValueError(f"Unknown agent tool: {name}")

        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}, indent=2))]


def create_agent_tools():
    """Return Agent tools definitions."""
    return AGENT_TOOLS
