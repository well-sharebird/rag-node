"""
Base Connector SDK - Abstract base class for all data source connectors
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any, AsyncIterator


@dataclass
class Document:
    """Unified document model for all connectors"""
    external_id: str
    title: str
    content: Optional[str] = None
    url: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    content_hash: Optional[str] = None  # For deduplication


@dataclass
class SyncResult:
    """Result of a sync operation"""
    items_synced: int = 0
    items_failed: int = 0
    errors: list[str] = field(default_factory=list)
    watermark: Optional[Any] = None  # For incremental sync


class BaseConnector(ABC):
    """
    Abstract base class for all data source connectors.

    Each connector should:
    1. Implement `ingest()` for full sync
    2. Implement `poll()` for incremental sync
    3. Implement `test_connection()` to verify connectivity
    """

    def __init__(self, config: dict):
        self.config = config
        self._last_watermark: Optional[Any] = None

    @abstractmethod
    async def ingest(self) -> AsyncIterator[Document]:
        """
        Perform full ingestion of all documents.
        Yields documents one by one for streaming processing.
        """
        pass

    @abstractmethod
    async def poll(self, watermark: Optional[Any] = None) -> tuple[list[Document], Optional[Any]]:
        """
        Poll for new/updated documents since last sync.

        Args:
            watermark: The last sync watermark (e.g., timestamp, ID, hash)

        Returns:
            Tuple of (new documents, new watermark)
        """
        pass

    @abstractmethod
    async def test_connection(self) -> tuple[bool, str]:
        """
        Test connection to the data source.

        Returns:
            Tuple of (success, message)
        """
        pass

    def get_schema(self) -> dict:
        """Return the configuration schema for this connector"""
        return {}

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - cleanup resources"""
        pass
