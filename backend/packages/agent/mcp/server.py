"""MCP Server implementation for RAG Platform.

This module provides the main MCP server that integrates all tool groups:
- Knowledge Base Management
- Model Management
- Prompt Engineering
- Agent Hub
"""

import logging
import json
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
from mcp.types import (
    Tool,
    TextContent,
    ListToolsResult,
    CallToolRequestParams,
    CallToolResult,
)
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.database import get_db, async_session_factory
from packages.agent.mcp.tools.kb_tools import KB_TOOLS, handle_kb_tool
from packages.agent.mcp.tools.model_tools import MODEL_TOOLS, handle_model_tool
from packages.agent.mcp.tools.prompt_tools import PROMPT_TOOLS, handle_prompt_tool
from packages.agent.mcp.tools.agent_tools import AGENT_TOOLS, handle_agent_tool

logger = logging.getLogger("app.mcp.server")


@asynccontextmanager
async def get_db_session():
    """Get database session context manager."""
    async for db in get_db():
        yield db


def create_mcp_server(
    name: str = "rag-platform",
    version: str = "1.0.0",
    description: str = "RAG Platform MCP Server - 提供知识库管理、模型管理、提示词工程、智能体广场等工具",
) -> Server:
    """Create an MCP server instance with all RAG platform tools.

    Args:
        name: Server name for MCP discovery
        version: Server version
        description: Server description

    Returns:
        Configured MCP Server instance with all tools registered
    """
    # Collect all tools from all tool groups
    all_tools: List[Tool] = [
        Tool(**tool_def)
        for tool_def in KB_TOOLS + MODEL_TOOLS + PROMPT_TOOLS + AGENT_TOOLS
    ]
    logger.info("MCP Server created: %s v%s with %d tools", name, version, len(all_tools))

    # Build tool name sets for routing
    kb_tool_names = {t["name"] for t in KB_TOOLS}
    model_tool_names = {t["name"] for t in MODEL_TOOLS}
    prompt_tool_names = {t["name"] for t in PROMPT_TOOLS}
    agent_tool_names = {t["name"] for t in AGENT_TOOLS}

    async def list_tools_handler(
        context: ServerRequestContext,
        params: Optional[Any] = None
    ) -> ListToolsResult:
        """Return all available tools."""
        return ListToolsResult(tools=all_tools)

    async def call_tool_handler(
        context: ServerRequestContext,
        params: CallToolRequestParams
    ) -> CallToolResult:
        """Route tool calls to appropriate handler."""
        name = params.name
        arguments = params.arguments or {}

        try:
            async with get_db_session() as db:
                if name in kb_tool_names:
                    result = await handle_kb_tool(name, arguments, db)
                    return CallToolResult(content=result)
                elif name in model_tool_names:
                    result = await handle_model_tool(name, arguments, db)
                    return CallToolResult(content=result)
                elif name in prompt_tool_names:
                    result = await handle_prompt_tool(name, arguments, db)
                    return CallToolResult(content=result)
                elif name in agent_tool_names:
                    result = await handle_agent_tool(name, arguments, db)
                    return CallToolResult(content=result)
                else:
                    raise ValueError(f"Unknown tool: {name}")
        except Exception as e:
            logger.error("Tool execution error for %s: %s", name, e)
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}, indent=2))]
            )

    server = Server(
        name=name,
        version=version,
        description=description,
        on_list_tools=list_tools_handler,
        on_call_tool=call_tool_handler,
    )

    return server


async def run_stdio_server(server: Optional[Server] = None) -> None:
    """Run the MCP server over stdio transport.

    This is the main entry point for running the MCP server
    with Claude Code or other MCP clients via stdio.

    Args:
        server: Optional pre-configured server. If None, creates default server.
    """
    if server is None:
        server = create_mcp_server()

    from mcp.server.stdio import stdio_server
    async with stdio_server() as (read_stream, write_stream):
        logger.info("Starting MCP server over stdio")
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


# Main entry point for running as stdio MCP server
if __name__ == "__main__":
    import asyncio
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    asyncio.run(run_stdio_server())
