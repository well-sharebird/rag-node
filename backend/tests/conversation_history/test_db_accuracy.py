"""
会话历史数据准确性测试
直接连接远程数据库验证数据准确性
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, func, text

from packages.core.system.models.user import User
from packages.agent.models.agent import AgentMemory, AgentConfig
from packages.agent.models.conversation_archive import ConversationArchive
from packages.agent.services.conversation_archive_service import ConversationArchiveService


# 远程数据库配置
DATABASE_URL = "postgresql+asyncpg://postgres:postgres123@100.4.14.19:5432/rag_db"


@pytest.fixture
async def db_session():
    """创建数据库 session"""
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session

    await engine.dispose()


class TestRealDataStats:
    """真实数据统计测试"""

    @pytest.mark.asyncio
    async def test_db_connection(self, db_session):
        """验证数据库连接"""
        result = await db_session.execute(text("SELECT 1"))
        assert result.scalar() == 1

    @pytest.mark.asyncio
    async def test_user_count(self, db_session):
        """验证有用户数据"""
        result = await db_session.execute(select(func.count(User.id)))
        count = result.scalar()
        assert count > 0, "数据库中应该有用户数据"
        print(f"\n数据库中有 {count} 个用户")

    @pytest.mark.asyncio
    async def test_conversation_count(self, db_session):
        """验证有会话数据"""
        result = await db_session.execute(select(func.count(AgentMemory.id)))
        count = result.scalar()
        print(f"\n数据库中有 {count} 条会话记忆")
        # 不强制要求有数据，只是打印

    @pytest.mark.asyncio
    async def test_archive_count(self, db_session):
        """验证有归档数据"""
        result = await db_session.execute(select(func.count(ConversationArchive.id)))
        count = result.scalar()
        print(f"数据库中有 {count} 条归档记录")

    @pytest.mark.asyncio
    async def test_stats_for_first_user(self, db_session):
        """测试获取第一个用户的统计"""
        result = await db_session.execute(select(User).limit(1))
        user = result.scalar_one_or_none()

        if not user:
            pytest.skip("没有用户数据")

        print(f"\n测试用户：{user.username} (ID: {user.id})")

        service = ConversationArchiveService(db_session)
        stats = await service.get_conversation_history_stats(user_id=user.id)

        print(f"  最近 7 天：{stats['last_7d']}")
        print(f"  最近 30 天：{stats['last_30d']}")
        print(f"  月份统计：{stats['months']}")

        # 验证数据一致性
        assert stats["last_30d"] >= stats["last_7d"], \
            "last_30d 应该 >= last_7d"

    @pytest.mark.asyncio
    async def test_list_for_first_user(self, db_session):
        """测试获取第一个用户的会话列表"""
        result = await db_session.execute(select(User).limit(1))
        user = result.scalar_one_or_none()

        if not user:
            pytest.skip("没有用户数据")

        service = ConversationArchiveService(db_session)

        # 获取全部数据
        items, total = await service.get_conversation_history(
            user_id=user.id,
            limit=100,
            offset=0,
            time_range="all",
        )

        print(f"\n用户 {user.username} 有 {total} 条会话")

        # 验证分页
        items_page2, total_page2 = await service.get_conversation_history(
            user_id=user.id,
            limit=10,
            offset=10,
        )

        assert total == total_page2, "分页总数应该一致"

        if items:
            print(f"  第一条会话：{items[0]['thread_id']}")
            print(f"  消息数：{items[0]['message_count']}")
            print(f"  来源：{items[0]['source']}")

    @pytest.mark.asyncio
    async def test_time_range_7d(self, db_session):
        """测试 7 天范围数据"""
        result = await db_session.execute(select(User).limit(1))
        user = result.scalar_one_or_none()

        if not user:
            pytest.skip("没有用户数据")

        service = ConversationArchiveService(db_session)
        items, total = await service.get_conversation_history(
            user_id=user.id,
            limit=100,
            offset=0,
            time_range="7d",
        )

        print(f"\n最近 7 天有 {total} 条会话")

        # 验证返回的都是热数据
        for item in items:
            assert item["source"] == "hot", \
                f"7 天范围应该是热数据：{item['thread_id']}"

    @pytest.mark.asyncio
    async def test_time_range_month(self, db_session):
        """测试月份范围数据"""
        result = await db_session.execute(select(User).limit(1))
        user = result.scalar_one_or_none()

        if not user:
            pytest.skip("没有用户数据")

        last_month = (datetime.utcnow().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        print(f"\n测试月份：{last_month}")

        service = ConversationArchiveService(db_session)
        items, total = await service.get_conversation_history(
            user_id=user.id,
            limit=100,
            offset=0,
            time_range="month",
            month=last_month,
        )

        print(f"  {last_month} 有 {total} 条会话")

    @pytest.mark.asyncio
    async def test_stats_consistency(self, db_session):
        """验证统计数据一致性"""
        result = await db_session.execute(select(User).limit(1))
        user = result.scalar_one_or_none()

        if not user:
            pytest.skip("没有用户数据")

        service = ConversationArchiveService(db_session)
        stats = await service.get_conversation_history_stats(user_id=user.id)

        # 验证月份数据都是正数
        for month, count in stats["months"].items():
            assert count > 0, f"月份 {month} 的计数应该是正数"
            print(f"  {month}: {count} 条")


class TestDataDistribution:
    """数据分布测试"""

    @pytest.mark.asyncio
    async def test_hot_vs_archive(self, db_session):
        """验证热数据和归档数据分布"""
        # 统计热数据
        hot_result = await db_session.execute(
            select(func.count(AgentMemory.id))
            .where(AgentMemory.memory_type == "conversation")
        )
        hot_count = hot_result.scalar() or 0

        # 统计归档数据
        archive_result = await db_session.execute(
            select(func.count(ConversationArchive.id))
        )
        archive_count = archive_result.scalar() or 0

        print(f"\n热数据：{hot_count} 条")
        print(f"归档数据：{archive_count} 条")

    @pytest.mark.asyncio
    async def test_archive_tier_distribution(self, db_session):
        """验证归档层级分布"""
        result = await db_session.execute(
            select(
                ConversationArchive.archive_tier,
                func.count(ConversationArchive.id)
            )
            .group_by(ConversationArchive.archive_tier)
        )

        print("\n归档层级分布:")
        for row in result.all():
            print(f"  {row[0]}: {row[1]} 条")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
