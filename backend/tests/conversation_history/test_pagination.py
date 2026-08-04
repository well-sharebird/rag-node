"""
会话历史分页功能测试
测试按时间段分组展示和分页功能
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from packages.agent.services.conversation_archive_service import ConversationArchiveService
from packages.agent.api.conversation_history import (
    list_conversation_history,
    get_conversation_history_stats,
)
from packages.core.system.models.user import User


class TestConversationHistoryPagination:
    """会话历史分页功能测试"""

    @pytest.fixture
    def mock_db(self):
        """模拟数据库 session"""
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.fixture
    def mock_config(self):
        """模拟归档配置"""
        config = MagicMock()
        config.hot_tier_days = 7
        config.warm_tier_days = 30
        config.cold_tier_days = 365
        return config

    @pytest.fixture
    def mock_user(self):
        """模拟当前用户"""
        user = MagicMock(spec=User)
        user.id = 1
        return user

    @pytest.fixture
    def mock_threads(self):
        """生成模拟会话数据"""
        now = datetime.utcnow()
        threads = []

        # 最近 7 天的数据 (10 条)
        for i in range(10):
            threads.append(MagicMock(
                thread_id=f"thread-7d-{i}",
                agent_id=str(uuid4()),
                agent_name=f"Agent 7d-{i}",
                message_count=5,
                last_message_at=now - timedelta(days=i),
                source="hot",
            ))

        # 8-30 天的数据 (15 条)
        for i in range(15):
            threads.append(MagicMock(
                thread_id=f"thread-30d-{i}",
                agent_id=str(uuid4()),
                agent_name=f"Agent 30d-{i}",
                message_count=8,
                last_message_at=now - timedelta(days=8 + i),
                source="archive",
                archive_tier="warm",
            ))

        # 更早的月份数据 (按月)
        for month_offset in range(1, 6):  # 过去 5 个月
            for i in range(10):
                threads.append(MagicMock(
                    thread_id=f"thread-month{month_offset}-{i}",
                    agent_id=str(uuid4()),
                    agent_name=f"Agent M{month_offset}-{i}",
                    message_count=10,
                    last_message_at=now - timedelta(days=30 * month_offset + i),
                    source="archive",
                    archive_tier="cold",
                ))

        return threads


class TestListConversationHistoryPagination(TestConversationHistoryPagination):
    """测试会话历史列表分页"""

    @pytest.mark.asyncio
    async def test_pagination_default(self, mock_db, mock_user, mock_threads):
        """测试默认分页（第一页，20 条）"""
        # 模拟服务返回第一页数据
        with patch.object(ConversationArchiveService, 'get_conversation_history',
                         return_value=(mock_threads[:20], 50)) as mock_get:
            result = await list_conversation_history(
                limit=20,
                offset=0,
                db=mock_db,
                current_user=mock_user,
            )

            assert len(result["items"]) == 20
            assert result["total"] == 50
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_pagination_page_2(self, mock_db, mock_user, mock_threads):
        """测试第二页分页"""
        with patch.object(ConversationArchiveService, 'get_conversation_history',
                         return_value=(mock_threads[20:40], 50)) as mock_get:
            result = await list_conversation_history(
                limit=20,
                offset=20,
                db=mock_db,
                current_user=mock_user,
            )

            assert len(result["items"]) == 20
            assert result["total"] == 50

    @pytest.mark.asyncio
    async def test_pagination_custom_limit(self, mock_db, mock_user, mock_threads):
        """测试自定义每页数量"""
        with patch.object(ConversationArchiveService, 'get_conversation_history',
                         return_value=(mock_threads[:10], 50)) as mock_get:
            result = await list_conversation_history(
                limit=10,
                offset=0,
                db=mock_db,
                current_user=mock_user,
            )

            assert len(result["items"]) == 10
            assert result["total"] == 50

    @pytest.mark.asyncio
    async def test_pagination_last_page(self, mock_db, mock_user, mock_threads):
        """测试最后一页（不足一页）"""
        # 模拟最后一页只有 10 条数据
        last_page_items = [MagicMock() for _ in range(10)]

        with patch.object(ConversationArchiveService, 'get_conversation_history',
                         return_value=(last_page_items, 50)) as mock_get:
            result = await list_conversation_history(
                limit=20,
                offset=40,
                db=mock_db,
                current_user=mock_user,
            )

            assert len(result["items"]) == 10  # 最后一页不足 20 条
            assert result["total"] == 50

    @pytest.mark.asyncio
    async def test_pagination_empty_result(self, mock_db, mock_user):
        """测试空结果分页"""
        with patch.object(ConversationArchiveService, 'get_conversation_history',
                         return_value=([], 0)) as mock_get:
            result = await list_conversation_history(
                limit=20,
                offset=100,
                db=mock_db,
                current_user=mock_user,
            )

            assert len(result["items"]) == 0
            assert result["total"] == 0


class TestTimeRangePagination(TestConversationHistoryPagination):
    """测试按时间范围分页"""

    @pytest.mark.asyncio
    async def test_time_range_7d(self, mock_db, mock_user, mock_threads):
        """测试最近 7 天范围"""
        # 只返回最近 7 天的数据
        threads_7d = [t for t in mock_threads if t.source == "hot"]

        with patch.object(ConversationArchiveService, 'get_conversation_history',
                         return_value=(threads_7d[:20], len(threads_7d))) as mock_get:
            result = await list_conversation_history(
                limit=20,
                offset=0,
                time_range="7d",
                db=mock_db,
                current_user=mock_user,
            )

            assert result["total"] == len(threads_7d)
            # 验证调用了正确的参数
            call_args = mock_get.call_args
            assert call_args.kwargs['time_range'] == "7d"

    @pytest.mark.asyncio
    async def test_time_range_30d(self, mock_db, mock_user, mock_threads):
        """测试最近 30 天范围"""
        threads_30d = [t for t in mock_threads if t.source in ["hot", "archive"] and t.archive_tier == "warm"]

        with patch.object(ConversationArchiveService, 'get_conversation_history',
                         return_value=(threads_30d[:20], len(threads_30d))) as mock_get:
            result = await list_conversation_history(
                limit=20,
                offset=0,
                time_range="30d",
                db=mock_db,
                current_user=mock_user,
            )

            assert result["total"] == len(threads_30d)
            call_args = mock_get.call_args
            assert call_args.kwargs['time_range'] == "30d"

    @pytest.mark.asyncio
    async def test_time_range_month(self, mock_db, mock_user, mock_threads):
        """测试指定月份范围"""
        with patch.object(ConversationArchiveService, 'get_conversation_history',
                         return_value=(mock_threads[:20], 30)) as mock_get:
            result = await list_conversation_history(
                limit=20,
                offset=0,
                time_range="month",
                month="2026-07",
                db=mock_db,
                current_user=mock_user,
            )

            call_args = mock_get.call_args
            assert call_args.kwargs['time_range'] == "month"
            assert call_args.kwargs['month'] == "2026-07"

    @pytest.mark.asyncio
    async def test_time_range_all(self, mock_db, mock_user, mock_threads):
        """测试全部时间范围"""
        with patch.object(ConversationArchiveService, 'get_conversation_history',
                         return_value=(mock_threads[:20], 100)) as mock_get:
            result = await list_conversation_history(
                limit=20,
                offset=0,
                time_range="all",
                db=mock_db,
                current_user=mock_user,
            )

            call_args = mock_get.call_args
            assert call_args.kwargs['time_range'] == "all"


class TestConversationHistoryStats(TestConversationHistoryPagination):
    """测试会话历史统计接口"""

    @pytest.mark.asyncio
    async def test_stats_success(self, mock_db, mock_user):
        """测试成功获取统计"""
        mock_stats = {
            "last_7d": 10,
            "last_30d": 25,
            "months": {
                "2026-07": 20,
                "2026-06": 15,
                "2026-05": 12,
            }
        }

        with patch.object(ConversationArchiveService, 'get_conversation_history_stats',
                         return_value=mock_stats) as mock_get:
            result = await get_conversation_history_stats(
                db=mock_db,
                current_user=mock_user,
            )

            assert result == mock_stats
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_stats_with_agent_filter(self, mock_db, mock_user):
        """测试带智能体过滤的统计"""
        mock_stats = {
            "last_7d": 5,
            "last_30d": 12,
            "months": {"2026-07": 10}
        }

        with patch.object(ConversationArchiveService, 'get_conversation_history_stats',
                         return_value=mock_stats) as mock_get:
            result = await get_conversation_history_stats(
                agent_id="agent-123",
                db=mock_db,
                current_user=mock_user,
            )

            call_args = mock_get.call_args
            assert call_args.kwargs['agent_id'] == "agent-123"

    @pytest.mark.asyncio
    async def test_stats_empty(self, mock_db, mock_user):
        """测试空统计"""
        mock_stats = {
            "last_7d": 0,
            "last_30d": 0,
            "months": {}
        }

        with patch.object(ConversationArchiveService, 'get_conversation_history_stats',
                         return_value=mock_stats):
            result = await get_conversation_history_stats(
                db=mock_db,
                current_user=mock_user,
            )

            assert result["last_7d"] == 0
            assert result["last_30d"] == 0
            assert result["months"] == {}


class TestServiceMethodPagination(TestConversationHistoryPagination):
    """测试服务层分页方法"""

    @pytest.mark.asyncio
    async def test_get_conversation_history_pagination(self, mock_db, mock_user, mock_config):
        """测试服务层分页"""
        service = ConversationArchiveService(mock_db)
        service._config = mock_config

        # 模拟数据库返回
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        items, total = await service.get_conversation_history(
            user_id=1,
            limit=20,
            offset=0,
        )

        assert isinstance(items, list)
        assert isinstance(total, int)

    @pytest.mark.asyncio
    async def test_get_conversation_history_with_time_range(self, mock_db, mock_user, mock_config):
        """测试服务层带时间范围的分页"""
        service = ConversationArchiveService(mock_db)
        service._config = mock_config

        # 模拟数据库返回
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        # 测试 7 天范围
        items, total = await service.get_conversation_history(
            user_id=1,
            limit=20,
            offset=0,
            time_range="7d",
        )

        assert isinstance(items, list)

        # 测试月份范围
        items, total = await service.get_conversation_history(
            user_id=1,
            limit=20,
            offset=0,
            time_range="month",
            month="2026-07",
        )

        assert isinstance(items, list)

    @pytest.mark.asyncio
    async def test_get_stats_method(self, mock_db, mock_user):
        """测试统计方法"""
        service = ConversationArchiveService(mock_db)

        # 模拟数据库返回
        mock_result = MagicMock()
        mock_result.scalar.return_value = 10
        mock_db.execute.return_value = mock_result

        stats = await service.get_conversation_history_stats(user_id=1)

        assert "last_7d" in stats
        assert "last_30d" in stats
        assert "months" in stats


class TestPaginationEdgeCases(TestConversationHistoryPagination):
    """测试分页边界情况"""

    @pytest.mark.asyncio
    async def test_offset_beyond_total(self, mock_db, mock_user):
        """测试偏移量超出总数"""
        with patch.object(ConversationArchiveService, 'get_conversation_history',
                         return_value=([], 10)) as mock_get:
            result = await list_conversation_history(
                limit=20,
                offset=100,  # 超出总数
                db=mock_db,
                current_user=mock_user,
            )

            assert len(result["items"]) == 0
            assert result["total"] == 10

    @pytest.mark.asyncio
    async def test_limit_max_value(self, mock_db, mock_user):
        """测试最大每页数量"""
        with patch.object(ConversationArchiveService, 'get_conversation_history',
                         return_value=([MagicMock()] * 100, 100)) as mock_get:
            result = await list_conversation_history(
                limit=100,  # 最大值
                offset=0,
                db=mock_db,
                current_user=mock_user,
            )

            assert len(result["items"]) == 100

    @pytest.mark.asyncio
    async def test_agent_filter_with_pagination(self, mock_db, mock_user):
        """测试带智能体过滤的分页"""
        with patch.object(ConversationArchiveService, 'get_conversation_history',
                         return_value=([MagicMock()] * 10, 10)) as mock_get:
            result = await list_conversation_history(
                limit=20,
                offset=0,
                agent_id="agent-123",
                db=mock_db,
                current_user=mock_user,
            )

            call_args = mock_get.call_args
            assert call_args.kwargs['agent_id'] == "agent-123"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
