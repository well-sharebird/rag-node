"""
追踪功能集成测试

需要运行中的服务:
- Elasticsearch (默认 localhost:9200)
- PostgreSQL
- Redis

运行方式:
    uv run pytest tests/test_tracing_integration.py -v --tb=short
"""
import asyncio
import pytest
import os

# 检查是否应该运行集成测试
RUN_INTEGRATION = os.getenv("RUN_INTEGRATION_TESTS", "false").lower() == "true"


@pytest.mark.skipif(not RUN_INTEGRATION, reason="需要运行中的 ES/PostgreSQL/Redis")
class TestTracingIntegration:
    """追踪集成测试"""

    @pytest.mark.asyncio
    async def test_full_document_pipeline_trace(self):
        """测试完整的文档处理追踪流程"""
        from packages.core.infra.es_client import get_es_client
        from packages.agent.services.trace_service import TraceService, TraceContext
        from packages.core.tracing import trace_execution, set_trace_context, set_trace_service

        # 获取 ES 客户端
        es = get_es_client()
        trace_service = TraceService(es)
        await trace_service.ensure_index()

        # 创建追踪上下文
        async with trace_execution(
            execution_type="document_pipeline",
            execution_id="test-doc-001",
            user_id=1,
            trace_service=trace_service,
        ) as ctx:
            set_trace_service(trace_service)
            set_trace_context(ctx)

            # 模拟文档处理步骤
            span1 = await trace_service.start_span(
                ctx=ctx,
                node_type="parsing",
                node_name="parse_pdf",
                input_data={"doc_id": "test-doc-001", "format": "pdf"},
            )
            await asyncio.sleep(0.01)  # 模拟处理时间
            await trace_service.end_span(
                ctx=ctx,
                span_id=span1,
                output_data={"pages": 5, "text_length": 1000},
            )

            span2 = await trace_service.start_span(
                ctx=ctx,
                node_type="chunking",
                node_name="chunk_text",
                input_data={"strategy": "recursive", "chunk_size": 512},
            )
            await asyncio.sleep(0.01)
            await trace_service.end_span(
                ctx=ctx,
                span_id=span2,
                output_data={"chunks": 10},
            )

            span3 = await trace_service.start_span(
                ctx=ctx,
                node_type="embedding",
                node_name="embed_texts",
                input_data={"model": "text-embedding-3-small", "dim": 1024},
            )
            await asyncio.sleep(0.01)
            await trace_service.end_span(
                ctx=ctx,
                span_id=span3,
                output_data={"vectors": 10},
            )

        # 等待 ES 刷新
        await asyncio.sleep(1)

        # 验证追踪记录
        trace_tree = await trace_service.get_trace_tree(ctx.trace_id)
        assert len(trace_tree) == 3  # 3 个 span

        # 验证统计
        stats = await trace_service.get_trace_stats(ctx.trace_id)
        assert stats["span_count"] == 3
        assert stats["final_status"] == "success"

        # 验证聚合元数据
        agg_result = await es.get(
            index="execution_traces_aggs",
            id=ctx.trace_id,
        )
        assert agg_result["_source"]["total_spans"] == 3

    @pytest.mark.asyncio
    async def test_concurrent_traces(self):
        """测试并发追踪"""
        from packages.core.infra.es_client import get_es_client
        from packages.agent.services.trace_service import TraceService
        from packages.core.tracing import trace_execution

        es = get_es_client()
        trace_service = TraceService(es)
        await trace_service.ensure_index()

        async def run_trace(trace_id: str):
            async with trace_execution(
                execution_type="agent_execution",
                execution_id=trace_id,
                user_id=1,
                trace_service=trace_service,
            ) as ctx:
                # 创建一些 span
                for i in range(3):
                    span_id = await trace_service.start_span(
                        ctx=ctx,
                        node_type="agent_node",
                        node_name=f"node_{i}",
                        input_data={"step": i},
                    )
                    await asyncio.sleep(0.01)
                    await trace_service.end_span(
                        ctx=ctx,
                        span_id=span_id,
                        output_data={"result": f"result_{i}"},
                    )
            return ctx.trace_id

        # 并发运行 3 个追踪
        trace_ids = await asyncio.gather(*[
            run_trace(f"agent-{i}") for i in range(3)
        ])

        # 等待 ES 刷新
        await asyncio.sleep(1)

        # 验证每个追踪
        for trace_id in trace_ids:
            stats = await trace_service.get_trace_stats(trace_id)
            assert stats["span_count"] == 3

    @pytest.mark.asyncio
    async def test_error_trace(self):
        """测试错误追踪"""
        from packages.core.infra.es_client import get_es_client
        from packages.agent.services.trace_service import TraceService
        from packages.core.tracing import trace_execution

        es = get_es_client()
        trace_service = TraceService(es)
        await trace_service.ensure_index()

        try:
            async with trace_execution(
                execution_type="test",
                execution_id="error-test",
                trace_service=trace_service,
            ) as ctx:
                span_id = await trace_service.start_span(
                    ctx=ctx,
                    node_type="test",
                    node_name="failing_func",
                )
                raise ValueError("Test error")
        except ValueError:
            pass  # 预期错误

        # 等待 ES 刷新
        await asyncio.sleep(1)

        # 验证错误状态
        stats = await trace_service.get_trace_stats(ctx.trace_id)
        assert stats["final_status"] == "failed"

        # 验证错误信息被记录
        trace_tree = await trace_service.get_trace_tree(ctx.trace_id)
        assert len(trace_tree) == 1
        # 注意：错误信息在 end_span 中记录，但由于异常中断，可能不完整


@pytest.mark.skipif(not RUN_INTEGRATION, reason="需要运行中的 ES")
@pytest.mark.asyncio
async def test_list_traces_pagination():
    """测试追踪列表分页"""
    from packages.core.infra.es_client import get_es_client
    from packages.agent.services.trace_service import TraceService
    from packages.core.tracing import trace_execution
    from datetime import datetime, timedelta

    es = get_es_client()
    trace_service = TraceService(es)
    await trace_service.ensure_index()

    # 创建多个追踪
    for i in range(25):
        async with trace_execution(
            execution_type="document_pipeline",
            execution_id=f"doc-{i:03d}",
            user_id=1,
            trace_service=trace_service,
        ) as ctx:
            pass

    # 等待 ES 刷新
    await asyncio.sleep(1)

    # 测试分页
    result1 = await trace_service.list_traces(
        execution_type="document_pipeline",
        size=10,
    )
    assert len(result1["traces"]) == 10
    assert result1["has_more"] == True

    result2 = await trace_service.list_traces(
        execution_type="document_pipeline",
        search_after=result1["next_search_after"],
        size=10,
    )
    assert len(result2["traces"]) == 10
    assert result2["has_more"] == True

    result3 = await trace_service.list_traces(
        execution_type="document_pipeline",
        search_after=result2["next_search_after"],
        size=10,
    )
    assert len(result3["traces"]) == 5  # 剩余 5 个
    assert result3["has_more"] == False


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
