"""
Agent 执行链集成测试
验证完整的执行链路：API → Orchestration → Factory → Agent
"""
import asyncio
import sys
import uuid
from datetime import datetime

sys.path.insert(0, '.')

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select

from app.models.agent import AgentConfig
from app.models.user import User
from app.services.agent_factory import AgentFactory
from app.services.agent_orchestration_service import AgentOrchestrationService

DATABASE_URL = "postgresql+asyncpg://postgres:postgres123@100.4.14.19:5432/rag_db"


class MockModelGateway:
    """模拟模型网关"""

    async def get_model_by_name(self, name: str):
        from app.schemas.chat import ModelConfig
        return ModelConfig(
            provider="local_qwen",
            model="qwen3.5-397b-a17b",
            temperature=0.7,
            max_tokens=4096,
            base_url="http://100.4.14.19:8000",
            api_key="not-needed",
        )


class MockSkillRegistry:
    """模拟技能注册表"""

    def get_tool(self, skill_id: str):
        return None


async def test_full_execution_chain():
    """测试完整执行链"""
    print("=" * 70)
    print("Agent 执行链集成测试")
    print("=" * 70)

    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # 准备测试数据
    test_agent_id = str(uuid.uuid4())
    user_id = 1
    tenant_id = "test"

    async with async_session() as session:
        # ========== Step 1: 创建测试 Agent 到数据库 ==========
        print("\n[Step 1] 创建测试 Agent 到数据库...")
        try:
            agent = AgentConfig(
                id=test_agent_id,
                user_id=user_id,
                tenant_id=tenant_id,
                name="执行链测试助手",
                description="用于测试完整执行链的 Agent",
                agent_type="single",
                default_model_config={
                    "provider": "local_qwen",
                    "model": "qwen3.5-397b-a17b",
                    "temperature": 0.7,
                    "max_tokens": 4096,
                },
                system_prompt="你是一个测试助手。请简洁回答，不要使用工具。",
                enabled_skills=[],
                mcp_servers=[],
                status="active",
                is_public=False,
            )

            session.add(agent)
            await session.commit()
            print(f"✓ Agent 创建成功，ID: {test_agent_id}")

        except Exception as e:
            await session.rollback()
            print(f"✗ Agent 创建失败：{e}")
            return

        # ========== Step 2: 测试 Factory.create_agent() ==========
        print("\n[Step 2] 测试 Factory.create_agent()...")
        try:
            mock_gateway = MockModelGateway()
            mock_registry = MockSkillRegistry()

            factory = AgentFactory(
                db=session,
                model_gateway=mock_gateway,
                skill_registry=mock_registry,
            )

            # 从数据库获取配置
            result = await session.execute(
                select(AgentConfig).where(AgentConfig.id == test_agent_id)
            )
            agent_config = result.scalar_one_or_none()

            if not agent_config:
                print("✗ 无法从数据库获取 Agent 配置")
                return

            agent = await factory.create_agent(agent_config, runtime_config={})

            print(f"✓ Agent 创建成功")
            print(f"  类型：{type(agent).__name__}")
            print(f"  图已编译：{hasattr(agent, 'compile')}")

        except Exception as e:
            print(f"✗ Factory.create_agent() 失败：{e}")
            import traceback
            traceback.print_exc()
            return

        # ========== Step 3: 测试 Factory.execute() ==========
        print("\n[Step 3] 测试 Factory.execute() 执行...")
        try:
            result = await factory.execute(
                agent_id=test_agent_id,
                user_id=user_id,
                query="你好，请用一句话介绍你自己。",
                runtime_config={},
            )

            print(f"✓ Factory.execute() 成功")
            print(f"  run_id: {result['run_id'][:8]}...")
            print(f"  agent_type: {result['agent_type']}")
            print(f"  response 长度：{len(result['response'])}")
            print(f"  response 预览：{result['response'][:100]}...")

        except Exception as e:
            print(f"✗ Factory.execute() 失败：{e}")
            import traceback
            traceback.print_exc()

        # ========== Step 4: 测试 Orchestration.execute_agent() ==========
        print("\n[Step 4] 测试 Orchestration.execute_agent()...")
        try:
            mock_gateway = MockModelGateway()
            mock_registry = MockSkillRegistry()

            orchestration = AgentOrchestrationService(
                db=session,
                model_gateway=mock_gateway,
                skill_registry=mock_registry,
            )

            result = await orchestration.execute_agent(
                agent_id=test_agent_id,
                user_id=user_id,
                query="你好，请用一句话介绍你自己。",
                runtime_config={},
            )

            print(f"✓ Orchestration.execute_agent() 成功")
            print(f"  run_id: {result['run_id'][:8]}...")
            print(f"  response 长度：{len(result['response'])}")

        except Exception as e:
            print(f"✗ Orchestration.execute_agent() 失败：{e}")
            import traceback
            traceback.print_exc()

        # ========== Step 5: 测试流式执行 ==========
        print("\n[Step 5] 测试流式执行 execute_agent_stream()...")
        try:
            mock_gateway = MockModelGateway()
            mock_registry = MockSkillRegistry()

            orchestration = AgentOrchestrationService(
                db=session,
                model_gateway=mock_gateway,
                skill_registry=mock_registry,
            )

            chunks = []
            async for chunk in orchestration.execute_agent_stream(
                agent_id=test_agent_id,
                user_id=user_id,
                query="你好，请用一句话介绍你自己。",
                runtime_config={},
            ):
                chunks.append(chunk)

            print(f"✓ 流式执行成功")
            print(f"  收到 chunk 数：{len(chunks)}")
            print(f"  总长度：{sum(len(c) for c in chunks)}")
            if chunks:
                print(f"  内容预览：{''.join(chunks)[:100]}...")

        except Exception as e:
            print(f"✗ 流式执行失败：{e}")
            import traceback
            traceback.print_exc()

        # ========== 清理测试数据 ==========
        print("\n[清理] 删除测试 Agent...")
        try:
            from sqlalchemy import delete
            await session.execute(
                delete(AgentConfig).where(AgentConfig.id == test_agent_id)
            )
            await session.commit()
            print(f"✓ 测试数据已清理")
        except Exception as e:
            await session.rollback()
            print(f"✗ 清理失败：{e}")

    print("\n" + "=" * 70)
    print("执行链测试完成")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_full_execution_chain())
