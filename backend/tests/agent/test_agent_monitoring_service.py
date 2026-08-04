"""
Agent 监控和调试服务测试
测试监控服务的核心功能：
1. 执行轨迹追踪
2. Token 消耗统计
3. 延迟监控
4. 错误分析
5. 告警检查
"""
import asyncio
import sys
import uuid
from datetime import datetime, timedelta

sys.path.insert(0, '.')

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, delete

from app.models.agent import AgentConfig, AgentCallLog
from app.services.agent_monitoring_service import AgentMonitoringService, AgentExecutionTrace

DATABASE_URL = "postgresql+asyncpg://postgres:postgres123@100.4.14.19:5432/rag_db"


class TestAgentMonitoringService:
    """Agent 监控服务测试类"""

    def __init__(self):
        self.engine = None
        self.session = None
        self.test_agent_id = None
        self.test_user_id = 1

    async def setup(self):
        """设置测试环境"""
        print("\n" + "=" * 60)
        print("设置测试环境 - 监控服务")
        print("=" * 60)

        self.engine = create_async_engine(DATABASE_URL, echo=False)
        async_session = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.session = async_session()

        # 创建测试 Agent
        self.test_agent_id = str(uuid.uuid4())
        agent = AgentConfig(
            id=self.test_agent_id,
            user_id=self.test_user_id,
            name="监控测试助手",
            description="用于测试监控服务的 Agent",
            agent_type="single",
            default_model_config={
                "provider": "local_qwen",
                "model": "qwen3.5-397b-a17b",
                "temperature": 0.7,
                "max_tokens": 4096,
            },
            system_prompt="你是一个测试助手。",
            status="active",
        )
        self.session.add(agent)
        await self.session.commit()
        print(f"✓ 测试 Agent 创建成功：{self.test_agent_id[:8]}...")

        # 创建监控服务
        self.monitoring_service = AgentMonitoringService(self.session)
        print(f"✓ 监控服务创建成功")

    async def teardown(self):
        """清理测试环境"""
        print("\n" + "=" * 60)
        print("清理测试环境")
        print("=" * 60)

        try:
            # 先删除调用日志
            await self.session.execute(
                delete(AgentCallLog).where(AgentCallLog.agent_id == self.test_agent_id)
            )
            # 再删除 Agent
            await self.session.execute(
                delete(AgentConfig).where(AgentConfig.id == self.test_agent_id)
            )
            await self.session.commit()
            print("✓ 测试数据已清理")
        except Exception as e:
            await self.session.rollback()
            print(f"✗ 清理失败：{e}")
        finally:
            await self.session.close()
            await self.engine.dispose()

    def test_trace_lifecycle(self):
        """测试轨迹追踪生命周期"""
        print("\n" + "=" * 60)
        print("测试：轨迹追踪生命周期")
        print("=" * 60)

        # 开始追踪
        trace = self.monitoring_service.start_trace(
            agent_id=self.test_agent_id,
            user_id=self.test_user_id,
        )

        print(f"✓ 轨迹追踪开始")
        print(f"  run_id: {trace.run_id[:8]}...")
        print(f"  agent_id: {trace.agent_id[:8]}...")

        # 添加步骤
        trace.add_step("init", {"status": "initialized"})
        trace.add_step("load_model", {"model": "qwen3.5"}, duration_ms=100)
        trace.add_step("execute", {"tokens": 100}, duration_ms=500)

        print(f"✓ 添加了 {len(trace.steps)} 个步骤")

        # 添加 Token 使用
        trace.add_token_usage(input_tokens=100, output_tokens=200)
        print(f"✓ Token 使用：input={trace.tokens['input']}, output={trace.tokens['output']}")

        # 结束追踪
        completed_trace = self.monitoring_service.end_trace(trace.run_id)

        print(f"✓ 轨迹追踪结束")
        print(f"  执行时长：{completed_trace.duration_ms}ms")
        print(f"  总 Token: {completed_trace.tokens['total']}")

        return completed_trace

    async def test_token_stats(self):
        """测试 Token 消耗统计"""
        print("\n" + "=" * 60)
        print("测试：Token 消耗统计")
        print("=" * 60)

        # 创建测试数据
        now = datetime.utcnow()
        for i in range(5):
            log = AgentCallLog(
                id=str(uuid.uuid4()),
                agent_id=self.test_agent_id,
                user_id=self.test_user_id,
                thread_id=f"test_thread_{i}",
                run_id=str(uuid.uuid4()),
                model_provider="local_qwen",
                model_name="qwen3.5-397b-a17b",
                input_tokens=100 + i * 10,
                output_tokens=200 + i * 20,
                total_tokens=300 + i * 30,
                latency_ms=500 + i * 100,
                status="success",
            )
            self.session.add(log)
        await self.session.commit()

        # 获取统计
        stats = await self.monitoring_service.get_token_stats(
            agent_id=self.test_agent_id,
            time_range="24h",
        )

        print(f"✓ Token 统计获取成功")
        print(f"  总输入 Token: {stats['total_input_tokens']}")
        print(f"  总输出 Token: {stats['total_output_tokens']}")
        print(f"  总 Token: {stats['total_tokens']}")
        print(f"  运行次数：{stats['total_runs']}")
        print(f"  平均 Token/次：{stats['avg_tokens_per_run']:.1f}")

        return stats

    async def test_latency_stats(self):
        """测试延迟统计"""
        print("\n" + "=" * 60)
        print("测试：延迟统计")
        print("=" * 60)

        # 获取统计
        stats = await self.monitoring_service.get_latency_stats(
            agent_id=self.test_agent_id,
            time_range="24h",
        )

        print(f"✓ 延迟统计获取成功")
        print(f"  样本数：{stats['count']}")
        print(f"  最小延迟：{stats['min_ms']}ms")
        print(f"  最大延迟：{stats['max_ms']}ms")
        print(f"  平均延迟：{stats['avg_ms']:.1f}ms")
        print(f"  P50 延迟：{stats['p50_ms']}ms")
        print(f"  P95 延迟：{stats['p95_ms']}ms")
        print(f"  P99 延迟：{stats['p99_ms']}ms")

        return stats

    async def test_error_stats(self):
        """测试错误统计"""
        print("\n" + "=" * 60)
        print("测试：错误统计")
        print("=" * 60)

        # 创建一些错误日志
        for i in range(2):
            log = AgentCallLog(
                id=str(uuid.uuid4()),
                agent_id=self.test_agent_id,
                user_id=self.test_user_id,
                thread_id=f"error_thread_{i}",
                run_id=str(uuid.uuid4()),
                model_provider="local_qwen",
                model_name="qwen3.5-397b-a17b",
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                latency_ms=0,
                status="error",
                error_message=f"Test error {i}: Connection timeout",
            )
            self.session.add(log)
        await self.session.commit()

        # 获取统计
        stats = await self.monitoring_service.get_error_stats(
            agent_id=self.test_agent_id,
            time_range="24h",
        )

        print(f"✓ 错误统计获取成功")
        print(f"  总运行次数：{stats['total_runs']}")
        print(f"  错误次数：{stats['error_count']}")
        print(f"  错误率：{stats['error_rate']:.2%}")
        print(f"  错误类型：{len(stats['error_types'])} 种")

        return stats

    async def test_alerts(self):
        """测试告警检查"""
        print("\n" + "=" * 60)
        print("测试：告警检查")
        print("=" * 60)

        # 设置低阈值以触发告警
        self.monitoring_service.alert_thresholds["max_error_rate"] = 0.01  # 1%
        self.monitoring_service.alert_thresholds["max_latency_ms"] = 100  # 100ms

        # 检查告警
        alerts = await self.monitoring_service.check_alerts(self.test_agent_id)

        print(f"✓ 告警检查完成")
        print(f"  告警数：{len(alerts)}")

        for alert in alerts:
            print(f"    - [{alert['severity']}] {alert['type']}: {alert['message']}")

        return alerts

    def test_debug_mode(self):
        """测试调试模式"""
        print("\n" + "=" * 60)
        print("测试：调试模式")
        print("=" * 60)

        # 开始追踪
        trace = self.monitoring_service.start_trace(
            agent_id=self.test_agent_id,
            user_id=self.test_user_id,
        )

        # 启用调试模式
        self.monitoring_service.set_debug_mode(trace.run_id, enabled=True)
        print(f"✓ 调试模式已启用")

        # 添加调试断点
        self.monitoring_service.add_debug_point(
            trace.run_id,
            "before_llm_call",
            {"prompt_length": 100, "temperature": 0.7},
        )
        self.monitoring_service.add_debug_point(
            trace.run_id,
            "after_llm_call",
            {"response_length": 200, "tokens": 150},
        )
        print(f"✓ 添加了 2 个调试断点")

        # 验证调试数据
        debug_steps = [s for s in trace.steps if s['step'].startswith('debug:')]
        print(f"✓ 调试步骤数：{len(debug_steps)}")

        # 结束追踪
        self.monitoring_service.end_trace(trace.run_id)

        return len(debug_steps)

    async def run_all_tests(self):
        """运行所有测试"""
        await self.setup()

        try:
            # 测试轨迹追踪
            self.test_trace_lifecycle()

            # 测试 Token 统计
            await self.test_token_stats()

            # 测试延迟统计
            await self.test_latency_stats()

            # 测试错误统计
            await self.test_error_stats()

            # 测试告警检查
            await self.test_alerts()

            # 测试调试模式
            self.test_debug_mode()

            print("\n" + "=" * 60)
            print("所有监控服务测试通过 ✅")
            print("=" * 60)

        except AssertionError as e:
            print(f"\n❌ 测试失败：{e}")
        except Exception as e:
            print(f"\n❌ 测试异常：{e}")
            import traceback
            traceback.print_exc()
        finally:
            await self.teardown()


async def main():
    """运行测试"""
    tester = TestAgentMonitoringService()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
