"""
事件驱动扩展示例

演示各种扩展点的用法
"""
from typing import Any, Dict
from .bus import (
    ExtensionContext,
    Interceptor,
    Transformer,
    EventHandler,
    ExecutionOrder,
)


class LoggingInterceptor(Interceptor):
    """
    日志拦截器
    
    记录所有事件的输入输出
    """
    
    name = "logging_interceptor"
    description = "Log all events"
    version = "1.0.0"
    priority = 100  # 高优先级，最先执行
    
    execution_order = ExecutionOrder.PRE
    
    async def pre_handle(self, ctx: ExtensionContext) -> None:
        """前置日志"""
        print(f"[LOG] Event: {ctx.event_type}")
        print(f"[LOG] Payload: {ctx.payload}")
        print(f"[LOG] Correlation ID: {ctx.correlation_id}")
    
    async def post_handle(self, ctx: ExtensionContext) -> None:
        """后置日志"""
        if ctx.error:
            print(f"[LOG] Error: {ctx.error}")
        else:
            print(f"[LOG] Result: {ctx.result}")


class AuthInterceptor(Interceptor):
    """
    认证拦截器
    
    验证用户权限
    """
    
    name = "auth_interceptor"
    description = "Authenticate user"
    version = "1.0.0"
    priority = 90  # 次高优先级
    
    execution_order = ExecutionOrder.PRE
    
    def __init__(self, required_role: str = None):
        self.required_role = required_role
    
    async def pre_handle(self, ctx: ExtensionContext) -> None:
        """验证权限"""
        user = ctx.metadata.get("user")
        
        if not user:
            ctx.stop_propagation()
            raise PermissionError("User not authenticated")
        
        if self.required_role and user.get("role") != self.required_role:
            ctx.stop_propagation()
            raise PermissionError(
                f"Required role: {self.required_role}"
            )


class ValidationInterceptor(Interceptor):
    """
    验证拦截器
    
    验证 payload 格式
    """
    
    name = "validation_interceptor"
    description = "Validate payload"
    version = "1.0.0"
    priority = 80
    
    execution_order = ExecutionOrder.PRE
    
    def __init__(self, validator: callable):
        self.validator = validator
    
    async def pre_handle(self, ctx: ExtensionContext) -> None:
        """验证 payload"""
        try:
            self.validator(ctx.payload)
        except ValueError as e:
            ctx.stop_propagation()
            raise


class PayloadTransformer(Transformer):
    """
    Payload 转换器
    
    转换输入数据格式
    """
    
    name = "payload_transformer"
    description = "Transform payload format"
    version = "1.0.0"
    priority = 50
    
    async def transform(self, payload: Any) -> Any:
        """转换 payload"""
        if isinstance(payload, dict):
            # 标准化键名
            return {k.lower(): v for k, v in payload.items()}
        return payload


class EnrichmentTransformer(Transformer):
    """
    增强转换器
    
    为 payload 添加额外信息
    """
    
    name = "enrichment_transformer"
    description = "Enrich payload with metadata"
    version = "1.0.0"
    priority = 40
    
    def __init__(self, enricher: callable):
        self.enricher = enricher
    
    async def transform(self, payload: Any) -> Any:
        """增强 payload"""
        if isinstance(payload, dict):
            enriched = self.enricher(payload)
            return {**payload, **enriched}
        return payload


class NotificationHandler(EventHandler):
    """
    通知处理器
    
    发送通知
    """
    
    name = "notification_handler"
    description = "Send notifications"
    version = "1.0.0"
    priority = 10
    
    target_event = "message.assistant"
    
    def __init__(self, notifier: callable):
        self.notifier = notifier
    
    async def handle(self, payload: Any) -> None:
        """发送通知"""
        await self.notifier(payload)


class MetricsHandler(EventHandler):
    """
    指标处理器
    
    收集性能指标
    """
    
    name = "metrics_handler"
    description = "Collect metrics"
    version = "1.0.0"
    priority = 5
    
    target_event = "all"  # 监听所有事件
    
    def __init__(self):
        self.metrics = []
    
    async def handle(self, payload: Any) -> None:
        """收集指标"""
        import time
        
        self.metrics.append({
            "timestamp": time.time(),
            "event_type": getattr(payload, "event_type", "unknown"),
            "payload_size": len(str(payload)),
        })
    
    def get_metrics(self) -> list:
        """获取指标"""
        return self.metrics.copy()


class CacheInterceptor(Interceptor):
    """
    缓存拦截器
    
    缓存查询结果
    """
    
    name = "cache_interceptor"
    description = "Cache query results"
    version = "1.0.0"
    priority = 70
    
    execution_order = ExecutionOrder.AROUND
    
    def __init__(self, cache: dict, ttl: int = 300):
        self.cache = cache
        self.ttl = ttl
    
    async def around_handle(self, ctx: ExtensionContext) -> None:
        """缓存处理"""
        cache_key = str(ctx.payload)
        
        # 检查缓存
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            # 检查 TTL
            import time
            if time.time() - cached["timestamp"] < self.ttl:
                ctx.set_result(cached["result"])
                return
        
        # 继续执行
        # 注意：around 模式需要在调用前后处理
        # 这里简化处理，实际应该调用下一个处理器
    
    async def post_handle(self, ctx: ExtensionContext) -> None:
        """后置缓存"""
        if not ctx.error and ctx.result:
            import time
            
            cache_key = str(ctx.payload)
            self.cache[cache_key] = {
                "result": ctx.result,
                "timestamp": time.time(),
            }


class RetryInterceptor(Interceptor):
    """
    重试拦截器
    
    自动重试失败的请求
    """
    
    name = "retry_interceptor"
    description = "Retry failed requests"
    version = "1.0.0"
    priority = 60
    
    execution_order = ExecutionOrder.ON_ERROR
    
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self.retry_counts = {}
    
    async def on_error_handle(self, ctx: ExtensionContext) -> None:
        """重试处理"""
        correlation_id = ctx.correlation_id
        
        if correlation_id not in self.retry_counts:
            self.retry_counts[correlation_id] = 0
        
        self.retry_counts[correlation_id] += 1
        
        if self.retry_counts[correlation_id] <= self.max_retries:
            print(f"Retry {self.retry_counts[correlation_id]}/{self.max_retries}")
            # 重置错误，允许重新执行
            ctx.error = None
            ctx.should_continue = True


__all__ = [
    "LoggingInterceptor",
    "AuthInterceptor",
    "ValidationInterceptor",
    "PayloadTransformer",
    "EnrichmentTransformer",
    "NotificationHandler",
    "MetricsHandler",
    "CacheInterceptor",
    "RetryInterceptor",
]
