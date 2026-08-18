"""
集成示例：展示所有优化系统的协同工作

整合：
1. 事件驱动扩展系统
2. 服务提供者/消费者模式
3. 统一错误处理
4. 可观测性系统
5. 热更新系统
"""
import asyncio
import logging
from typing import Dict, Any
from datetime import datetime

from packages.agent.events.bus import EventBus, ExtensionContext, ExtensionRegistry
from packages.agent.services.provider import (
    ServiceProvider, ServiceConsumer, ServiceRegistry, ServiceContainer,
    ServiceMetadata, ServiceStatus
)
from packages.agent.errors.types import (
    ErrorHandler, ValidationError, AuthenticationError, 
    ServiceUnavailableError, RecoveryStrategy
)
from packages.agent.observability.metrics import (
    ObservabilityService, MetricType, SpanStatus
)
from packages.agent.hotreload.watcher import create_hot_reload_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# 1. 定义服务
# ============================================================================

class ModelServiceProvider(ServiceProvider[Dict[str, Any]]):
    """模型服务提供者"""
    
    metadata = ServiceMetadata(
        name="model_service",
        version="1.0.0",
        description="LLM 模型服务",
        capabilities=["inference", "embedding"],
        dependencies=[]
    )
    
    def __init__(self):
        super().__init__()
        self._model_loaded = False
    
    async def _start_impl(self):
        logger.info("Starting model service...")
        await asyncio.sleep(0.1)  # 模拟加载时间
        self._model_loaded = True
        logger.info("Model service started")
    
    async def _stop_impl(self):
        logger.info("Stopping model service...")
        self._model_loaded = False
        logger.info("Model service stopped")
    
    async def provide(self) -> Dict[str, Any]:
        if not self._model_loaded:
            raise ServiceUnavailableError("Model service not started")
        return {"model": "deepseek-v3", "status": "ready"}


class ToolServiceProvider(ServiceProvider[Dict[str, Any]]):
    """工具服务提供者"""
    
    metadata = ServiceMetadata(
        name="tool_service",
        version="1.0.0",
        description="工具调用服务",
        capabilities=["tool_execution"],
        dependencies=["model_service"]  # 依赖模型服务
    )
    
    def __init__(self):
        super().__init__()
        self._tools = []
    
    async def _start_impl(self):
        logger.info("Starting tool service...")
        self._tools = ["search", "calculator", "code_interpreter"]
        logger.info(f"Tool service started with {len(self._tools)} tools")
    
    async def _stop_impl(self):
        logger.info("Stopping tool service...")
        self._tools = []
        logger.info("Tool service stopped")
    
    async def provide(self) -> Dict[str, Any]:
        return {"tools": self._tools, "status": "ready"}


class EventServiceProvider(ServiceProvider[EventBus]):
    """事件服务提供者"""
    
    metadata = ServiceMetadata(
        name="event_service",
        version="1.0.0",
        description="事件总线服务",
        capabilities=["event_pub_sub"],
        dependencies=[]
    )
    
    def __init__(self):
        super().__init__()
        self._event_bus = None
    
    async def _start_impl(self):
        logger.info("Starting event service...")
        self._event_bus = EventBus()
        logger.info("Event service started")
    
    async def _stop_impl(self):
        logger.info("Stopping event service...")
        self._event_bus = None
        logger.info("Event service stopped")
    
    async def provide(self) -> EventBus:
        if not self._event_bus:
            raise ServiceUnavailableError("Event service not started")
        return self._event_bus


# ============================================================================
# 2. 定义 Agent 执行器（服务消费者）
# ============================================================================

class AgentExecutor(ServiceConsumer):
    """Agent 执行器 - 消费多个服务"""
    
    def __init__(self, error_handler: ErrorHandler, observability: ObservabilityService):
        super().__init__()
        self._error_handler = error_handler
        self._observability = observability
        self._event_bus: EventBus = None
        self._container: ServiceContainer = None
    
    async def initialize(self, container: ServiceContainer):
        """初始化，获取服务引用"""
        self._container = container
        event_service = await container.registry.get_service("event_service").provide()
        self._event_bus = event_service
        
        # 注册事件处理器
        self._register_event_handlers()
    
    def _register_event_handlers(self):
        """注册事件处理器"""
        async def log_pre_execute(ctx: ExtensionContext):
            self._observability.metrics.increment("agent.execution.count")
            payload = ctx.payload if isinstance(ctx.payload, dict) else {}
            logger.info(f"Pre-execute: {payload.get('query', 'unknown')}")
        
        async def log_post_execute(ctx: ExtensionContext):
            logger.info(f"Post-execute: Success")
        
        async def handle_error(ctx: ExtensionContext):
            payload = ctx.payload if isinstance(ctx.payload, dict) else {}
            error = payload.get('error')
            self._observability.metrics.increment("agent.error.count")
            logger.error(f"Agent error: {error}")
        
        self._event_bus.subscribe("agent.pre_execute", log_pre_execute)
        self._event_bus.subscribe("agent.post_execute", log_post_execute)
        self._event_bus.subscribe("agent.on_error", handle_error)
    
    async def execute(self, query: str) -> Dict[str, Any]:
        """执行 Agent 查询"""
        correlation_id = f"exec_{datetime.now().timestamp()}"
        
        # 开始追踪
        span = self._observability.tracer.start_span("agent_execute")
        span.set_attribute("query", query)
        span.set_attribute("correlation_id", correlation_id)
        
        try:
            # 发布 PRE 事件
            context = ExtensionContext(
                event_type="agent.pre_execute",
                payload={"query": query, "correlation_id": correlation_id},
                correlation_id=correlation_id
            )
            await self._event_bus.publish("agent.pre_execute", context)
            
            # 获取服务（通过 ServiceRegistry）
            model_service = await self._container.registry.get_service("model_service").provide()
            tool_service = await self._container.registry.get_service("tool_service").provide()
            
            # 模拟执行
            await asyncio.sleep(0.2)
            
            result = {
                "query": query,
                "model": model_service["model"],
                "tools": tool_service["tools"],
                "response": f"Response to: {query}",
                "correlation_id": correlation_id
            }
            
            # 发布 POST 事件
            post_context = ExtensionContext(
                event_type="agent.post_execute",
                payload={"result": result, "correlation_id": correlation_id},
                correlation_id=correlation_id
            )
            await self._event_bus.publish("agent.post_execute", post_context)
            
            self._observability.metrics.record_histogram(
                "agent.execution.duration.ms",
                200,  # 模拟 200ms
                labels={"status": "success"}
            )
            
            span.set_status(SpanStatus.OK)
            return result
                
        except Exception as e:
                # 错误处理
                agent_error = ValidationError(
                    message=f"Execution failed: {str(e)}"
                )
                
                # 记录错误
                self._observability.metrics.increment("agent.error.count")
                self._observability.audit.log(
                    action="agent.execution.error",
                    resource=query,
                    details={"error": str(e)}
                )
                
                # 发布错误事件
                error_context = ExtensionContext(
                    event_type="agent.on_error",
                    payload={"error": agent_error, "correlation_id": correlation_id},
                    correlation_id=correlation_id
                )
                await self._event_bus.publish("agent.on_error", error_context)
                
                span.set_status(SpanStatus.ERROR)
                raise
        finally:
            span.end()


# ============================================================================
# 3. 集成演示
# ============================================================================

async def run_integration_demo():
    """运行集成演示"""
    print("\n" + "="*60)
    print("KnowRAG Phase 1-5 集成演示")
    print("="*60 + "\n")
    
    # 1. 创建错误处理器
    print("1. 初始化错误处理系统...")
    error_handler = ErrorHandler()
    # 错误处理通过错误类型的 recovery_strategy 自动应用
    print("   ✓ 错误处理系统就绪\n")
    
    # 2. 创建可观测性服务
    print("2. 初始化可观测性系统...")
    observability = ObservabilityService()
    print("   ✓ 指标收集器就绪")
    print("   ✓ 追踪器就绪")
    print("   ✓ 审计日志就绪\n")
    
    # 3. 创建服务容器
    print("3. 初始化服务容器...")
    container = ServiceContainer()
    
    # 注册服务
    model_service = ModelServiceProvider()
    tool_service = ToolServiceProvider()
    event_service = EventServiceProvider()
    
    container.add_service(model_service)
    container.add_service(tool_service)
    container.add_service(event_service)
    print("   ✓ 服务注册完成\n")
    
    # 4. 启动服务
    print("4. 启动服务（自动解析依赖）...")
    await container.initialize()
    print("   ✓ 所有服务已启动\n")
    
    # 5. 创建 Agent 执行器
    print("5. 创建 Agent 执行器...")
    executor = AgentExecutor(error_handler, observability)
    await executor.initialize(container)
    print("   ✓ Agent 执行器就绪\n")
    
    # 6. 执行查询
    print("6. 执行 Agent 查询...")
    print("-" * 60)
    result = await executor.execute("What is the capital of France?")
    print(f"   Query: {result['query']}")
    print(f"   Model: {result['model']}")
    print(f"   Tools: {result['tools']}")
    print(f"   Response: {result['response']}")
    print(f"   Correlation ID: {result['correlation_id']}")
    print("-" * 60 + "\n")
    
    # 7. 查看可观测性数据
    print("7. 查看可观测性数据...")
    print("-" * 60)
    
    # 指标
    metrics_summary = observability.metrics.get_summary()
    print("   指标摘要:")
    for metric_name, data in metrics_summary.items():
        print(f"     - {metric_name}: {data}")
    
    # 追踪
    completed_spans = observability.tracer.get_completed_spans()
    print(f"\n   追踪跨度：{len(completed_spans)} 个")
    for span in completed_spans:
        print(f"     - {span.name}: {span.duration_ms:.2f}ms")
    
    # 审计日志
    audit_summary = observability.audit.get_summary()
    print(f"\n   审计日志：{audit_summary}")
    print("-" * 60 + "\n")
    
    # 8. 停止服务
    print("8. 停止服务（反向关闭）...")
    await container.shutdown()
    print("   ✓ 所有服务已停止\n")
    
    print("="*60)
    print("演示完成！")
    print("="*60 + "\n")
    
    return {
        "result": result,
        "metrics": metrics_summary,
        "spans": completed_spans,
        "audit_summary": audit_summary
    }


def run_demo():
    """运行演示（同步入口）"""
    return asyncio.run(run_integration_demo())


if __name__ == "__main__":
    run_demo()
