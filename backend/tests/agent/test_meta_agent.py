"""
Meta Agent 测试
测试自主智能体创建和管理其他智能体的能力
"""
import asyncio
import sys

sys.path.insert(0, '.')

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select

from app.models.agent import AgentConfig

DATABASE_URL = "postgresql+asyncpg://postgres:postgres123@100.4.14.19:5432/rag_db"


async def test_meta_agent_create_agents():
    """
    测试 Meta Agent 自主创建智能体
    场景：用户说"创建一个有产品能力和架构能力的智能体"
    期望：Meta Agent 自主决定创建产品经理和架构师两个智能体
    """
    print("=" * 70)
    print("Meta Agent 测试 - 自主创建智能体")
    print("=" * 70)

    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        from app.services.meta_agent_service import MetaAgentService

        service = MetaAgentService(
            db=session,
            user_id=1,
            tenant_id="test",
        )

        # 模拟用户请求：创建有产品能力和架构能力的智能体
        user_query = "创建一个有产品能力和架构能力的智能体，能够帮我做产品需求分析和系统架构设计"

        print(f"\n用户请求：{user_query}")
        print("\n执行 Meta Agent...")

        try:
            result = await service.execute(query=user_query)

            print(f"\n✓ Meta Agent 执行成功")
            print(f"\n响应内容:\n{result['response']}")

            # 检查是否创建了新智能体
            print("\n检查创建的智能体...")
            created_agents_result = await session.execute(
                select(AgentConfig).where(
                    AgentConfig.user_id == 1,
                    AgentConfig.name.in_(["产品经理助手", "高级架构师", "产品经理", "架构师"])
                )
            )
            created_agents = created_agents_result.scalars().all()

            if created_agents:
                print(f"\n✓ 创建了 {len(created_agents)} 个智能体:")
                for agent in created_agents:
                    print(f"  - {agent.name} (ID: {agent.id})")
                    print(f"    System Prompt: {agent.system_prompt[:100]}...")
            else:
                print("\n⚠️  可能使用了现有智能体或创建的智能体名称不同")

        except Exception as e:
            print(f"\n✗ Meta Agent 执行失败：{e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 70)
    print("测试完成")
    print("=" * 70)


async def test_meta_agent_list_and_execute():
    """
    测试 Meta Agent 查询并执行现有智能体
    """
    print("=" * 70)
    print("Meta Agent 测试 - 查询并执行现有智能体")
    print("=" * 70)

    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        from app.services.meta_agent_service import MetaAgentService

        service = MetaAgentService(
            db=session,
            user_id=1,
            tenant_id="test",
        )

        # 模拟用户请求：使用现有智能体
        user_query = "帮我写一份产品需求文档，关于一个电商 APP 的用户模块"

        print(f"\n用户请求：{user_query}")
        print("\n执行 Meta Agent...")

        try:
            result = await service.execute(query=user_query)

            print(f"\n✓ Meta Agent 执行成功")
            print(f"\n响应内容:\n{result['response']}")

        except Exception as e:
            print(f"\n✗ Meta Agent 执行失败：{e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 70)
    print("测试完成")
    print("=" * 70)


if __name__ == "__main__":
    print("\n>>> 运行测试 1: 自主创建智能体\n")
    asyncio.run(test_meta_agent_create_agents())

    print("\n>>> 运行测试 2: 查询并执行现有智能体\n")
    asyncio.run(test_meta_agent_list_and_execute())
