"""
MCP 工具集成和技能工具加载测试
测试 agent_factory.py 中的新增功能：
1. _load_mcp_tools - MCP 工具加载
2. _load_skill_tools - 技能工具加载
"""
import pytest
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, '.')

from sqlalchemy.ext.asyncio import AsyncSession
from app.services.agent_factory import AgentFactory


# ============================================================
# Mock 对象
# ============================================================

class MockModelGateway:
    """模拟模型网关"""

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


class MockSkillRegistry:
    """模拟技能注册表"""

    def get_tool(self, skill_id: str):
        return None


# ============================================================
# MCP 工具加载测试
# ============================================================

class TestLoadMcpTools:
    """测试 _load_mcp_tools 方法"""

    @pytest.fixture
    async def factory(self):
        """创建 AgentFactory 实例"""
        mock_db = AsyncMock(spec=AsyncSession)
        model_gateway = MockModelGateway()
        skill_registry = MockSkillRegistry()

        return AgentFactory(mock_db, model_gateway, skill_registry)

    @pytest.mark.asyncio
    async def test_load_mcp_tools_empty_servers(self, factory):
        """测试加载空的 MCP 服务器列表"""
        tools = await factory._load_mcp_tools([])
        assert tools == []

    @pytest.mark.asyncio
    async def test_load_mcp_tools_kb_server(self, factory):
        """测试加载知识库 MCP 工具"""
        tools = await factory._load_mcp_tools(["kb"])
        assert len(tools) == 4
        tool_names = [t.name for t in tools]
        assert "mcp_kb_list" in tool_names
        assert "mcp_kb_get" in tool_names
        assert "mcp_kb_create" in tool_names
        assert "mcp_kb_delete" in tool_names

    @pytest.mark.asyncio
    async def test_load_mcp_tools_model_server(self, factory):
        """测试加载模型 MCP 工具"""
        tools = await factory._load_mcp_tools(["model"])
        assert len(tools) == 5
        tool_names = [t.name for t in tools]
        assert "mcp_model_list" in tool_names
        assert "mcp_model_get" in tool_names
        assert "mcp_model_create" in tool_names
        assert "mcp_model_update" in tool_names
        assert "mcp_model_delete" in tool_names

    @pytest.mark.asyncio
    async def test_load_mcp_tools_prompt_server(self, factory):
        """测试加载提示词 MCP 工具"""
        tools = await factory._load_mcp_tools(["prompt"])
        assert len(tools) == 5
        tool_names = [t.name for t in tools]
        assert "mcp_prompt_list" in tool_names
        assert "mcp_prompt_get" in tool_names
        assert "mcp_prompt_create" in tool_names
        assert "mcp_prompt_update" in tool_names
        assert "mcp_prompt_delete" in tool_names

    @pytest.mark.asyncio
    async def test_load_mcp_tools_agent_server(self, factory):
        """测试加载 Agent MCP 工具"""
        tools = await factory._load_mcp_tools(["agent"])
        assert len(tools) == 5
        tool_names = [t.name for t in tools]
        assert "mcp_agent_list" in tool_names
        assert "mcp_agent_get" in tool_names
        assert "mcp_agent_create" in tool_names
        assert "mcp_agent_update" in tool_names
        assert "mcp_agent_delete" in tool_names

    @pytest.mark.asyncio
    async def test_load_mcp_tools_all_servers(self, factory):
        """测试加载所有 MCP 工具"""
        tools = await factory._load_mcp_tools(["all"])
        # 4 (kb) + 5 (model) + 5 (prompt) + 5 (agent) = 19
        assert len(tools) == 19

    @pytest.mark.asyncio
    async def test_load_mcp_tools_multiple_servers(self, factory):
        """测试加载多个 MCP 服务器"""
        tools = await factory._load_mcp_tools(["kb", "model"])
        assert len(tools) == 9  # 4 + 5


# ============================================================
# 技能工具加载测试
# ============================================================

class TestLoadSkillTools:
    """测试 _load_skill_tools 方法"""

    @pytest.fixture
    async def factory(self):
        """创建 AgentFactory 实例"""
        mock_db = AsyncMock(spec=AsyncSession)
        model_gateway = MockModelGateway()
        skill_registry = MockSkillRegistry()

        return AgentFactory(mock_db, model_gateway, skill_registry)

    @pytest.mark.asyncio
    async def test_load_skill_tools_empty_skills(self, factory):
        """测试加载空的技能列表"""
        tools = await factory._load_skill_tools([])
        assert tools == []

    @pytest.mark.asyncio
    async def test_load_skill_tools_kb_skill(self, factory):
        """测试加载知识库技能"""
        tools = await factory._load_skill_tools(["kb"])
        assert len(tools) == 6
        tool_names = [t.name for t in tools]
        assert "skill_kb_list" in tool_names
        assert "skill_kb_get" in tool_names
        assert "skill_kb_create" in tool_names
        assert "skill_kb_delete" in tool_names
        assert "skill_doc_list" in tool_names
        assert "skill_doc_delete" in tool_names

    @pytest.mark.asyncio
    async def test_load_skill_tools_kb_skill_aliases(self, factory):
        """测试知识库技能别名 (knowledge_base, knowledge)"""
        for skill_name in ["knowledge_base", "knowledge"]:
            tools = await factory._load_skill_tools([skill_name])
            assert len(tools) == 6

    @pytest.mark.asyncio
    async def test_load_skill_tools_model_skill(self, factory):
        """测试加载模型技能"""
        tools = await factory._load_skill_tools(["model"])
        assert len(tools) == 4
        tool_names = [t.name for t in tools]
        assert "skill_model_list" in tool_names
        assert "skill_provider_list" in tool_names
        assert "skill_model_get" in tool_names
        assert "skill_model_test" in tool_names

    @pytest.mark.asyncio
    async def test_load_skill_tools_model_skill_aliases(self, factory):
        """测试模型技能别名 (models, llm)"""
        for skill_name in ["models", "llm"]:
            tools = await factory._load_skill_tools([skill_name])
            assert len(tools) == 4

    @pytest.mark.asyncio
    async def test_load_skill_tools_prompt_skill(self, factory):
        """测试加载提示词技能"""
        tools = await factory._load_skill_tools(["prompt"])
        assert len(tools) == 5
        tool_names = [t.name for t in tools]
        assert "skill_prompt_list" in tool_names
        assert "skill_prompt_get" in tool_names
        assert "skill_prompt_create" in tool_names
        assert "skill_prompt_tests" in tool_names
        assert "skill_prompt_run_test" in tool_names

    @pytest.mark.asyncio
    async def test_load_skill_tools_prompt_skill_aliases(self, factory):
        """测试提示词技能别名 (prompts, prompt_engineering)"""
        for skill_name in ["prompts", "prompt_engineering"]:
            tools = await factory._load_skill_tools([skill_name])
            assert len(tools) == 5

    @pytest.mark.asyncio
    async def test_load_skill_tools_agent_skill(self, factory):
        """测试加载 Agent 技能"""
        tools = await factory._load_skill_tools(["agent"])
        assert len(tools) == 6
        tool_names = [t.name for t in tools]
        assert "skill_agent_list" in tool_names
        assert "skill_agent_get" in tool_names
        assert "skill_agent_create" in tool_names
        assert "skill_agent_update" in tool_names
        assert "skill_agent_delete" in tool_names
        assert "skill_agent_plaza" in tool_names

    @pytest.mark.asyncio
    async def test_load_skill_tools_agent_skill_aliases(self, factory):
        """测试 Agent 技能别名 (agents, bot, bots)"""
        for skill_name in ["agents", "bot", "bots"]:
            tools = await factory._load_skill_tools([skill_name])
            assert len(tools) == 6

    @pytest.mark.asyncio
    async def test_load_skill_tools_multiple_skills(self, factory):
        """测试加载多个技能"""
        tools = await factory._load_skill_tools(["kb", "model"])
        assert len(tools) == 10  # 6 + 4

    @pytest.mark.asyncio
    async def test_load_skill_tools_all_skills(self, factory):
        """测试加载所有技能"""
        tools = await factory._load_skill_tools(["kb", "model", "prompt", "agent"])
        # 6 (kb) + 4 (model) + 5 (prompt) + 6 (agent) = 21
        assert len(tools) == 21

    @pytest.mark.asyncio
    async def test_load_skill_tools_unknown_skill(self, factory, caplog):
        """测试加载未知技能"""
        tools = await factory._load_skill_tools(["unknown_skill"])
        assert tools == []
        # 验证日志中是否有警告
        assert "Unknown skill" in caplog.text


# ============================================================
# 集成测试
# ============================================================

class TestToolLoadingIntegration:
    """工具加载集成测试"""

    @pytest.fixture
    async def factory(self):
        """创建 AgentFactory 实例"""
        mock_db = AsyncMock(spec=AsyncSession)
        model_gateway = MockModelGateway()
        skill_registry = MockSkillRegistry()

        return AgentFactory(mock_db, model_gateway, skill_registry)

    @pytest.mark.asyncio
    async def test_mcp_and_skills_combined(self, factory):
        """测试 MCP 工具和技能工具同时加载"""
        mcp_tools = await factory._load_mcp_tools(["kb"])
        skill_tools = await factory._load_skill_tools(["model"])

        assert len(mcp_tools) == 4
        assert len(skill_tools) == 4

        # 验证工具名称不重复
        mcp_names = {t.name for t in mcp_tools}
        skill_names = {t.name for t in skill_tools}
        assert mcp_names.isdisjoint(skill_names)
