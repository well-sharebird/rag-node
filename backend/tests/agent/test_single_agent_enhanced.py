"""
单 Agent 执行引擎增强测试
测试增强后的单 Agent 执行能力：
1. 性能指标收集
2. 错误处理和重试
3. 流式输出
4. 工具调用统计
"""
import asyncio
import sys
import uuid
from datetime import datetime

sys.path.insert(0, '.')

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, delete

from app.models.agent import AgentConfig
from app.models.user import User
from app.services.agent_factory import AgentFactory, AgentExecutionMetrics

DATABASE_URL = "postgresql+asyncpg://postgres:postgres123@100.4.14.19:5432/rag_db"


class MockModelGateway:
    """模拟模型网关"""

    async def get_model_by_name(self, name: str):
        from app.schemas.chat import ModelConfig
        return ModelConfig(
            provider="local_qwen",
            model="qwen3.5-397b-a17b",
            temperature=0.7,
            max_tokens=4096,
            base_url="http://100.4.14.19:8000",
            api_key="not-needed",
        )


class MockSkillRegistry:
    """模拟技能注册表"""

    def get_tool(self, skill_id: str):
        return None


async def test_single_agent_execution_with_metrics():
    """测试单 Agent 执行（带性能指标）"""
    print("=" * 70)
    print("单 Agent 执行引擎增强测试 - 性能指标收集")
    print("=" * 70)

    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    test_agent_id = str(uuid.uuid4())
    user_id = 1

    async with async_session() as session:
        # ========== Step 1: 创建测试 Agent ==========
        print("\n[Step 1] 创建测试 Agent...")
        try:
            agent = AgentConfig(
                id=test_agent_id,
                user_id=user_id,
                name="性能测试助手",
                description="用于测试性能指标收集的 Agent",
                agent_type="single",
                default_model_config={
                    "provider": "local_qwen",
                    "model": "qwen3.5-397b-a17b",
                    "temperature": 0.7,
                    "max_tokens": 4096,
                },
                system_prompt="你是一个测试助手。请简洁回答。",
                enabled_skills=[],
                mcp_servers=[],
                status="active",
            )

            session.add(agent)
            await session.commit()
            print(f"✓ Agent 创建成功，ID: {test_agent_id[:8]}...")

        except Exception as e:
            await session.rollback()
            print(f"✗ Agent 创建失败：{e}")
            return

        # ========== Step 2: 执行并收集性能指标 ==========
        print("\n[Step 2] 执行 Agent 并收集性能指标...")
        try:
            mock_gateway = MockModelGateway()
            mock_registry = MockSkillRegistry()

            factory = AgentFactory(
                db=session,
                model_gateway=mock_gateway,
                skill_registry=mock_registry,
            )

            result = await factory.execute(
                agent_id=test_agent_id,
                user_id=user_id,
                query="你好，请用一句话介绍你自己。",
                runtime_config={},
            )

            print(f"✓ 执行成功")
            print(f"  run_id: {result['run_id'][:8]}...")
            print(f"  response 长度：{len(result['response'])}")

            # 检查性能指标
            if 'metrics' in result:
                metrics = result['metrics']
                print(f"\n  性能指标:")
                print(f"    延迟：{metrics.get('latency_ms', 'N/A')}ms")
                print(f"    状态：{metrics.get('status', 'N/A')}")
                print(f"    工具调用：{metrics.get('tool_calls', 0)}次")
                print(f"    输入 Token: {metrics.get('input_tokens', 0)}")
                print(f"    输出 Token: {metrics.get('output_tokens', 0)}")
            else:
                print(f"  ⚠ 未找到性能指标")

        except Exception as e:
            print(f"✗ 执行失败：{e}")
            import traceback
            traceback.print_exc()

        # ========== Step 3: 测试错误处理 ==========
        print("\n[Step 3] 测试错误处理（不存在的 Agent）...")
        try:
            result = await factory.execute(
                agent_id="non-existent-id",
                user_id=user_id,
                query="测试",
                runtime_config={},
            )

            if 'error' in result:
                print(f"✓ 错误正确处理：{result['error'][:50]}...")
            else:
                print(f"✗ 错误未被捕获")

        except Exception as e:
            print(f"✓ 异常被正确抛出：{str(e)[:50]}...")

        # ========== Step 4: 测试流式输出 ==========
        print("\n[Step 4] 测试流式输出...")
        try:
            chunks = []
            async for chunk in factory.execute_stream(
                agent_id=test_agent_id,
                user_id=user_id,
                query="你好，请用 3 个词形容春天。",
                runtime_config={},
            ):
                chunks.append(chunk)

            print(f"✓ 流式输出成功")
            print(f"  收到 chunk 数：{len(chunks)}")
            print(f"  总长度：{sum(len(c) for c in chunks)}")
            if chunks:
                print(f"  内容预览：{''.join(chunks)[:100]}...")

        except Exception as e:
            print(f"✗ 流式输出失败：{e}")
            import traceback
            traceback.print_exc()

        # ========== 清理 ==========
        print("\n[清理] 删除测试 Agent...")
        try:
            await session.execute(
                delete(AgentConfig).where(AgentConfig.id == test_agent_id)
            )
            await session.commit()
            print(f"✓ 测试数据已清理")
        except Exception as e:
            await session.rollback()
            print(f"✗ 清理失败：{e}")

    print("\n" + "=" * 70)
    print("单 Agent 执行引擎测试完成")
    print("=" * 70)


async def test_agent_execution_retry():
    """测试 Agent 执行重试机制"""
    print("\n" + "=" * 70)
    print("单 Agent 执行引擎测试 - 重试机制")
    print("=" * 70)

    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    test_agent_id = str(uuid.uuid4())
    user_id = 1

    async with async_session() as session:
        # 创建测试 Agent
        print("\n[准备] 创建测试 Agent...")
        agent = AgentConfig(
            id=test_agent_id,
            user_id=user_id,
            name="重试测试助手",
            description="用于测试重试机制的 Agent",
            agent_type="single",
            default_model_config={
                "provider": "local_qwen",
                "model": "qwen3.5-397b-a17b",
                "temperature": 0.7,
                "max_tokens": 4096,
            },
            system_prompt="你是一个测试助手。",
            enabled_skills=[],
            mcp_servers=[],
            status="active",
        )
        session.add(agent)
        await session.commit()

        # 测试重试（正常情况应该不需要重试）
        print("\n[测试] 执行 Agent（max_retries=2）...")
        try:
            mock_gateway = MockModelGateway()
            mock_registry = MockSkillRegistry()

            factory = AgentFactory(
                db=session,
                model_gateway=mock_gateway,
                skill_registry=mock_registry,
            )

            result = await factory.execute(
                agent_id=test_agent_id,
                user_id=user_id,
                query="你好",
                runtime_config={},
                max_retries=2,
            )

            print(f"✓ 执行完成")
            print(f"  状态：{result.get('metrics', {}).get('status', 'N/A')}")

        except Exception as e:
            print(f"✗ 执行失败：{e}")

        # 清理
        await session.execute(
            delete(AgentConfig).where(AgentConfig.id == test_agent_id)
        )
        await session.commit()

    print("\n" + "=" * 70)
    print("重试机制测试完成")
    print("=" * 70)


async def main():
    """运行所有测试"""
    await test_single_agent_execution_with_metrics()
    await test_agent_execution_retry()


if __name__ == "__main__":
    asyncio.run(main())
