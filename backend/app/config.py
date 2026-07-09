from __future__ import annotations
import os
from pydantic_settings import BaseSettings

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # ============================================================
    # Application
    # ============================================================
    app_name: str = "RAG Backend"
    debug: bool = False
    api_prefix: str = "/api/v1"

    # ============================================================
    # PostgreSQL — business metadata + system settings
    # ============================================================
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_user: str = "rag"
    pg_password: str = "rag_password"
    pg_db: str = "rag"
    pg_pool_size: int = 20
    pg_max_overflow: int = 10
    pg_pool_recycle: int = 3600
    pg_pool_timeout: int = 30

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_db}"
        )

    @property
    def database_connect_args(self) -> dict:
        return {
            "pool_size": self.pg_pool_size,
            "max_overflow": self.pg_max_overflow,
            "pool_recycle": self.pg_pool_recycle,
            "pool_timeout": self.pg_pool_timeout,
            "pool_pre_ping": True,
            "connect_args": {
                "server_settings": {
                    "application_name": "rag-backend",
                    "timezone": "Asia/Shanghai",
                },
            },
        }

    # ============================================================
    # Milvus — vector database
    # ============================================================
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_user: str = ""
    milvus_password: str = ""
    milvus_db_name: str = "default"

    @property
    def milvus_uri(self) -> str:
        return f"http://{self.milvus_host}:{self.milvus_port}"

    @property
    def milvus_token(self) -> str:
        if self.milvus_user and self.milvus_password:
            return f"{self.milvus_user}:{self.milvus_password}"
        return ""

    # ============================================================
    # Redis — cache + queue + metrics
    # ============================================================
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0
    redis_pool_size: int = 20
    redis_pool_timeout: int = 30
    redis_socket_timeout: int = 10
    redis_socket_connect_timeout: int = 5
    redis_retry_on_timeout: bool = True
    redis_health_check_interval: int = 30

    @property
    def redis_url(self) -> str:
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # ============================================================
    # MinIO — document object storage
    # ============================================================
    minio_host: str = "localhost"
    minio_port: int = 9000
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "rag-documents"
    minio_secure: bool = False

    @property
    def minio_endpoint(self) -> str:
        return f"{self.minio_host}:{self.minio_port}"

    # ============================================================
    # CORS
    # ============================================================
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # ============================================================
    # Security & Authentication
    # ============================================================
    secret_key: str = "your-secret-key-change-in-production"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # ============================================================
    # Rate Limiting
    # ============================================================
    rate_limit_requests: int = 100  # per minute
    rate_limit_window_seconds: int = 60


settings = Settings()
