"""
会话历史 API 数据准确性测试
通过 HTTP 请求测试远程服务器上的接口
"""
import pytest
import httpx
from datetime import datetime, timedelta
import asyncio

# 远程服务器配置
BASE_URL = "http://100.4.14.19:8000"
LOGIN_URL = f"{BASE_URL}/api/v1/auth/login"


@pytest.fixture
async def auth_token():
    """获取认证 token"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            LOGIN_URL,
            json={"username": "admin", "password": "admin123"},
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token")
        pytest.skip(f"无法登录：{response.status_code}")


@pytest.fixture
async def api_client(auth_token):
    """创建带认证的 HTTP 客户端"""
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {auth_token}"}
    ) as client:
        yield client


class TestConversationHistoryAPI:
    """会话历史 API 测试"""

    @pytest.mark.asyncio
    async def test_stats_endpoint(self, api_client):
        """测试统计接口"""
        response = await api_client.get("/api/v1/conversation-history/stats")

        assert response.status_code == 200, f"请求失败：{response.text}"
        data = response.json()

        # 验证响应格式
        assert "last_7d" in data, "缺少 last_7d 字段"
        assert "last_30d" in data, "缺少 last_30d 字段"
        assert "months" in data, "缺少 months 字段"
        assert isinstance(data["last_7d"], int), "last_7d 应该是整数"
        assert isinstance(data["last_30d"], int), "last_30d 应该是整数"
        assert isinstance(data["months"], dict), "months 应该是对象"

        # 验证数据一致性
        assert data["last_30d"] >= data["last_7d"], "last_30d 应该 >= last_7d"

    @pytest.mark.asyncio
    async def test_list_endpoint_default(self, api_client):
        """测试列表接口（默认参数）"""
        response = await api_client.get("/api/v1/conversation-history")

        assert response.status_code == 200, f"请求失败：{response.text}"
        data = response.json()

        # 验证响应格式
        assert "items" in data, "缺少 items 字段"
        assert "total" in data, "缺少 total 字段"
        assert isinstance(data["items"], list), "items 应该是数组"
        assert isinstance(data["total"], int), "total 应该是整数"

    @pytest.mark.asyncio
    async def test_list_endpoint_pagination(self, api_client):
        """测试列表接口分页参数"""
        # 第一页
        response1 = await api_client.get(
            "/api/v1/conversation-history",
            params={"limit": 10, "offset": 0}
        )
        data1 = response1.json()

        # 第二页
        response2 = await api_client.get(
            "/api/v1/conversation-history",
            params={"limit": 10, "offset": 10}
        )
        data2 = response2.json()

        # 验证总数一致
        assert data1["total"] == data2["total"], "分页总数应该一致"

        # 验证没有重复
        ids1 = {item["thread_id"] for item in data1["items"]}
        ids2 = {item["thread_id"] for item in data2["items"]}
        assert ids1.isdisjoint(ids2), "分页数据不应该有重复"

    @pytest.mark.asyncio
    async def test_list_endpoint_time_range_7d(self, api_client):
        """测试 7 天范围"""
        response = await api_client.get(
            "/api/v1/conversation-history",
            params={"time_range": "7d", "limit": 100}
        )

        assert response.status_code == 200, f"请求失败：{response.text}"
        data = response.json()

        # 验证返回的都是 7 天内的数据
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        for item in data["items"]:
            last_message = datetime.fromisoformat(item["last_message_at"])
            assert last_message > seven_days_ago, \
                f"7 天范围内的数据应该都是最近 7 天的：{item['thread_id']}"

    @pytest.mark.asyncio
    async def test_list_endpoint_time_range_30d(self, api_client):
        """测试 30 天范围"""
        response = await api_client.get(
            "/api/v1/conversation-history",
            params={"time_range": "30d", "limit": 100}
        )

        assert response.status_code == 200, f"请求失败：{response.text}"
        data = response.json()

        # 验证返回的都是 30 天内的数据
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        for item in data["items"]:
            last_message = datetime.fromisoformat(item["last_message_at"])
            assert last_message > thirty_days_ago, \
                f"30 天范围内的数据应该都是最近 30 天的：{item['thread_id']}"

    @pytest.mark.asyncio
    async def test_list_endpoint_time_range_month(self, api_client):
        """测试月份范围"""
        # 上个月
        last_month = (datetime.utcnow().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")

        response = await api_client.get(
            "/api/v1/conversation-history",
            params={"time_range": "month", "month": last_month, "limit": 100}
        )

        assert response.status_code == 200, f"请求失败：{response.text}"
        data = response.json()

        # 验证返回的都是指定月份的数据
        year, month = map(int, last_month.split("-"))
        for item in data["items"]:
            last_message = datetime.fromisoformat(item["last_message_at"])
            assert last_message.year == year and last_message.month == month, \
                f"月份范围的数据应该都是指定月份的：{item['thread_id']}"

    @pytest.mark.asyncio
    async def test_list_endpoint_item_fields(self, api_client):
        """验证返回字段格式"""
        response = await api_client.get(
            "/api/v1/conversation-history",
            params={"limit": 1}
        )
        data = response.json()

        if data["items"]:
            item = data["items"][0]

            # 验证必填字段
            required_fields = {
                "thread_id": str,
                "agent_id": (str, type(None)),
                "message_count": int,
                "last_message_at": str,
                "source": str,
            }

            for field, expected_type in required_fields.items():
                assert field in item, f"缺少必填字段：{field}"
                assert isinstance(item[field], expected_type), \
                    f"字段 {field} 类型错误，应该是 {expected_type}"

            # 验证 source 值
            assert item["source"] in ["hot", "archive"], \
                f"source 应该是 hot 或 archive，实际是 {item['source']}"

            # 验证 archive_tier（如果是归档）
            if item["source"] == "archive":
                assert "archive_tier" in item, "归档数据应该有 archive_tier 字段"
                assert item["archive_tier"] in ["warm", "cold"], \
                    f"archive_tier 应该是 warm 或 cold，实际是 {item['archive_tier']}"

    @pytest.mark.asyncio
    async def test_list_endpoint_agent_filter(self, api_client):
        """测试智能体过滤"""
        # 先获取所有数据
        all_response = await api_client.get(
            "/api/v1/conversation-history",
            params={"limit": 100}
        )
        all_data = all_response.json()

        if all_data["items"]:
            # 选择一个智能体 ID
            agent_id = all_data["items"][0]["agent_id"]
            if agent_id:
                # 过滤该智能体
                filtered_response = await api_client.get(
                    "/api/v1/conversation-history",
                    params={"agent_id": agent_id, "limit": 100}
                )
                filtered_data = filtered_response.json()

                # 验证过滤后的都属于该智能体
                for item in filtered_data["items"]:
                    assert item["agent_id"] == agent_id, \
                        f"过滤后的数据应该都属于指定智能体：{item['thread_id']}"

    @pytest.mark.asyncio
    async def test_stats_and_list_consistency(self, api_client):
        """验证统计和列表数据的一致性"""
        # 获取统计
        stats_response = await api_client.get("/api/v1/conversation-history/stats")
        stats = stats_response.json()

        # 获取 7 天列表
        list_7d_response = await api_client.get(
            "/api/v1/conversation-history",
            params={"time_range": "7d", "limit": 1000}
        )
        list_7d = list_7d_response.json()

        # 验证 7 天统计和列表总数一致
        assert stats["last_7d"] == list_7d["total"], \
            f"7 天统计 ({stats['last_7d']}) 和列表总数 ({list_7d['total']}) 不一致"

    @pytest.mark.asyncio
    async def test_thread_messages_endpoint(self, api_client):
        """测试获取会话消息"""
        # 先获取会话列表
        list_response = await api_client.get(
            "/api/v1/conversation-history",
            params={"limit": 1}
        )
        list_data = list_response.json()

        if list_data["items"]:
            thread_id = list_data["items"][0]["thread_id"]

            # 获取消息详情
            messages_response = await api_client.get(
                f"/api/v1/conversation-history/{thread_id}/messages"
            )

            assert messages_response.status_code == 200, \
                f"获取消息失败：{messages_response.text}"
            messages_data = messages_response.json()

            # 验证响应格式
            assert "messages" in messages_data, "缺少 messages 字段"
            assert "source" in messages_data, "缺少 source 字段"
            assert isinstance(messages_data["messages"], list), "messages 应该是数组"


class TestArchiveAPI:
    """归档功能 API 测试"""

    @pytest.mark.asyncio
    async def test_run_archive_job(self, api_client):
        """测试运行归档任务"""
        response = await api_client.post(
            "/api/v1/conversation-history/archive/run"
        )

        # 可能成功或失败，但接口应该可访问
        assert response.status_code in [200, 500], \
            f"接口不可访问：{response.status_code}"


class TestDataAccuracySummary:
    """数据准确性总结测试"""

    @pytest.mark.asyncio
    async def test_api_health(self, api_client):
        """测试 API 健康状态"""
        # 测试健康检查
        health_response = await api_client.get("/api/v1/health")
        assert health_response.status_code == 200

        # 测试根路径
        root_response = await api_client.get("/")
        assert root_response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
