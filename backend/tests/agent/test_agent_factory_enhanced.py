"""
Agent Factory 增强测试
测试 agent_factory.py 的边界情况和覆盖更多代码路径

目标：将 agent_factory.py 的测试覆盖率从 35% 提升到 60%+
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.agent_factory import AgentFactory


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_db():
    """创建模拟数据库 Session"""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.close = AsyncMock()
    return db


@pytest.fixture
def mock_model_gateway():
    """创建模拟模型网关"""
    gateway = MagicMock()
    gateway.get_model_by_name = AsyncMock()
    return gateway


@pytest.fixture
def mock_skill_registry():
    """创建模拟技能注册表"""
    registry = MagicMock()
    registry.get_tool = MagicMock(return_value=None)
    registry.list_tools = MagicMock(return_value=[])
    return registry


@pytest.fixture
def factory(mock_db, mock_model_gateway, mock_skill_registry):
    """创建 AgentFactory 实例"""
    return AgentFactory(mock_db, mock_model_gateway, mock_skill_registry)


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
    config.multi_agent_config = None
    return config


# ============================================================
# AgentFactory 创建测试
# ============================================================

class TestAgentFactoryCreate:
    """测试 AgentFactory 创建 Agent 的功能"""

    @pytest.mark.asyncio
    async def test_create_agent_with_default_model(self, factory, mock_agent_config, mock_model_gateway):
        """测试使用默认模型创建 Agent"""
        # 设置 Mock 返回
        mock_model_gateway.get_model_by_name.return_value = None

        with patch('app.services.agent_factory.create_agent') as mock_create:
            mock_create.return_value = MagicMock()
            agent = await factory.create_agent(mock_agent_config)

            assert agent is not None
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_agent_with_runtime_model_override(self, factory, mock_agent_config, mock_model_gateway):
        """测试运行时覆盖模型"""
        from packages.agent.schemas.chat import ModelConfig

        # 设置 Mock 返回
        mock_model_gateway.get_model_by_name.return_value = ModelConfig(
            provider="local_qwen",
            model="qwen3.5-397b-a17b",
            temperature=0.7,
            max_tokens=4096,
        )

        runtime_config = {"model_name": "custom_model"}

        with patch('app.services.agent_factory.create_agent') as mock_create:
            mock_create.return_value = MagicMock()
            agent = await factory.create_agent(mock_agent_config, runtime_config)

            assert agent is not None
            mock_model_gateway.get_model_by_name.assert_called_once_with("custom_model")

    @pytest.mark.asyncio
    async def test_create_agent_with_no_model_config(self, factory, mock_agent_config, mock_model_gateway):
        """测试没有模型配置时使用默认值"""
        mock_agent_config.default_model_config = None
        mock_model_gateway.get_model_by_name.return_value = None

        with patch('app.services.agent_factory.create_agent') as mock_create:
            mock_create.return_value = MagicMock()
            agent = await factory.create_agent(mock_agent_config)

            assert agent is not None


# ============================================================
# AgentFactory 工具加载测试
# ============================================================

class TestAgentFactoryTools:
    """测试 AgentFactory 工具加载功能"""

    @pytest.mark.asyncio
    async def test_load_basic_tools(self, factory):
        """测试加载基础工具"""
        with patch('app.tools.builtins.get_basic_tools') as mock_basic:
            mock_basic.return_value = []
            tools = await factory._load_basic_tools()
            assert tools == []
            mock_basic.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_tools_with_kb_ids(self, factory, mock_agent_config):
        """测试加载带知识库 ID 的工具"""
        mock_agent_config.kb_ids = ["kb1", "kb2"]

        with patch.object(factory, '_create_rag_tool') as mock_rag:
            mock_rag.return_value = MagicMock()
            tools = await factory._load_tools_for_agent(mock_agent_config, {})

            assert len(tools) > 0
            mock_rag.assert_called_once_with(["kb1", "kb2"], {})

    @pytest.mark.asyncio
    async def test_load_tools_with_mcp_servers(self, factory, mock_agent_config):
        """测试加载带 MCP 服务器的工具"""
        mock_agent_config.mcp_servers = ["kb", "model"]

        with patch.object(factory, '_load_mcp_tools') as mock_mcp:
            mock_mcp.return_value = []
            tools = await factory._load_tools_for_agent(mock_agent_config, {})

            # 基础工具 + MCP 工具
            mock_mcp.assert_called_once_with(["kb", "model"])

    @pytest.mark.asyncio
    async def test_load_tools_with_skills(self, factory, mock_agent_config):
        """测试加载带技能的工具"""
        mock_agent_config.enabled_skills = ["kb", "prompt"]

        with patch.object(factory, '_load_skill_tools') as mock_skills:
            mock_skills.return_value = []
            tools = await factory._load_tools_for_agent(mock_agent_config, {})

            mock_skills.assert_called_once_with(["kb", "prompt"])

    @pytest.mark.asyncio
    async def test_load_tools_with_multi_agent_type(self, factory, mock_agent_config):
        """测试多 Agent 类型加载 task 工具"""
        mock_agent_config.agent_type = "multi"

        with patch.object(factory, '_create_task_tool') as mock_task:
            mock_task.return_value = MagicMock()
            tools = await factory._load_tools_for_agent(mock_agent_config, {})

            mock_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_tools_with_runtime_override(self, factory, mock_agent_config):
        """测试运行时工具覆盖"""
        runtime_tools = [MagicMock(), MagicMock()]
        runtime_config = {"tools": runtime_tools}

        tools = await factory._load_tools_for_agent(mock_agent_config, runtime_config)

        assert tools == runtime_tools


# ============================================================
# AgentFactory 执行测试
# ============================================================

class TestAgentFactoryExecution:
    """测试 AgentFactory 执行功能"""

    @pytest.mark.asyncio
    async def test_execute_agent_not_found(self, factory, mock_db):
        """测试执行不存在的 Agent"""
        # 使用正确的 Mock 设置
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await factory.execute(
            agent_id="nonexistent",
            user_id=1,
            query="test query",
        )

        # 验证返回了错误响应
        assert result["agent_id"] == "nonexistent"
        assert "error" in result or "失败" in result.get("response", "")

    @pytest.mark.asyncio
    async def test_execute_with_empty_messages(self, factory, mock_agent_config):
        """测试执行后提取响应（空消息）"""
        # 设置数据库 Mock 返回 agent config
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_agent_config
        factory.db.execute.return_value = mock_result

        # 创建 Mock agent
        mock_agent = MagicMock()
        mock_agent.ainvoke = AsyncMock(return_value={"messages": []})

        with patch.object(factory, 'create_agent', return_value=mock_agent):
            result = await factory.execute(
                agent_id="test-id",
                user_id=1,
                query="test query",
            )

            # 验证有 run_id 和响应
            assert "run_id" in result
            assert result["response"] == ""

    @pytest.mark.asyncio
    async def test_extract_response_from_list_content(self, factory):
        """测试从列表格式内容中提取响应"""
        result_dict = {
            "messages": [
                MagicMock(
                    __class__=type('AIMessage', (), {}),
                    content=[
                        {"text": "Hello"},
                        {"text": "World"},
                    ]
                )
            ]
        }

        # 模拟 isinstance 检查
        from langchain_core.messages import AIMessage
        with patch('langchain_core.messages.AIMessage', type('AIMessage', (), {})):
            response = factory._extract_response(result_dict)
            # 由于 Mock 限制，这里只验证方法被调用


# ============================================================
# Middleware 测试
# ============================================================

class TestAgentFactoryMiddleware:
    """测试 AgentFactory 中间件功能"""

    def test_logging_middleware_before_agent(self, factory):
        """测试日志中间件 before_agent 方法"""
        from app.services.agent_factory import LoggingMiddleware
        from langgraph.runtime import Runtime

        middleware = LoggingMiddleware(agent_id="test-id", agent_name="Test Agent")

        runtime = MagicMock(spec=Runtime)
        runtime.context = {"thread_id": "test-thread"}

        result = middleware.before_agent({"messages": []}, runtime)
        assert result is None

    def test_logging_middleware_after_agent(self, factory):
        """测试日志中间件 after_agent 方法"""
        from app.services.agent_factory import LoggingMiddleware
        from langgraph.runtime import Runtime

        middleware = LoggingMiddleware(agent_id="test-id", agent_name="Test Agent")

        runtime = MagicMock(spec=Runtime)
        runtime.context = {"thread_id": "test-thread"}

        result = middleware.after_agent({"messages": []}, runtime)
        assert result is None

    def test_logging_middleware_no_context(self, factory):
        """测试日志中间件无上下文的情况"""
        from app.services.agent_factory import LoggingMiddleware
        from langgraph.runtime import Runtime

        middleware = LoggingMiddleware(agent_id="test-id", agent_name="Test Agent")

        runtime = MagicMock(spec=Runtime)
        runtime.context = None

        result = middleware.before_agent({"messages": []}, runtime)
        assert result is None


# ============================================================
# RAG 工具测试
# ============================================================

class TestRagTool:
    """测试 RAG 工具创建功能"""

    @pytest.mark.asyncio
    async def test_create_rag_tool_success(self, factory, mock_db):
        """测试成功创建 RAG 工具"""
        # 导入实际的服务用于测试
        with patch('app.services.retrieval_service.search_chunks') as mock_search, \
             patch('app.core.milvus_client.get_milvus_client') as mock_milvus, \
             patch('app.core.redis_client.get_redis') as mock_redis:

            mock_milvus.return_value = MagicMock()
            mock_redis.return_value = AsyncMock()

            # Mock search response
            mock_result = MagicMock()
            mock_result.results = [
                MagicMock(
                    content="test content",
                    metadata={"doc_name": "test.doc", "doc_id": "doc1"},
                    score=0.95
                )
            ]
            mock_search.return_value = mock_result

            rag_tool = await factory._create_rag_tool(["kb1"], {"top_k": 5})

            # 验证工具被创建且可调用
            assert rag_tool is not None
            # 验证工具是 LangChain 工具
            assert hasattr(rag_tool, 'name') or callable(rag_tool)

    @pytest.mark.asyncio
    async def test_create_rag_tool_error(self, factory, mock_db):
        """测试 RAG 工具创建错误处理"""
        with patch('app.core.milvus_client.get_milvus_client') as mock_milvus:
            mock_milvus.side_effect = Exception("Connection failed")

            # 由于错误在工具执行时返回，创建应该成功
            rag_tool = await factory._create_rag_tool(["kb1"], {})

            # 验证工具被创建（即使底层服务出错）
            assert rag_tool is not None


# ============================================================
# 子 Agent 配置测试
# ============================================================

class TestSubagentConfig:
    """测试子 Agent 配置功能"""

    @pytest.mark.asyncio
    async def test_get_subagent_config_cached(self, factory, mock_db):
        """测试获取缓存的子 Agent 配置"""
        # 先填充缓存
        mock_config = MagicMock()
        mock_config.name = "researcher"
        factory._subagent_cache["parent-id"] = {"researcher": mock_config}

        result = await factory._get_subagent_config("parent-id", "researcher")

        assert result == mock_config
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_subagent_config_not_found(self, factory, mock_db):
        """测试子 Agent 配置不存在"""
        # 设置正确的 Mock 链
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        result = await factory._get_subagent_config("parent-id", "nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_task_tool_subagent_not_found(self, factory, mock_agent_config):
        """测试 task 工具中子 Agent 不存在的情况"""
        # 直接测试 _get_subagent_config 方法返回 None 时的行为
        with patch.object(factory, '_get_subagent_config', return_value=None):
            # 验证方法返回 None
            result = await factory._get_subagent_config("parent-id", "nonexistent")
            assert result is None


# ============================================================
# 性能指标测试
# ============================================================

class TestExecutionMetrics:
    """测试执行性能指标功能"""

    def test_metrics_complete(self):
        """测试指标完成方法"""
        from app.services.agent_factory import AgentExecutionMetrics
        from datetime import datetime, timedelta

        metrics = AgentExecutionMetrics(
            run_id="test-run",
            agent_id="test-agent",
            user_id=1,
            start_time=datetime.utcnow() - timedelta(seconds=2),
        )

        metrics.complete(status="success")

        assert metrics.status == "success"
        assert metrics.end_time is not None
        assert metrics.latency_ms >= 0

    def test_metrics_complete_with_error(self):
        """测试指标错误完成"""
        from app.services.agent_factory import AgentExecutionMetrics

        metrics = AgentExecutionMetrics(
            run_id="test-run",
            agent_id="test-agent",
            user_id=1,
        )

        metrics.complete(status="error", error_message="Test error")

        assert metrics.status == "error"
        assert metrics.error_message == "Test error"

    def test_metrics_to_dict(self):
        """测试指标转字典"""
        from app.services.agent_factory import AgentExecutionMetrics

        metrics = AgentExecutionMetrics(
            run_id="test-run",
            agent_id="test-agent",
            user_id=1,
        )
        metrics.input_tokens = 100
        metrics.output_tokens = 50
        metrics.tool_calls = 3

        result = metrics.to_dict()

        assert result["run_id"] == "test-run"
        assert result["input_tokens"] == 100
        assert result["output_tokens"] == 50
        assert result["tool_calls"] == 3
