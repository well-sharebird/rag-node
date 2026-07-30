"""
Agent Factory 重构测试
验证统一使用 create_agent() 后的功能
"""
import asyncio
import sys
from datetime import datetime

sys.path.insert(0, '.')

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.agent import AgentConfig
from app.schemas.chat import ModelConfig
from app.services.agent_factory import AgentFactory
from app.services.agent_orchestration_service import AgentOrchestrationService

DATABASE_URL = "postgresql+asyncpg://postgres:postgres123@100.4.14.19:5432/rag_db"

import uuid


class MockModelGateway:
    """模拟模型网关用于测试"""

    async def get_model_by_name(self, name: str):
        return ModelConfig(
            provider="local_qwen",
            model="qwen3.5-397b-a17b",
            temperature=0.7,
            max_tokens=4096,
        )


class MockSkillRegistry:
    """模拟技能注册表用于测试"""

    def get_tool(self, skill_id: str):
        return None


async def test_agent_factory_create_agent():
    """测试 AgentFactory.create_agent() 核心功能"""
    print("=" * 60)
    print("Agent Factory 重构测试 - 统一使用 create_agent()")
    print("=" * 60)

    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        mock_gateway = MockModelGateway()
        mock_registry = MockSkillRegistry()

        factory = AgentFactory(
            db=session,
            model_gateway=mock_gateway,
            skill_registry=mock_registry,
        )

        # 生成测试 UUID
        test_agent_id_1 = str(uuid.uuid4())
        test_agent_id_2 = str(uuid.uuid4())

        # ========== Test 1: 创建简单 Agent ==========
        print("\n[Test 1] 创建简单 Agent（单智能体）...")
        try:
            agent_config = AgentConfig(
                id=test_agent_id_1,
                user_id=1,
                tenant_id="test",
                name="测试助手",
                description="测试用简单 Agent",
                agent_type="single",
                default_model_config={
                    "provider": "local_qwen",
                    "model": "qwen3.5-397b-a17b",
                    "temperature": 0.7,
                },
                system_prompt="你是一个测试助手。",
                enabled_skills=[],
                mcp_servers=[],
            )

            agent = await factory.create_agent(agent_config)

            print(f"✓ Agent 创建成功")
            print(f"  类型：{type(agent).__name__}")
            print(f"  有中间件：{len(factory._build_middlewares(agent_config, {})) > 0}")

        except Exception as e:
            print(f"✗ 创建失败：{e}")
            import traceback
            traceback.print_exc()

        # ========== Test 2: 创建带计划模式的 Agent ==========
        print("\n[Test 2] 创建带计划模式的 Agent...")
        try:
            agent_config = AgentConfig(
                id=test_agent_id_2,
                user_id=1,
                tenant_id="test",
                name="计划模式助手",
                agent_type="single",
                default_model_config={
                    "provider": "local_qwen",
                    "model": "qwen3.5-397b-a17b",
                    "temperature": 0.7,
                },
                system_prompt="你是一个支持计划模式的助手。",
                enabled_skills=[],
                mcp_servers=[],
            )

            agent = await factory.create_agent(
                agent_config,
                runtime_config={"plan_mode": True}
            )

            print(f"✓ 计划模式 Agent 创建成功")

        except Exception as e:
            print(f"✗ 创建失败：{e}")

        # ========== Test 3: 测试 execute 统一入口 ==========
        print("\n[Test 3] 测试 execute 统一入口（需要数据库中有 Agent）...")
        print("  ⊘ 跳过 - 需要数据库中预先存在 Agent")

        # ========== Test 4: 测试 AgentOrchestrationService ==========
        print("\n[Test 4] 测试 AgentOrchestrationService 结构...")
        try:
            orchestration = AgentOrchestrationService(
                db=session,
                model_gateway=mock_gateway,
                skill_registry=mock_registry,
            )

            print(f"✓ AgentOrchestrationService 创建成功")
            print(f"  使用 AgentFactory: {orchestration.agent_factory is not None}")

        except Exception as e:
            print(f"✗ 创建失败：{e}")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_agent_factory_create_agent())
