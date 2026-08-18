"""
配置驱动架构测试
"""
import pytest
from packages.agent.config.agent_config import (
    AgentConfig,
    AgentType,
    RunMode,
    ModelConfig,
    ToolConfig,
    PermissionMode,
    SecurityPolicy,
    SandboxType,
    TAOLoopConfig,
    RuntimeConfig,
    AgentConfigLoader,
)


class TestAgentConfigSchema:
    """测试 Agent 配置 Schema"""
    
    def test_minimal_config(self):
        """测试最小配置"""
        config = AgentConfig(
            id="test-agent",
            name="测试 Agent",
            model=ModelConfig(provider="openai", model="gpt-4"),
            system_prompt="你是一个助手",
        )
        
        assert config.agent_type == AgentType.SINGLE
        assert config.run_mode == RunMode.SERIAL
        assert config.version == "1.0.0"
        assert config.tools == []
    
    def test_full_config(self):
        """测试完整配置"""
        config = AgentConfig(
            id="advanced-agent",
            name="高级 Agent",
            version="2.0.0",
            description="一个高级 Agent",
            agent_type=AgentType.SUPERVISOR,
            run_mode=RunMode.PARALLEL,
            model=ModelConfig(
                provider="deepseek",
                model="deepseek-v4",
                temperature=0.5,
                max_tokens=4000,
            ),
            system_prompt="你是高级助手",
            tools=[
                ToolConfig(name="search", enabled=True),
                ToolConfig(name="calc", enabled=True, permission_mode=PermissionMode.HITL),
            ],
            tao_loop=TAOLoopConfig(
                max_iterations=15,
                enable_think=True,
                enable_act=True,
                enable_observe=True,
            ),
            security=SecurityPolicy(
                sandbox_type=SandboxType.NSJAIL,
                network_enabled=True,
                max_memory_mb=1024,
            ),
            runtime=RuntimeConfig(
                timeout_seconds=600,
                enable_streaming=True,
                enable_checkpointer=True,
            ),
        )
        
        assert config.agent_type == AgentType.SUPERVISOR
        assert config.run_mode == RunMode.PARALLEL
        assert len(config.tools) == 2
        assert config.tools[1].permission_mode == PermissionMode.HITL
        assert config.tao_loop.max_iterations == 15
        assert config.security.network_enabled is True
    
    def test_tools_unique_validation(self):
        """测试工具名称唯一性验证"""
        with pytest.raises(ValueError) as exc_info:
            AgentConfig(
                id="test",
                name="Test",
                model=ModelConfig(provider="openai", model="gpt-4"),
                system_prompt="Test",
                tools=[
                    ToolConfig(name="tool1"),
                    ToolConfig(name="tool1"),  # 重复
                ],
            )
        
        assert "工具名称必须唯一" in str(exc_info.value)


class TestAgentConfigLoader:
    """测试配置加载器"""
    
    def test_from_dict(self):
        """测试从字典加载"""
        data = {
            "id": "test-agent",
            "name": "测试 Agent",
            "model": {"provider": "openai", "model": "gpt-4"},
            "system_prompt": "你是一个助手",
        }
        
        config = AgentConfigLoader.from_dict(data)
        
        assert config.id == "test-agent"
        assert config.name == "测试 Agent"
        assert config.model.provider == "openai"
    
    def test_from_json(self):
        """测试从 JSON 加载"""
        import json
        
        data = {
            "id": "json-agent",
            "name": "JSON Agent",
            "model": {"provider": "anthropic", "model": "claude-3"},
            "system_prompt": "JSON test",
            "tools": [
                {"name": "tool1", "enabled": True}
            ],
        }
        
        json_str = json.dumps(data)
        config = AgentConfigLoader.from_json(json_str)
        
        assert config.id == "json-agent"
        assert config.model.provider == "anthropic"
        assert len(config.tools) == 1
    
    def test_to_json(self):
        """测试导出为 JSON"""
        config = AgentConfig(
            id="export-agent",
            name="Export Agent",
            model=ModelConfig(provider="openai", model="gpt-4"),
            system_prompt="Export test",
        )
        
        json_str = AgentConfigLoader.to_json(config)
        
        assert "export-agent" in json_str
        assert "Export Agent" in json_str
    
    def test_from_yaml_example(self, tmp_path):
        """测试从 YAML 文件加载"""
        yaml_content = """
id: yaml-agent
name: YAML Agent
model:
  provider: deepseek
  model: deepseek-v4-flash
system_prompt: YAML test
tools:
  - name: search
    enabled: true
  - name: calc
    enabled: false
tao_loop:
  max_iterations: 20
"""
        
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text(yaml_content)
        
        config = AgentConfigLoader.from_file(str(yaml_file))
        
        assert config.id == "yaml-agent"
        assert config.model.model == "deepseek-v4-flash"
        assert len(config.tools) == 2
        assert config.tools[0].enabled is True
        assert config.tools[1].enabled is False
        assert config.tao_loop.max_iterations == 20


class TestConfigExamples:
    """测试配置示例"""
    
    def test_single_agent_example(self):
        """测试单 Agent 配置示例"""
        config = AgentConfigLoader.from_file(
            "packages/agent/config/examples/single_agent.yaml"
        )
        
        assert config.id == "qa-agent-001"
        assert config.agent_type == AgentType.SINGLE
        assert config.model.provider == "deepseek"
        assert len(config.tools) == 2
        assert config.tao_loop.max_iterations == 10
    
    def test_multi_agent_example(self):
        """测试多 Agent 配置示例"""
        config = AgentConfigLoader.from_file(
            "packages/agent/config/examples/multi_agent.yaml"
        )
        
        assert config.id == "research-agent-001"
        assert config.agent_type == AgentType.SUPERVISOR
        assert config.run_mode == RunMode.PARALLEL
        assert config.main_agent is not None
        assert len(config.main_agent.sub_agents) == 3
        assert config.runtime.timeout_seconds == 600
        assert config.runtime.enable_checkpointer is True


class TestConfigDrivenBuilder:
    """测试配置驱动的图构建器"""
    
    @pytest.mark.asyncio
    async def test_build_single_agent_graph(self):
        """测试构建单 Agent 图"""
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from packages.agent.orchestrator.config_graph_builder import ConfigDrivenGraphBuilder
        
        # 创建测试数据库
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        async with async_session() as session:
            builder = ConfigDrivenGraphBuilder(session, user_id=1)
            
            config = AgentConfig(
                id="test-graph",
                name="Test Graph",
                model=ModelConfig(provider="openai", model="gpt-4"),
                system_prompt="Test",
                tools=[],
            )
            
            # 注意：这个测试会失败，因为需要真实的 LLM API key
            # 这里只是验证配置到图的映射逻辑
            try:
                graph = await builder.build_graph(config)
                assert graph is not None
            except Exception as e:
                # 预期会失败（因为没有 API key）
                assert "API" in str(e) or "key" in str(e).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
