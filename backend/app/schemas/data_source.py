from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class DataSourceType(str, Enum):
    """Data source type enumeration"""
    LOCAL_FILE = "local_file"  # Local document uploads
    WEB_PAGE = "web_page"  # Web page URLs
    WECHAT_OFFICIAL = "wechat_official"  # WeChat Official Account articles
    DATABASE = "database"  # Database tables (MySQL, PostgreSQL, etc.)
    API = "api"  # REST API endpoints
    OBJECT_STORAGE = "object_storage"  # S3/OSS/MinIO buckets
    SHAREPOINT = "sharepoint"  # SharePoint documents
    CONFLUENCE = "confluence"  # Confluence pages
    NOTION = "notion"  # Notion pages


class DataSourceStatus(str, Enum):
    """Data source status"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SYNCING = "syncing"
    ERROR = "error"
    PENDING = "pending"


class SyncMode(str, Enum):
    """Synchronization mode"""
    MANUAL = "manual"  # Manual trigger only
    SCHEDULED = "scheduled"  # Cron-based scheduled sync
    REALTIME = "realtime"  # Real-time webhook triggered
    INCREMENTAL = "incremental"  # Incremental sync based on watermark


# ============================================================
# Database Connection Config
# ============================================================

class DatabaseConfig(BaseModel):
    """Database connection configuration"""
    db_type: str = "mysql"  # mysql, postgresql, sqlserver, oracle
    host: str
    port: int
    database: str
    username: str
    password: str
    table_name: str
    query: Optional[str] = None  # Custom SQL query
    primary_key: str = "id"
    updated_at_column: Optional[str] = None  # For incremental sync


# ============================================================
# Web Page Config
# ============================================================

class WebPageConfig(BaseModel):
    """Web page scraping configuration"""
    urls: list[str]
    url_pattern: Optional[str] = None  # Regex pattern for URL matching
    max_depth: int = 1  # Crawl depth
    selector_type: str = "css"  # css, xpath
    title_selector: str = "h1"
    content_selector: str = "article, .content, #content, main"
    exclude_selectors: list[str] = Field(default_factory=lambda: [
        "nav", "footer", "script", "style", ".ads", ".sidebar"
    ])
    wait_time: int = 2  # Seconds to wait for JS rendering
    user_agent: Optional[str] = None


# ============================================================
# WeChat Official Account Config
# ============================================================

class WeChatOfficialConfig(BaseModel):
    """WeChat Official Account scraping configuration"""
    account_name: str
    account_id: Optional[str] = None  # WeChat account ID
    cookie: Optional[str] = None  # WeChat cookie for auth
    proxy: Optional[str] = None
    start_date: Optional[datetime] = None  # Fetch articles from this date
    end_date: Optional[datetime] = None
    max_articles: int = 100


# ============================================================
# API Source Config
# ============================================================

class APIConfig(BaseModel):
    """API endpoint configuration"""
    base_url: str
    endpoint: str
    method: str = "GET"
    headers: dict = Field(default_factory=dict)
    auth_type: str = "none"  # none, bearer, basic, api_key
    auth_token: Optional[str] = None
    auth_header: str = "Authorization"
    data_path: str = "data"  # JSON path to data array
    pagination_type: str = "offset"  # offset, cursor, link
    pagination_field: str = "page"
    limit_field: str = "limit"
    limit_value: int = 100


# ============================================================
# Object Storage Config
# ============================================================

class ObjectStorageConfig(BaseModel):
    """Object storage (S3/OSS) configuration"""
    provider: str = "s3"  # s3, oss, cos, obs
    endpoint: str
    access_key: str
    secret_key: str
    bucket: str
    prefix: Optional[str] = None  # Folder prefix
    file_pattern: Optional[str] = None  # Regex pattern for files
    allowed_extensions: list[str] = Field(default_factory=lambda: [
        "pdf", "docx", "txt", "md", "html", "xlsx", "pptx"
    ])


# ============================================================
# Data Source Schemas
# ============================================================

class DataSourceBase(BaseModel):
    """Base data source schema"""
    name: str = Field(..., min_length=1, max_length=200)
    source_type: DataSourceType
    description: Optional[str] = Field(None, max_length=500)
    kb_id: str  # Target knowledge base ID (UUID)

    # Sync settings
    sync_mode: SyncMode = SyncMode.MANUAL
    cron_expression: Optional[str] = None  # For scheduled sync
    auto_process: bool = True  # Auto process after sync

    # Common config
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)


class DataSourceCreate(DataSourceBase):
    """Schema for creating a data source"""
    # Type-specific config (one of these will be set)
    database_config: Optional[DatabaseConfig] = None
    web_page_config: Optional[WebPageConfig] = None
    wechat_config: Optional[WeChatOfficialConfig] = None
    api_config: Optional[APIConfig] = None
    storage_config: Optional[ObjectStorageConfig] = None

    # Raw config as JSON for flexibility
    config_json: dict = Field(default_factory=dict)


class DataSourceUpdate(BaseModel):
    """Schema for updating a data source"""
    name: Optional[str] = None
    description: Optional[str] = None
    database_config: Optional[dict] = None
    web_page_config: Optional[dict] = None
    wechat_config: Optional[dict] = None
    api_config: Optional[dict] = None
    storage_config: Optional[dict] = None
    config_json: Optional[dict] = None
    sync_mode: Optional[SyncMode] = None
    cron_expression: Optional[str] = None
    auto_process: Optional[bool] = None
    enabled: Optional[bool] = None
    tags: Optional[list[str]] = None


class DataSourceResponse(DataSourceBase):
    """Schema for data source response"""
    id: int
    status: DataSourceStatus = DataSourceStatus.PENDING
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    sync_message: Optional[str] = None
    items_synced: int = 0
    items_failed: int = 0
    config_json: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DataSourceList(BaseModel):
    """Schema for data source list response"""
    items: list[DataSourceResponse]
    total: int
    page: int = 1
    page_size: int = 20


# ============================================================
# Sync Job Schemas
# ============================================================

class SyncJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SyncJobCreate(BaseModel):
    """Schema for creating a sync job"""
    data_source_id: int
    full_sync: bool = True  # False = incremental
    trigger_by: str = "manual"  # manual, scheduled, api


class SyncJobResponse(BaseModel):
    """Schema for sync job response"""
    id: int
    data_source_id: int
    status: SyncJobStatus
    trigger_by: str
    items_synced: int = 0
    items_failed: int = 0
    progress_percent: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ============================================================
# Data Source Presets
# ============================================================

class DataSourcePreset(BaseModel):
    """Pre-configured data source template"""
    id: str
    name: str
    description: str
    source_type: DataSourceType
    icon: str
    config_template: dict
    use_cases: list[str]


COMMON_DATA_SOURCE_PRESETS: list[DataSourcePreset] = [
    DataSourcePreset(
        id="web-page",
        name="网页抓取",
        description="从指定网页抓取内容，支持自动分页",
        source_type=DataSourceType.WEB_PAGE,
        icon="Globe",
        config_template={
            "urls": ["https://example.com"],
            "max_depth": 1,
            "content_selector": "article",
        },
        use_cases=["产品文档", "新闻网站", "博客文章"],
    ),
    DataSourcePreset(
        id="wechat-official",
        name="微信公众号",
        description="抓取微信公众号历史文章",
        source_type=DataSourceType.WECHAT_OFFICIAL,
        icon="MessageSquare",
        config_template={
            "account_name": "",
            "max_articles": 100,
        },
        use_cases=["企业公众号", "行业资讯号", "技术分享号"],
    ),
    DataSourcePreset(
        id="mysql-database",
        name="MySQL 数据库",
        description="从 MySQL 数据库表同步数据",
        source_type=DataSourceType.DATABASE,
        icon="Database",
        config_template={
            "db_type": "mysql",
            "host": "localhost",
            "port": 3306,
            "table_name": "",
        },
        use_cases=["业务数据", "产品目录", "客户信息"],
    ),
    DataSourcePreset(
        id="postgresql-database",
        name="PostgreSQL 数据库",
        description="从 PostgreSQL 数据库表同步数据",
        source_type=DataSourceType.DATABASE,
        icon="Database",
        config_template={
            "db_type": "postgresql",
            "host": "localhost",
            "port": 5432,
            "table_name": "",
        },
        use_cases=["业务数据", "日志数据", "分析数据"],
    ),
    DataSourcePreset(
        id="rest-api",
        name="REST API",
        description="从 REST API 接口获取数据",
        source_type=DataSourceType.API,
        icon="Cloud",
        config_template={
            "base_url": "https://api.example.com",
            "endpoint": "/v1/items",
            "method": "GET",
        },
        use_cases=["第三方系统", "SaaS 服务", "开放平台"],
    ),
    DataSourcePreset(
        id="s3-bucket",
        name="S3/OSS 存储",
        description="从对象存储批量导入文件",
        source_type=DataSourceType.OBJECT_STORAGE,
        icon="HardDrive",
        config_template={
            "provider": "s3",
            "bucket": "",
            "prefix": "",
        },
        use_cases=["备份文件", "归档文档", "媒体资源"],
    ),
    DataSourcePreset(
        id="local-file",
        name="本地文件",
        description="上传本地文档到知识库",
        source_type=DataSourceType.LOCAL_FILE,
        icon="FileText",
        config_template={},
        use_cases=["PDF 文档", "Word 文档", "Markdown 笔记"],
    ),
]
