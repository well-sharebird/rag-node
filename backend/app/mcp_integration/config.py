"""MCP Server configuration."""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class McpServerConfig(BaseModel):
    """Configuration for MCP server."""
    name: str = Field(default="rag-platform", description="Server name")
    version: str = Field(default="1.0.0", description="Server version")
    description: str = Field(default="RAG Platform MCP Server", description="Server description")
    enabled: bool = Field(default=True, description="Whether this MCP server is enabled")
    transport: str = Field(default="stdio", description="Transport type: stdio, sse, http")


class McpConfig(BaseModel):
    """MCP configuration container."""
    server: McpServerConfig = Field(default_factory=McpServerConfig)
    tools_enabled: Dict[str, bool] = Field(default_factory=lambda: {
        "knowledge_base": True,
        "model_management": True,
        "prompt_engineering": True,
        "agent_hub": True,
    })

    # Milvus configuration for KB tools
    milvus_uri: str = Field(default="http://localhost:19530", description="Milvus server URI")

    # Default user ID for MCP context (in production should come from auth)
    default_user_id: int = Field(default=1, description="Default user ID")


def get_mcp_config() -> McpConfig:
    """Get MCP configuration from environment or config file."""
    # In production, load from extensions_config.json or environment
    return McpConfig()


# Default MCP configuration
DEFAULT_CONFIG = McpConfig()
