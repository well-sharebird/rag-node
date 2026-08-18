"""
可观测性系统

提供指标收集、分布式追踪、审计日志
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum
import time
import uuid
import json


class MetricType(str, Enum):
    """指标类型"""
    COUNTER = "counter"        # 计数器（只增）
    GAUGE = "gauge"            # 仪表盘（可增减）
    HISTOGRAM = "histogram"    # 直方图（分布）
    SUMMARY = "summary"        # 摘要（分位数）


class SpanStatus(str, Enum):
    """追踪状态"""
    OK = "ok"
    ERROR = "error"
    UNSET = "unset"


@dataclass
class MetricPoint:
    """指标数据点"""
    name: str
    value: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    labels: Dict[str, str] = field(default_factory=dict)
    metric_type: MetricType = MetricType.COUNTER
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "timestamp": self.timestamp.isoformat(),
            "labels": self.labels,
            "type": self.metric_type.value,
        }


@dataclass
class Span:
    """追踪跨度"""
    trace_id: str
    span_id: str
    name: str
    start_time: datetime
    end_time: Optional[datetime] = None
    status: SpanStatus = SpanStatus.UNSET
    parent_span_id: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "status": self.status.value,
            "attributes": self.attributes,
            "events": self.events,
            "duration_ms": self.duration_ms,
        }
    
    @property
    def duration_ms(self) -> Optional[float]:
        """获取持续时间（毫秒）"""
        if self.end_time:
            delta = self.end_time - self.start_time
            return delta.total_seconds() * 1000
        return None
    
    def set_attribute(self, key: str, value: Any):
        """设置属性"""
        self.attributes[key] = value
    
    def add_event(self, name: str, attributes: Dict[str, Any] = None):
        """添加事件"""
        self.events.append({
            "name": name,
            "timestamp": datetime.utcnow().isoformat(),
            "attributes": attributes or {},
        })
    
    def set_status(self, status: SpanStatus):
        """设置状态"""
        self.status = status
    
    def end(self):
        """结束跨度"""
        self.end_time = datetime.utcnow()


@dataclass
class AuditLogEntry:
    """审计日志条目"""
    timestamp: datetime
    actor: str  # 执行者
    action: str  # 操作
    resource: str  # 资源
    resource_type: str  # 资源类型
    result: str  # 结果（success/failure）
    details: Dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "actor": self.actor,
            "action": self.action,
            "resource": self.resource,
            "resource_type": self.resource_type,
            "result": self.result,
            "details": self.details,
            "correlation_id": self.correlation_id,
        }


class MetricCollector:
    """
    指标收集器
    
    收集和管理各种指标
    """
    
    def __init__(self):
        self._metrics: Dict[str, List[MetricPoint]] = {}
        self._counters: Dict[str, float] = {}
        self._gauges: Dict[str, float] = {}
    
    def increment(
        self,
        name: str,
        value: float = 1,
        labels: Dict[str, str] = None
    ):
        """增加计数器"""
        key = self._make_key(name, labels)
        
        if key not in self._counters:
            self._counters[key] = 0
        
        self._counters[key] += value
        
        # 记录数据点
        point = MetricPoint(
            name=name,
            value=self._counters[key],
            labels=labels or {},
            metric_type=MetricType.COUNTER,
        )
        
        if name not in self._metrics:
            self._metrics[name] = []
        self._metrics[name].append(point)
    
    def set_gauge(
        self,
        name: str,
        value: float,
        labels: Dict[str, str] = None
    ):
        """设置仪表盘"""
        key = self._make_key(name, labels)
        self._gauges[key] = value
        
        point = MetricPoint(
            name=name,
            value=value,
            labels=labels or {},
            metric_type=MetricType.GAUGE,
        )
        
        if name not in self._metrics:
            self._metrics[name] = []
        self._metrics[name].append(point)
    
    def record_histogram(
        self,
        name: str,
        value: float,
        labels: Dict[str, str] = None
    ):
        """记录直方图"""
        point = MetricPoint(
            name=name,
            value=value,
            labels=labels or {},
            metric_type=MetricType.HISTOGRAM,
        )
        
        if name not in self._metrics:
            self._metrics[name] = []
        self._metrics[name].append(point)
    
    def _make_key(self, name: str, labels: Dict[str, str] = None) -> str:
        """生成唯一键"""
        if not labels:
            return name
        
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"
    
    def get_metric(self, name: str) -> List[MetricPoint]:
        """获取指标"""
        return self._metrics.get(name, [])
    
    def get_all_metrics(self) -> Dict[str, List[MetricPoint]]:
        """获取所有指标"""
        return self._metrics.copy()
    
    def get_summary(self) -> Dict[str, Any]:
        """获取指标摘要"""
        summary = {
            "total_metrics": len(self._metrics),
            "counters": len(self._counters),
            "gauges": len(self._gauges),
            "metrics": {},
        }
        
        for name, points in self._metrics.items():
            if not points:
                continue
            
            summary["metrics"][name] = {
                "type": points[0].metric_type.value,
                "count": len(points),
                "latest": points[-1].value if points else None,
                "labels": points[-1].labels if points else {},
            }
        
        return summary
    
    def clear(self):
        """清空所有指标"""
        self._metrics.clear()
        self._counters.clear()
        self._gauges.clear()


class Tracer:
    """
    追踪器
    
    实现分布式追踪
    """
    
    def __init__(self, service_name: str = "knowrag"):
        self.service_name = service_name
        self._active_spans: Dict[str, Span] = {}
        self._completed_spans: List[Span] = []
        self._exporters: List[callable] = []
    
    def start_span(
        self,
        name: str,
        parent: Optional[Span] = None,
        attributes: Dict[str, Any] = None
    ) -> Span:
        """开始新的跨度"""
        trace_id = parent.trace_id if parent else str(uuid.uuid4())
        span_id = str(uuid.uuid4())
        
        span = Span(
            trace_id=trace_id,
            span_id=span_id,
            name=name,
            start_time=datetime.utcnow(),
            parent_span_id=parent.span_id if parent else None,
            attributes=attributes or {},
        )
        
        # 添加服务属性
        span.set_attribute("service.name", self.service_name)
        
        self._active_spans[span_id] = span
        
        return span
    
    def end_span(self, span: Span, status: SpanStatus = SpanStatus.OK):
        """结束跨度"""
        span.set_status(status)
        span.end()
        
        if span.span_id in self._active_spans:
            del self._active_spans[span.span_id]
        
        self._completed_spans.append(span)
        
        # 导出
        self._export(span)
    
    def _export(self, span: Span):
        """导出跨度"""
        for exporter in self._exporters:
            try:
                exporter(span)
            except Exception as e:
                print(f"Exporter error: {e}")
    
    def register_exporter(self, exporter: callable):
        """注册导出器"""
        self._exporters.append(exporter)
    
    def get_active_span(self, span_id: str) -> Optional[Span]:
        """获取活跃的跨度"""
        return self._active_spans.get(span_id)
    
    def get_completed_spans(
        self,
        trace_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Span]:
        """获取已完成的跨度"""
        spans = self._completed_spans
        
        if trace_id:
            spans = [s for s in spans if s.trace_id == trace_id]
        
        return spans[-limit:]
    
    def clear(self):
        """清空追踪"""
        self._active_spans.clear()
        self._completed_spans.clear()


class AuditLogger:
    """
    审计日志记录器
    
    记录所有重要操作
    """
    
    def __init__(self):
        self._logs: List[AuditLogEntry] = []
        self._filters: List[callable] = []
    
    def log(
        self,
        actor: str,
        action: str,
        resource: str,
        resource_type: str,
        result: str,
        details: Dict[str, Any] = None,
        correlation_id: Optional[str] = None
    ):
        """记录审计日志"""
        entry = AuditLogEntry(
            timestamp=datetime.utcnow(),
            actor=actor,
            action=action,
            resource=resource,
            resource_type=resource_type,
            result=result,
            details=details or {},
            correlation_id=correlation_id,
        )
        
        # 应用过滤器
        if self._should_log(entry):
            self._logs.append(entry)
    
    def _should_log(self, entry: AuditLogEntry) -> bool:
        """检查是否应该记录"""
        for filter_func in self._filters:
            try:
                if not filter_func(entry):
                    return False
            except Exception:
                pass
        return True
    
    def add_filter(self, filter_func: callable):
        """添加过滤器"""
        self._filters.append(filter_func)
    
    def get_logs(
        self,
        actor: Optional[str] = None,
        resource: Optional[str] = None,
        start_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[AuditLogEntry]:
        """获取审计日志"""
        logs = self._logs
        
        if actor:
            logs = [l for l in logs if l.actor == actor]
        
        if resource:
            logs = [l for l in logs if l.resource == resource]
        
        if start_time:
            logs = [l for l in logs if l.timestamp >= start_time]
        
        return logs[-limit:]
    
    def get_summary(self) -> Dict[str, Any]:
        """获取审计日志摘要"""
        summary = {
            "total_logs": len(self._logs),
            "by_actor": {},
            "by_action": {},
            "by_result": {},
            "recent_logs": [],
        }
        
        for log in self._logs[-100:]:
            # 按执行者统计
            actor = log.actor
            summary["by_actor"][actor] = summary["by_actor"].get(actor, 0) + 1
            
            # 按操作统计
            action = log.action
            summary["by_action"][action] = summary["by_action"].get(action, 0) + 1
            
            # 按结果统计
            result = log.result
            summary["by_result"][result] = summary["by_result"].get(result, 0) + 1
        
        # 最近日志
        summary["recent_logs"] = [
            log.to_dict() for log in self._logs[-10:]
        ]
        
        return summary
    
    def clear(self):
        """清空审计日志"""
        self._logs.clear()


class ObservabilityService:
    """
    可观测性服务
    
    整合指标、追踪、审计日志
    """
    
    def __init__(self, service_name: str = "knowrag"):
        self.metrics = MetricCollector()
        self.tracer = Tracer(service_name)
        self.audit = AuditLogger()
        
        # 自动指标
        self._setup_default_metrics()
    
    def _setup_default_metrics(self):
        """设置默认指标"""
        # 请求计数器
        self.metrics.increment("system.startup")
    
    def record_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        user_id: Optional[str] = None
    ):
        """记录请求指标"""
        labels = {
            "method": method,
            "status": str(status_code),
        }
        
        if user_id:
            labels["user_id"] = user_id
        
        # 请求计数
        self.metrics.increment("http.requests.total", labels=labels)
        
        # 请求延迟
        self.metrics.record_histogram(
            "http.request.duration_ms",
            duration_ms,
            labels={"method": method}
        )
        
        # 审计日志
        result = "success" if 200 <= status_code < 400 else "failure"
        self.audit.log(
            actor=user_id or "anonymous",
            action=method,
            resource=path,
            resource_type="http_request",
            result=result,
            details={"status_code": status_code, "duration_ms": duration_ms},
        )
    
    def record_agent_action(
        self,
        agent_id: str,
        action: str,
        session_id: Optional[str] = None,
        details: Dict[str, Any] = None
    ):
        """记录 Agent 动作"""
        self.metrics.increment(
            "agent.actions.total",
            labels={"agent_id": agent_id, "action": action}
        )
        
        self.audit.log(
            actor=agent_id,
            action=action,
            resource=session_id or "global",
            resource_type="agent_session",
            result="success",
            details=details or {},
        )
    
    def record_error(
        self,
        error_code: str,
        error_category: str,
        severity: str,
        details: Dict[str, Any] = None
    ):
        """记录错误指标"""
        self.metrics.increment(
            "errors.total",
            labels={
                "error_code": error_code,
                "category": error_category,
                "severity": severity,
            }
        )
    
    def get_dashboard(self) -> Dict[str, Any]:
        """获取可观测性仪表板"""
        return {
            "metrics": self.metrics.get_summary(),
            "tracing": {
                "active_spans": len(self.tracer._active_spans),
                "completed_spans": len(self.tracer._completed_spans),
            },
            "audit": self.audit.get_summary(),
            "timestamp": datetime.utcnow().isoformat(),
        }


__all__ = [
    "MetricType",
    "SpanStatus",
    "MetricPoint",
    "Span",
    "AuditLogEntry",
    "MetricCollector",
    "Tracer",
    "AuditLogger",
    "ObservabilityService",
]
