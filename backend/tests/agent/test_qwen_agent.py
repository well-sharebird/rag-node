"""
测试 Qwen3.5 测试助手 Agent
"""
import asyncio
import sys
from datetime import datetime

sys.path.insert(0, '.')

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select

from packages.agent.models.agent import AgentConfig
from app.services.agent_factory import AgentFactory

DATABASE_URL = "postgresql+asyncpg://postgres:postgres123@100.4.14.19:5432/rag_db"


class MockModelGateway:
    """模拟模型网关"""

    async def get_model_by_name(self, name: str):
        from packages.agent.schemas.chat import ModelConfig
        # 返回 Qwen3.5 配置
        return ModelConfig(
            provider="local_qwen",
            model="qwen3.5-397b-a17b",
            temperature=0.7,
            max_tokens=4096,
            api_url="http://100.4.14.19:8000",
            api_key="not-needed",
        )


class MockSkillRegistry:
    """模拟技能注册表"""

    def get_tool(self, skill_id: str):
        return None


async def test_qwen_agent():
    """测试 Qwen3.5 测试助手 Agent"""
    print("=" * 70)
    print("Qwen3.5 测试助手 Agent 测试")
    print("=" * 70)

    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # 查找名为 "Qwen3.5 测试助手" 的 Agent
        print("\n[Step 1] 查找 Qwen3.5 测试助手 Agent...")
        result = await session.execute(
            select(AgentConfig).where(AgentConfig.name == "Qwen3.5 测试助手")
        )
        agent_config = result.scalar_one_or_none()

        if not agent_config:
            print("✗ 未找到 Qwen3.5 测试助手 Agent")
            # 尝试查找名称中包含 "测试" 的 Agent
            print("\n尝试查找其他测试 Agent...")
            result = await session.execute(
                select(AgentConfig).where(AgentConfig.name.contains("测试"))
            )
            agents = result.scalars().all()
            if agents:
                print(f"找到 {len(agents)} 个测试 Agent:")
                for a in agents:
                    print(f"  - {a.name} (ID: {a.id})")
                agent_config = agents[0]
                print(f"\n使用第一个 Agent: {agent_config.name}")
            else:
                print("✗ 未找到任何测试 Agent")
                return

        print(f"✓ 找到 Agent: {agent_config.name}")
        print(f"  ID: {agent_config.id}")
        print(f"  类型：{agent_config.agent_type}")
        print(f"  默认模型：{agent_config.default_model_config}")

        # 创建 Factory 并执行
        print("\n[Step 2] 创建 AgentFactory...")
        mock_gateway = MockModelGateway()
        mock_registry = MockSkillRegistry()

        factory = AgentFactory(
            db=session,
            model_gateway=mock_gateway,
            skill_registry=mock_registry,
        )

        print("\n[Step 3] 执行 Agent...")
        try:
            result = await factory.execute(
                agent_id=str(agent_config.id),
                user_id=1,
                query="你好，请用一句话介绍你自己。",
                runtime_config={
                    "model_name": "qwen3.5-397b-a17b",
                },
            )

            print(f"✓ Agent 执行成功")
            print(f"  run_id: {result['run_id'][:8]}...")
            print(f"  agent_type: {result['agent_type']}")
            print(f"  response 长度：{len(result['response'])}")
            print(f"\n  响应内容:\n  {result['response']}")

        except Exception as e:
            print(f"✗ Agent 执行失败：{e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 70)
    print("测试完成")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_qwen_agent())
