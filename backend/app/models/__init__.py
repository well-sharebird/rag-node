# Import all models to ensure they are registered with SQLAlchemy
from packages.core.base_model import Base
from packages.rag.models.document import Document
from packages.rag.models.knowledge_base import KnowledgeBase
from packages.core.system.models.system_setting import SystemSetting
from packages.model_gateway.models.model_config import ModelConfig
from packages.rag.models.data_source import DataSource, SyncJob, SyncedItem
from packages.core.system.models.menu import Menu, role_menus  # Import before user.py (Role references role_menus)
from packages.core.system.models.user import User, Role, Permission, APIKey, AuditLog
from packages.model_gateway.models.token_usage import TokenUsage, UserQuota
from packages.model_gateway.models.model_gateway import ModelProvider, ModelRoutingRule, ModelCallLog, ModelCache
from packages.prompt.models.prompt_template import (
    PromptTemplate,
    PromptVersion,
    PromptTag,
    PromptTestCase,
    PromptEvalRun,
    PromptAuditLog,
)
from packages.agent.models.agent import (
    AgentConfig,
    AgentVersion,
    AgentMemory,
    AgentCallLog,
)
from packages.agent.models.conversation_archive import (
    ConversationArchive,
    ConversationArchiveConfig,
)
from packages.rag.models.synonym import Synonym
from packages.rag.models.desensitization_config import DesensitizationConfig
from packages.core.system.models.department import Department, UserDepartment

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
    "ModelRoutingRule",
    "ModelCallLog",
    "ModelCache",
    "PromptTemplate",
    "PromptVersion",
    "PromptTag",
    "PromptTestCase",
    "PromptEvalRun",
    "PromptAuditLog",
    "AgentConfig",
    "AgentVersion",
    "AgentMemory",
    "AgentCallLog",
    "ConversationArchive",
    "ConversationArchiveConfig",
    "Department",
    "UserDepartment",
    "Menu",
    "role_menus",
    "Synonym",
    "DesensitizationConfig",
]
