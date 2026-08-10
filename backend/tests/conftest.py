"""
Pytest 配置文件
提供通用的 Mock 服务和测试工具
"""
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# ============================================================
# Mock 服务类
# ============================================================

class MockModelGateway:
    """
    模拟模型网关 - 用于测试

    提供模型配置的 Mock 实现，避免依赖真实模型服务
    """

    async def get_model_by_name(self, name: str):
        from packages.agent.schemas.chat import ModelConfig
        return ModelConfig(
            provider="local_qwen",
            model="qwen3.5-397b-a17b",
            temperature=0.7,
            max_tokens=4096,
            base_url="http://localhost:8000",
            api_key="not-needed",
        )

    async def get_model(self, model_id: str):
        from packages.agent.schemas.chat import ModelConfig
        return ModelConfig(
            provider="local_qwen",
            model="qwen3.5-397b-a17b",
            temperature=0.7,
            max_tokens=4096,
            base_url="http://localhost:8000",
            api_key="not-needed",
        )

    async def list_models(self, provider: str = None, limit: int = 20):
        from packages.agent.schemas.chat import ModelConfig
        return [
            ModelConfig(
                provider="local_qwen",
                model="qwen3.5-397b-a17b",
                temperature=0.7,
                max_tokens=4096,
            )
        ]


class MockSkillRegistry:
    """
    模拟技能注册表 - 用于测试

    提供技能工具的 Mock 实现，避免依赖真实技能服务
    """

    def get_tool(self, skill_id: str):
        return None

    def list_tools(self):
        return []

    def register_tool(self, tool):
        pass


class MockMilvusClient:
    """
    模拟 Milvus 客户端 - 用于测试

    提供向量数据库操作的 Mock 实现
    """

    def __init__(self):
        self.collections = {}

    def has_collection(self, collection_name: str) -> bool:
        return collection_name in self.collections

    def create_collection(self, collection_name: str, **kwargs):
        self.collections[collection_name] = []

    def drop_collection(self, collection_name: str):
        if collection_name in self.collections:
            del self.collections[collection_name]

    def insert(self, collection_name: str, data: list):
        if collection_name in self.collections:
            self.collections[collection_name].extend(data)

    def search(self, collection_name: str, **kwargs):
        return []

    def close(self):
        pass


class MockRedisClient:
    """
    模拟 Redis 客户端 - 用于测试

    提供缓存操作的 Mock 实现
    """

    def __init__(self):
        self.data = {}

    async def get(self, key: str):
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int = None):
        self.data[key] = value

    async def delete(self, key: str):
        if key in self.data:
            del self.data[key]

    async def exists(self, key: str):
        return key in self.data

    async def close(self):
        pass


# ============================================================
# Pytest Fixtures
# ============================================================

@pytest.fixture
def mock_db_session():
    """创建模拟数据库 Session"""
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.refresh = AsyncMock()
    session.scalar_one_or_none = AsyncMock()
    session.scalars = AsyncMock()
    return session


@pytest.fixture
def mock_model_gateway():
    """创建模拟模型网关"""
    return MockModelGateway()


@pytest.fixture
def mock_skill_registry():
    """创建模拟技能注册表"""
    return MockSkillRegistry()


@pytest.fixture
def mock_milvus_client():
    """创建模拟 Milvus 客户端"""
    return MockMilvusClient()


@pytest.fixture
def mock_redis_client():
    """创建模拟 Redis 客户端"""
    return MockRedisClient()


@pytest.fixture
def mock_agent_config():
    """创建模拟 Agent 配置"""
    config = MagicMock()
    config.id = "test-agent-id"
    config.name = "Test Agent"
    config.agent_type = "single"
    config.system_prompt = "You are a helpful assistant."
    config.description = "Test agent for unit testing"
    config.enabled_skills = []
    config.mcp_servers = []
    config.kb_ids = []
    config.default_model_config = {
        "provider": "local_qwen",
        "model": "qwen3.5-397b-a17b",
        "temperature": 0.7,
        "max_tokens": 4096,
    }
    return config


# ============================================================
# 原有测试配置（保留向后兼容）
# ============================================================

@pytest.fixture
async def client():
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def test_kb(client):
    """Create a test knowledge base for API tests."""
    kb_id = str(uuid.uuid4())
    kb_name = f"test_kb_{kb_id[:8]}"

    try:
        # Create knowledge base via API
        response = await client.post(
            "/api/v1/knowledge-bases",
            json={"name": kb_name, "description": "Test knowledge base"},
        )

        if response.status_code == 201:
            kb_data = response.json()

            class KB:
                def __init__(self, kb_id):
                    self.id = kb_id
            yield KB(kb_data["id"])

            # Cleanup
            try:
                await client.delete(f"/api/v1/knowledge-bases/{kb_data['id']}")
            except:
                pass
        else:
            # Try to find existing kb
            list_response = await client.get("/api/v1/knowledge-bases")
            if list_response.status_code == 200:
                kbs = list_response.json().get("items", [])
                if kbs:
                    class KB:
                        def __init__(self, kb_id):
                            self.id = kb_id
                    yield KB(kbs[0]["id"])
                    return

            pytest.skip(f"Could not create test knowledge base: {response.status_code}")
    except Exception as e:
        pytest.skip(f"Could not create test knowledge base: {e}")


@pytest.fixture
async def test_db_session():
    """Create a test database session."""
    from packages.core.database import async_session_factory
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    # Use in-memory SQLite for testing
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    test_session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # Create tables
    from app.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with test_session_factory() as session:
        yield session

    # Cleanup
    await engine.dispose()


@pytest.fixture
async def db_session(test_db_session):
    """Alias for test_db_session - for backward compatibility"""
    yield test_db_session


# ============================================================
# Mock DB Session for Harness testing (no database required)
# ============================================================

@pytest.fixture
def mock_db():
    """
    创建完全 Mock 的数据库 Session，用于测试 Harness 引擎

    Harness 引擎主要测试逻辑，不需要真实数据库
    """
    from unittest.mock import AsyncMock, MagicMock, patch
    from sqlalchemy.ext.asyncio import AsyncSession

    session = AsyncMock(spec=AsyncSession)
    session.add = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    session.scalar_one_or_none = AsyncMock()
    session.scalars = AsyncMock()

    # Mock 返回空结果
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value = []
    session.execute.return_value = mock_result

    return session
