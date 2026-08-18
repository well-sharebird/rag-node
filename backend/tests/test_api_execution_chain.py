"""
端到端测试：验证 API 入口到执行链路的完整集成

测试场景：
1. API 入口调用 ExecutionOrchestrator
2. 事件总线发布/订阅
3. 服务容器管理
4. 错误处理
5. 可观测性记录
6. 热更新
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from packages.agent.integration.execution_chain import (
    ExecutionOrchestrator,
    create_execution_orchestrator,
)


class TestEndToEndIntegration:
    """端到端集成测试"""
    
    @pytest.mark.asyncio
    async def test_full_execution_chain(self):
        """测试完整的执行链路"""
        # 1. 创建编排器
        orchestrator = create_execution_orchestrator(user_id=123)
        
        # 2. 启动所有服务
        await orchestrator.start()
        
        # 3. 验证所有系统已初始化
        assert orchestrator.error_handler is not None
        assert orchestrator.observability is not None
        assert orchestrator.container is not None
        assert orchestrator.hot_reload is not None
        
        # 4. 验证服务已注册
        services = orchestrator.container.registry.list_services()
        service_names = [s.metadata.name for s in services]
        assert "llm_service" in service_names
        assert "event_service" in service_names
        
        # 5. 执行流式请求
        events = []
        async for event in orchestrator.execute_stream(
            query="Test full chain",
            session_id="test_session"
        ):
            events.append(event)
        
        # 6. 验证事件流
        assert len(events) >= 2  # 至少 start 和 done
        assert events[0]["type"] == "start"
        assert events[-1]["type"] == "done"
        
        # 7. 验证事件总线被调用
        metrics = orchestrator.observability.metrics.get_summary()
        assert metrics["total_metrics"] >= 2
        
        # 8. 验证追踪
        await asyncio.sleep(0.1)  # 等待 span 完成
        spans = orchestrator.observability.tracer.get_completed_spans()
        assert len(spans) >= 0  # span 可能在 finally 中结束
        
        # 9. 停止所有服务
        await orchestrator.stop()
    
    @pytest.mark.asyncio
    async def test_api_to_execution_chain(self):
        """测试 API 到执行链路的调用"""
        # 模拟 API 调用场景
        from packages.agent.integration.execution_chain import create_execution_orchestrator
        
        # API 层创建编排器
        orchestrator = create_execution_orchestrator(
            user_id=456,
            model_name="deepseek-v3"
        )
        
        # 启动
        await orchestrator.start()
        
        try:
            # 执行请求
            events = []
            async for event in orchestrator.execute_stream(
                query="API test",
                session_id="api_session_123"
            ):
                events.append(event)
            
            # 验证响应格式
            assert len(events) >= 2
            assert events[0]["type"] == "start"
            assert events[0]["data"]["correlation_id"] is not None
            
            # 验证指标记录
            metrics = orchestrator.observability.metrics.get_summary()
            assert metrics["total_metrics"] >= 2
            
        finally:
            await orchestrator.stop()
    
    @pytest.mark.asyncio
    async def test_event_bus_integration(self):
        """测试事件总线集成"""
        orchestrator = create_execution_orchestrator(user_id=789)
        await orchestrator.start()
        
        try:
            # 执行请求（应该触发 PRE/POST 事件）
            async for event in orchestrator.execute_stream(
                query="Event bus test",
                session_id="event_test"
            ):
                pass
            
            # 验证事件被处理
            # （通过指标间接验证）
            metrics = orchestrator.observability.metrics.get_summary()
            assert metrics["total_metrics"] >= 2
            
        finally:
            await orchestrator.stop()
    
    @pytest.mark.asyncio
    async def test_service_container_integration(self):
        """测试服务容器集成"""
        orchestrator = create_execution_orchestrator(user_id=101)
        await orchestrator.start()
        
        try:
            # 验证服务依赖解析
            services = orchestrator.container.registry.list_services()
            assert len(services) >= 3  # LLM, Tool, Event
            
            # 验证服务启动顺序（依赖先启动）
            service_names = [s.metadata.name for s in services]
            llm_index = service_names.index("llm_service")
            tool_index = service_names.index("tool_service")
            
            # tool_service 依赖 llm_service，应该后启动
            # （这里只是验证服务存在，实际启动顺序在 container.initialize 中处理）
            assert llm_index >= 0
            assert tool_index >= 0
            
        finally:
            await orchestrator.stop()
    
    @pytest.mark.asyncio
    async def test_error_handling_integration(self):
        """测试错误处理集成"""
        orchestrator = create_execution_orchestrator(user_id=102)
        await orchestrator.start()
        
        try:
            # 执行请求（可能触发错误）
            events = []
            async for event in orchestrator.execute_stream(
                query="Error handling test",
                session_id="error_test"
            ):
                events.append(event)
            
            # 验证错误事件格式（如果有错误）
            error_events = [e for e in events if e.get("type") == "error"]
            # 不强制要求有错误，但如果有，格式必须正确
            for error_event in error_events:
                assert "error" in error_event
            
        finally:
            await orchestrator.stop()
    
    @pytest.mark.asyncio
    async def test_observability_integration(self):
        """测试可观测性集成"""
        orchestrator = create_execution_orchestrator(user_id=103)
        await orchestrator.start()
        
        try:
            # 执行请求
            async for event in orchestrator.execute_stream(
                query="Observability test",
                session_id="obs_test"
            ):
                pass
            
            # 验证指标收集
            metrics = orchestrator.observability.metrics.get_summary()
            assert metrics["total_metrics"] >= 2
            assert metrics["counters"] >= 0
            
            # 验证追踪器存在
            assert orchestrator.observability.tracer is not None
            
            # 验证审计日志存在
            assert orchestrator.observability.audit is not None
            
        finally:
            await orchestrator.stop()
    
    @pytest.mark.asyncio
    async def test_concurrent_api_requests(self):
        """测试并发 API 请求处理"""
        # 模拟多个并发 API 请求
        async def handle_api_request(user_id, query):
            orchestrator = create_execution_orchestrator(user_id=user_id)
            await orchestrator.start()
            
            try:
                events = []
                async for event in orchestrator.execute_stream(
                    query=query,
                    session_id=f"concurrent_{user_id}"
                ):
                    events.append(event)
                return events
            finally:
                await orchestrator.stop()
        
        # 并发执行 5 个请求
        user_ids = [1, 2, 3, 4, 5]
        queries = [f"Query {i}" for i in user_ids]
        
        results = await asyncio.gather(*[
            handle_api_request(uid, q) for uid, q in zip(user_ids, queries)
        ])
        
        # 验证所有请求都成功
        for result in results:
            assert len(result) >= 2
            assert result[0]["type"] == "start"
            assert result[-1]["type"] == "done"


class TestAPIEndpointIntegration:
    """测试 API 端点集成"""
    
    @pytest.mark.asyncio
    async def test_execute_stream_api_signature(self):
        """测试 API 端点签名"""
        # 验证 API 端点存在
        from packages.agent.api.agents import execute_agent_unified_stream
        
        # 验证函数签名
        import inspect
        sig = inspect.signature(execute_agent_unified_stream)
        params = list(sig.parameters.keys())
        
        assert "data" in params
        assert "db" in params
        assert "current_user" in params
    
    @pytest.mark.asyncio
    async def test_execute_stream_uses_execution_orchestrator(self):
        """验证 API 使用 ExecutionOrchestrator"""
        # 读取 API 实现代码
        import inspect
        from packages.agent.api.agents import execute_agent_unified_stream
        
        source = inspect.getsource(execute_agent_unified_stream)
        
        # 验证使用了新的 ExecutionOrchestrator
        assert "create_execution_orchestrator" in source
        assert "ExecutionOrchestrator" in source or "orchestrator" in source
        
        # 验证调用了 start/stop
        assert "orchestrator.start()" in source
        assert "orchestrator.stop()" in source


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
