"""
Git Repository Connector - fetch files from Git repositories (GitHub, GitLab, etc.)
"""
import logging
import hashlib
import re
from typing import Dict, Any, List, Optional, AsyncIterator, Tuple
import aiohttp
from datetime import datetime
from packages.rag.connectors.base import BaseConnector, Document

logger = logging.getLogger("app.connectors.git")


# Supported code file extensions
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".rb", ".php",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".swift", ".kt", ".scala", ".r", ".m",
    ".sql", ".sh", ".bash", ".zsh", ".ps1", ".yaml", ".yml", ".json", ".xml",
    ".md", ".rst", ".txt", ".toml", ".ini", ".cfg", ".conf", ".env",
    ".html", ".css", ".scss", ".less", ".vue", ".svelte",
    ".dockerfile", ".makefile", ".cmake",
}

# Files to skip
SKIP_PATTERNS = {
    "node_modules", "__pycache__", ".git", ".venv", "venv", ".idea", ".vscode",
    "dist", "build", "target", "out", ".next", "coverage",
}


class GitConnector(BaseConnector):
    """
    Git repository connector for fetching source code files.
    Supports GitHub and GitLab APIs.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.platform = config.get("platform", "github").lower()  # github, gitlab
        self.repo_url = config.get("repo_url", "")
        self.owner = config.get("owner", "")
        self.repo = config.get("repo", "")
        self.branch = config.get("branch", "main")
        self.api_token = config.get("api_token", "")
        self.paths = config.get("paths", ["**"])  # Glob patterns for files to include
        self.exclude_paths = config.get("exclude_paths", [])

        # Parse repo_url if owner/repo not provided
        if not self.owner or not self.repo:
            self._parse_repo_url()

        self._session: Optional[aiohttp.ClientSession] = None

    def _parse_repo_url(self):
        """Parse owner and repo from repo_url"""
        if self.repo_url:
            # GitHub: https://github.com/owner/repo
            # GitLab: https://gitlab.com/owner/repo or https://gitlab.example.com/owner/repo
            match = re.search(r"/([^/]+)/([^/]+?)(?:\.git)?$", self.repo_url)
            if match:
                self.owner = match.group(1)
                self.repo = match.group(2).replace(".git", "")

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create authenticated session"""
        if self._session is None:
            headers = {}
            if self.api_token:
                if self.platform == "github":
                    headers["Authorization"] = f"Bearer {self.api_token}"
                elif self.platform == "gitlab":
                    headers["PRIVATE-TOKEN"] = self.api_token

            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def ingest(self) -> AsyncIterator[Document]:
        """
        Perform full sync of repository files.
        Yields Document objects one by one.
        """
        session = await self._get_session()

        try:
            if self.platform == "github":
                async for doc in self._fetch_github_files(session):
                    yield doc
            elif self.platform == "gitlab":
                async for doc in self._fetch_gitlab_files(session):
                    yield doc
            else:
                logger.error(f"Unsupported Git platform: {self.platform}")
        finally:
            if self._session:
                await self._session.close()
                self._session = None

    async def poll(self, watermark: Optional[Any] = None) -> Tuple[List[Document], Optional[Any]]:
        """
        Poll for changed files since last sync.
        Uses commit history to find modified files.
        """
        session = await self._get_session()
        docs = []

        if watermark:
            # Fetch files changed since the watermark (commit SHA or timestamp)
            if self.platform == "github":
                async for doc in self._fetch_github_changes(session, watermark):
                    docs.append(doc)
            elif self.platform == "gitlab":
                async for doc in self._fetch_gitlab_changes(session, watermark):
                    docs.append(doc)
        else:
            # No watermark = full sync
            async for doc in self.ingest():
                docs.append(doc)

        new_watermark = datetime.utcnow().isoformat()
        return docs, new_watermark

    async def test_connection(self) -> Tuple[bool, str]:
        """Test Git platform API connection"""
        try:
            session = await self._get_session()

            if self.platform == "github":
                url = f"https://api.github.com/repos/{self.owner}/{self.repo}"
            elif self.platform == "gitlab":
                # URL encode owner/repo for GitLab
                project_path = f"{self.owner}/{self.repo}"
                import urllib.parse
                encoded_path = urllib.parse.quote(project_path, safe="")
                url = f"https://gitlab.com/api/v4/projects/{encoded_path}"
            else:
                return False, f"Unsupported platform: {self.platform}"

            async with session.get(url) as resp:
                if resp.status == 200:
                    return True, f"Connected to {self.platform} repo {self.owner}/{self.repo}"
                return False, f"HTTP {resp.status}: {resp.reason}"
        except Exception as e:
            return False, str(e)

    async def _fetch_github_files(self, session: aiohttp.ClientSession) -> AsyncIterator[Document]:
        """Fetch all files from GitHub repository"""
        # Get tree recursively
        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/git/trees/{self.branch}"
        params = {"recursive": "1"}

        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                logger.error("Failed to fetch GitHub tree: %s", resp.status)
                return

            data = await resp.json()
            tree = data.get("tree", [])

            for item in tree:
                if item["type"] != "blob":
                    continue

                path = item["path"]

                # Skip excluded paths
                if self._should_skip_path(path):
                    continue

                # Check file extension
                if not self._is_code_file(path):
                    continue

                # Fetch file content
                content = await self._fetch_github_file_content(session, item["sha"])
                if content:
                    yield self._format_document(path, content, "github")

    async def _fetch_github_file_content(
        self,
        session: aiohttp.ClientSession,
        sha: str
    ) -> Optional[str]:
        """Fetch file content from GitHub"""
        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/git/blobs/{sha}"
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                content = data.get("content", "")
                encoding = data.get("encoding", "utf-8")
                if encoding == "base64":
                    import base64
                    try:
                        return base64.b64decode(content).decode("utf-8")
                    except:
                        return content
                return content
        return None

    async def _fetch_github_changes(
        self,
        session: aiohttp.ClientSession,
        watermark: Any
    ) -> AsyncIterator[Document]:
        """Fetch files changed since a commit SHA"""
        # Compare branch with the watermark commit
        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/compare/{watermark}...{self.branch}"

        async with session.get(url) as resp:
            if resp.status != 200:
                return

            data = await resp.json()
            files = data.get("files", [])

            for file in files:
                path = file["filename"]
                if self._should_skip_path(path) or not self._is_code_file(path):
                    continue

                content = await self._fetch_github_file_content(session, file["sha"])
                if content:
                    yield self._format_document(path, content, "github")

    async def _fetch_gitlab_files(self, session: aiohttp.ClientSession) -> AsyncIterator[Document]:
        """Fetch all files from GitLab repository"""
        import urllib.parse
        project_path = f"{self.owner}/{self.repo}"
        encoded_path = urllib.parse.quote(project_path, safe="")

        # Get repository tree
        url = f"https://gitlab.com/api/v4/projects/{encoded_path}/repository/tree"
        params = {"ref": self.branch, "recursive": True, "per_page": 100}

        while True:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.error("Failed to fetch GitLab tree: %s", resp.status)
                    return

                tree = await resp.json()

                if not tree:
                    break

                for item in tree:
                    if item["type"] != "blob":
                        continue

                    path = item["path"]
                    if self._should_skip_path(path) or not self._is_code_file(path):
                        continue

                    content = await self._fetch_gitlab_file_content(
                        session, encoded_path, path, self.branch
                    )
                    if content:
                        yield self._format_document(path, content, "gitlab")

                # Pagination
                if len(tree) < 100:
                    break
                params["page"] = params.get("page", 1) + 1

    async def _fetch_gitlab_file_content(
        self,
        session: aiohttp.ClientSession,
        encoded_path: str,
        file_path: str,
        ref: str
    ) -> Optional[str]:
        """Fetch file content from GitLab"""
        import urllib.parse
        encoded_file_path = urllib.parse.quote(file_path, safe="")
        url = f"https://gitlab.com/api/v4/projects/{encoded_path}/repository/files/{encoded_file_path}/raw"
        params = {"ref": ref}

        async with session.get(url, params=params) as resp:
            if resp.status == 200:
                return await resp.text()
        return None

    async def _fetch_gitlab_changes(
        self,
        session: aiohttp.ClientSession,
        watermark: Any
    ) -> AsyncIterator[Document]:
        """Fetch files changed since a commit SHA"""
        import urllib.parse
        project_path = f"{self.owner}/{self.repo}"
        encoded_path = urllib.parse.quote(project_path, safe="")

        url = f"https://gitlab.com/api/v4/projects/{encoded_path}/repository/compare"
        params = {"from": watermark, "to": self.branch}

        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                return

            data = await resp.json()
            diffs = data.get("diffs", [])

            for diff in diffs:
                path = diff["new_path"]
                if self._should_skip_path(path) or not self._is_code_file(path):
                    continue

                content = await self._fetch_gitlab_file_content(
                    session, encoded_path, path, self.branch
                )
                if content:
                    yield self._format_document(path, content, "gitlab")

    def _should_skip_path(self, path: str) -> bool:
        """Check if path should be skipped"""
        # Check exclude patterns
        for pattern in self.exclude_paths:
            if pattern in path:
                return True

        # Check skip patterns
        for skip in SKIP_PATTERNS:
            if skip in path.lower():
                return True

        return False

    def _is_code_file(self, path: str) -> bool:
        """Check if file is a code file based on extension"""
        if not self.paths or self.paths == ["**"]:
            # Default: include all code files
            ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
            return ext in CODE_EXTENSIONS or path.lower() in ("dockerfile", "makefile")
        else:
            # Check against include patterns
            for pattern in self.paths:
                if self._match_glob(path, pattern):
                    return True
            return False

    def _match_glob(self, path: str, pattern: str) -> bool:
        """Simple glob matching"""
        import fnmatch
        return fnmatch.fnmatch(path, pattern)

    def _format_document(self, path: str, content: str, platform: str) -> Document:
        """Format file to Document format"""
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        # Build URL
        if platform == "github":
            url = f"https://github.com/{self.owner}/{self.repo}/blob/{self.branch}/{path}"
        else:
            url = f"https://gitlab.com/{self.owner}/{self.repo}/-/blob/{self.branch}/{path}"

        return Document(
            external_id=f"{platform}:{path}",
            title=path,
            content=content,
            url=url,
            metadata={
                "source_type": f"git_{platform}",
                "path": path,
                "branch": self.branch,
                "owner": self.owner,
                "repo": self.repo,
            },
            content_hash=content_hash,
        )

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup session"""
        if self._session:
            await self._session.close()
            self._session = None
        return await super().__aexit__(exc_type, exc_val, exc_tb)
