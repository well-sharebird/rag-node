"""
Confluence Connector - fetch pages from Atlassian Confluence
"""
import logging
import hashlib
from typing import Dict, Any, List, Optional, AsyncIterator, Tuple
import aiohttp
from datetime import datetime
from packages.rag.connectors.base import BaseConnector, Document, SyncResult

logger = logging.getLogger("app.connectors.confluence")


class ConfluenceConnector(BaseConnector):
    """Confluence connector for fetching wiki pages"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.base_url = config.get("base_url", "").rstrip("/")
        self.username = config.get("username", "")
        self.api_token = config.get("api_token", "")
        self.space_keys = config.get("space_keys", [])
        self.cql = config.get("cql", "")
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create authenticated session"""
        if self._session is None:
            self._session = aiohttp.ClientSession(
                auth=aiohttp.BasicAuth(self.username, self.api_token),
                headers={"Accept": "application/json"}
            )
        return self._session

    async def ingest(self) -> AsyncIterator[Document]:
        """
        Perform full sync of Confluence pages.
        Yields Document objects one by one.
        """
        session = await self._get_session()

        try:
            # Get pages from specified spaces or all spaces
            if self.space_keys:
                for space_key in self.space_keys:
                    async for page in self._fetch_space_pages(session, space_key):
                        yield page
            elif self.cql:
                async for page in self._fetch_cql_results(session, self.cql):
                    yield page
            else:
                # Fetch all spaces
                async for space in self._list_spaces(session):
                    async for page in self._fetch_space_pages(session, space["key"]):
                        yield page
        finally:
            if self._session:
                await self._session.close()
                self._session = None

    async def poll(self, watermark: Optional[Any] = None) -> Tuple[List[Document], Optional[Any]]:
        """
        Poll for new/updated Confluence pages since last sync.
        Uses CQL to find recently modified pages.
        """
        session = await self._get_session()
        docs = []

        # Build CQL query for pages modified since watermark
        if watermark:
            cql = f"lastModified >= '{watermark}'"
            if self.space_keys:
                space_filter = " OR ".join([f"space = '{k}'" for k in self.space_keys])
                cql = f"({space_filter}) AND {cql}"
        else:
            # No watermark = full sync
            async for doc in self.ingest():
                docs.append(doc)
            return docs, datetime.utcnow().isoformat()

        # Fetch recently modified pages
        async for page in self._fetch_cql_results(session, cql):
            docs.append(page)

        new_watermark = datetime.utcnow().isoformat()
        return docs, new_watermark

    async def test_connection(self) -> Tuple[bool, str]:
        """Test Confluence connection"""
        try:
            session = await self._get_session()
            url = f"{self.base_url}/rest/api/space"
            async with session.get(url) as resp:
                if resp.status == 200:
                    return True, "Connected to Confluence"
                return False, f"HTTP {resp.status}: {resp.reason}"
        except Exception as e:
            return False, str(e)

    async def _list_spaces(self, session: aiohttp.ClientSession) -> AsyncIterator[Dict]:
        """List all spaces"""
        url = f"{self.base_url}/rest/api/space"
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                for space in data.get("results", []):
                    yield space

    async def _fetch_space_pages(
        self,
        session: aiohttp.ClientSession,
        space_key: str
    ) -> AsyncIterator[Document]:
        """Fetch all pages from a space"""
        start = 0
        limit = 25

        while True:
            url = f"{self.base_url}/rest/api/space/{space_key}/content"
            params = {
                "type": "page",
                "expand": "body.storage,version,ancestors,labels",
                "start": start,
                "limit": limit
            }
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.error(f"Failed to fetch pages from {space_key}: {resp.status}")
                    break

                data = await resp.json()
                results = data.get("results", [])

                if not results:
                    break

                for page in results:
                    yield self._format_page(page, space_key)

                start += limit
                if start >= data.get("size", 0):
                    break

    async def _fetch_cql_results(
        self,
        session: aiohttp.ClientSession,
        cql: str
    ) -> AsyncIterator[Document]:
        """Fetch pages using CQL query"""
        start = 0
        limit = 25

        while True:
            url = f"{self.base_url}/rest/api/search"
            params = {
                "cql": cql,
                "expand": "content.body.storage,content.version,content.ancestors",
                "start": start,
                "limit": limit
            }
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    break

                data = await resp.json()
                results = data.get("results", [])

                if not results:
                    break

                for result in results:
                    content = result.get("content", {})
                    if content.get("type") == "page":
                        space_key = content.get("_expandable", {}).get("space", "").split("/")[-1]
                        yield self._format_page(content, space_key)

                start += limit
                if start >= data.get("size", 0):
                    break

    def _format_page(self, page: Dict[str, Any], space_key: str) -> Document:
        """Format Confluence page to Document format"""
        body = page.get("body", {}).get("storage", {}).get("value", "")
        content_hash = hashlib.sha256(body.encode()).hexdigest()

        return Document(
            external_id=str(page.get("id")),
            title=page.get("title", ""),
            content=body,
            url=f"{self.base_url}/pages/{page.get('id')}",
            metadata={
                "source_type": "confluence",
                "space_key": space_key,
                "version": page.get("version", {}).get("number", 0),
                "created_at": page.get("version", {}).get("when", ""),
                "author": page.get("version", {}).get("by", {}).get("displayName", ""),
                "labels": [l.get("name") for l in page.get("labels", {}).get("results", [])],
            },
            content_hash=content_hash,
        )

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup session"""
        if self._session:
            await self._session.close()
            self._session = None
        return await super().__aexit__(exc_type, exc_val, exc_tb)
