# Import all models to ensure they are registered with SQLAlchemy
from app.models.base import Base
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.models.system_setting import SystemSetting
from app.models.model_config import ModelConfig
from app.models.data_source import DataSource, SyncJob, SyncedItem
from app.models.user import User, Role, Permission, APIKey, AuditLog
from app.models.token_usage import TokenUsage, UserQuota, ModelProvider
from app.models.prompt_template import (
    PromptTemplate,
    PromptVersion,
    PromptTag,
    PromptTestCase,
    PromptEvalRun,
    PromptAuditLog,
)

__all__ = [
    "Base",
    "Document",
    "KnowledgeBase",
    "SystemSetting",
    "ModelConfig",
    "DataSource",
    "SyncJob",
    "SyncedItem",
    "User",
    "Role",
    "Permission",
    "APIKey",
    "AuditLog",
    "TokenUsage",
    "UserQuota",
    "ModelProvider",
    "PromptTemplate",
    "PromptVersion",
    "PromptTag",
    "PromptTestCase",
    "PromptEvalRun",
    "PromptAuditLog",
]
