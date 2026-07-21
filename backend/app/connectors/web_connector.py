"""
Web page scraper connector using httpx + BeautifulSoup
"""
import logging
import hashlib
from datetime import datetime
from typing import Optional, Any, AsyncIterator
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.connectors.base import BaseConnector, Document, SyncResult

logger = logging.getLogger("app.connectors.web")


class WebConnector(BaseConnector):
    """Connector for scraping web pages"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.urls: list[str] = config.get("urls", [])
        self.max_depth: int = config.get("max_depth", 1)
        self.content_selector: str = config.get("content_selector", "article, .content, main")
        self.title_selector: str = config.get("title_selector", "h1")
        self.exclude_selectors: list[str] = config.get("exclude_selectors", ["nav", "footer", "script", "style"])
        self.wait_time: int = config.get("wait_time", 2)
        self.user_agent: str = config.get("user_agent",
            "RAG-Bot/1.0 (Enterprise Knowledge Platform)")
        self.url_pattern: Optional[str] = config.get("url_pattern")

        self._client: Optional[httpx.AsyncClient] = None
        self._visited: set[str] = set()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
                headers={"User-Agent": self.user_agent},
            )
        return self._client

    async def ingest(self) -> AsyncIterator[Document]:
        """Crawl URLs and yield Document objects"""
        self._visited.clear()
        for url in self.urls:
            async for doc in self._crawl_page(url, depth=0):
                yield doc

    async def _crawl_page(self, url: str, depth: int) -> AsyncIterator[Document]:
        """Recursively crawl a page and yield documents"""
        if depth > self.max_depth or url in self._visited:
            return
        self._visited.add(url)

        client = await self._get_client()

        try:
            response = await client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Failed to fetch %s: %s", url, e)
            return

        soup = BeautifulSoup(response.text, "html.parser")

        # Extract title
        title = url
        if self.title_selector:
            title_elem = soup.select_one(self.title_selector)
            if title_elem:
                title = title_elem.get_text(strip=True)

        # Remove excluded elements
        for selector in self.exclude_selectors:
            for elem in soup.select(selector):
                elem.decompose()

        # Extract content
        content = ""
        if self.content_selector:
            for elem in soup.select(self.content_selector):
                text = elem.get_text(separator="\n", strip=True)
                if text:
                    content += text + "\n\n"
        else:
            # Extract from body
            body = soup.find("body")
            if body:
                content = body.get_text(separator="\n", strip=True)

        if not content.strip():
            logger.debug("No content found for %s", url)
            return

        content_hash = hashlib.sha256(content.encode()).hexdigest()

        yield Document(
            external_id=url,
            title=title,
            content=content,
            url=url,
            metadata={
                "source_type": "web_page",
                "url": url,
                "depth": depth,
                "content_length": len(content),
            },
            content_hash=content_hash,
        )

        # Crawl links if depth < max_depth
        if depth < self.max_depth:
            base_domain = urlparse(url).netloc
            for link in soup.find_all("a", href=True):
                href = link["href"]
                full_url = urljoin(url, href)
                parsed = urlparse(full_url)

                # Only follow same-domain links
                if parsed.netloc == base_domain and full_url not in self._visited:
                    if self.url_pattern:
                        import re
                        if not re.match(self.url_pattern, full_url):
                            continue
                    async for doc in self._crawl_page(full_url, depth + 1):
                        yield doc

    async def poll(self, watermark: Optional[Any] = None) -> tuple[list[Document], Optional[Any]]:
        """Poll for changes - for web, re-crawl all URLs"""
        docs = []
        async for doc in self.ingest():
            docs.append(doc)
        watermark = datetime.utcnow().isoformat()
        return docs, watermark

    async def test_connection(self) -> tuple[bool, str]:
        """Test connection to the first URL"""
        if not self.urls:
            return False, "No URLs configured"

        try:
            client = await self._get_client()
            response = await client.head(self.urls[0])
            if response.status_code < 400:
                return True, f"Connection successful (HTTP {response.status_code})"
            return False, f"HTTP {response.status_code}: {response.reason_phrase}"
        except Exception as e:
            return False, str(e)

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()
            self._client = None
