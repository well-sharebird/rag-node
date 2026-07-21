#!/usr/bin/env python3
"""
Test script for Token Usage Tracking
测试 Token 使用记录功能
"""
import asyncio
import httpx

BASE_URL = "http://localhost:8000/api/v1"

async def test_token_usage():
    async with httpx.AsyncClient(timeout=30) as client:
        # Step 1: Login as admin
        print("=" * 60)
        print("Step 1: 登录获取 Token")
        print("=" * 60)

        try:
            response = await client.post(
                f"{BASE_URL}/auth/login",
                json={"username": "admin", "password": "admin123"}
            )
            print(f"Login response: {response.status_code}")

            if response.status_code != 200:
                print(f"登录失败：{response.text}")
                # Try to create admin user first
                print("尝试初始化 admin 用户...")
                init_response = await client.post(f"{BASE_URL}/users/init")
                print(f"Init response: {init_response.status_code} - {init_response.text}")

                response = await client.post(
                    f"{BASE_URL}/auth/login",
                    json={"username": "admin", "password": "admin123"}
                )
                print(f"Login response (retry): {response.status_code}")

            if response.status_code != 200:
                print("无法登录，跳过测试")
                return

            data = response.json()
            access_token = data["access_token"]
            print(f"✓ 登录成功！Token: {access_token[:20]}...")
        except Exception as e:
            print(f"登录失败：{e}")
            return

        headers = {"Authorization": f"Bearer {access_token}"}

        # Step 2: Check current token usage stats
        print("\n" + "=" * 60)
        print("Step 2: 查看当前 Token 使用统计")
        print("=" * 60)

        try:
            response = await client.get(
                f"{BASE_URL}/token-usage/my-stats?days=7",
                headers=headers
            )
            print(f"Token usage stats: {response.status_code}")
            if response.status_code == 200:
                print(f"✓ 当前统计：{response.json()}")
            else:
                print(f"获取统计失败：{response.text}")
        except Exception as e:
            print(f"获取统计失败：{e}")

        # Step 3: Check quota
        print("\n" + "=" * 60)
        print("Step 3: 查看配额")
        print("=" * 60)

        try:
            response = await client.get(
                f"{BASE_URL}/token-usage/my-quota",
                headers=headers
            )
            print(f"Quota response: {response.status_code}")
            if response.status_code == 200:
                print(f"✓ 配额信息：{response.json()}")
            else:
                print(f"获取配额失败：{response.text}")
        except Exception as e:
            print(f"获取配额失败：{e}")

        # Step 4: Simulate recording token usage
        print("\n" + "=" * 60)
        print("Step 4: 模拟记录 Token 使用")
        print("=" * 60)

        try:
            response = await client.post(
                f"{BASE_URL}/token-usage/record",
                headers=headers,
                json={
                    "model_name": "Qwen2.5-72B",
                    "model_type": "llm",
                    "provider": "openai",
                    "input_tokens": 100,
                    "output_tokens": 250,
                    "total_tokens": 350,
                    "cost": 0.001,
                    "currency": "USD",
                    "request_type": "chat",
                    "status": "success",
                    "latency_ms": 500,
                }
            )
            print(f"Record response: {response.status_code}")
            if response.status_code == 200:
                print(f"✓ Token 使用记录成功：{response.json()}")
            else:
                print(f"记录失败：{response.text}")
        except Exception as e:
            print(f"记录失败：{e}")

        # Step 5: Check stats again
        print("\n" + "=" * 60)
        print("Step 5: 再次查看统计（应该有数据了）")
        print("=" * 60)

        try:
            response = await client.get(
                f"{BASE_URL}/token-usage/my-stats?days=7",
                headers=headers
            )
            print(f"Token usage stats (after): {response.status_code}")
            if response.status_code == 200:
                print(f"✓ 更新后统计：{response.json()}")
            else:
                print(f"获取统计失败：{response.text}")
        except Exception as e:
            print(f"获取统计失败：{e}")

        # Step 6: Check trend
        print("\n" + "=" * 60)
        print("Step 6: 查看使用趋势")
        print("=" * 60)

        try:
            response = await client.get(
                f"{BASE_URL}/token-usage/my-trend?days=7",
                headers=headers
            )
            print(f"Trend response: {response.status_code}")
            if response.status_code == 200:
                print(f"✓ 趋势数据：{response.json()}")
            else:
                print(f"获取趋势失败：{response.text}")
        except Exception as e:
            print(f"获取趋势失败：{e}")

        print("\n" + "=" * 60)
        print("测试完成！")
        print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_token_usage())
