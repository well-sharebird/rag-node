"""
测试可观测性系统
"""
import pytest
from datetime import datetime
from packages.agent.observability.metrics import (
    MetricType,
    SpanStatus,
    MetricPoint,
    Span,
    AuditLogEntry,
    MetricCollector,
    Tracer,
    AuditLogger,
    ObservabilityService,
)


class TestMetricPoint:
    """测试指标数据点"""
    
    def test_metric_point_creation(self):
        """测试数据点创建"""
        point = MetricPoint(
            name="http.requests",
            value=100,
            labels={"method": "GET", "status": "200"},
            metric_type=MetricType.COUNTER,
        )
        
        assert point.name == "http.requests"
        assert point.value == 100
        assert point.labels["method"] == "GET"
        assert point.metric_type == MetricType.COUNTER
    
    def test_metric_point_to_dict(self):
        """测试数据点转字典"""
        point = MetricPoint(
            name="test.metric",
            value=50,
        )
        
        data = point.to_dict()
        
        assert data["name"] == "test.metric"
        assert data["value"] == 50
        assert "timestamp" in data
        assert data["type"] == "counter"


class TestSpan:
    """测试追踪跨度"""
    
    def test_span_creation(self):
        """测试跨度创建"""
        span = Span(
            trace_id="trace-123",
            span_id="span-456",
            name="test_operation",
            start_time=datetime.utcnow(),
        )
        
        assert span.trace_id == "trace-123"
        assert span.span_id == "span-456"
        assert span.name == "test_operation"
        assert span.status == SpanStatus.UNSET
    
    def test_span_duration(self):
        """测试跨度持续时间"""
        start = datetime.utcnow()
        span = Span(
            trace_id="trace-123",
            span_id="span-456",
            name="test",
            start_time=start,
        )
        
        # 未结束应该返回 None
        assert span.duration_ms is None
        
        # 结束跨度
        span.end()
        
        assert span.duration_ms is not None
        assert span.duration_ms >= 0
    
    def test_span_attributes(self):
        """测试跨度属性"""
        span = Span(
            trace_id="trace-123",
            span_id="span-456",
            name="test",
            start_time=datetime.utcnow(),
        )
        
        span.set_attribute("user_id", "123")
        span.set_attribute("action", "create")
        
        assert span.attributes["user_id"] == "123"
        assert span.attributes["action"] == "create"
    
    def test_span_events(self):
        """测试跨度事件"""
        span = Span(
            trace_id="trace-123",
            span_id="span-456",
            name="test",
            start_time=datetime.utcnow(),
        )
        
        span.add_event("start", {"step": 1})
        span.add_event("end", {"step": 2})
        
        assert len(span.events) == 2
        assert span.events[0]["name"] == "start"
        assert span.events[1]["name"] == "end"
    
    def test_span_status(self):
        """测试跨度状态"""
        span = Span(
            trace_id="trace-123",
            span_id="span-456",
            name="test",
            start_time=datetime.utcnow(),
        )
        
        span.set_status(SpanStatus.OK)
        assert span.status == SpanStatus.OK
        
        span.set_status(SpanStatus.ERROR)
        assert span.status == SpanStatus.ERROR
    
    def test_span_to_dict(self):
        """测试跨度转字典"""
        span = Span(
            trace_id="trace-123",
            span_id="span-456",
            name="test",
            start_time=datetime.utcnow(),
        )
        span.end()
        
        data = span.to_dict()
        
        assert data["trace_id"] == "trace-123"
        assert data["span_id"] == "span-456"
        assert data["name"] == "test"
        assert "duration_ms" in data


class TestAuditLogEntry:
    """测试审计日志条目"""
    
    def test_audit_log_creation(self):
        """测试审计日志创建"""
        entry = AuditLogEntry(
            timestamp=datetime.utcnow(),
            actor="user-123",
            action="create",
            resource="document-456",
            resource_type="document",
            result="success",
            details={"size": 1024},
        )
        
        assert entry.actor == "user-123"
        assert entry.action == "create"
        assert entry.resource == "document-456"
        assert entry.result == "success"
    
    def test_audit_log_to_dict(self):
        """测试审计日志转字典"""
        entry = AuditLogEntry(
            timestamp=datetime.utcnow(),
            actor="user-123",
            action="delete",
            resource="doc-1",
            resource_type="document",
            result="failure",
        )
        
        data = entry.to_dict()
        
        assert data["actor"] == "user-123"
        assert data["action"] == "delete"
        assert data["result"] == "failure"
        assert "timestamp" in data


class TestMetricCollector:
    """测试指标收集器"""
    
    def test_increment_counter(self):
        """测试增加计数器"""
        collector = MetricCollector()
        
        collector.increment("requests.total")
        collector.increment("requests.total")
        collector.increment("requests.total", value=5)
        
        assert collector._counters["requests.total"] == 7
    
    def test_increment_with_labels(self):
        """测试带标签的计数器"""
        collector = MetricCollector()
        
        collector.increment("requests", labels={"method": "GET"})
        collector.increment("requests", labels={"method": "POST"})
        collector.increment("requests", labels={"method": "GET"})
        
        get_key = "requests{method=GET}"
        post_key = "requests{method=POST}"
        
        assert collector._counters[get_key] == 2
        assert collector._counters[post_key] == 1
    
    def test_set_gauge(self):
        """测试设置仪表盘"""
        collector = MetricCollector()
        
        collector.set_gauge("memory.usage", 1024)
        collector.set_gauge("memory.usage", 2048)
        
        assert collector._gauges["memory.usage"] == 2048
    
    def test_record_histogram(self):
        """测试记录直方图"""
        collector = MetricCollector()
        
        collector.record_histogram("request.duration", 100)
        collector.record_histogram("request.duration", 150)
        collector.record_histogram("request.duration", 200)
        
        points = collector.get_metric("request.duration")
        
        assert len(points) == 3
        assert points[0].value == 100
        assert points[2].value == 200
    
    def test_get_summary(self):
        """测试获取摘要"""
        collector = MetricCollector()
        
        collector.increment("requests")
        collector.set_gauge("memory", 1024)
        
        summary = collector.get_summary()
        
        assert summary["total_metrics"] > 0
        assert "counters" in summary
        assert "gauges" in summary
    
    def test_clear(self):
        """测试清空"""
        collector = MetricCollector()
        
        collector.increment("requests")
        collector.set_gauge("memory", 1024)
        collector.clear()
        
        assert len(collector._counters) == 0
        assert len(collector._gauges) == 0


class TestTracer:
    """测试追踪器"""
    
    def test_start_span(self):
        """测试开始跨度"""
        tracer = Tracer(service_name="test-service")
        
        span = tracer.start_span("test_operation")
        
        assert span.name == "test_operation"
        assert span.attributes["service.name"] == "test-service"
        assert span.trace_id is not None
        assert span.span_id is not None
    
    def test_end_span(self):
        """测试结束跨度"""
        tracer = Tracer()
        
        span = tracer.start_span("test")
        
        assert span.span_id in tracer._active_spans
        
        tracer.end_span(span, SpanStatus.OK)
        
        assert span.span_id not in tracer._active_spans
        assert len(tracer._completed_spans) == 1
        assert span.status == SpanStatus.OK
    
    def test_parent_child_span(self):
        """测试父子跨度"""
        tracer = Tracer()
        
        parent = tracer.start_span("parent")
        child = tracer.start_span("child", parent=parent)
        
        assert child.parent_span_id == parent.span_id
        assert child.trace_id == parent.trace_id
    
    def test_span_exporter(self):
        """测试跨度导出器"""
        tracer = Tracer()
        
        exported = []
        
        def exporter(span):
            exported.append(span)
        
        tracer.register_exporter(exporter)
        
        span = tracer.start_span("test")
        tracer.end_span(span)
        
        assert len(exported) == 1
        assert exported[0] == span
    
    def test_get_completed_spans(self):
        """测试获取已完成的跨度"""
        tracer = Tracer()
        
        span1 = tracer.start_span("test1")
        tracer.end_span(span1)
        
        span2 = tracer.start_span("test2")
        tracer.end_span(span2)
        
        spans = tracer.get_completed_spans()
        
        assert len(spans) == 2
    
    def test_get_spans_by_trace_id(self):
        """测试按 trace_id 获取跨度"""
        tracer = Tracer()
        
        span1 = tracer.start_span("test1")
        tracer.end_span(span1)
        
        span2 = tracer.start_span("test2", parent=span1)
        tracer.end_span(span2)
        
        spans = tracer.get_completed_spans(trace_id=span1.trace_id)
        
        assert len(spans) == 2


class TestAuditLogger:
    """测试审计日志记录器"""
    
    def test_log(self):
        """测试记录日志"""
        logger = AuditLogger()
        
        logger.log(
            actor="user-123",
            action="create",
            resource="doc-1",
            resource_type="document",
            result="success",
        )
        
        assert len(logger._logs) == 1
    
    def test_get_logs(self):
        """测试获取日志"""
        logger = AuditLogger()
        
        logger.log("user-1", "create", "doc-1", "document", "success")
        logger.log("user-2", "delete", "doc-2", "document", "failure")
        logger.log("user-1", "update", "doc-1", "document", "success")
        
        # 按执行者获取
        logs = logger.get_logs(actor="user-1")
        assert len(logs) == 2
        
        # 按资源获取
        logs = logger.get_logs(resource="doc-1")
        assert len(logs) == 2
    
    def test_get_summary(self):
        """测试获取摘要"""
        logger = AuditLogger()
        
        logger.log("user-1", "create", "doc-1", "document", "success")
        logger.log("user-1", "update", "doc-1", "document", "success")
        logger.log("user-2", "delete", "doc-2", "document", "failure")
        
        summary = logger.get_summary()
        
        assert summary["total_logs"] == 3
        assert summary["by_actor"]["user-1"] == 2
        assert summary["by_actor"]["user-2"] == 1
        assert summary["by_result"]["success"] == 2
        assert summary["by_result"]["failure"] == 1
    
    def test_clear(self):
        """测试清空"""
        logger = AuditLogger()
        
        logger.log("user-1", "create", "doc-1", "document", "success")
        logger.clear()
        
        assert len(logger._logs) == 0


class TestObservabilityService:
    """测试可观测性服务"""
    
    def test_service_creation(self):
        """测试服务创建"""
        service = ObservabilityService(service_name="knowrag-test")
        
        assert service.metrics is not None
        assert service.tracer is not None
        assert service.audit is not None
        assert service.tracer.service_name == "knowrag-test"
    
    def test_record_request(self):
        """测试记录请求"""
        service = ObservabilityService()
        
        service.record_request(
            method="GET",
            path="/api/users",
            status_code=200,
            duration_ms=50,
            user_id="user-123",
        )
        
        # 验证指标
        requests = service.metrics.get_metric("http.requests.total")
        assert len(requests) == 1
        assert requests[0].labels["method"] == "GET"
        assert requests[0].labels["status"] == "200"
        
        # 验证审计日志
        logs = service.audit.get_logs(actor="user-123")
        assert len(logs) == 1
    
    def test_record_agent_action(self):
        """测试记录 Agent 动作"""
        service = ObservabilityService()
        
        service.record_agent_action(
            agent_id="agent-1",
            action="chat",
            session_id="session-123",
            details={"message": "Hello"},
        )
        
        actions = service.metrics.get_metric("agent.actions.total")
        assert len(actions) == 1
        assert actions[0].labels["agent_id"] == "agent-1"
    
    def test_record_error(self):
        """测试记录错误"""
        service = ObservabilityService()
        
        service.record_error(
            error_code="validation_error",
            error_category="validation",
            severity="low",
        )
        
        errors = service.metrics.get_metric("errors.total")
        assert len(errors) == 1
        assert errors[0].labels["error_code"] == "validation_error"
    
    def test_get_dashboard(self):
        """测试获取仪表板"""
        service = ObservabilityService()
        
        service.record_request("GET", "/api/test", 200, 50)
        
        dashboard = service.get_dashboard()
        
        assert "metrics" in dashboard
        assert "tracing" in dashboard
        assert "audit" in dashboard
        assert "timestamp" in dashboard


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
