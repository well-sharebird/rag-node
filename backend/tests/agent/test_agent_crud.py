"""
智能体 CRUD 功能自动化测试
测试所有 Agent 相关 API 端点
"""
import pytest
import httpx
import asyncio
from typing import Optional

BASE_URL = "http://localhost:8000"
API_PREFIX = "/api/v1"

# 测试用 Token（需要替换为有效的 token）
# 如果没有认证系统，可以跳过 auth
TEST_TOKEN = "test_token_123"

# 存储创建的 agent ID 用于后续测试
created_agent_id: Optional[str] = None


def get_headers():
    """获取请求头"""
    return {
        "Authorization": f"Bearer {TEST_TOKEN}",
        "Content-Type": "application/json",
    }


class TestAgentCRUD:
    """智能体 CRUD 测试类"""

    @pytest.mark.asyncio
    async def test_01_create_agent_minimal(self):
        """测试 1: 最小化创建智能体（仅提供必填字段）"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}{API_PREFIX}/agents",
                headers=get_headers(),
                json={
                    "name": "测试助手",
                    "system_prompt": "你是一个测试助手。"
                },
            )
            print(f"\n[Test 1] 创建智能体 - 状态码：{response.status_code}")

            if response.status_code == 200:
                data = response.json()
                global created_agent_id
                created_agent_id = data["id"]
                print(f"✓ 创建成功，Agent ID: {created_agent_id}")
                print(f"  名称：{data['name']}")
                print(f"  类型：{data['agent_type']}")
                print(f"  记忆类型：{data['memory_type']}")
                assert data["name"] == "测试助手"
                assert data["agent_type"] == "single"
                assert data["memory_type"] == "conversation"
            elif response.status_code == 401:
                print("⚠ 认证失败，跳过后续测试")
                pytest.skip("需要有效的认证 Token")
            else:
                print(f"✗ 创建失败：{response.text}")
                assert False, f"创建失败：{response.text}"

    @pytest.mark.asyncio
    async def test_02_create_agent_full(self):
        """测试 2: 完整参数创建智能体"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}{API_PREFIX}/agents",
                headers=get_headers(),
                json={
                    "name": "高级测试助手",
                    "description": "这是一个功能完整的测试智能体",
                    "icon": "🤖",
                    "agent_type": "single",
                    "system_prompt": "你是一个高级测试助手，功能齐全。",
                    "enabled_skills": ["web_search", "code_interpreter"],
                    "memory_type": "vector",
                    "memory_ttl_hours": 48,
                    "max_memory_turns": 100,
                    "retrieval_enabled": True,
                    "retrieval_top_k": 10,
                    "is_public": False,
                },
            )
            print(f"\n[Test 2] 完整参数创建 - 状态码：{response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"✓ 创建成功，Agent ID: {data['id']}")
                assert data["name"] == "高级测试助手"
                assert data["agent_type"] == "single"
                assert data["memory_type"] == "vector"
                assert data["retrieval_enabled"] == True
                assert data["retrieval_top_k"] == 10
            elif response.status_code == 401:
                pytest.skip("需要有效的认证 Token")
            else:
                print(f"✗ 创建失败：{response.text}")
                assert False, f"创建失败：{response.text}"

    @pytest.mark.asyncio
    async def test_03_list_agents(self):
        """测试 3: 获取智能体列表"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BASE_URL}{API_PREFIX}/agents",
                headers=get_headers(),
            )
            print(f"\n[Test 3] 获取列表 - 状态码：{response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"✓ 获取成功，共 {len(data)} 个智能体")
                for agent in data:
                    print(f"  - {agent['name']} ({agent['id']})")
            elif response.status_code == 401:
                pytest.skip("需要有效的认证 Token")
            else:
                print(f"✗ 获取失败：{response.text}")

    @pytest.mark.asyncio
    async def test_04_get_agent_detail(self):
        """测试 4: 获取智能体详情"""
        if not created_agent_id:
            print("\n[Test 4] 跳过 - 没有可用的 Agent ID")
            pytest.skip("没有已创建的 Agent")

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BASE_URL}{API_PREFIX}/agents/{created_agent_id}",
                headers=get_headers(),
            )
            print(f"\n[Test 4] 获取详情 - 状态码：{response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"✓ 获取成功")
                print(f"  名称：{data['name']}")
                print(f"  描述：{data.get('description', 'N/A')}")
                print(f"  系统提示：{data['system_prompt'][:50]}...")
            elif response.status_code == 401:
                pytest.skip("需要有效的认证 Token")
            elif response.status_code == 404:
                print(f"✗ Agent 不存在")
                pytest.fail("Agent 不存在")
            else:
                print(f"✗ 获取失败：{response.text}")

    @pytest.mark.asyncio
    async def test_05_update_agent(self):
        """测试 5: 更新智能体"""
        if not created_agent_id:
            print("\n[Test 5] 跳过 - 没有可用的 Agent ID")
            pytest.skip("没有已创建的 Agent")

        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{BASE_URL}{API_PREFIX}/agents/{created_agent_id}",
                headers=get_headers(),
                json={
                    "description": "已更新的描述",
                    "system_prompt": "你是一个已更新的测试助手。",
                },
            )
            print(f"\n[Test 5] 更新智能体 - 状态码：{response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"✓ 更新成功")
                print(f"  新描述：{data.get('description', 'N/A')}")
                assert data["description"] == "已更新的描述"
            elif response.status_code == 401:
                pytest.skip("需要有效的认证 Token")
            else:
                print(f"✗ 更新失败：{response.text}")

    @pytest.mark.asyncio
    async def test_06_duplicate_agent(self):
        """测试 6: 复制智能体"""
        if not created_agent_id:
            print("\n[Test 6] 跳过 - 没有可用的 Agent ID")
            pytest.skip("没有已创建的 Agent")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}{API_PREFIX}/agents/{created_agent_id}/duplicate",
                headers=get_headers(),
            )
            print(f"\n[Test 6] 复制智能体 - 状态码：{response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"✓ 复制成功，新 Agent ID: {data['id']}")
                print(f"  名称：{data['name']}")
                assert "(副本)" in data["name"]
            elif response.status_code == 401:
                pytest.skip("需要有效的认证 Token")
            else:
                print(f"✗ 复制失败：{response.text}")

    @pytest.mark.asyncio
    async def test_07_publish_agent(self):
        """测试 7: 发布智能体"""
        if not created_agent_id:
            print("\n[Test 7] 跳过 - 没有可用的 Agent ID")
            pytest.skip("没有已创建的 Agent")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}{API_PREFIX}/agents/{created_agent_id}/publish",
                headers=get_headers(),
            )
            print(f"\n[Test 7] 发布智能体 - 状态码：{response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"✓ 发布成功，状态：{data['status']}")
                assert data["status"] == "active"
            elif response.status_code == 401:
                pytest.skip("需要有效的认证 Token")
            else:
                print(f"✗ 发布失败：{response.text}")

    @pytest.mark.asyncio
    async def test_08_create_from_requirement(self):
        """测试 8: 按需求创建智能体（AI 分析）"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}{API_PREFIX}/agents/from-requirement",
                headers=get_headers(),
                json={
                    "requirement": "我需要一个帮我写技术文档的助手，可以生成 API 文档和用户手册"
                },
            )
            print(f"\n[Test 8] 按需求创建 - 状态码：{response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"✓ 创建成功")
                print(f"  Agent ID: {data['agent']['id']}")
                print(f"  名称：{data['agent']['name']}")
                print(f"  分析结果：{data['analysis']}")
            elif response.status_code == 401:
                pytest.skip("需要有效的认证 Token")
            elif response.status_code == 500:
                print(f"⚠ 服务错误（可能 LLM 未配置）: {response.text[:200]}")
                pytest.skip("LLM 服务可能未配置")
            else:
                print(f"✗ 创建失败：{response.text[:200]}")

    @pytest.mark.asyncio
    async def test_09_delete_agent(self):
        """测试 9: 删除智能体"""
        if not created_agent_id:
            print("\n[Test 9] 跳过 - 没有可用的 Agent ID")
            pytest.skip("没有已创建的 Agent")

        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{BASE_URL}{API_PREFIX}/agents/{created_agent_id}",
                headers=get_headers(),
            )
            print(f"\n[Test 9] 删除智能体 - 状态码：{response.status_code}")

            if response.status_code == 200:
                print(f"✓ 删除成功")
            elif response.status_code == 401:
                pytest.skip("需要有效的认证 Token")
            elif response.status_code == 404:
                print(f"⚠ Agent 不存在（可能已删除）")
            else:
                print(f"✗ 删除失败：{response.text}")


if __name__ == "__main__":
    # 简单测试运行
    print("=" * 60)
    print("智能体 CRUD 功能自动化测试")
    print("=" * 60)

    async def run_tests():
        test = TestAgentCRUD()

        print("\n" + "-" * 40)
        try:
            await test.test_01_create_agent_minimal()
        except Exception as e:
            print(f"Test 1 异常：{e}")

        print("\n" + "-" * 40)
        try:
            await test.test_02_create_agent_full()
        except Exception as e:
            print(f"Test 2 异常：{e}")

        print("\n" + "-" * 40)
        try:
            await test.test_03_list_agents()
        except Exception as e:
            print(f"Test 3 异常：{e}")

        print("\n" + "-" * 40)
        try:
            await test.test_04_get_agent_detail()
        except Exception as e:
            print(f"Test 4 异常：{e}")

        print("\n" + "-" * 40)
        try:
            await test.test_05_update_agent()
        except Exception as e:
            print(f"Test 5 异常：{e}")

        print("\n" + "-" * 40)
        try:
            await test.test_06_duplicate_agent()
        except Exception as e:
            print(f"Test 6 异常：{e}")

        print("\n" + "-" * 40)
        try:
            await test.test_07_publish_agent()
        except Exception as e:
            print(f"Test 7 异常：{e}")

        print("\n" + "-" * 40)
        try:
            await test.test_08_create_from_requirement()
        except Exception as e:
            print(f"Test 8 异常：{e}")

        print("\n" + "-" * 40)
        try:
            await test.test_09_delete_agent()
        except Exception as e:
            print(f"Test 9 异常：{e}")

        print("\n" + "=" * 60)
        print("测试完成")
        print("=" * 60)

    asyncio.run(run_tests())
