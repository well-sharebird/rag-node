"""
Database connector for syncing data from relational databases (MySQL, PostgreSQL)
"""
import logging
import hashlib
from datetime import datetime
from typing import Optional, Any

from app.connectors.base import BaseConnector, Document

logger = logging.getLogger("app.connectors.database")


class DatabaseConnector(BaseConnector):
    """Connector for relational database tables"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.db_type: str = config.get("db_type", "postgresql")
        self.host: str = config.get("host", "localhost")
        self.port: int = config.get("port", 5432)
        self.database: str = config.get("database", "")
        self.username: str = config.get("username", "")
        self.password: str = config.get("password", "")
        self.table_name: str = config.get("table_name", "")
        self.query: Optional[str] = config.get("query")
        self.primary_key: str = config.get("primary_key", "id")
        self.updated_at_column: Optional[str] = config.get("updated_at_column")
        self.text_columns: list[str] = config.get("text_columns", [])
        self.title_column: Optional[str] = config.get("title_column")

        self._pool = None

    async def _get_pool(self):
        """Get or create async database connection pool"""
        if self._pool is None:
            import asyncpg
            self._pool = await asyncpg.create_pool(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.username,
                password=self.password,
                min_size=1,
                max_size=5,
            )
        return self._pool

    async def ingest(self):
        """Read all rows from the table and yield Document objects"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if self.query:
                sql = self.query
            else:
                columns = "*"
                sql = f"SELECT {columns} FROM {self.table_name}"

            records = await conn.fetch(sql)
            for row in records:
                doc = self._row_to_document(dict(row))
                yield doc
        return
        yield  # Make this an async generator

    async def _row_to_document(self, row: dict) -> Document:
        """Convert a database row to a Document"""
        external_id = str(row.get(self.primary_key, hash(str(row))))

        # Determine title
        if self.title_column and self.title_column in row:
            title = str(row[self.title_column])
        else:
            title = f"{self.table_name}#{external_id}"

        # Determine text content
        if self.text_columns:
            # Build content from specified text columns
            parts = []
            for col in self.text_columns:
                if col in row and row[col] is not None:
                    parts.append(f"### {col}\n{row[col]}")
            content = "\n\n".join(parts)
        else:
            # Use all non-id, non-metadata columns as content
            parts = []
            for key, value in row.items():
                if key != self.primary_key and key != self.updated_at_column:
                    parts.append(f"### {key}\n{value}")
            content = "\n\n".join(parts)

        content_hash = hashlib.sha256(content.encode()).hexdigest()

        return Document(
            external_id=external_id,
            title=title,
            content=content,
            metadata={
                "source_type": "database",
                "db_type": self.db_type,
                "table": self.table_name,
                "primary_key": external_id,
                "row_data": {
                    k: str(v) for k, v in row.items()
                    if k != self.password
                },
            },
            content_hash=content_hash,
        )

    async def poll(self, watermark: Optional[Any] = None) -> tuple[list[Document], Optional[Any]]:
        """Poll for new/updated rows since last watermark"""
        pool = await self._get_pool()
        new_watermark = datetime.utcnow().isoformat()
        docs: list[Document] = []

        async with pool.acquire() as conn:
            if self.updated_at_column and watermark:
                sql = (
                    f"SELECT * FROM {self.table_name} "
                    f"WHERE {self.updated_at_column} > $1 "
                    f"ORDER BY {self.updated_at_column} ASC"
                )
                records = await conn.fetch(sql, watermark)
            elif watermark:
                sql = (
                    f"SELECT * FROM {self.table_name} "
                    f"WHERE {self.primary_key} > $1 "
                    f"ORDER BY {self.primary_key} ASC"
                )
                records = await conn.fetch(sql, watermark)
            else:
                # No watermark = full sync
                async for doc in self.ingest():
                    docs.append(doc)
                return docs, new_watermark

            for row in records:
                docs.append(self._row_to_document(dict(row)))

            if records:
                new_watermark = records[-1].get(
                    self.updated_at_column, records[-1].get(self.primary_key)
                )

        return docs, new_watermark

    async def test_connection(self) -> tuple[bool, str]:
        """Test database connection"""
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True, f"Connected to {self.db_type}://{self.host}:{self.port}/{self.database}"
        except Exception as e:
            return False, str(e)

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._pool:
            await self._pool.close()
            self._pool = None
