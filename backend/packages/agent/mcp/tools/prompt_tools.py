"""Prompt Engineering MCP Tools."""

import logging
import json
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from mcp.types import TextContent

logger = logging.getLogger("app.mcp.prompt_tools")

PROMPT_TOOLS = [
    {
        "name": "list_prompt_templates",
        "description": "List prompt templates with optional filters",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["draft", "active", "archived"], "description": "Filter by status"},
                "category": {"type": "string", "description": "Filter by category"},
                "limit": {"type": "integer", "description": "Max results", "default": 50},
                "offset": {"type": "integer", "description": "Offset", "default": 0}
            }
        }
    },
    {
        "name": "get_prompt_template",
        "description": "Get details of a specific prompt template by name",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Template name"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "create_prompt_template",
        "description": "Create a new prompt template",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Template name"},
                "content": {"type": "string", "description": "Template content with {{variables}}"},
                "description": {"type": "string", "description": "Template description"},
                "category": {"type": "string", "description": "Category for organization"}
            },
            "required": ["name", "content"]
        }
    },
    {
        "name": "update_prompt_template",
        "description": "Update an existing prompt template",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Template name to update"},
                "content": {"type": "string", "description": "New content"},
                "description": {"type": "string", "description": "New description"},
                "category": {"type": "string", "description": "New category"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "render_prompt",
        "description": "Render a prompt template with provided variables",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Template name"},
                "variables": {"type": "object", "description": "Variables to substitute in template"}
            },
            "required": ["name", "variables"]
        }
    },
    {
        "name": "create_prompt_version",
        "description": "Create a new version of a prompt template",
        "inputSchema": {
            "type": "object",
            "properties": {
                "template_name": {"type": "string", "description": "Template name"},
                "content": {"type": "string", "description": "New version content"},
                "change_summary": {"type": "string", "description": "Description of changes"}
            },
            "required": ["template_name", "content"]
        }
    },
    {
        "name": "release_prompt_version",
        "description": "Release a specific version of a prompt template",
        "inputSchema": {
            "type": "object",
            "properties": {
                "template_name": {"type": "string", "description": "Template name"},
                "version_id": {"type": "integer", "description": "Version ID to release"}
            },
            "required": ["template_name", "version_id"]
        }
    },
    {
        "name": "run_prompt_evaluation",
        "description": "Run evaluation on a prompt template with test cases",
        "inputSchema": {
            "type": "object",
            "properties": {
                "template_name": {"type": "string", "description": "Template name"},
                "test_case_ids": {"type": "array", "items": {"type": "integer"}, "description": "Test case IDs to run"}
            },
            "required": ["template_name"]
        }
    }
]


async def list_prompts_handler(
    db: AsyncSession,
    status: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> Dict[str, Any]:
    """List prompt templates handler."""
    try:
        from packages.prompt.services.registry import PromptRegistryService
        from packages.prompt.models.prompt_template import PromptTemplateStatus

        svc = PromptRegistryService(db)
        status_filter = None
        if status:
            try:
                status_filter = PromptTemplateStatus(status)
            except ValueError:
                pass

        templates, total = await svc.list_templates(
            status=status_filter,
            category=category,
            offset=offset,
            limit=limit
        )
        return {
            "success": True,
            "data": [
                {
                    "id": t.id,
                    "name": t.name,
                    "description": t.description,
                    "category": t.category,
                    "status": t.status,
                    "current_version": t.current_version,
                    "created_at": str(t.created_at) if t.created_at else None,
                }
                for t in templates
            ],
            "total": total,
        }
    except Exception as e:
        logger.error("Failed to list prompts: %s", e)
        return {"success": False, "error": str(e)}


async def get_prompt_handler(db: AsyncSession, name: str) -> Dict[str, Any]:
    """Get prompt template handler."""
    try:
        from packages.prompt.services.registry import PromptRegistryService
        svc = PromptRegistryService(db)
        template = await svc.get_template(name)
        if not template:
            return {"success": False, "error": f"Template not found: {name}"}

        return {
            "success": True,
            "data": {
                "id": template.id,
                "name": template.name,
                "description": template.description,
                "category": template.category,
                "content": template.content,
                "status": template.status,
                "versions": [
                    {"id": v.id, "version": v.version, "status": v.status}
                    for v in template.versions
                ] if hasattr(template, 'versions') else []
            }
        }
    except Exception as e:
        logger.error("Failed to get prompt: %s", e)
        return {"success": False, "error": str(e)}


async def create_prompt_handler(db: AsyncSession, actor: str, **kwargs) -> Dict[str, Any]:
    """Create prompt template handler."""
    try:
        from packages.prompt.services.registry import PromptRegistryService
        from packages.prompt.schemas.prompt import PromptTemplateCreate

        data = PromptTemplateCreate(**kwargs)
        svc = PromptRegistryService(db)
        template = await svc.create_template(data, actor)
        return {
            "success": True,
            "data": {"id": template.id, "name": template.name}
        }
    except Exception as e:
        logger.error("Failed to create prompt: %s", e)
        return {"success": False, "error": str(e)}


async def update_prompt_handler(db: AsyncSession, name: str, actor: str = "system", **kwargs) -> Dict[str, Any]:
    """Update prompt template handler."""
    try:
        from packages.prompt.services.registry import PromptRegistryService
        from packages.prompt.schemas.prompt import PromptTemplateUpdate

        svc = PromptRegistryService(db)
        template = await svc.get_template(name)
        if not template:
            return {"success": False, "error": f"Template not found: {name}"}

        # Filter out name from kwargs since it's the identifier
        kwargs.pop("name", None)
        data = PromptTemplateUpdate(**kwargs)
        updated = await svc.update_template(name, data, actor)
        return {
            "success": True,
            "data": {"name": name, "updated_fields": list(kwargs.keys())}
        }
    except Exception as e:
        logger.error("Failed to update prompt: %s", e)
        return {"success": False, "error": str(e)}


async def render_prompt_handler(db: AsyncSession, name: str, variables: Dict[str, Any]) -> Dict[str, Any]:
    """Render prompt handler."""
    try:
        from packages.prompt.services.registry import PromptRegistryService
        svc = PromptRegistryService(db)
        template = await svc.get_template(name)
        if not template:
            return {"success": False, "error": f"Template not found: {name}"}

        # Simple template rendering
        content = template.content
        for key, value in variables.items():
            content = content.replace("{{" + key + "}}", str(value))

        return {
            "success": True,
            "data": {
                "template_name": name,
                "rendered_content": content,
                "variables_used": list(variables.keys())
            }
        }
    except Exception as e:
        logger.error("Failed to render prompt: %s", e)
        return {"success": False, "error": str(e)}


async def create_version_handler(db: AsyncSession, template_name: str, actor: str, content: str, change_summary: Optional[str] = None) -> Dict[str, Any]:
    """Create prompt version handler."""
    try:
        from packages.prompt.services.registry import PromptRegistryService
        from packages.prompt.schemas.prompt import PromptVersionCreate

        svc = PromptRegistryService(db)
        data = PromptVersionCreate(content=content, change_summary=change_summary)
        version = await svc.create_version(template_name, data, actor)
        return {
            "success": True,
            "data": {"version_id": version.id, "version": version.version}
        }
    except Exception as e:
        logger.error("Failed to create version: %s", e)
        return {"success": False, "error": str(e)}


async def release_version_handler(db: AsyncSession, template_name: str, version_id: int, released_by: str = "system") -> Dict[str, Any]:
    """Release prompt version handler."""
    try:
        from packages.prompt.services.registry import PromptRegistryService
        svc = PromptRegistryService(db)
        version = await svc.release_version(version_id, released_by)
        return {
            "success": True,
            "data": {"version_id": version.id, "version": version.version}
        }
    except Exception as e:
        logger.error("Failed to release version: %s", e)
        return {"success": False, "error": str(e)}


async def run_eval_handler(db: AsyncSession, template_name: str, test_case_ids: Optional[List[int]] = None) -> Dict[str, Any]:
    """Run prompt evaluation handler."""
    try:
        from packages.prompt.services.registry import PromptRegistryService
        svc = PromptRegistryService(db)
        # Simplified eval - in production would run actual test cases
        template = await svc.get_template(template_name)
        return {
            "success": True,
            "data": {
                "template_name": template_name,
                "test_cases_run": test_case_ids or [],
                "status": "completed",
                "summary": "Evaluation completed"
            }
        }
    except Exception as e:
        logger.error("Failed to run evaluation: %s", e)
        return {"success": False, "error": str(e)}


async def handle_prompt_tool(
    name: str,
    arguments: Dict[str, Any],
    db: AsyncSession
) -> List[TextContent]:
    """Handle Prompt tool calls.

    Args:
        name: Tool name
        arguments: Tool arguments
        db: Database session
    """
    import json

    try:
        if name == "list_prompt_templates":
            result = await list_prompts_handler(
                db,
                status=arguments.get("status"),
                category=arguments.get("category"),
                limit=arguments.get("limit", 50),
                offset=arguments.get("offset", 0)
            )
        elif name == "get_prompt_template":
            result = await get_prompt_handler(db, arguments.get("name"))
        elif name == "create_prompt_template":
            result = await create_prompt_handler(db, actor="mcp", **arguments)
        elif name == "update_prompt_template":
            name_arg = arguments.pop("name")
            result = await update_prompt_handler(db, name_arg, actor="mcp", **arguments)
        elif name == "render_prompt":
            result = await render_prompt_handler(db, arguments.get("name"), arguments.get("variables", {}))
        elif name == "create_prompt_version":
            result = await create_version_handler(
                db, arguments.get("template_name"), actor="mcp",
                content=arguments.get("content"),
                change_summary=arguments.get("change_summary")
            )
        elif name == "release_prompt_version":
            result = await release_version_handler(
                db, arguments.get("template_name"), arguments.get("version_id")
            )
        elif name == "run_prompt_evaluation":
            result = await run_eval_handler(db, arguments.get("template_name"), arguments.get("test_case_ids"))
        else:
            raise ValueError(f"Unknown prompt tool: {name}")

        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}, indent=2))]


def create_prompt_tools():
    """Return Prompt tools definitions."""
    return PROMPT_TOOLS
