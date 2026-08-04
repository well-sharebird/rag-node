"""
Connector Factory - creates connector instances based on data source type
"""
import logging
from typing import Optional

from packages.rag.connectors.base import BaseConnector
from packages.rag.connectors.web_connector import WebConnector
from packages.rag.connectors.database_connector import DatabaseConnector
from packages.rag.connectors.api_connector import APIConnector
from packages.rag.connectors.confluence_connector import ConfluenceConnector
from packages.rag.connectors.notion_connector import NotionConnector
from packages.rag.connectors.git_connector import GitConnector

logger = logging.getLogger("app.connectors.factory")

CONNECTOR_REGISTRY: dict[str, type[BaseConnector]] = {
    "web_page": WebConnector,
    "database": DatabaseConnector,
    "api": APIConnector,
    "mysql": DatabaseConnector,
    "postgresql": DatabaseConnector,
    "confluence": ConfluenceConnector,
    "notion": NotionConnector,
    "git_repo": GitConnector,
    "github": GitConnector,
    "gitlab": GitConnector,
}


def register_connector(source_type: str, connector_cls: type[BaseConnector]):
    """Register a new connector type"""
    CONNECTOR_REGISTRY[source_type] = connector_cls
    logger.info("Registered connector: %s -> %s", source_type, connector_cls.__name__)


def create_connector(source_type: str, config: dict) -> Optional[BaseConnector]:
    """
    Create a connector instance based on source type and configuration.

    Args:
        source_type: The type of data source (e.g., 'web_page', 'database', 'api')
        config: Configuration dictionary from data source's config_json

    Returns:
        A connector instance, or None if the source type is not supported
    """
    # Normalize source type
    source_type = source_type.lower().replace("-", "_")

    # Handle database subtypes
    if source_type in ("mysql", "postgresql"):
        source_type = "database"
        config = {**config, "db_type": source_type}

    connector_cls = CONNECTOR_REGISTRY.get(source_type)
    if connector_cls is None:
        logger.warning("No connector registered for source type: %s", source_type)
        return None

    return connector_cls(config)
