"""
Web page scraper connector using crawl4ai for RAG-optimized content extraction.

Supports:
- JavaScript-rendered pages (SPA, dynamic content)
- Smart content extraction with automatic noise removal
- Markdown output optimized for RAG pipelines
- Screenshot capture for visual reference
"""
import logging
import hashlib
from datetime import datetime
from typing import Optional, Any, AsyncIterator

from crawl4ai import AsyncWebCrawler, CacheMode, CrawlerRunConfig
from crawl4ai.content_filter_strategy import PruningContentFilter

from app.connectors.base import BaseConnector, Document, SyncResult

logger = logging.getLogger("app.connectors.web")


class WebConnector(BaseConnector):
    """
    Connector for scraping web pages using crawl4ai.

    Features:
    - JavaScript rendering support (Chromium-based)
    - Automatic content extraction (removes nav, footer, ads)
    - Markdown output optimized for LLM consumption
    - Link extraction for recursive crawling
    - Screenshot support for visual reference
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.urls: list[str] = config.get("urls", [])
        self.max_depth: int = config.get("max_depth", 1)
        self.wait_time: float = config.get("wait_time", 2.0)  # Seconds to wait for JS
        self.user_agent: str = config.get("user_agent", "RAG-Bot/1.0 (Enterprise Knowledge Platform)")
        self.url_pattern: Optional[str] = config.get("url_pattern")
        self.exclude_external_links: bool = config.get("exclude_external_links", True)
        self.capture_screenshot: bool = config.get("capture_screenshot", False)
        self.word_count_threshold: int = config.get("word_count_threshold", 10)

        # Crawler instance (lazy-loaded)
        self._crawler: Optional[AsyncWebCrawler] = None
        self._visited: set[str] = set()

    async def _get_crawler(self) -> AsyncWebCrawler:
        """Get or create crawler instance (lazy initialization)"""
        if self._crawler is None:
            self._crawler = AsyncWebCrawler(
                headless=True,
                cache_mode=CacheMode.BYPASS,  # Don't use cache for fresh content
                browser_args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
                verbose=False,
            )
        return self._crawler

    async def ingest(self) -> AsyncIterator[Document]:
        """
        Crawl URLs and yield Document objects.

        Yields:
            Document: Scraped document with Markdown content
        """
        self._visited.clear()

        for url in self.urls:
            async for doc in self._crawl_page(url, depth=0):
                yield doc

    async def _crawl_page(self, url: str, depth: int = 0) -> AsyncIterator[Document]:
        """
        Recursively crawl a page and yield documents.

        Args:
            url: The URL to crawl
            depth: Current crawl depth (0 = starting page)
        """
        # Check depth limit and visited
        if depth > self.max_depth or url in self._visited:
            return
        self._visited.add(url)

        crawler = await self._get_crawler()

        # Configure crawl run
        config = CrawlerRunConfig(
            word_count_threshold=self.word_count_threshold,
            exclude_external_links=self.exclude_external_links,
            remove_overlay_elements=True,  # Remove popups/modals
            wait_time=self.wait_time,  # Wait for JS to render
            content_filter=PruningContentFilter(),  # Smart content extraction
        )

        try:
            result = await crawler.arun(url=url, config=config)

            if not result.success:
                logger.warning("Failed to crawl %s: %s", url, result.error_message or "Unknown error")
                return

            # Extract content
            content = result.markdown or ""
            title = result.title or url

            if not content.strip():
                logger.debug("No content found for %s", url)
                return

            # Generate content hash for deduplication
            content_hash = hashlib.sha256(content.encode()).hexdigest()

            # Build metadata
            metadata = {
                "source_type": "web_page",
                "url": url,
                "depth": depth,
                "content_length": len(content),
                "crawl_timestamp": datetime.utcnow().isoformat(),
            }

            # Add extracted links for next depth
            if depth < self.max_depth and result.links:
                metadata["extracted_links"] = [
                    link.href for link in result.links[:20]  # Limit links
                ]

            # Add screenshot if captured
            if self.capture_screenshot and result.screenshot:
                metadata["screenshot_base64"] = result.screenshot[:1000]  # Store partial for reference

            yield Document(
                external_id=url,
                title=title,
                content=content,
                url=url,
                metadata=metadata,
                content_hash=content_hash,
            )

            # Crawl extracted links if depth allows
            if depth < self.max_depth and result.links:
                base_domain = self._get_domain(url)
                for link in result.links[:10]:  # Limit concurrent crawls
                    full_url = link.href

                    # Skip if already visited or external
                    if full_url in self._visited:
                        continue

                    # Check same-domain constraint
                    if self._get_domain(full_url) != base_domain:
                        continue

                    # Apply URL pattern filter if configured
                    if self.url_pattern:
                        import re
                        if not re.match(self.url_pattern, full_url):
                            continue

                    # Recursively crawl
                    async for doc in self._crawl_page(full_url, depth + 1):
                        yield doc

        except Exception as e:
            logger.error("Error crawling %s: %s", url, e)
            return

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL"""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc

    async def poll(self, watermark: Optional[Any] = None) -> tuple[list[Document], Optional[Any]]:
        """
        Poll for changes - re-crawl all URLs.

        Args:
            watermark: Optional timestamp for incremental updates

        Returns:
            Tuple of (documents, new_watermark)
        """
        docs = []
        async for doc in self.ingest():
            docs.append(doc)
        watermark = datetime.utcnow().isoformat()
        return docs, watermark

    async def test_connection(self) -> tuple[bool, str]:
        """
        Test connection to the first URL.

        Returns:
            Tuple of (success, message)
        """
        if not self.urls:
            return False, "No URLs configured"

        try:
            crawler = await self._get_crawler()
            result = await crawler.arun(
                url=self.urls[0],
                config=CrawlerRunConfig(wait_time=1.0),
            )
            if result.success:
                return True, f"Connection successful - Title: {result.title}"
            return False, f"Failed: {result.error_message}"
        except Exception as e:
            return False, str(e)

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup crawler resources"""
        if self._crawler:
            await self._crawler.aclose()
            self._crawler = None
