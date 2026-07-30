"""
追踪功能测试脚本

测试场景:
1. 文档处理流程追踪 (process_document)
2. Agent 执行追踪 (execute_agent)
3. 装饰器追踪 (@traceable)
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# 测试追踪装饰器
class TestTraceableDecorator:
    """测试 @traceable 装饰器"""

    @pytest.mark.asyncio
    async def test_traceable_captures_input_output(self):
        """测试装饰器捕获输入输出"""
        from app.core.tracing import traceable, set_trace_context, set_trace_service
        from app.services.trace_service import TraceService, TraceContext

        # 创建模拟追踪服务
        mock_service = AsyncMock(spec=TraceService)
        mock_service.start_span = AsyncMock(return_value="span-123")
        mock_service.end_span = AsyncMock()

        # 创建追踪上下文
        mock_ctx = TraceContext(
            execution_type="test",
            execution_id="test-123",
        )

        # 设置全局追踪上下文
        set_trace_context(mock_ctx)
        set_trace_service(mock_service)

        # 定义被装饰的函数
        @traceable(node_type='test', node_name='test_func')
        async def test_func(a: int, b: str) -> str:
            return f"{a}-{b}"

        # 执行函数
        result = await test_func(42, "hello")

        # 验证结果
        assert result == "42-hello"
        mock_service.start_span.assert_called_once()
        mock_service.end_span.assert_called_once()

    @pytest.mark.asyncio
    async def test_traceable_handles_error(self):
        """测试装饰器捕获错误"""
        from app.core.tracing import traceable, set_trace_context, set_trace_service
        from app.services.trace_service import TraceService, TraceContext

        mock_service = AsyncMock(spec=TraceService)
        mock_service.start_span = AsyncMock(return_value="span-123")
        mock_service.end_span = AsyncMock()

        mock_ctx = TraceContext(execution_type="test", execution_id="test-123")
        set_trace_context(mock_ctx)
        set_trace_service(mock_service)

        @traceable(node_type='test', node_name='test_func')
        async def failing_func():
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            await failing_func()

        # 验证 end_span 被调用且包含错误信息
        mock_service.end_span.assert_called_once()
        call_kwargs = mock_service.end_span.call_args[1]
        assert call_kwargs.get('error') is not None


class TestDocumentPipelineTracing:
    """测试文档处理流程追踪"""

    @pytest.mark.asyncio
    async def test_process_document_creates_trace(self):
        """测试文档处理创建追踪记录"""
        from app.workers.document_pipeline import process_document
        from app.core.tracing import trace_execution, get_trace_context
        from app.services.trace_service import TraceService

        # Mock ES client
        mock_es = AsyncMock()
        mock_es.indices.exists = AsyncMock(return_value=True)
        mock_es.index = AsyncMock()
        mock_es.bulk = AsyncMock(return_value={"errors": False})

        with patch('app.workers.document_pipeline.get_es_client', return_value=mock_es):
            with patch('app.workers.document_pipeline.TraceService') as MockTraceService:
                mock_trace_service = AsyncMock(spec=TraceService)
                mock_trace_service.ensure_index = AsyncMock()
                MockTraceService.return_value = mock_trace_service

                # Mock other dependencies
                with patch('app.workers.document_pipeline.async_session_factory') as mock_session_factory:
                    mock_session = AsyncMock()
                    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

                    # Mock document query
                    mock_result = MagicMock()
                    mock_result.scalar_one.return_value = MagicMock(
                        id="doc-123",
                        kb_id="kb-1",
                        original_name="test.pdf",
                        format="pdf",
                        minio_key="test.pdf",
                        status="pending"
                    )
                    mock_session.execute = AsyncMock(return_value=mock_result)

                    # 注意：这个测试需要完整的依赖链，实际测试需要更详细的 mock
                    # 这里只是展示测试结构
                    pass


class TestAgentExecutionTracing:
    """测试 Agent 执行追踪"""

    @pytest.mark.asyncio
    async def test_execute_agent_creates_trace(self):
        """测试 Agent 执行创建追踪记录"""
        from app.services.agent_orchestration_service import AgentOrchestrationService
        from app.core.tracing import get_trace_context
        from app.services.trace_service import TraceService

        # Mock database
        mock_db = AsyncMock()

        # Mock model gateway and skill registry
        mock_gateway = MagicMock()
        mock_skills = MagicMock()

        service = AgentOrchestrationService(mock_db, mock_gateway, mock_skills)

        # Mock ES client
        mock_es = AsyncMock()
        mock_es.indices.exists = AsyncMock(return_value=True)

        with patch('app.services.agent_orchestration_service.get_es_client', return_value=mock_es):
            with patch('app.services.agent_orchestration_service.TraceService') as MockTraceService:
                mock_trace_service = AsyncMock(spec=TraceService)
                mock_trace_service.ensure_index = AsyncMock()
                MockTraceService.return_value = mock_trace_service

                # Mock agent factory
                with patch.object(service, 'agent_factory') as mock_factory:
                    mock_factory.execute = AsyncMock(return_value={
                        "run_id": "run-123",
                        "response": "Test response",
                        "messages": []
                    })

                    # Execute agent
                    result = await service.execute_agent(
                        agent_id="agent-1",
                        user_id=1,
                        query="Test query"
                    )

                    # Verify
                    assert result["run_id"] == "run-123"
                    mock_trace_service.ensure_index.assert_called_once()


class TestTraceContext:
    """测试追踪上下文"""

    def test_trace_context_generation(self):
        """测试追踪上下文生成"""
        from app.services.trace_service import TraceContext

        ctx = TraceContext(
            execution_type="document_pipeline",
            execution_id="doc-123",
            user_id=1
        )

        assert ctx.trace_id is not None
        assert ctx.run_id is not None
        assert ctx.execution_type == "document_pipeline"
        assert ctx.execution_id == "doc-123"
        assert ctx.user_id == 1

    def test_span_id_generation(self):
        """测试 Span ID 生成"""
        from app.services.trace_service import TraceContext

        ctx = TraceContext(execution_type="test", execution_id="test-1")

        span1 = ctx.generate_span_id()
        span2 = ctx.generate_span_id()
        span3 = ctx.generate_span_id()

        # Span ID 格式：{trace_id}-{counter:04d}
        assert span1.endswith("-0001")
        assert span2.endswith("-0002")
        assert span3.endswith("-0003")
        # 验证 trace_id 相同
        assert span1.split('-')[0] == span2.split('-')[0] == span3.split('-')[0]

    def test_span_stack(self):
        """测试 Span 栈管理"""
        from app.services.trace_service import TraceContext

        ctx = TraceContext(execution_type="test", execution_id="test-1")

        span1 = ctx.generate_span_id()
        ctx.push_span(span1)
        assert ctx.parent_span_id == span1

        span2 = ctx.generate_span_id()
        ctx.push_span(span2)
        assert ctx.parent_span_id == span2

        ctx.pop_span()
        assert ctx.parent_span_id == span1

        ctx.pop_span()
        assert ctx.parent_span_id is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
