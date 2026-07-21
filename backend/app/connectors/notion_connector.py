"""
Notion Connector - fetch pages from Notion workspace
"""
import logging
import hashlib
from typing import Dict, Any, List, Optional, AsyncIterator, Tuple
import aiohttp
from datetime import datetime
from app.connectors.base import BaseConnector, Document, SyncResult

logger = logging.getLogger("app.connectors.notion")


class NotionConnector(BaseConnector):
    """Notion connector for fetching workspace pages"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("api_token", "")
        self.database_ids = config.get("database_ids", [])
        self.page_ids = config.get("page_ids", [])
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create authenticated session"""
        if self._session is None:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json"
            }
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def ingest(self) -> AsyncIterator[Document]:
        """
        Perform full sync of Notion pages.
        Yields Document objects one by one.
        """
        session = await self._get_session()

        try:
            # Fetch from databases
            for db_id in self.database_ids:
                async for page in self._fetch_database_pages(session, db_id):
                    yield page

            # Fetch specific pages
            for page_id in self.page_ids:
                page = await self._fetch_page(session, page_id)
                if page:
                    yield page

            # If no specific IDs, search all pages
            if not self.database_ids and not self.page_ids:
                async for page in self._search_pages(session):
                    yield page
        finally:
            if self._session:
                await self._session.close()
                self._session = None

    async def poll(self, watermark: Optional[Any] = None) -> Tuple[List[Document], Optional[Any]]:
        """
        Poll for new/updated Notion pages since last sync.
        Notion API doesn't support incremental queries, so we re-fetch all and compare hashes.
        """
        docs = []
        async for doc in self.ingest():
            docs.append(doc)

        new_watermark = datetime.utcnow().isoformat()
        return docs, new_watermark

    async def test_connection(self) -> Tuple[bool, str]:
        """Test Notion API connection"""
        try:
            session = await self._get_session()
            url = "https://api.notion.com/v1/users/me"
            async with session.get(url) as resp:
                if resp.status == 200:
                    return True, "Connected to Notion"
                return False, f"HTTP {resp.status}: {resp.reason}"
        except Exception as e:
            return False, str(e)

    async def _fetch_database_pages(
        self,
        session: aiohttp.ClientSession,
        database_id: str
    ) -> AsyncIterator[Document]:
        """Fetch all pages from a database"""
        has_more = True
        start_cursor = None

        while has_more:
            body = {"page_size": 100}
            if start_cursor:
                body["start_cursor"] = start_cursor

            url = f"https://api.notion.com/v1/databases/{database_id}/query"
            async with session.post(url, json=body) as resp:
                if resp.status != 200:
                    logger.error(f"Failed to query database {database_id}")
                    break

                data = await resp.json()
                results = data.get("results", [])

                for page in results:
                    content = await self._get_page_content(session, page["id"])
                    yield self._format_page(page, content)

                has_more = data.get("has_more", False)
                start_cursor = data.get("next_cursor")

    async def _fetch_page(
        self,
        session: aiohttp.ClientSession,
        page_id: str
    ) -> Optional[Document]:
        """Fetch a specific page"""
        url = f"https://api.notion.com/v1/pages/{page_id}"
        async with session.get(url) as resp:
            if resp.status == 200:
                page = await resp.json()
                content = await self._get_page_content(session, page_id)
                return self._format_page(page, content)
        return None

    async def _search_pages(
        self,
        session: aiohttp.ClientSession
    ) -> AsyncIterator[Document]:
        """Search all accessible pages"""
        has_more = True
        start_cursor = None

        while has_more:
            body = {
                "filter": {"property": "object", "value": "page"},
                "page_size": 100
            }
            if start_cursor:
                body["start_cursor"] = start_cursor

            url = "https://api.notion.com/v1/search"
            async with session.post(url, json=body) as resp:
                if resp.status != 200:
                    break

                data = await resp.json()
                results = data.get("results", [])

                for page in results:
                    content = await self._get_page_content(session, page["id"])
                    yield self._format_page(page, content)

                has_more = data.get("has_more", False)
                start_cursor = data.get("next_cursor")

    async def _get_page_content(
        self,
        session: aiohttp.ClientSession,
        page_id: str
    ) -> str:
        """Get page content blocks"""
        content_parts = []
        has_more = True
        start_cursor = None

        while has_more:
            url = f"https://api.notion.com/v1/blocks/{page_id}/children"
            params = {"page_size": 100}
            if start_cursor:
                params["start_cursor"] = start_cursor

            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    break

                data = await resp.json()
                blocks = data.get("results", [])

                for block in blocks:
                    text = self._extract_block_text(block)
                    if text:
                        content_parts.append(text)

                has_more = data.get("has_more", False)
                start_cursor = data.get("next_cursor")

        return "\n\n".join(content_parts)

    def _extract_block_text(self, block: Dict[str, Any]) -> str:
        """Extract text from a block"""
        block_type = block.get("type")
        if block_type in ("paragraph", "heading_1", "heading_2", "heading_3", "quote", "callout"):
            rich_text = block.get(block_type, {}).get("rich_text", [])
            return "".join(rt.get("plain_text", "") for rt in rich_text)
        elif block_type == "bulleted_list_item" or block_type == "numbered_list_item":
            rich_text = block.get(block_type, {}).get("rich_text", [])
            prefix = "• " if block_type == "bulleted_list_item" else "1. "
            return prefix + "".join(rt.get("plain_text", "") for rt in rich_text)
        elif block_type == "code":
            rich_text = block.get("code", {}).get("rich_text", [])
            return "```\n" + "".join(rt.get("plain_text", "") for rt in rich_text) + "\n```"
        elif block_type == "toggle":
            rich_text = block.get("toggle", {}).get("rich_text", [])
            return "> " + "".join(rt.get("plain_text", "") for rt in rich_text)
        return ""

    def _format_page(self, page: Dict[str, Any], content: str) -> Document:
        """Format Notion page to Document format"""
        properties = page.get("properties", {})
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        return Document(
            external_id=page.get("id", ""),
            title=self._get_title(properties),
            content=content,
            url=page.get("url", ""),
            metadata={
                "source_type": "notion",
                "created_time": page.get("created_time", ""),
                "last_edited_time": page.get("last_edited_time", ""),
                "properties": properties,
            },
            content_hash=content_hash,
        )

    def _get_title(self, properties: Dict[str, Any]) -> str:
        """Get page title from properties"""
        if "title" in properties:
            title_prop = properties["title"]
            if title_prop.get("title"):
                return title_prop["title"][0].get("plain_text", "")
        return "Untitled"

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup session"""
        if self._session:
            await self._session.close()
            self._session = None
        return await super().__aexit__(exc_type, exc_val, exc_tb)
