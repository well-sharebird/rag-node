"""
测试执行链路集成：验证 Phase 1-5 的优化系统在真实 API 中的协同工作
装饰器模式：ExecutionOrchestrator 包装 OrchestratorRuntime
"""
import pytest
import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

# Mock langchain 避免依赖问题
sys.modules['langchain.agents.middleware'] = MagicMock()

from packages.agent.integration.execution_chain import (
    ExecutionOrchestrator,
    EventServiceProvider,
    create_execution_orchestrator,
)


class TestExecutionOrchestrator:
    """测试执行链路编排器（装饰器模式）"""
    
    @pytest.mark.asyncio
    async def test_cross_cutting_systems_init(self):
        """测试横切关注点系统初始化"""
        mock_db = AsyncMock()
        
        # Mock OrchestratorRuntime 避免依赖问题
        with patch('packages.agent.orchestrator.graph.OrchestratorRuntime', create=True):
            orchestrator = create_execution_orchestrator(
                db=mock_db,
                user_id=123
            )
            
            # 验证横切关注点系统已初始化
            assert orchestrator.error_handler is not None
            assert orchestrator.observability is not None
            assert orchestrator.container is not None
            assert orchestrator.hot_reload is not None
    
    @pytest.mark.asyncio
    async def test_event_service_registration(self):
        """测试事件服务注册"""
        mock_db = AsyncMock()
        
        with patch('packages.agent.orchestrator.graph.OrchestratorRuntime', create=True):
            orchestrator = create_execution_orchestrator(
                db=mock_db,
                user_id=123
            )
            
            # 验证服务容器
            services = orchestrator.container.registry.list_services()
            service_names = [s.metadata.name for s in services]
            
            assert "event_service" in service_names
    
    @pytest.mark.asyncio
    async def test_execute_stream_delegates_to_runtime(self):
        """测试执行流委托给 OrchestratorRuntime"""
        mock_db = AsyncMock()
        
        # 创建 Mock Runtime
        mock_runtime = AsyncMock()
        mock_events = [
            {"type": "orchestrator_plan", "data": {}},
            {"type": "token", "content": "Hello"},
            {"type": "token", "content": "world"},
            {"type": "done"},
        ]
        
        async def mock_run_stream(*args, **kwargs):
            for event in mock_events:
                yield event
        
        mock_runtime.run_stream = mock_run_stream
        
        with patch('packages.agent.orchestrator.graph.OrchestratorRuntime', return_value=mock_runtime):
            orchestrator = create_execution_orchestrator(
                db=mock_db,
                user_id=123
            )
            await orchestrator.start()
            
            try:
                events = []
                async for event in orchestrator.execute_stream(
                    query="Test delegation",
                    session_id="test_123"
                ):
                    events.append(event)
                
                # 验证事件被传递
                assert len(events) == 4
                assert events[0]["type"] == "orchestrator_plan"
                assert events[-1]["type"] == "done"
                
                # 验证指标被记录
                metrics = orchestrator.observability.metrics.get_summary()
                assert metrics["total_metrics"] >= 2  # request + tokens
                
            finally:
                await orchestrator.stop()
    
    @pytest.mark.asyncio
    async def test_execute_stream_with_error(self):
        """测试错误处理"""
        mock_db = AsyncMock()
        
        # 创建会抛出异常的 Mock Runtime
        mock_runtime = AsyncMock()
        
        async def mock_run_stream_error(*args, **kwargs):
            raise Exception("Test error")
            yield  # 使函数成为生成器
        
        mock_runtime.run_stream = mock_run_stream_error
        
        with patch('packages.agent.orchestrator.graph.OrchestratorRuntime', return_value=mock_runtime):
            orchestrator = create_execution_orchestrator(
                db=mock_db,
                user_id=123
            )
            await orchestrator.start()
            
            try:
                # 验证错误被抛出
                with pytest.raises(Exception, match="Test error"):
                    async for event in orchestrator.execute_stream(
                        query="Test error",
                        session_id="test_123"
                    ):
                        pass
                
                # 验证错误指标
                metrics = orchestrator.observability.metrics.get_summary()
                assert metrics["total_metrics"] >= 1  # 至少有错误指标
                
            finally:
                await orchestrator.stop()
    
    @pytest.mark.asyncio
    async def test_event_interceptors(self):
        """测试事件拦截器"""
        mock_db = AsyncMock()
        mock_runtime = AsyncMock()
        
        async def mock_run_stream(*args, **kwargs):
            yield {"type": "done"}
        
        mock_runtime.run_stream = mock_run_stream
        
        with patch('packages.agent.orchestrator.graph.OrchestratorRuntime', return_value=mock_runtime):
            orchestrator = create_execution_orchestrator(
                db=mock_db,
                user_id=123
            )
            await orchestrator.start()
            
            try:
                async for event in orchestrator.execute_stream(
                    query="Test interceptors",
                    session_id="test_123"
                ):
                    pass
                
                # 验证拦截器被调用（通过指标间接验证）
                metrics = orchestrator.observability.metrics.get_summary()
                assert metrics["total_metrics"] >= 2  # request + success
                
            finally:
                await orchestrator.stop()
    
    @pytest.mark.asyncio
    async def test_distributed_tracing(self):
        """测试分布式追踪"""
        mock_db = AsyncMock()
        mock_runtime = AsyncMock()
        
        async def mock_run_stream(*args, **kwargs):
            yield {"type": "done"}
        
        mock_runtime.run_stream = mock_run_stream
        
        with patch('packages.agent.orchestrator.graph.OrchestratorRuntime', return_value=mock_runtime):
            orchestrator = create_execution_orchestrator(
                db=mock_db,
                user_id=123
            )
            await orchestrator.start()
            
            try:
                async for event in orchestrator.execute_stream(
                    query="Test tracing",
                    session_id="test_123"
                ):
                    pass
                
                # 验证追踪器存在
                assert orchestrator.observability.tracer is not None
                
            finally:
                await orchestrator.stop()
    
    @pytest.mark.asyncio
    async def test_audit_logging(self):
        """测试审计日志"""
        mock_db = AsyncMock()
        mock_runtime = AsyncMock()
        
        async def mock_run_stream(*args, **kwargs):
            yield {"type": "done"}
        
        mock_runtime.run_stream = mock_run_stream
        
        with patch('packages.agent.orchestrator.graph.OrchestratorRuntime', return_value=mock_runtime):
            orchestrator = create_execution_orchestrator(
                db=mock_db,
                user_id=123
            )
            await orchestrator.start()
            
            try:
                async for event in orchestrator.execute_stream(
                    query="Test audit",
                    session_id="test_123"
                ):
                    pass
                
                # 验证审计日志存在
                assert orchestrator.observability.audit is not None
                
            finally:
                await orchestrator.stop()
    
    @pytest.mark.asyncio
    async def test_concurrent_requests(self):
        """测试并发请求处理"""
        async def handle_request(uid, query):
            mock_db = AsyncMock()
            mock_runtime = AsyncMock()
            
            async def mock_run_stream(*args, **kwargs):
                yield {"type": "done"}
            
            mock_runtime.run_stream = mock_run_stream
            
            with patch('packages.agent.orchestrator.graph.OrchestratorRuntime', return_value=mock_runtime):
                orchestrator = create_execution_orchestrator(
                    db=mock_db,
                    user_id=uid
                )
                await orchestrator.start()
                
                try:
                    async for event in orchestrator.execute_stream(
                        query=query,
                        session_id=f"session_{uid}"
                    ):
                        pass
                finally:
                    await orchestrator.stop()
        
        # 并发执行 3 个请求
        await asyncio.gather(*[
            handle_request(i, f"Query {i}")
            for i in range(3)
        ])


class TestExecutionChainIntegration:
    """测试执行链路与实际 API 的集成"""
    
    @pytest.mark.asyncio
    async def test_api_to_execution_chain(self):
        """测试 API 到执行链路的调用"""
        mock_db = AsyncMock()
        mock_runtime = AsyncMock()
        
        async def mock_run_stream(*args, **kwargs):
            yield {"type": "done"}
        
        mock_runtime.run_stream = mock_run_stream
        
        with patch('packages.agent.orchestrator.graph.OrchestratorRuntime', return_value=mock_runtime):
            # API 层创建编排器
            orchestrator = create_execution_orchestrator(
                db=mock_db,
                user_id=456,
                model_name="deepseek-v3"
            )
            
            # 启动
            await orchestrator.start()
            
            try:
                # 执行请求
                async for event in orchestrator.execute_stream(
                    query="API test",
                    session_id="api_session"
                ):
                    pass
                
                # 验证指标记录
                metrics = orchestrator.observability.metrics.get_summary()
                assert metrics["total_metrics"] >= 2
                
            finally:
                await orchestrator.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
