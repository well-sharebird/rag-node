"""
REST API connector for syncing data from external APIs
"""
import logging
import hashlib
from datetime import datetime
from typing import Optional, Any

import httpx

from packages.rag.connectors.base import BaseConnector, Document

logger = logging.getLogger("app.connectors.api")


class APIConnector(BaseConnector):
    """Connector for REST API endpoints"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.base_url: str = config.get("base_url", "")
        self.endpoint: str = config.get("endpoint", "")
        self.method: str = config.get("method", "GET")
        self.headers: dict = config.get("headers", {})
        self.auth_type: str = config.get("auth_type", "none")
        self.auth_token: Optional[str] = config.get("auth_token")
        self.auth_header: str = config.get("auth_header", "Authorization")
        self.data_path: str = config.get("data_path", "data")
        self.pagination_type: str = config.get("pagination_type", "offset")
        self.pagination_field: str = config.get("pagination_field", "page")
        self.limit_field: str = config.get("limit_field", "limit")
        self.limit_value: int = config.get("limit_value", 100)
        self.title_field: str = config.get("title_field", "title")
        self.content_fields: list[str] = config.get("content_fields", [])

        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {**self.headers}
            if self.auth_type == "bearer" and self.auth_token:
                headers[self.auth_header] = f"Bearer {self.auth_token}"
            elif self.auth_type == "api_key" and self.auth_token:
                headers[self.auth_header] = self.auth_token

            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0),
                headers=headers,
            )
        return self._client

    def _extract_data(self, response_data: dict) -> list[dict]:
        """Extract data array from nested JSON using data_path"""
        if not self.data_path or self.data_path == "data":
            if isinstance(response_data, list):
                return response_data
            return response_data.get("data", response_data.get("items", response_data.get("results", [])))
        # Navigate nested path like "result.data.items"
        parts = self.data_path.split(".")
        current = response_data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part, [])
            elif isinstance(current, list):
                # Try to index into list
                try:
                    idx = int(part)
                    current = current[idx]
                except (ValueError, IndexError):
                    return []
            else:
                return []
        return current if isinstance(current, list) else [current]

    async def ingest(self):
        """Fetch all pages from the API and yield Document objects"""
        page = 0
        next_token = None

        while True:
            response = await self._fetch_page(page, next_token)
            if response is None:
                break

            items = self._extract_data(response)
            if not items:
                break

            for item in items:
                yield self._item_to_document(item)

            # Pagination
            if self.pagination_type == "link":
                # Check for next link in response
                links = response.get("links", response.get("_links", {}))
                next_url = links.get("next") if isinstance(links, dict) else response.get("next")
                if not next_url:
                    break
                next_token = next_url
            elif self.pagination_type == "cursor":
                cursor = response.get("cursor", response.get("next_cursor"))
                if not cursor:
                    break
                next_token = cursor
            else:
                # Offset pagination
                total = response.get("total", response.get("count", 0))
                if total > 0 and (page + 1) * self.limit_value >= total:
                    break
                page += 1

        return
        yield  # Make this an async generator

    async def _fetch_page(self, page: int = 0, cursor: Optional[str] = None) -> Optional[dict]:
        """Fetch a single page of results"""
        client = await self._get_client()
        url = f"{self.base_url.rstrip('/')}{self.endpoint}"

        params = {}
        if self.pagination_type == "offset":
            params[self.pagination_field] = page + 1  # 1-indexed
            params[self.limit_field] = self.limit_value
        elif self.pagination_type == "cursor" and cursor:
            params[self.pagination_field] = cursor

        try:
            if self.method.upper() == "GET":
                resp = await client.get(url, params=params)
            elif self.method.upper() == "POST":
                resp = await client.post(url, json=params)
            else:
                resp = await client.request(self.method.upper(), url, json=params)

            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.warning("API request failed for %s: %s", url, e)
            return None

    def _item_to_document(self, item: dict) -> Document:
        """Convert an API response item to a Document"""
        title = str(item.get(self.title_field, item.get("title", item.get("name", item.get("id", "")))))
        external_id = str(item.get("id", str(hash(str(item)))))

        # Build content
        if self.content_fields:
            parts = []
            for field in self.content_fields:
                if field in item and item[field] is not None:
                    parts.append(f"### {field}\n{item[field]}")
            content = "\n\n".join(parts)
        else:
            # Use all non-id fields
            parts = []
            for key, value in item.items():
                if key not in ("id", self.title_field) and not key.startswith("_"):
                    parts.append(f"### {key}\n{value}")
            content = "\n\n".join(parts)

        content_hash = hashlib.sha256(content.encode()).hexdigest()

        return Document(
            external_id=external_id,
            title=title,
            content=content,
            metadata={
                "source_type": "api",
                "base_url": self.base_url,
                "endpoint": self.endpoint,
                "item_data": {k: str(v) for k, v in item.items() if not isinstance(v, (dict, list))},
            },
            content_hash=content_hash,
        )

    async def poll(self, watermark: Optional[Any] = None) -> tuple[list[Document], Optional[Any]]:
        """Poll for new items (full re-sync for stateless APIs)"""
        docs = []
        async for doc in self.ingest():
            docs.append(doc)
        new_watermark = datetime.utcnow().isoformat()
        return docs, new_watermark

    async def test_connection(self) -> tuple[bool, str]:
        """Test API connection"""
        try:
            client = await self._get_client()
            url = f"{self.base_url.rstrip('/')}{self.endpoint}"
            resp = await client.head(url)
            if resp.status_code < 500:
                return True, f"API accessible (HTTP {resp.status_code})"
            return False, f"HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()
            self._client = None
