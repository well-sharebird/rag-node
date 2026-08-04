"""
会话归档服务测试
测试 ConversationArchiveService 的核心功能
"""
import pytest
import gzip
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.conversation_archive_service import ConversationArchiveService


class TestConversationArchiveService:
    """会话归档服务测试类"""

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
    def mock_messages(self):
        """模拟消息数据"""
        return [
            {"role": "user", "content": "Hello", "timestamp": "2026-01-01T00:00:00Z"},
            {"role": "assistant", "content": "Hi there!", "timestamp": "2026-01-01T00:01:00Z"},
            {"role": "user", "content": "How are you?", "timestamp": "2026-01-01T00:02:00Z"},
        ]

    @pytest.fixture
    def service(self, mock_db):
        """创建服务实例"""
        return ConversationArchiveService(mock_db)


class TestArchiveConfig(TestConversationArchiveService):
    """测试归档配置获取"""

    @pytest.mark.asyncio
    async def test_get_config_cached(self, service):
        """测试获取缓存的配置"""
        # 设置缓存配置
        mock_config = MagicMock()
        mock_config.compression_enabled = True
        mock_config.compression_level = 6
        service._config = mock_config

        result = await service._get_config()

        assert result == mock_config

    @pytest.mark.asyncio
    async def test_get_config_from_db(self, service, mock_db):
        """测试从数据库获取配置"""
        service._config = None

        mock_config = MagicMock()
        mock_config.compression_enabled = True
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_db.execute.return_value = mock_result

        result = await service._get_config()

        assert result == mock_config
        assert service._config == mock_config  # 验证缓存


class TestArchiveToWarm(TestConversationArchiveService):
    """测试归档到温存储"""

    @pytest.mark.asyncio
    async def test_archive_to_warm_success(self, service, mock_db, mock_messages):
        """测试成功归档到温存储"""
        mock_config = MagicMock()
        mock_config.compression_enabled = True
        mock_config.compression_level = 6
        service._config = mock_config

        with patch.object(service, '_get_agent_name', return_value="Test Agent"):
            await service._archive_to_warm(
                user_id=1,
                thread_id="thread-1",
                agent_id="agent-1",
                messages=mock_messages,
                date_range_start=datetime.utcnow() - timedelta(days=10),
                date_range_end=datetime.utcnow(),
            )

        # 验证添加了归档记录
        mock_db.add.assert_called_once()
        archive = mock_db.add.call_args[0][0]
        assert archive.archive_tier == "warm"
        assert archive.message_count == 3
        assert archive.compressed_content is not None


class TestArchiveToCold(TestConversationArchiveService):
    """测试归档到冷存储"""

    @pytest.mark.asyncio
    async def test_archive_to_cold_success(self, service, mock_db, mock_messages):
        """测试成功归档到冷存储"""
        mock_config = MagicMock()
        mock_config.compression_level = 6
        mock_config.minio_bucket = "test-bucket"
        mock_config.minio_prefix = "archives"
        service._config = mock_config

        mock_minio = MagicMock()
        mock_minio.put_object = MagicMock()

        with patch.object(service, '_get_agent_name', return_value="Test Agent"):
            with patch('app.services.conversation_archive_service.get_minio_client',
                      return_value=mock_minio):
                await service._archive_to_cold(
                    user_id=1,
                    thread_id="thread-1",
                    agent_id="agent-1",
                    messages=mock_messages,
                    date_range_start=datetime.utcnow() - timedelta(days=60),
                    date_range_end=datetime.utcnow() - timedelta(days=30),
                )

        # 验证 MinIO 上传
        mock_minio.put_object.assert_called_once()
        mock_db.add.assert_called_once()


class TestRestoreArchive(TestConversationArchiveService):
    """测试恢复归档"""

    @pytest.mark.asyncio
    async def test_restore_from_warm(self, service, mock_db, mock_messages):
        """测试从温存储恢复"""
        # 创建压缩内容
        jsonl_lines = [json.dumps(msg) for msg in mock_messages]
        jsonl_content = "\n".join(jsonl_lines)
        compressed = gzip.compress(jsonl_content.encode("utf-8"))

        mock_archive = MagicMock()
        mock_archive.id = "archive-1"
        mock_archive.archive_tier = "warm"
        mock_archive.compressed_content = compressed
        mock_archive.thread_id = "thread-1"
        mock_archive.agent_id = "agent-1"
        mock_archive.user_id = 1

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_archive
        mock_db.execute.return_value = mock_result

        result = await service.restore_archive("archive-1")

        assert result is True
        mock_db.add.assert_called()  # 验证添加了 AgentMemory

    @pytest.mark.asyncio
    async def test_restore_from_cold(self, service, mock_db, mock_messages):
        """测试从冷存储恢复"""
        # 创建压缩内容
        jsonl_lines = [json.dumps(msg) for msg in mock_messages]
        jsonl_content = "\n".join(jsonl_lines)
        compressed = gzip.compress(jsonl_content.encode("utf-8"))

        mock_archive = MagicMock()
        mock_archive.id = "archive-1"
        mock_archive.archive_tier = "cold"
        mock_archive.archive_path = "archives/1/thread-1.jsonl.gz"
        mock_archive.thread_id = "thread-1"
        mock_archive.agent_id = "agent-1"
        mock_archive.user_id = 1

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_archive
        mock_db.execute.return_value = mock_result

        mock_minio_response = MagicMock()
        mock_minio_response.read.return_value = compressed

        mock_minio = MagicMock()
        mock_minio.get_object.return_value = mock_minio_response

        mock_config = MagicMock()
        mock_config.minio_bucket = "test-bucket"

        with patch.object(service, '_get_config', return_value=mock_config):
            with patch('app.services.conversation_archive_service.get_minio_client',
                      return_value=mock_minio):
                result = await service.restore_archive("archive-1")

        assert result is True
        mock_minio.get_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_restore_not_found(self, service, mock_db):
        """测试恢复不存在的归档"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError) as exc_info:
            await service.restore_archive("nonexistent")

        assert "not found" in str(exc_info.value)


class TestGetArchiveContent(TestConversationArchiveService):
    """测试获取归档内容"""

    @pytest.mark.asyncio
    async def test_get_warm_content(self, service, mock_db, mock_messages):
        """测试获取温归档内容"""
        jsonl_lines = [json.dumps(msg) for msg in mock_messages]
        jsonl_content = "\n".join(jsonl_lines)
        compressed = gzip.compress(jsonl_content.encode("utf-8"))

        mock_archive = MagicMock()
        mock_archive.archive_tier = "warm"
        mock_archive.compressed_content = compressed

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_archive
        mock_db.execute.return_value = mock_result

        result = await service.get_archive_content("archive-1")

        assert len(result) == len(mock_messages)
        assert result[0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_get_cold_content(self, service, mock_db, mock_messages):
        """测试获取冷归档内容"""
        jsonl_lines = [json.dumps(msg) for msg in mock_messages]
        jsonl_content = "\n".join(jsonl_lines)
        compressed = gzip.compress(jsonl_content.encode("utf-8"))

        mock_archive = MagicMock()
        mock_archive.archive_tier = "cold"
        mock_archive.archive_path = "archives/1/thread-1.jsonl.gz"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_archive
        mock_db.execute.return_value = mock_result

        mock_minio_response = MagicMock()
        mock_minio_response.read.return_value = compressed

        mock_minio = MagicMock()
        mock_minio.get_object.return_value = mock_minio_response

        mock_config = MagicMock()
        mock_config.minio_bucket = "test-bucket"

        with patch.object(service, '_get_config', return_value=mock_config):
            with patch('app.services.conversation_archive_service.get_minio_client',
                      return_value=mock_minio):
                result = await service.get_archive_content("archive-1")

        assert len(result) == len(mock_messages)

    @pytest.mark.asyncio
    async def test_get_content_not_found(self, service, mock_db):
        """测试获取不存在的归档内容"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError) as exc_info:
            await service.get_archive_content("nonexistent")

        assert "not found" in str(exc_info.value)


class TestSummaryAndKeywords(TestConversationArchiveService):
    """测试摘要和关键词生成"""

    def test_generate_summary(self, service, mock_messages):
        """测试生成摘要"""
        summary = service._generate_summary(mock_messages)

        assert isinstance(summary, str)
        assert "用户询问" in summary or len(summary) > 0

    def test_generate_summary_empty(self, service):
        """测试空消息的摘要"""
        summary = service._generate_summary([])
        assert summary == ""

    def test_extract_keywords(self, service, mock_messages):
        """测试提取关键词（简单版本返回空列表）"""
        keywords = service._extract_keywords(mock_messages)
        assert keywords == []

    def test_get_last_message_preview(self, service, mock_messages):
        """测试获取最后消息预览"""
        preview = service._get_last_message_preview(mock_messages)

        assert isinstance(preview, str)
        assert len(preview) <= 100

    def test_get_last_message_preview_empty(self, service):
        """测试空消息的预览"""
        preview = service._get_last_message_preview([])
        assert preview == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
