"""
Agent 记忆服务测试
测试记忆管理的核心功能：
1. 对话记忆添加和获取
2. 对话记忆清除
3. 向量记忆引用
4. 对话摘要
5. 过期记忆清理
"""
import asyncio
import sys
import uuid
from datetime import datetime, timedelta

sys.path.insert(0, '.')

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, delete

from packages.agent.models.agent import AgentConfig, AgentMemory
from packages.core.system.models.user import User
from packages.agent.services.agent_memory_service import AgentMemoryService

DATABASE_URL = "postgresql+asyncpg://postgres:postgres123@100.4.14.19:5432/rag_db"


async def get_test_session():
    """创建测试数据库 session"""
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session

    await engine.dispose()


class TestAgentMemoryService:
    """Agent 记忆服务测试类"""

    def __init__(self):
        self.engine = None
        self.session = None
        self.test_user_id = 1
        self.test_agent_id = None

    async def setup(self):
        """设置测试环境"""
        print("\n" + "=" * 60)
        print("设置测试环境")
        print("=" * 60)

        self.engine = create_async_engine(DATABASE_URL, echo=False)
        async_session = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.session = async_session()

        # 创建测试 Agent
        self.test_agent_id = str(uuid.uuid4())
        agent = AgentConfig(
            id=self.test_agent_id,
            user_id=self.test_user_id,
            name="记忆测试助手",
            description="用于测试记忆服务的 Agent",
            agent_type="single",
            default_model_config={
                "provider": "local_qwen",
                "model": "qwen3.5-397b-a17b",
                "temperature": 0.7,
                "max_tokens": 4096,
            },
            system_prompt="你是一个测试助手。",
            status="active",
        )
        self.session.add(agent)
        await self.session.commit()
        print(f"✓ 测试 Agent 创建成功：{self.test_agent_id[:8]}...")

    async def teardown(self):
        """清理测试环境"""
        print("\n" + "=" * 60)
        print("清理测试环境")
        print("=" * 60)

        try:
            # 先删除记忆
            await self.session.execute(
                delete(AgentMemory).where(AgentMemory.agent_id == self.test_agent_id)
            )
            # 再删除 Agent
            await self.session.execute(
                delete(AgentConfig).where(AgentConfig.id == self.test_agent_id)
            )
            await self.session.commit()
            print("✓ 测试数据已清理")
        except Exception as e:
            await self.session.rollback()
            print(f"✗ 清理失败：{e}")
        finally:
            await self.session.close()
            await self.engine.dispose()

    async def test_add_conversation(self):
        """测试添加对话记忆"""
        print("\n" + "=" * 60)
        print("测试：添加对话记忆")
        print("=" * 60)

        service = AgentMemoryService(self.session)
        thread_id = f"test_thread_{uuid.uuid4().hex[:8]}"

        messages = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！有什么可以帮助你的？"},
        ]

        memory_id = await service.add_conversation(
            agent_id=self.test_agent_id,
            user_id=self.test_user_id,
            thread_id=thread_id,
            messages=messages,
            ttl_hours=24,
        )

        print(f"✓ 对话记忆添加成功")
        print(f"  memory_id: {memory_id[:8]}...")
        print(f"  thread_id: {thread_id}")
        print(f"  消息数：{len(messages)}")

        return thread_id

    async def test_get_conversation(self, thread_id: str):
        """测试获取对话历史"""
        print("\n" + "=" * 60)
        print("测试：获取对话历史")
        print("=" * 60)

        service = AgentMemoryService(self.session)

        history = await service.get_conversation(
            agent_id=self.test_agent_id,
            user_id=self.test_user_id,
            thread_id=thread_id,
            limit=50,
        )

        print(f"✓ 对话历史获取成功")
        print(f"  消息数：{len(history)}")
        if history:
            print(f"  第一条：{history[0].get('content', '')[:30]}...")
            print(f"  最后一条：{history[-1].get('content', '')[:30]}...")

        assert len(history) >= 2, "应该至少有 2 条消息"
        return history

    async def test_clear_conversation(self, thread_id: str):
        """测试清除对话历史"""
        print("\n" + "=" * 60)
        print("测试：清除对话历史")
        print("=" * 60)

        service = AgentMemoryService(self.session)

        # 先确认有数据
        before = await service.get_conversation(
            agent_id=self.test_agent_id,
            user_id=self.test_user_id,
            thread_id=thread_id,
        )
        print(f"清除前消息数：{len(before)}")

        # 清除
        deleted_count = await service.clear_conversation(
            agent_id=self.test_agent_id,
            user_id=self.test_user_id,
            thread_id=thread_id,
        )

        # 验证清除
        after = await service.get_conversation(
            agent_id=self.test_agent_id,
            user_id=self.test_user_id,
            thread_id=thread_id,
        )

        print(f"✓ 对话历史清除成功")
        print(f"  删除数：{deleted_count}")
        print(f"  清除后消息数：{len(after)}")

        assert len(after) == 0, "清除后应该没有消息"
        return deleted_count

    async def test_add_summary(self):
        """测试添加对话摘要"""
        print("\n" + "=" * 60)
        print("测试：添加对话摘要")
        print("=" * 60)

        service = AgentMemoryService(self.session)
        thread_id = f"test_summary_{uuid.uuid4().hex[:8]}"

        # 先添加一些对话
        await service.add_conversation(
            agent_id=self.test_agent_id,
            user_id=self.test_user_id,
            thread_id=thread_id,
            messages=[
                {"role": "user", "content": "什么是人工智能？"},
                {"role": "assistant", "content": "人工智能是..."},
            ],
        )

        # 添加摘要
        summary_id = await service.add_summary(
            agent_id=self.test_agent_id,
            user_id=self.test_user_id,
            thread_id=thread_id,
            summary="用户询问人工智能的定义，助手进行了解释。",
            keywords=["人工智能", "定义", "解释"],
        )

        print(f"✓ 对话摘要添加成功")
        print(f"  summary_id: {summary_id[:8]}...")

        # 获取摘要
        summary = await service.get_summary(
            agent_id=self.test_agent_id,
            user_id=self.test_user_id,
            thread_id=thread_id,
        )

        if summary:
            print(f"  摘要内容：{summary.get('summary', '')[:50]}...")
            print(f"  关键词：{summary.get('keywords', [])}")

        return thread_id

    async def test_cleanup_expired(self):
        """测试清理过期记忆"""
        print("\n" + "=" * 60)
        print("测试：清理过期记忆")
        print("=" * 60)

        service = AgentMemoryService(self.session)
        thread_id = f"test_expired_{uuid.uuid4().hex[:8]}"

        # 添加一个已过期的记忆
        from datetime import datetime, timedelta
        expired_time = datetime.utcnow() - timedelta(hours=1)

        memory = AgentMemory(
            id=str(uuid.uuid4()),
            agent_id=self.test_agent_id,
            user_id=self.test_user_id,
            thread_id=thread_id,
            memory_type="conversation",
            content={"messages": [{"role": "user", "content": "过期测试"}]},
            expires_at=expired_time,
        )
        self.session.add(memory)
        await self.session.commit()

        print(f"✓ 已添加过期记忆")

        # 执行清理
        deleted_count = await service.cleanup_expired()

        print(f"✓ 过期记忆清理完成")
        print(f"  清理数：{deleted_count}")

        return deleted_count

    async def test_vector_memory(self):
        """测试向量记忆"""
        print("\n" + "=" * 60)
        print("测试：向量记忆")
        print("=" * 60)

        service = AgentMemoryService(self.session)
        thread_id = f"test_vector_{uuid.uuid4().hex[:8]}"

        # 添加向量记忆
        memory_id = await service.add_vector_memory(
            agent_id=self.test_agent_id,
            user_id=self.test_user_id,
            thread_id=thread_id,
            text="这是一段测试文本",
            milvus_collection="test_collection",
            milvus_ids=["id1", "id2", "id3"],
        )

        print(f"✓ 向量记忆添加成功")
        print(f"  memory_id: {memory_id[:8]}...")

        # 获取向量记忆引用
        refs = await service.get_vector_memory_refs(
            agent_id=self.test_agent_id,
            user_id=self.test_user_id,
            thread_id=thread_id,
        )

        print(f"✓ 向量记忆引用获取成功")
        print(f"  引用数：{len(refs)}")
        for collection, ids in refs:
            print(f"    collection: {collection}, ids: {ids}")

        return len(refs)

    async def run_all_tests(self):
        """运行所有测试"""
        await self.setup()

        try:
            # 测试对话记忆
            thread_id = await self.test_add_conversation()
            await self.test_get_conversation(thread_id)
            await self.test_clear_conversation(thread_id)

            # 测试摘要
            await self.test_add_summary()

            # 测试向量记忆
            await self.test_vector_memory()

            # 测试过期清理
            await self.test_cleanup_expired()

            print("\n" + "=" * 60)
            print("所有记忆服务测试通过 ✅")
            print("=" * 60)

        except AssertionError as e:
            print(f"\n❌ 测试失败：{e}")
        except Exception as e:
            print(f"\n❌ 测试异常：{e}")
            import traceback
            traceback.print_exc()
        finally:
            await self.teardown()


async def main():
    """运行测试"""
    tester = TestAgentMemoryService()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
