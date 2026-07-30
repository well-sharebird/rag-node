"""
智能体 CRUD 功能简单测试
直接调用 Service 层，绕过 HTTP 认证
"""
import asyncio
import sys
from datetime import datetime

# 添加路径
sys.path.insert(0, '.')

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.models.agent import AgentConfig
from app.models.user import User
from app.schemas.chat import AgentCreate, AgentUpdate
from app.services.agent_config_service import AgentConfigService
from app.services.agent_builder_service import AgentBuilderService

# 数据库 URL - 使用远程服务器
DATABASE_URL = "postgresql+asyncpg://postgres:postgres123@100.4.14.19:5432/rag_db"


async def test_agent_crud():
    """测试 Agent CRUD 功能"""
    print("=" * 60)
    print("智能体 CRUD 功能测试")
    print("=" * 60)

    # 创建数据库引擎
    try:
        engine = create_async_engine(DATABASE_URL)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    except Exception as e:
        print(f"✗ 数据库连接失败：{e}")
        print("  请确保 PostgreSQL 正在运行且数据库存在")
        return

    async with async_session() as session:
        # 获取或创建测试用户
        user_id = 1
        tenant_id = "test"

        # 测试用的 agent ID
        created_agent_id = None

        # ========== Test 1: 最小化创建 ==========
        print("\n[Test 1] 最小化创建智能体...")
        try:
            service = AgentConfigService(session)
            agent = await service.create(
                user_id=user_id,
                tenant_id=tenant_id,
                data=AgentCreate(
                    name="测试助手",
                    system_prompt="你是一个测试助手。",
                ),
            )
            created_agent_id = str(agent.id)
            print(f"✓ 创建成功")
            print(f"  Agent ID: {created_agent_id}")
            print(f"  名称：{agent.name}")
            print(f"  类型：{agent.agent_type}")
            print(f"  记忆类型：{agent.memory_type}")
            print(f"  状态：{agent.status}")
        except Exception as e:
            print(f"✗ 创建失败：{e}")

        # ========== Test 2: 完整参数创建 ==========
        print("\n[Test 2] 完整参数创建智能体...")
        try:
            service = AgentConfigService(session)
            agent = await service.create(
                user_id=user_id,
                tenant_id=tenant_id,
                data=AgentCreate(
                    name="高级测试助手",
                    description="这是一个功能完整的测试智能体",
                    icon="🤖",
                    agent_type="single",
                    system_prompt="你是一个高级测试助手，功能齐全。",
                    enabled_skills=["web_search", "code_interpreter"],
                    memory_type="vector",
                    memory_ttl_hours=48,
                    max_memory_turns=100,
                    retrieval_enabled=True,
                    retrieval_top_k=10,
                    is_public=False,
                ),
            )
            print(f"✓ 创建成功")
            print(f"  Agent ID: {agent.id}")
            print(f"  名称：{agent.name}")
            print(f"  技能：{agent.enabled_skills}")
            print(f"  记忆类型：{agent.memory_type}")
        except Exception as e:
            print(f"✗ 创建失败：{e}")

        # ========== Test 3: 获取列表 ==========
        print("\n[Test 3] 获取智能体列表...")
        try:
            service = AgentConfigService(session)
            agents, total = await service.list(
                user_id=user_id,
                skip=0,
                limit=20,
            )
            print(f"✓ 获取成功，共 {total} 个智能体")
            for a in agents:
                print(f"  - {a.name} ({a.id}) - 状态：{a.status}")
        except Exception as e:
            print(f"✗ 获取失败：{e}")

        # ========== Test 4: 获取详情 ==========
        print(f"\n[Test 4] 获取智能体详情 ({created_agent_id})...")
        if created_agent_id:
            try:
                service = AgentConfigService(session)
                agent = await service.get_by_id(created_agent_id, user_id=user_id)
                if agent:
                    print(f"✓ 获取成功")
                    print(f"  名称：{agent.name}")
                    print(f"  系统提示：{agent.system_prompt[:50]}...")
                    print(f"  创建时间：{agent.created_at}")
                else:
                    print(f"✗ Agent 不存在")
            except Exception as e:
                print(f"✗ 获取失败：{e}")
        else:
            print("⊘ 跳过 - 没有可用的 Agent ID")

        # ========== Test 5: 更新智能体 ==========
        print(f"\n[Test 5] 更新智能体 ({created_agent_id})...")
        if created_agent_id:
            try:
                service = AgentConfigService(session)
                agent = await service.update(
                    agent_id=created_agent_id,
                    user_id=user_id,
                    data=AgentUpdate(
                        description="已更新的描述",
                        system_prompt="你是一个已更新的测试助手。",
                    ),
                )
                if agent:
                    print(f"✓ 更新成功")
                    print(f"  新描述：{agent.description}")
                    print(f"  新系统提示：{agent.system_prompt[:50]}...")
                else:
                    print(f"✗ Agent 不存在")
            except Exception as e:
                print(f"✗ 更新失败：{e}")
        else:
            print("⊘ 跳过 - 没有可用的 Agent ID")

        # ========== Test 6: 复制智能体 ==========
        print(f"\n[Test 6] 复制智能体 ({created_agent_id})...")
        if created_agent_id:
            try:
                service = AgentConfigService(session)
                agent = await service.duplicate(
                    agent_id=created_agent_id,
                    user_id=user_id,
                    tenant_id=tenant_id,
                )
                if agent:
                    print(f"✓ 复制成功")
                    print(f"  新 Agent ID: {agent.id}")
                    print(f"  名称：{agent.name}")
                else:
                    print(f"✗ Agent 不存在")
            except Exception as e:
                print(f"✗ 复制失败：{e}")
        else:
            print("⊘ 跳过 - 没有可用的 Agent ID")

        # ========== Test 7: 发布智能体 ==========
        print(f"\n[Test 7] 发布智能体 ({created_agent_id})...")
        if created_agent_id:
            try:
                service = AgentConfigService(session)
                agent = await service.publish(
                    agent_id=created_agent_id,
                    user_id=user_id,
                )
                if agent:
                    print(f"✓ 发布成功")
                    print(f"  状态：{agent.status}")
                    print(f"  发布时间：{agent.published_at}")
                else:
                    print(f"✗ Agent 不存在")
            except Exception as e:
                print(f"✗ 发布失败：{e}")
        else:
            print("⊘ 跳过 - 没有可用的 Agent ID")

        # ========== Test 8: 按需求创建 (AI 分析) ==========
        print("\n[Test 8] 按需求创建智能体 (AI 分析)...")
        try:
            service = AgentBuilderService(session)
            agent, analysis = await service.create_agent_from_requirement(
                user_id=user_id,
                tenant_id=tenant_id,
                requirement="我需要一个帮我写技术文档的助手",
            )
            print(f"✓ 创建成功")
            print(f"  Agent ID: {agent.id}")
            print(f"  名称：{agent.name}")
            print(f"  分析结果：{analysis}")
        except Exception as e:
            print(f"⚠ 创建失败 (可能 LLM 未配置): {e}")

        # ========== Test 9: 删除智能体 ==========
        print(f"\n[Test 9] 删除智能体 ({created_agent_id})...")
        if created_agent_id:
            try:
                service = AgentConfigService(session)
                success = await service.delete(created_agent_id, user_id=user_id)
                if success:
                    print(f"✓ 删除成功")
                else:
                    print(f"✗ Agent 不存在")
            except Exception as e:
                print(f"✗ 删除失败：{e}")
        else:
            print("⊘ 跳过 - 没有可用的 Agent ID")

    # 关闭引擎
    await engine.dispose()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_agent_crud())
