"""MCP (Model Context Protocol) Server for RAG Platform.

This module provides MCP tools for:
- Knowledge Base Management (6 tools)
- Model Management (7 tools)
- Prompt Engineering (8 tools)
- Agent Hub (8 tools)

Total: 29 MCP tools available for AI assistants.

Usage:
    from packages.agent.mcp import create_mcp_server, run_stdio_server

    # Create server
    server = create_mcp_server()

    # Run over stdio (for Claude Code integration)
    import asyncio
    asyncio.run(run_stdio_server())
"""

from .server import create_mcp_server, run_stdio_server

__all__ = [
    "create_mcp_server",
    "run_stdio_server",
]
