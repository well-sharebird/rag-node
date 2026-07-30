from __future__ import annotations
import os
from pydantic import Field
from pydantic_settings import BaseSettings

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore", "populate_by_name": True}

    # ============================================================
    # Application
    # ============================================================
    app_name: str = "RAG Backend"
    debug: bool = False
    api_prefix: str = "/api/v1"

    # ============================================================
    # PostgreSQL — business metadata + system settings
    # ============================================================
    pg_host: str = Field(default="localhost", validation_alias="PG_HOST")
    pg_port: int = Field(default=5432, validation_alias="PG_PORT")
    pg_user: str = Field(default="rag", validation_alias="PG_USER")
    pg_password: str = Field(default="rag_password", validation_alias="PG_PASSWORD")
    pg_db: str = Field(default="rag", validation_alias="PG_DB")
    pg_pool_size: int = Field(default=20, validation_alias="PG_POOL_SIZE")
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
    milvus_host: str = Field(default="localhost", validation_alias="MILVUS_HOST")
    milvus_port: int = Field(default=19530, validation_alias="MILVUS_PORT")
    milvus_user: str = Field(default="", validation_alias="MILVUS_USER")
    milvus_password: str = Field(default="", validation_alias="MILVUS_PASSWORD")
    milvus_db_name: str = Field(default="default", validation_alias="MILVUS_DB_NAME")

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
    redis_host: str = Field(default="localhost", validation_alias="REDIS_HOST")
    redis_port: int = Field(default=6379, validation_alias="REDIS_PORT")
    redis_password: str = Field(default="", validation_alias="REDIS_PASSWORD")
    redis_db: int = Field(default=0, validation_alias="REDIS_DB")
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
    minio_host: str = Field(default="localhost", validation_alias="MINIO_HOST")
    minio_port: int = Field(default=9000, validation_alias="MINIO_PORT")
    minio_access_key: str = Field(default="minioadmin", validation_alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(default="minioadmin", validation_alias="MINIO_SECRET_KEY")
    minio_bucket: str = Field(default="rag-documents", validation_alias="MINIO_BUCKET")
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

    # ============================================================
    # Elasticsearch — full-text search (BM25)
    # ============================================================
    es_host: str = Field(default="localhost", validation_alias="ES_HOST")
    es_port: int = Field(default=9200, validation_alias="ES_PORT")
    es_user: str = Field(default="", validation_alias="ES_USER")
    es_password: str = Field(default="", validation_alias="ES_PASSWORD")
    es_scheme: str = Field(default="http", validation_alias="ES_SCHEME")
    es_index_prefix: str = Field(default="rag", validation_alias="ES_INDEX_PREFIX")

    # ============================================================
    # Neo4j — knowledge graph
    # ============================================================
    neo4j_uri: str = Field(default="bolt://localhost:7687", validation_alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", validation_alias="NEO4J_USER")
    neo4j_password: str = Field(default="neo4j_password", validation_alias="NEO4J_PASSWORD")

    # ============================================================
    # Kafka — message queue
    # ============================================================
    kafka_bootstrap_servers: str = Field(default="localhost:9092", validation_alias="KAFKA_BOOTSTRAP_SERVERS")
    kafka_consumer_group: str = Field(default="rag-consumer", validation_alias="KAFKA_CONSUMER_GROUP")


settings = Settings()
