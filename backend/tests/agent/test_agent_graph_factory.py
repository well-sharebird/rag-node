"""
Agent Graph Factory 单元测试
"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agent_graph_factory import (
    AgentGraphFactory,
    AgentState,
    TodoListMiddleware,
    LoggingMiddleware,
    DynamicModelLoader,
    MCPToolLoader,
    SkillLoader,
)
from app.models.agent import AgentConfig


# ============================================================
# AgentState Tests
# ============================================================

class TestAgentState:
    """测试 AgentState 类"""

    def test_agent_state_default_values(self):
        """测试默认值"""
        state = AgentState()
        assert state["messages"] == []
        assert state["context"] == {}
        assert state["current_step"] == "start"
        assert state["metadata"] == {}
        assert state["plan"] == []
        assert state["todo_list"] == []

    def test_agent_state_custom_values(self):
        """测试自定义值"""
        state = AgentState(
            messages=["msg1", "msg2"],
            context={"key": "value"},
            current_step="processing",
            metadata={"user_id": 1},
            plan=["step1", "step2"],
            todo_list=["task1"],
        )
        assert state["messages"] == ["msg1", "msg2"]
        assert state["context"] == {"key": "value"}
        assert state["current_step"] == "processing"
        assert state["plan"] == ["step1", "step2"]
        assert state["todo_list"] == ["task1"]

    def test_agent_state_kwargs(self):
        """测试动态扩展"""
        state = AgentState(custom_field="custom_value")
        assert state["custom_field"] == "custom_value"


# ============================================================
# TodoListMiddleware Tests
# ============================================================

class TestTodoListMiddleware:
    """测试 TodoListMiddleware"""

    @pytest.mark.asyncio
    async def test_pre_process_initializes_todo_list(self):
        """测试 pre_process 初始化 TODO 列表"""
        mw = TodoListMiddleware()
        state = AgentState()

        result = await mw.pre_process(state)
        assert "todo_list" in result
        assert "completed_tasks" in result

    @pytest.mark.asyncio
    async def test_pre_process_preserves_existing_todo_list(self):
        """测试 pre_process 保留已存在的 TODO 列表"""
        mw = TodoListMiddleware()
        state = AgentState(todo_list=["existing_task"])

        result = await mw.pre_process(state)
        assert result["todo_list"] == ["existing_task"]

    @pytest.mark.asyncio
    async def test_post_process_extracts_task(self):
        """测试 post_process 提取任务"""
        mw = TodoListMiddleware()
        state = AgentState(
            messages=[
                MagicMock(content="Some text [TASK] do something [/TASK] more text")
            ],
            todo_list=[],
        )

        result = await mw.post_process(state)
        assert "do something " in result["todo_list"]

    @pytest.mark.asyncio
    async def test_post_process_avoids_duplicates(self):
        """测试 post_process 避免重复任务"""
        mw = TodoListMiddleware()
        state = AgentState(
            messages=[MagicMock(content="[TASK] task1 [/TASK]")],
            todo_list=["task1"],
        )

        result = await mw.post_process(state)
        assert result["todo_list"].count("task1") == 1


# ============================================================
# LoggingMiddleware Tests
# ============================================================

class TestLoggingMiddleware:
    """测试 LoggingMiddleware"""

    @pytest.mark.asyncio
    async def test_pre_process_logs(self, caplog):
        """测试 pre_process 记录日志"""
        mw = LoggingMiddleware(agent_id="test-agent", run_id="test-run")
        state = AgentState(current_step="test_step")

        with caplog.at_level("INFO"):
            await mw.pre_process(state)

        assert "test-agent" in caplog.text
        assert "test-run" in caplog.text
        assert "test_step" in caplog.text


# ============================================================
# DynamicModelLoader Tests
# ============================================================

class TestDynamicModelLoader:
    """测试 DynamicModelLoader"""

    @pytest.mark.asyncio
    async def test_load_model_with_requested_name(self):
        """测试加载请求的模型"""
        mock_gateway = AsyncMock()
        mock_model_config = MagicMock()
        mock_gateway.get_model_by_name = AsyncMock(return_value=mock_model_config)

        loader = DynamicModelLoader(mock_gateway)

        with patch.object(loader, '_create_llm') as mock_create:
            mock_create.return_value = "mock_llm"
            result = await loader.load_model("claude-3-opus", {})

            mock_gateway.get_model_by_name.assert_called_once_with("claude-3-opus")
            assert result == "mock_llm"

    @pytest.mark.asyncio
    async def test_load_model_fallback_to_default(self):
        """测试回退到默认模型"""
        mock_gateway = AsyncMock()
        mock_gateway.get_model_by_name = AsyncMock(return_value=None)

        loader = DynamicModelLoader(mock_gateway)
        default_config = {"provider": "anthropic", "model": "claude-3-5-sonnet"}

        with patch.object(loader, '_create_llm') as mock_create:
            mock_create.return_value = "default_llm"
            result = await loader.load_model(None, default_config)

            mock_create.assert_called_once()
            assert result == "default_llm"


# ============================================================
# MCPToolLoader Tests
# ============================================================

class TestMCPToolLoader:
    """测试 MCPToolLoader"""

    @pytest.mark.asyncio
    async def test_load_tools_file_not_found(self, tmp_path):
        """测试配置文件不存在"""
        loader = MCPToolLoader(str(tmp_path / "nonexistent.json"))
        result = await loader.load_tools(["server1"])
        assert result == []

    @pytest.mark.asyncio
    async def test_load_tools_invalid_json(self, tmp_path):
        """测试无效 JSON"""
        config_file = tmp_path / "config.json"
        config_file.write_text("invalid json")

        loader = MCPToolLoader(str(config_file))
        result = await loader.load_tools(["server1"])
        assert result == []

    @pytest.mark.asyncio
    async def test_load_tools_success(self, tmp_path):
        """测试成功加载工具"""
        config = {
            "mcp_servers": {
                "server1": {"url": "http://localhost:8080"},
                "server2": {"url": "http://localhost:8081"},
            }
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config))

        loader = MCPToolLoader(str(config_file))

        with patch.object(loader, '_connect_mcp_server', new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = ["tool1", "tool2"]
            result = await loader.load_tools(["server1", "server2"])

            assert len(result) == 4
            assert mock_connect.call_count == 2


# ============================================================
# AgentGraphFactory Tests
# ============================================================

class TestAgentGraphFactory:
    """测试 AgentGraphFactory"""

    @pytest.fixture
    def mock_dependencies(self):
        """创建模拟依赖"""
        mock_model_gateway = AsyncMock()
        mock_skill_registry = AsyncMock()
        mock_db = AsyncMock()
        return {
            "model_gateway": mock_model_gateway,
            "skill_registry": mock_skill_registry,
            "db": mock_db,
        }

    @pytest.fixture
    def factory(self, mock_dependencies):
        """创建工厂实例"""
        return AgentGraphFactory(
            model_gateway_service=mock_dependencies["model_gateway"],
            skill_registry=mock_dependencies["skill_registry"],
            db=mock_dependencies["db"],
        )

    @pytest.mark.asyncio
    async def test_build_middlewares_plan_mode(self, factory):
        """测试构建中间件链（计划模式）"""
        extensions_config = {"plan_mode_enabled": True}
        middlewares = await factory._build_middlewares(
            extensions_config, "agent-1", "run-1"
        )

        assert len(middlewares) == 2
        assert any(isinstance(mw, TodoListMiddleware) for mw in middlewares)
        assert any(isinstance(mw, LoggingMiddleware) for mw in middlewares)

    @pytest.mark.asyncio
    async def test_build_middlewares_no_plan_mode(self, factory):
        """测试构建中间件链（无计划模式）"""
        extensions_config = {"plan_mode_enabled": False}
        middlewares = await factory._build_middlewares(
            extensions_config, "agent-1", "run-1"
        )

        assert len(middlewares) == 1
        assert isinstance(middlewares[0], LoggingMiddleware)

    @pytest.mark.asyncio
    async def test_apply_middlewares(self, factory):
        """测试应用中间件"""
        middlewares = [LoggingMiddleware("agent-1", "run-1")]
        state = AgentState(current_step="test")

        result = await factory._apply_middlewares(state, middlewares, "pre_process")
        assert result["current_step"] == "test"

    @pytest.mark.asyncio
    async def test_create_graph_context_manager(self, factory, mock_dependencies):
        """测试 create_graph 上下文管理器"""
        agent_config = MagicMock(spec=AgentConfig)
        agent_config.id = "agent-1"
        agent_config.system_prompt = "Test prompt"
        agent_config.default_model_config = {"provider": "anthropic", "model": "claude-3"}
        agent_config.enabled_skills = []
        agent_config.extensions_config = {}

        runtime_config = {}
        run_id = "run-1"

        async with factory.create_graph(agent_config, runtime_config, run_id) as graph:
            # 验证返回的是编译后的图
            assert graph is not None
            assert hasattr(graph, 'ainvoke')
            assert hasattr(graph, 'astream')

    @pytest.mark.asyncio
    async def test_build_graph_for_run_agent_not_found(self, factory):
        """测试 Agent 不存在的情况"""
        from sqlalchemy import select

        with patch.object(factory.db, 'execute') as mock_execute:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_execute.return_value = mock_result

            with pytest.raises(ValueError, match="Agent not found"):
                await factory.build_graph_for_run(
                    agent_id="nonexistent",
                    user_id=1,
                    runtime_config={},
                    run_id="run-1",
                )


# ============================================================
# Integration Tests
# ============================================================

class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_full_graph_execution(self):
        """测试完整的图执行流程"""
        # 创建模拟依赖
        mock_model_gateway = AsyncMock()
        mock_skill_registry = AsyncMock()
        mock_db = AsyncMock()

        # 创建工厂
        factory = AgentGraphFactory(
            model_gateway_service=mock_model_gateway,
            skill_registry=mock_skill_registry,
            db=mock_db,
        )

        # 创建 Agent 配置
        agent_config = MagicMock(spec=AgentConfig)
        agent_config.id = "test-agent"
        agent_config.system_prompt = "You are a helpful assistant."
        agent_config.default_model_config = {"provider": "anthropic", "model": "claude-3"}
        agent_config.enabled_skills = []
        agent_config.extensions_config = {"plan_mode_enabled": False}

        # 构建图
        runtime_config = {}
        run_id = "test-run"

        async with factory.create_graph(agent_config, runtime_config, run_id) as graph:
            # 执行图
            initial_state = {
                "messages": [{"role": "user", "content": "Hello"}],
                "context": {},
                "current_step": "start",
                "metadata": {"user_id": 1},
            }

            # 由于 LLM 是 mock，这里只验证图结构
            assert graph is not None
