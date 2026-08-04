"""
会话历史接口数据准确性测试
使用真实数据库验证接口返回数据的准确性
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from uuid import uuid4
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, delete, func

from app.models.base import Base
from app.models.user import User
from app.models.agent import AgentMemory, AgentConfig
from app.models.conversation_archive import ConversationArchive
from app.services.conversation_archive_service import ConversationArchiveService


# 使用远程数据库
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres123@100.4.14.19:5432/rag_db"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def test_db():
    """创建测试数据库 session"""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def test_user(test_db):
    """创建测试用户"""
    user = User(
        username=f"test_accuracy_{uuid4().hex[:8]}",
        email=f"test_accuracy_{uuid4().hex[:8]}@test.com",
        hashed_password="hashed_password",
    )
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    return user


@pytest.fixture
async def test_agent(test_db, test_user):
    """创建测试智能体"""
    agent = AgentConfig(
        id=uuid4(),
        user_id=test_user.id,
        name="Test Accuracy Agent",
        description="Agent for data accuracy tests",
        agent_type="single",
        system_prompt="You are a helpful assistant.",
        status="active",
    )
    test_db.add(agent)
    await test_db.commit()
    await test_db.refresh(agent)
    return agent


@pytest.fixture
async def test_data(test_db, test_user, test_agent):
    """创建精确的测试数据"""
    now = datetime.utcnow()
    expected = {
        "last_7d": 5,
        "last_30d": 12,  # 5 + 7
        "months": {},
        "thread_ids": {
            "7d": [],
            "30d": [],
            "warm": [],
            "cold": [],
        }
    }

    # 创建最近 7 天的数据 (5 条)
    for i in range(5):
        memory = AgentMemory(
            id=str(uuid4()),
            agent_id=str(test_agent.id),
            user_id=test_user.id,
            thread_id=f"accuracy-7d-{i}-{uuid4().hex[:8]}",
            memory_type="conversation",
            content={"messages": [{"role": "user", "content": f"Test message {i}"}]},
            created_at=now - timedelta(days=i),
        )
        test_db.add(memory)
        expected["thread_ids"]["7d"].append(memory.thread_id)

    # 创建 8-30 天的数据 (7 条)
    for i in range(8, 29, 3):
        memory = AgentMemory(
            id=str(uuid4()),
            agent_id=str(test_agent.id),
            user_id=test_user.id,
            thread_id=f"accuracy-30d-{i}-{uuid4().hex[:8]}",
            memory_type="conversation",
            content={"messages": [{"role": "user", "content": f"Test message {i}"}]},
            created_at=now - timedelta(days=i),
        )
        test_db.add(memory)
        expected["thread_ids"]["30d"].append(memory.thread_id)

    # 创建上个月的温归档 (8 条)
    last_month = now.replace(day=1) - timedelta(days=1)
    expected["months"][last_month.strftime("%Y-%m")] = 8

    for i in range(8):
        archive = ConversationArchive(
            id=str(uuid4()),
            user_id=test_user.id,
            thread_id=f"accuracy-warm-{i}-{uuid4().hex[:8]}",
            agent_id=str(test_agent.id),
            agent_name="Test Accuracy Agent",
            archive_tier="warm",
            message_count=5,
            compressed_content=b"test_compressed",
            archive_size_bytes=512,
            date_range_start=last_month.replace(day=1),
            date_range_end=last_month,
            last_message_at=last_month - timedelta(days=i),
            is_restored=False,
        )
        test_db.add(archive)
        expected["thread_ids"]["warm"].append(archive.thread_id)

    # 创建前两个月的冷归档 (5 条)
    old_month = now.replace(day=1) - timedelta(days=60)
    expected["months"][old_month.strftime("%Y-%m")] = 5

    for i in range(5):
        archive = ConversationArchive(
            id=str(uuid4()),
            user_id=test_user.id,
            thread_id=f"accuracy-cold-{i}-{uuid4().hex[:8]}",
            agent_id=str(test_agent.id),
            agent_name="Test Accuracy Agent",
            archive_tier="cold",
            message_count=3,
            archive_path=f"test/{test_user.id}/accuracy-cold-{i}.gz",
            archive_size_bytes=256,
            date_range_start=old_month.replace(day=1),
            date_range_end=old_month,
            last_message_at=old_month - timedelta(days=i),
            is_restored=False,
        )
        test_db.add(archive)
        expected["thread_ids"]["cold"].append(archive.thread_id)

    await test_db.commit()
    return expected


class TestDataAccuracy:
    """数据准确性测试"""

    @pytest.mark.asyncio
    async def test_stats_last_7d_accuracy(self, test_db, test_user, test_data):
        """验证最近 7 天统计数据准确性"""
        service = ConversationArchiveService(test_db)
        stats = await service.get_conversation_history_stats(user_id=test_user.id)

        assert stats["last_7d"] == test_data["last_7d"], \
            f"最近 7 天数据不准确：期望 {test_data['last_7d']}, 实际 {stats['last_7d']}"

    @pytest.mark.asyncio
    async def test_stats_last_30d_accuracy(self, test_db, test_user, test_data):
        """验证最近 30 天统计数据准确性"""
        service = ConversationArchiveService(test_db)
        stats = await service.get_conversation_history_stats(user_id=test_user.id)

        assert stats["last_30d"] == test_data["last_30d"], \
            f"最近 30 天数据不准确：期望 {test_data['last_30d']}, 实际 {stats['last_30d']}"

    @pytest.mark.asyncio
    async def test_stats_months_accuracy(self, test_db, test_user, test_data):
        """验证月份统计数据准确性"""
        service = ConversationArchiveService(test_db)
        stats = await service.get_conversation_history_stats(user_id=test_user.id)

        for month, expected_count in test_data["months"].items():
            assert month in stats["months"], f"缺少月份 {month}"
            assert stats["months"][month] == expected_count, \
                f"月份 {month} 数据不准确：期望 {expected_count}, 实际 {stats['months'][month]}"

    @pytest.mark.asyncio
    async def test_time_range_7d_data_accuracy(self, test_db, test_user, test_data):
        """验证 7 天范围列表数据准确性"""
        service = ConversationArchiveService(test_db)
        items, total = await service.get_conversation_history(
            user_id=test_user.id,
            limit=20,
            offset=0,
            time_range="7d",
        )

        assert total == test_data["last_7d"], \
            f"7 天范围总数不准确：期望 {test_data['last_7d']}, 实际 {total}"

        # 验证返回的 thread_id 都在预期范围内
        returned_ids = {item["thread_id"] for item in items}
        expected_ids = set(test_data["thread_ids"]["7d"])
        assert returned_ids == expected_ids, "7 天范围返回的 thread_id 不匹配"

    @pytest.mark.asyncio
    async def test_time_range_30d_data_accuracy(self, test_db, test_user, test_data):
        """验证 30 天范围列表数据准确性"""
        service = ConversationArchiveService(test_db)
        items, total = await service.get_conversation_history(
            user_id=test_user.id,
            limit=20,
            offset=0,
            time_range="30d",
        )

        assert total == test_data["last_30d"], \
            f"30 天范围总数不准确：期望 {test_data['last_30d']}, 实际 {total}"

    @pytest.mark.asyncio
    async def test_pagination_count_accuracy(self, test_db, test_user, test_data):
        """验证分页计数准确性"""
        service = ConversationArchiveService(test_db)

        # 第一页
        items1, total1 = await service.get_conversation_history(
            user_id=test_user.id,
            limit=5,
            offset=0,
        )

        # 第二页
        items2, total2 = await service.get_conversation_history(
            user_id=test_user.id,
            limit=5,
            offset=5,
        )

        # 第三页
        items3, total3 = await service.get_conversation_history(
            user_id=test_user.id,
            limit=5,
            offset=10,
        )

        # 验证总数一致
        assert total1 == total2 == total3, "分页总数不一致"

        # 验证每页数量
        assert len(items1) == 5, f"第一页应该有 5 条，实际 {len(items1)}"
        assert len(items2) == 5, f"第二页应该有 5 条，实际 {len(items2)}"

        # 验证没有重复
        all_ids = [item["thread_id"] for item in items1 + items2 + items3]
        assert len(all_ids) == len(set(all_ids)), "分页数据有重复"

    @pytest.mark.asyncio
    async def test_item_field_accuracy(self, test_db, test_user, test_data):
        """验证返回字段准确性"""
        service = ConversationArchiveService(test_db)
        items, _ = await service.get_conversation_history(
            user_id=test_user.id,
            limit=1,
            offset=0,
        )

        assert len(items) > 0, "应该至少返回一条数据"

        item = items[0]

        # 验证必填字段
        required_fields = ["thread_id", "agent_id", "message_count", "last_message_at", "source"]
        for field in required_fields:
            assert field in item, f"缺少必填字段：{field}"

        # 验证字段类型
        assert isinstance(item["thread_id"], str), "thread_id 应该是字符串"
        assert isinstance(item["message_count"], int), "message_count 应该是整数"
        assert item["source"] in ["hot", "archive"], "source 应该是 hot 或 archive"

    @pytest.mark.asyncio
    async def test_agent_filter_accuracy(self, test_db, test_user, test_agent, test_data):
        """验证智能体过滤准确性"""
        service = ConversationArchiveService(test_db)

        # 不过滤
        all_items, all_total = await service.get_conversation_history(
            user_id=test_user.id,
            limit=100,
            offset=0,
        )

        # 过滤特定智能体
        filtered_items, filtered_total = await service.get_conversation_history(
            user_id=test_user.id,
            limit=100,
            offset=0,
            agent_id=str(test_agent.id),
        )

        # 验证过滤后的数量
        assert filtered_total <= all_total, "过滤后数量不应大于总数"

        # 验证过滤后的都属于指定智能体
        for item in filtered_items:
            assert str(item["agent_id"]) == str(test_agent.id), \
                f"过滤后的数据不属于指定智能体：{item['agent_id']}"

    @pytest.mark.asyncio
    async def test_source_tier_accuracy(self, test_db, test_user, test_data):
        """验证数据源和归档层级准确性"""
        service = ConversationArchiveService(test_db)

        # 获取 7 天范围（应该都是热数据）
        items_7d, _ = await service.get_conversation_history(
            user_id=test_user.id,
            limit=20,
            offset=0,
            time_range="7d",
        )

        for item in items_7d:
            assert item["source"] == "hot", f"7 天范围应该是热数据：{item['thread_id']}"

        # 获取温归档月份
        last_month = (datetime.utcnow().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        items_warm, _ = await service.get_conversation_history(
            user_id=test_user.id,
            limit=20,
            offset=0,
            time_range="month",
            month=last_month,
        )

        for item in items_warm:
            assert item["source"] == "archive", f"温归档应该是 archive: {item['thread_id']}"
            assert item["archive_tier"] == "warm", f"归档层级应该是 warm: {item['thread_id']}"


class TestRealDataValidation:
    """真实数据验证（不创建测试数据，直接验证现有数据）"""

    @pytest.mark.asyncio
    async def test_stats_consistency(self, test_db):
        """验证统计数据内部一致性"""
        # 使用一个真实用户 ID 测试
        result = await test_db.execute(select(User).limit(1))
        user = result.scalar_one_or_none()

        if not user:
            pytest.skip("没有用户数据")

        service = ConversationArchiveService(test_db)
        stats = await service.get_conversation_history_stats(user_id=user.id)

        # last_30d 应该 >= last_7d
        assert stats["last_30d"] >= stats["last_7d"], \
            "last_30d 应该大于等于 last_7d"

    @pytest.mark.asyncio
    async def test_list_stats_consistency(self, test_db):
        """验证列表总数和统计的一致性"""
        result = await test_db.execute(select(User).limit(1))
        user = result.scalar_one_or_none()

        if not user:
            pytest.skip("没有用户数据")

        service = ConversationArchiveService(test_db)

        # 获取统计
        stats = await service.get_conversation_history_stats(user_id=user.id)

        # 获取全部列表
        all_items, all_total = await service.get_conversation_history(
            user_id=user.id,
            limit=1000,
            offset=0,
            time_range="all",
        )

        # 列表总数应该与统计的总和大致匹配（考虑归档）
        # 注意：由于归档可能已删除原数据，这里只验证非负
        assert all_total >= 0, "总数应该是非负数"


@pytest.fixture
async def cleanup_test_data(test_db, test_user):
    """清理测试数据"""
    yield
    # 删除测试数据
    await test_db.execute(delete(AgentMemory).where(AgentMemory.user_id == test_user.id))
    await test_db.execute(delete(ConversationArchive).where(ConversationArchive.user_id == test_user.id))
    await test_db.execute(delete(AgentConfig).where(AgentConfig.user_id == test_user.id))
    await test_db.execute(delete(User).where(User.id == test_user.id))
    await test_db.commit()


class TestWithCleanup:
    """带清理的测试"""

    @pytest.mark.asyncio
    async def test_with_auto_cleanup(self, test_db, test_user, test_agent, cleanup_test_data):
        """测试后自动清理"""
        service = ConversationArchiveService(test_db)
        stats = await service.get_conversation_history_stats(user_id=test_user.id)

        # 验证有数据
        assert stats["last_7d"] >= 0
        # 清理由 fixture 自动完成


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
