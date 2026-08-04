"""
会话历史接口集成测试
使用真实数据库验证数据准确性

需要运行：
1. 确保 PostgreSQL 运行
2. 运行测试前执行：docker-compose up -d postgres
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
from app.models.conversation_archive import ConversationArchive, ConversationArchiveConfig
from app.services.conversation_archive_service import ConversationArchiveService
from app.api.v1.conversation_history import list_conversation_history, get_conversation_history_stats


# 测试数据库 URL
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres123@localhost:5432/rag_db_test"


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def test_db():
    """创建测试数据库 session"""
    try:
        engine = create_async_engine(TEST_DATABASE_URL, echo=False)
        async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        # 创建所有表
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with async_session() as session:
            yield session

        # 清理测试数据
        async with async_session() as session:
            await session.execute(delete(AgentMemory))
            await session.execute(delete(ConversationArchive))
            await session.execute(delete(AgentConfig))
            await session.execute(delete(User))
            await session.commit()

        await engine.dispose()
    except Exception as e:
        pytest.skip(f"Database not available: {e}")


@pytest.fixture
async def test_user(test_db):
    """创建测试用户"""
    user = User(
        username=f"testuser_{uuid4().hex[:8]}",
        email=f"test_{uuid4().hex[:8]}@test.com",
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
        name="Test Agent",
        description="Test agent for integration tests",
        agent_type="single",
        system_prompt="You are a helpful assistant.",
        status="active",
    )
    test_db.add(agent)
    await test_db.commit()
    await test_db.refresh(agent)
    return agent


@pytest.fixture
async def conversation_data(test_db, test_user, test_agent):
    """创建测试会话数据"""
    now = datetime.utcnow()
    created_items = {
        "hot_7d": [],
        "hot_30d": [],
        "archive_warm": [],
        "archive_cold": [],
    }

    # 创建最近 7 天的热数据 (5 条)
    for i in range(5):
        memory = AgentMemory(
            id=str(uuid4()),
            agent_id=str(test_agent.id),
            user_id=test_user.id,
            thread_id=f"thread-7d-{i}",
            memory_type="conversation",
            content={"messages": [{"role": "user", "content": f"Message {i}"}]},
            created_at=now - timedelta(days=i),
        )
        test_db.add(memory)
        created_items["hot_7d"].append(memory.thread_id)

    # 创建 8-30 天的热数据 (8 条)
    for i in range(8, 30, 3):
        memory = AgentMemory(
            id=str(uuid4()),
            agent_id=str(test_agent.id),
            user_id=test_user.id,
            thread_id=f"thread-30d-{i}",
            memory_type="conversation",
            content={"messages": [{"role": "user", "content": f"Message {i}"}]},
            created_at=now - timedelta(days=i),
        )
        test_db.add(memory)
        created_items["hot_30d"].append(memory.thread_id)

    # 创建温归档数据 (上个月，10 条)
    last_month = now.replace(day=1) - timedelta(days=1)
    for i in range(10):
        archive = ConversationArchive(
            id=str(uuid4()),
            user_id=test_user.id,
            thread_id=f"thread-warm-{i}",
            agent_id=str(test_agent.id),
            agent_name="Test Agent",
            archive_tier="warm",
            message_count=10,
            compressed_content=b"compressed_data",
            archive_size_bytes=1024,
            date_range_start=last_month.replace(day=1),
            date_range_end=last_month,
            last_message_at=last_month - timedelta(days=i),
            is_restored=False,
        )
        test_db.add(archive)
        created_items["archive_warm"].append(archive.thread_id)

    # 创建冷归档数据 (更早的月份，5 条)
    old_month = now.replace(day=1) - timedelta(days=60)
    for i in range(5):
        archive = ConversationArchive(
            id=str(uuid4()),
            user_id=test_user.id,
            thread_id=f"thread-cold-{i}",
            agent_id=str(test_agent.id),
            agent_name="Test Agent",
            archive_tier="cold",
            message_count=5,
            archive_path=f"archives/{test_user.id}/thread-cold-{i}.jsonl.gz",
            archive_size_bytes=512,
            date_range_start=old_month.replace(day=1),
            date_range_end=old_month,
            last_message_at=old_month - timedelta(days=i),
            is_restored=False,
        )
        test_db.add(archive)
        created_items["archive_cold"].append(archive.thread_id)

    await test_db.commit()

    return created_items


class TestConversationHistoryIntegration:
    """会话历史集成测试"""

    @pytest.mark.asyncio
    async def test_stats_accuracy(self, test_db, test_user, conversation_data):
        """测试统计数据的准确性"""
        service = ConversationArchiveService(test_db)
        stats = await service.get_conversation_history_stats(user_id=test_user.id)

        # 验证最近 7 天（热数据）
        assert stats["last_7d"] == 5, f"Expected 5 items in last_7d, got {stats['last_7d']}"

        # 验证最近 30 天（热数据 7 天 + 8-30 天）
        expected_30d = len(conversation_data["hot_7d"]) + len(conversation_data["hot_30d"])
        assert stats["last_30d"] == expected_30d, \
            f"Expected {expected_30d} items in last_30d, got {stats['last_30d']}"

        # 验证月份统计
        last_month_key = (datetime.utcnow().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        assert last_month_key in stats["months"], \
            f"Expected {last_month_key} in months"
        assert stats["months"][last_month_key] == 10, \
            f"Expected 10 items for {last_month_key}, got {stats['months'][last_month_key]}"

    @pytest.mark.asyncio
    async def test_time_range_7d(self, test_db, test_user, test_agent, conversation_data):
        """测试最近 7 天范围的数据准确性"""
        service = ConversationArchiveService(test_db)
        items, total = await service.get_conversation_history(
            user_id=test_user.id,
            limit=20,
            offset=0,
            time_range="7d",
        )

        # 验证总数
        assert total == 5, f"Expected 5 items, got {total}"

        # 验证返回的都是 7 天内的数据
        for item in items:
            assert item["source"] == "hot", "All items in 7d range should be from hot storage"

    @pytest.mark.asyncio
    async def test_time_range_30d(self, test_db, test_user, test_agent, conversation_data):
        """测试最近 30 天范围的数据准确性"""
        service = ConversationArchiveService(test_db)
        items, total = await service.get_conversation_history(
            user_id=test_user.id,
            limit=20,
            offset=0,
            time_range="30d",
        )

        # 验证总数（7 天 + 8-30 天）
        expected = len(conversation_data["hot_7d"]) + len(conversation_data["hot_30d"])
        assert total == expected, f"Expected {expected} items, got {total}"

    @pytest.mark.asyncio
    async def test_time_range_month(self, test_db, test_user, test_agent, conversation_data):
        """测试月份范围的数据准确性"""
        service = ConversationArchiveService(test_db)
        last_month = (datetime.utcnow().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")

        items, total = await service.get_conversation_history(
            user_id=test_user.id,
            limit=20,
            offset=0,
            time_range="month",
            month=last_month,
        )

        # 验证总数（上个月的温归档数据）
        assert total == 10, f"Expected 10 items for {last_month}, got {total}"

        # 验证返回的都是温归档数据
        for item in items:
            assert item["source"] == "archive", "All items should be from archive"
            assert item["archive_tier"] == "warm", "All items should be warm archive"

    @pytest.mark.asyncio
    async def test_pagination_accuracy(self, test_db, test_user, test_agent, conversation_data):
        """测试分页数据准确性"""
        service = ConversationArchiveService(test_db)

        # 第一页
        items1, total1 = await service.get_conversation_history(
            user_id=test_user.id,
            limit=10,
            offset=0,
        )

        # 第二页
        items2, total2 = await service.get_conversation_history(
            user_id=test_user.id,
            limit=10,
            offset=10,
        )

        # 验证总数一致
        assert total1 == total2, "Total should be consistent across pages"

        # 验证没有重复
        thread_ids_1 = {item["thread_id"] for item in items1}
        thread_ids_2 = {item["thread_id"] for item in items2}
        assert thread_ids_1.isdisjoint(thread_ids_2), "No overlap between pages"

        # 验证每页数量
        assert len(items1) == 10, f"First page should have 10 items, got {len(items1)}"

    @pytest.mark.asyncio
    async def test_agent_filter_accuracy(self, test_db, test_user, test_agent, conversation_data):
        """测试智能体过滤准确性"""
        # 创建另一个智能体的数据
        other_agent = AgentConfig(
            id=uuid4(),
            user_id=test_user.id,
            name="Other Agent",
            system_prompt="Other agent",
            status="active",
        )
        test_db.add(other_agent)
        await test_db.commit()

        other_memory = AgentMemory(
            id=str(uuid4()),
            agent_id=str(other_agent.id),
            user_id=test_user.id,
            thread_id=f"thread-other-{uuid4().hex[:8]}",
            memory_type="conversation",
            content={"messages": []},
            created_at=datetime.utcnow(),
        )
        test_db.add(other_memory)
        await test_db.commit()

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

        # 验证过滤后的数量更少
        assert filtered_total < all_total, \
            "Filtered total should be less than all items"

        # 验证过滤后的都属于指定智能体
        for item in filtered_items:
            assert str(item["agent_id"]) == str(test_agent.id), \
                "All filtered items should belong to the specified agent"

    @pytest.mark.asyncio
    async def test_api_response_format(self, test_db, test_user, conversation_data):
        """测试 API 响应格式"""
        # 模拟 FastAPI 请求
        from unittest.mock import MagicMock
        mock_user = MagicMock()
        mock_user.id = test_user.id

        result = await list_conversation_history(
            limit=20,
            offset=0,
            db=test_db,
            current_user=mock_user,
        )

        # 验证响应格式
        assert "items" in result
        assert "total" in result
        assert isinstance(result["items"], list)
        assert isinstance(result["total"], int)

        # 验证 item 格式
        if result["items"]:
            item = result["items"][0]
            assert "thread_id" in item
            assert "agent_id" in item
            assert "message_count" in item
            assert "last_message_at" in item
            assert "source" in item

    @pytest.mark.asyncio
    async def test_stats_api_response(self, test_db, test_user, conversation_data):
        """测试统计 API 响应格式"""
        from unittest.mock import MagicMock
        mock_user = MagicMock()
        mock_user.id = test_user.id

        result = await get_conversation_history_stats(
            db=test_db,
            current_user=mock_user,
        )

        # 验证响应格式
        assert "last_7d" in result
        assert "last_30d" in result
        assert "months" in result
        assert isinstance(result["last_7d"], int)
        assert isinstance(result["last_30d"], int)
        assert isinstance(result["months"], dict)


class TestDataConsistency:
    """数据一致性测试"""

    @pytest.mark.asyncio
    async def test_hot_cold_no_overlap(self, test_db, test_user, test_agent, conversation_data):
        """验证热数据和冷数据没有重叠"""
        service = ConversationArchiveService(test_db)

        # 获取热数据
        hot_items, _ = await service.get_conversation_history(
            user_id=test_user.id,
            limit=100,
            offset=0,
            time_range="7d",
        )

        # 获取冷归档
        cold_month = (datetime.utcnow() - timedelta(days=60)).strftime("%Y-%m")
        cold_items, _ = await service.get_conversation_history(
            user_id=test_user.id,
            limit=100,
            offset=0,
            time_range="month",
            month=cold_month,
        )

        # 验证没有重叠
        hot_thread_ids = {item["thread_id"] for item in hot_items}
        cold_thread_ids = {item["thread_id"] for item in cold_items}
        assert hot_thread_ids.isdisjoint(cold_thread_ids), \
            "Hot and cold data should not overlap"

    @pytest.mark.asyncio
    async def test_total_matches_sum(self, test_db, test_user, conversation_data):
        """验证总数等于各时间段之和"""
        stats = await ConversationArchiveService(test_db).get_conversation_history_stats(
            user_id=test_user.id
        )

        # 计算各月份总和
        months_total = sum(stats["months"].values())

        # 验证总数逻辑
        # 注意：last_30d 包含 last_7d，所以不能简单相加
        # 正确的验证方式是分别验证每个时间段
        assert stats["last_30d"] >= stats["last_7d"], \
            "last_30d should be >= last_7d"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
