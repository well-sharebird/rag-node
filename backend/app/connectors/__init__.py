from app.connectors.base import BaseConnector, Document, SyncResult
from app.connectors.factory import create_connector, register_connector, CONNECTOR_REGISTRY
from app.connectors.web_connector import WebConnector
from app.connectors.database_connector import DatabaseConnector
from app.connectors.api_connector import APIConnector

__all__ = [
    "BaseConnector",
    "Document",
    "SyncResult",
    "create_connector",
    "register_connector",
    "CONNECTOR_REGISTRY",
    "WebConnector",
    "DatabaseConnector",
    "APIConnector",
]
