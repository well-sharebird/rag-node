"""
LLM Streaming Test - 测试配置的 LLM 返回结构

用法:
    cd backend
    uv run python tests/test_llm_stream.py

功能:
    1. 读取默认 LLM 配置
    2. 发送测试问题
    3. 打印原始 SSE 流结构
    4. 解析并展示结构化数据
"""
import asyncio
import json
import httpx
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import async_session_factory
from app.models.model_config import ModelConfig
from sqlalchemy import select


async def get_llm_config() -> dict | None:
    """获取默认 LLM 配置"""
    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(ModelConfig)
                .where(ModelConfig.model_type == "llm")
                .where(ModelConfig.is_enabled == True)
                .where(ModelConfig.is_default == True)
                .limit(1)
            )
            model = result.scalar_one_or_none()
            if model:
                print(f"\n✅ 找到 LLM 配置:")
                print(f"   名称：{model.name}")
                print(f"   模型 ID: {model.model_id}")
                print(f"   API URL: {model.api_url}")
                print(f"   适配器：{model.adapter_type}")
                return {
                    "id": model.id,
                    "name": model.name,
                    "api_url": model.api_url or "",
                    "api_key": model.api_key or "",
                    "model_id": model.model_id,
                    "adapter_type": model.adapter_type,
                }
    except Exception as e:
        print(f"❌ 读取 LLM 配置失败：{e}")
    return None


async def test_non_streaming(llm_config: dict):
    """测试非流式调用"""
    print("\n" + "=" * 60)
    print("📝 测试非流式调用 (stream=False)")
    print("=" * 60)

    base_url = llm_config["api_url"].rstrip("/")
    if not base_url.endswith("/v1"):
        api_url = f"{base_url}/v1/chat/completions"
    else:
        api_url = f"{base_url}/chat/completions"

    headers = {"Content-Type": "application/json"}
    if llm_config["api_key"]:
        headers["Authorization"] = f"Bearer {llm_config['api_key']}"

    test_query = "什么是 RAG？请简要解释。"
    messages = [
        {"role": "system", "content": "你是一个有帮助的助手。"},
        {"role": "user", "content": test_query},
    ]

    print(f"\n📤 请求 URL: {api_url}")
    print(f"📤 请求模型：{llm_config['model_id']}")
    print(f"📤 测试问题：{test_query}")

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            response = await client.post(
                api_url,
                json={
                    "model": llm_config["model_id"],
                    "messages": messages,
                    "temperature": 0.3,
                    "max_tokens": 512,
                    "stream": False,
                },
                headers=headers,
            )

            print(f"\n📥 响应状态码：{response.status_code}")
            print(f"📥 响应头：{dict(response.headers)}")
            print(f"\n📥 原始响应 JSON:")
            print(json.dumps(response.json(), indent=2, ensure_ascii=False))

            # 解析结构
            data = response.json()
            print(f"\n📊 解析结果:")
            print(f"   - object: {data.get('object')}")
            print(f"   - choices 数量：{len(data.get('choices', []))}")

            if data.get("choices"):
                choice = data["choices"][0]
                message = choice.get("message", {})
                print(f"   - message.role: {message.get('role')}")
                print(f"   - message.content 长度：{len(message.get('content', ''))}")
                print(f"   - message.reasoning: {message.get('reasoning', 'N/A')}")
                print(f"   - finish_reason: {choice.get('finish_reason')}")

            if data.get("usage"):
                usage = data["usage"]
                print(f"\n📊 Token 使用:")
                print(f"   - prompt_tokens: {usage.get('prompt_tokens')}")
                print(f"   - completion_tokens: {usage.get('completion_tokens')}")
                print(f"   - total_tokens: {usage.get('total_tokens')}")

    except Exception as e:
        print(f"\n❌ 请求失败：{e}")


async def test_streaming(llm_config: dict):
    """测试流式调用"""
    print("\n" + "=" * 60)
    print("📡 测试流式调用 (stream=True)")
    print("=" * 60)

    base_url = llm_config["api_url"].rstrip("/")
    if not base_url.endswith("/v1"):
        api_url = f"{base_url}/v1/chat/completions"
    else:
        api_url = f"{base_url}/chat/completions"

    headers = {"Content-Type": "application/json"}
    if llm_config["api_key"]:
        headers["Authorization"] = f"Bearer {llm_config['api_key']}"

    test_query = "什么是 RAG？"
    messages = [
        {"role": "system", "content": "你是一个有帮助的助手。请用中文回答。"},
        {"role": "user", "content": test_query},
    ]

    print(f"\n📤 请求 URL: {api_url}")
    print(f"📤 测试问题：{test_query}")
    print(f"\n📡 开始接收 SSE 流:\n")
    print("-" * 60)

    accumulated_reasoning = ""
    accumulated_content = ""
    event_count = 0

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            request = client.build_request(
                "POST",
                api_url,
                json={
                    "model": llm_config["model_id"],
                    "messages": messages,
                    "temperature": 0.3,
                    "max_tokens": 512,
                    "stream": True,
                },
                headers=headers,
            )

            async with client.stream(request) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    print(f"\n❌ 请求失败 {response.status_code}: {error_text[:300]}")
                    return

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue

                    # 移除 "data: " 前缀
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        print("\n- - - - - - - - - - - - - - - - - - - - - - - - - -")
                        print("📡 流结束 [DONE]")
                        break

                    event_count += 1

                    try:
                        chunk = json.loads(data_str)

                        # 打印原始 chunk
                        print(f"\n[事件 {event_count}] 原始数据:")
                        print(json.dumps(chunk, indent=2, ensure_ascii=False)[:500])

                        # 解析
                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            finish_reason = choices[0].get("finish_reason")

                            if delta.get("role"):
                                print(f"  → 角色：{delta['role']}")

                            if delta.get("reasoning_content") or delta.get("reasoning"):
                                reasoning = delta.get("reasoning_content") or delta.get("reasoning", "")
                                accumulated_reasoning += reasoning
                                print(f"  → 思考内容：{reasoning[:100]}...")

                            if delta.get("content"):
                                content = delta["content"]
                                accumulated_content += content
                                print(f"  → 回答内容：{content[:100]}...")

                            if finish_reason:
                                print(f"  → 结束原因：{finish_reason}")

                        # 检查 usage
                        if chunk.get("usage"):
                            print(f"\n📊 Token 使用：{json.dumps(chunk['usage'], ensure_ascii=False)}")

                    except json.JSONDecodeError as e:
                        print(f"  ⚠️ JSON 解析失败：{e}")
                        print(f"  原始数据：{data_str[:200]}")

                print("\n" + "=" * 60)
                print("📊 流式调用汇总")
                print("=" * 60)
                print(f"事件总数：{event_count}")
                print(f"思考内容长度：{len(accumulated_reasoning)}")
                print(f"回答内容长度：{len(accumulated_content)}")
                print(f"\n思考内容预览:")
                print(accumulated_reasoning[:300] if accumulated_reasoning else "无")
                print(f"\n回答内容预览:")
                print(accumulated_content[:300] if accumulated_content else "无")

    except Exception as e:
        print(f"\n❌ 流式请求失败：{e}")
        import traceback
        traceback.print_exc()


async def main():
    """主函数"""
    print("=" * 60)
    print("🧪 LLM 流式调用测试工具")
    print("=" * 60)

    # 获取 LLM 配置
    llm_config = await get_llm_config()
    if not llm_config:
        print("\n❌ 未找到启用的默认 LLM 配置")
        print("请先在 Model Management 中配置 LLM")
        return

    # 自动执行两种测试
    print("\n🚀 自动执行两种测试...\n")
    await test_non_streaming(llm_config)
    await asyncio.sleep(1)
    await test_streaming(llm_config)


if __name__ == "__main__":
    asyncio.run(main())
