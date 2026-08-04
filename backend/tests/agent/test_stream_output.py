"""
测试流式输出是否重复
"""
import asyncio
import sys

sys.path.insert(0, '.')

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from packages.agent.models.agent import AgentConfig
from app.services.agent_factory import AgentFactory
from app.services.agent_orchestration_service import AgentOrchestrationService

DATABASE_URL = "postgresql+asyncpg://postgres:postgres123@100.4.14.19:5432/rag_db"


class MockModelGateway:
    async def get_model_by_name(self, name: str):
        from packages.agent.schemas.chat import ModelConfig
        return ModelConfig(
            provider="local_qwen",
            model="qwen3.5-397b-a17b",
            temperature=0.7,
            max_tokens=4096,
            api_url="http://100.4.14.19:8000",
            api_key="not-needed",
        )


class MockSkillRegistry:
    def get_tool(self, skill_id: str):
        return None


async def test_stream_no_duplicates():
    """测试流式输出不重复"""
    print("=" * 70)
    print("流式输出重复测试")
    print("=" * 70)

    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # 查找测试 Agent
        from sqlalchemy import select
        result = await session.execute(
            select(AgentConfig).where(AgentConfig.name == "Qwen3.5 测试助手")
        )
        agent_config = result.scalar_one_or_none()

        if not agent_config:
            print("✗ 未找到测试 Agent")
            return

        print(f"\n使用 Agent: {agent_config.name}")

        # 创建编排服务
        mock_gateway = MockModelGateway()
        mock_registry = MockSkillRegistry()

        orchestration = AgentOrchestrationService(
            db=session,
            model_gateway=mock_gateway,
            skill_registry=mock_registry,
        )

        # 流式执行并收集所有 chunk
        print("\n流式执行中...")
        chunks = []
        async for chunk in orchestration.execute_agent_stream(
            agent_id=str(agent_config.id),
            user_id=1,
            query="你好，请用一句话介绍你自己。",
            runtime_config={},
        ):
            chunks.append(chunk)
            print(f"Chunk {len(chunks)}: {repr(chunk[:50] if len(chunk) > 50 else chunk)}")

        # 检查是否有重复
        full_content = ''.join(chunks)
        print(f"\n=== 结果 ===")
        print(f"Chunk 数量：{len(chunks)}")
        print(f"总长度：{sum(len(c) for c in chunks)}")
        print(f"完整内容：{full_content}")

        # 检查重复
        if len(chunks) != len(set(chunks)):
            print("\n⚠️  检测到重复 chunk！")
        else:
            print("\n✓ 没有重复 chunk")

    print("\n" + "=" * 70)
    print("测试完成")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_stream_no_duplicates())
