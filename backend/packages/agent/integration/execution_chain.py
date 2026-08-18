"""
执行链路集成：将 Phase 1-5 的优化系统集成到 /execute/stream

设计模式：装饰器 (Decorator Pattern)
- ExecutionOrchestrator 包装 OrchestratorRuntime
- 提供横切关注点支持（事件/服务/错误/观测/热更新）
- 业务逻辑仍由 OrchestratorRuntime 负责
"""
import asyncio
import logging
from typing import Dict, Any, Optional, AsyncGenerator
from datetime import datetime

from packages.agent.events.bus import EventBus, ExtensionContext
from packages.agent.services.provider import ServiceContainer, ServiceProvider, ServiceMetadata
from packages.agent.errors.types import ErrorHandler, ValidationError, ServiceUnavailableError, RecoveryStrategy
from packages.agent.observability.metrics import ObservabilityService, SpanStatus
from packages.agent.hotreload.watcher import create_hot_reload_service

logger = logging.getLogger(__name__)


# ============================================================================
# 1. 定义执行链路服务
# ============================================================================

class EventServiceProvider(ServiceProvider):
    """事件服务提供者"""
    
    metadata = ServiceMetadata(
        name="event_service",
        version="1.0.0",
        description="事件总线服务",
        capabilities=["event_pub_sub", "interceptors"],
        dependencies=[]
    )
    
    def __init__(self):
        super().__init__()
        self._event_bus = None
    
    async def _start_impl(self):
        logger.info("Starting event service")
        self._event_bus = EventBus()
    
    async def _stop_impl(self):
        logger.info("Stopping event service")
        self._event_bus = None
    
    async def provide(self):
        if not self._event_bus:
            raise ServiceUnavailableError("Event service not started")
        return self._event_bus


# ============================================================================
# 2. 执行链路编排器（装饰器模式）
# ============================================================================

class ExecutionOrchestrator:
    """
    执行链路编排器（装饰器）
    
    包装 OrchestratorRuntime，提供横切关注点支持：
    - 事件驱动扩展
    - 服务容器管理
    - 统一错误处理
    - 完整可观测性
    - 热更新能力
    
    业务逻辑仍由 OrchestratorRuntime 负责
    """
    
    def __init__(self, db, user_id: int, model_name: str = "deepseek-v3"):
        self.db = db
        self.user_id = user_id
        self.model_name = model_name
        
        # 初始化优化系统（横切关注点）
        self._init_cross_cutting_systems()
        
        # 包装现有的业务运行时（被装饰者）
        self._init_business_runtime()
        
        # Step 执行门面（P0：Step/Turn 模型 + 结构化事件流 + 钩子 + 事件溯源）
        from packages.agent.execution.runner import StepExecutionRuntime
        self._step_runtime = None
        self._execution_hooks = None  # 用户自定义钩子（P1）
    
    def _init_cross_cutting_systems(self):
        """初始化横切关注点系统"""
        # 1. 错误处理系统
        self.error_handler = ErrorHandler()
        
        # 2. 可观测性系统
        self.observability = ObservabilityService(service_name="knowrag")
        
        # 3. 服务容器
        self.container = ServiceContainer()
        event_service = EventServiceProvider()
        self.container.add_service(event_service)
        
        # 4. 热更新服务
        self.hot_reload = create_hot_reload_service(
            watch_dirs=["/config", "/plugins"],
            enabled=True
        )
        self.hot_reload.watch_config(self._on_config_reload)
    
    def _init_business_runtime(self):
        """初始化业务运行时（延迟导入，避免循环依赖）"""
        # 注意：这里不立即创建 OrchestratorRuntime，而是在 execute_stream 中按需创建
        # 这样可以避免测试时的依赖问题
        self._runtime = None
    
    @property
    def runtime(self):
        """延迟创建 OrchestratorRuntime"""
        if self._runtime is None:
            from packages.agent.orchestrator.graph import OrchestratorRuntime
            self._runtime = OrchestratorRuntime(
                db=self.db,
                model_name=self.model_name,
                user_id=self.user_id
            )
        return self._runtime
    
    # ---- P0/P1/P2 执行框架透出（Step 门面能力） ----
    @property
    def execution(self):
        """Step 执行门面（P0 执行模型）。未执行时为 None。"""
        return self._step_runtime

    def add_pre_step_hook(self, hook, name: str = ""):
        """注册 pre-step 钩子（P1）。"""
        from packages.agent.execution.hooks import HookRegistry
        if self._execution_hooks is None:
            self._execution_hooks = HookRegistry()
        self._execution_hooks.add_pre_step(hook, name)

    def add_post_step_hook(self, hook, name: str = ""):
        """注册 post-step 钩子（P1）。"""
        from packages.agent.execution.hooks import HookRegistry
        if self._execution_hooks is None:
            self._execution_hooks = HookRegistry()
        self._execution_hooks.add_post_step(hook, name)

    def add_waterfall(self, event: str, transform, name: str = ""):
        """注册 waterfall 拦截器（P1）。"""
        from packages.agent.execution.hooks import HookRegistry
        if self._execution_hooks is None:
            self._execution_hooks = HookRegistry()
        self._execution_hooks.add_waterfall(event, transform, name)
    
    async def start(self):
        """启动所有服务"""
        logger.info("Starting execution orchestrator...")
        
        # 启动服务容器
        await self.container.initialize()
        
        # 启动热更新
        self.hot_reload.start()
        
        # 注册事件拦截器
        await self._register_interceptors()
        
        logger.info("Execution orchestrator started")
    
    async def stop(self):
        """停止所有服务"""
        logger.info("Stopping execution orchestrator...")
        
        # 停止热更新
        self.hot_reload.stop()
        
        # 停止服务容器
        await self.container.shutdown()
        
        logger.info("Execution orchestrator stopped")
    
    async def _register_interceptors(self):
        """注册事件拦截器"""
        event_bus = await self.container.registry.get_service("event_service").provide()
        
        # PRE 拦截器：请求验证
        async def validate_request(ctx: ExtensionContext):
            self.observability.metrics.increment("execution.request.count")
            query = ctx.payload.get('query', '') if isinstance(ctx.payload, dict) else str(ctx.payload)
            logger.info(f"Validating request: {query[:50]}")
        
        event_bus.subscribe("execution.pre", validate_request)
        
        # POST 拦截器：响应处理
        async def process_response(ctx: ExtensionContext):
            self.observability.metrics.increment("execution.success.count")
            logger.info("Request completed successfully")
        
        event_bus.subscribe("execution.post", process_response)
        
        # ON_ERROR 拦截器：错误处理
        async def handle_error(ctx: ExtensionContext):
            self.observability.metrics.increment("execution.error.count")
            error = ctx.payload.get('error')
            logger.error(f"Execution error: {error}")
        
        event_bus.subscribe("execution.error", handle_error)
    
    def _on_config_reload(self, config: Dict, path: str):
        """配置重载回调"""
        logger.info(f"Config reloaded: {path}")
        # 可以动态更新配置
    
    async def execute_stream(
        self,
        query: str,
        main_prompt: Optional[str] = None,
        run_mode: str = "serial",
        allow_sub_agents: bool = True,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式执行（装饰器模式）
        
        包装 OrchestratorRuntime.run_stream()，添加横切关注点支持：
        - 事件发布
        - 指标记录
        - 分布式追踪
        - 审计日志
        - 错误处理
        
        业务逻辑（Agent 调度、状态管理、RAG 等）仍由 OrchestratorRuntime 负责
        """
        correlation_id = f"exec_{datetime.now().timestamp()}"
        start_time = datetime.utcnow()
        
        # 开始追踪
        span = self.observability.tracer.start_span("execute_stream")
        span.set_attribute("query", query)
        span.set_attribute("user_id", self.user_id)
        span.set_attribute("session_id", session_id)
        span.set_attribute("correlation_id", correlation_id)
        span.set_attribute("model", self.model_name)
        
        try:
            # 1. 发布 PRE 事件
            event_bus = await self.container.registry.get_service("event_service").provide()
            pre_context = ExtensionContext(
                event_type="execution.pre",
                payload={
                    "query": query,
                    "main_prompt": main_prompt,
                    "session_id": session_id,
                    "correlation_id": correlation_id,
                    "user_id": self.user_id,
                },
                correlation_id=correlation_id
            )
            await event_bus.publish("execution.pre", pre_context)
            
            # 2. 记录请求开始指标
            self.observability.metrics.increment("execution.request.count")
            self.observability.audit.log(
                actor=str(self.user_id),
                action="execution.start",
                resource=query[:100],  # 截断避免过长
                resource_type="execution_request",
                result="pending",
                details={
                    "session_id": session_id,
                    "model": self.model_name,
                    "correlation_id": correlation_id,
                },
            )
            
            # 3. 委托给 StepExecutionRuntime（P0 执行模型）→ 内部再调用 OrchestratorRuntime.run_stream
            #    StepExecutionRuntime 产出结构化 step/turn 事件、执行钩子、写入会话日志、保存检查点。
            from packages.agent.execution.runner import StepExecutionRuntime
            self._step_runtime = StepExecutionRuntime(
                self.runtime, session_id=session_id,
                user_id=self.user_id, agent_id=agent_id,
            )
            # 透传用户自定义钩子（若已注册）
            if getattr(self, "_execution_hooks", None):
                self._step_runtime.hooks.pre_step.extend(self._execution_hooks.pre_step)
                self._step_runtime.hooks.post_step.extend(self._execution_hooks.post_step)
                for ev, transforms in (self._execution_hooks.waterfalls or {}).items():
                    for t in transforms:
                        self._step_runtime.hooks.add_waterfall(ev, t)

            token_count = 0
            async for event in self._step_runtime.execute_stream(
                query=query,
                main_prompt=main_prompt,
                run_mode=run_mode,
                allow_sub_agents=allow_sub_agents,
                session_id=session_id,
                agent_id=agent_id,
            ):
                # 4. 记录指标
                if isinstance(event, dict):
                    event_type = event.get("type", "unknown")
                    
                    if event_type == "token":
                        token_count += 1
                        self.observability.metrics.increment("execution.token.count")
                    
                    elif event_type == "sub_agent":
                        self.observability.metrics.increment("execution.sub_agent.count")
                
                # 5. 产出事件
                yield event
            
            # 6. 计算执行时间
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            # 7. 发布 POST 事件
            post_context = ExtensionContext(
                event_type="execution.post",
                payload={
                    "query": query,
                    "duration_ms": duration_ms,
                    "token_count": token_count,
                    "correlation_id": correlation_id,
                },
                correlation_id=correlation_id
            )
            await event_bus.publish("execution.post", post_context)
            
            # 8. 记录成功指标
            self.observability.metrics.increment("execution.success.count")
            self.observability.metrics.record_histogram(
                "execution.duration.ms",
                duration_ms,
                labels={"status": "success", "model": self.model_name}
            )
            
            # 9. 记录审计日志
            self.observability.audit.log(
                actor=str(self.user_id),
                action="execution.complete",
                resource=query[:100],
                resource_type="execution_request",
                result="success",
                details={
                    "duration_ms": duration_ms,
                    "token_count": token_count,
                    "correlation_id": correlation_id,
                },
            )
            
            span.set_status(SpanStatus.OK)
            
        except Exception as e:
            # 错误处理
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            # 1. 记录错误指标
            self.observability.metrics.increment("execution.error.count")
            
            # 2. 记录审计日志
            self.observability.audit.log(
                actor=str(self.user_id),
                action="execution.error",
                resource=query[:100],
                resource_type="execution_request",
                result="error",
                details={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "correlation_id": correlation_id,
                },
            )
            
            # 3. 发布错误事件
            event_bus = await self.container.registry.get_service("event_service").provide()
            error_context = ExtensionContext(
                event_type="execution.error",
                payload={
                    "error": e,
                    "error_type": type(e).__name__,
                    "correlation_id": correlation_id,
                },
                correlation_id=correlation_id
            )
            await event_bus.publish("execution.error", error_context)
            
            span.set_status(SpanStatus.ERROR)
            
            # 4. 重新抛出异常（让 API 层处理）
            raise
        
        finally:
            # 结束追踪
            span.end()


# ============================================================================
# 3. 工厂函数
# ============================================================================

def create_execution_orchestrator(
    db,
    user_id: int,
    model_name: str = "deepseek-v3"
) -> ExecutionOrchestrator:
    """
    创建执行链路编排器
    
    Args:
        db: 数据库会话（用于 OrchestratorRuntime）
        user_id: 用户 ID
        model_name: 模型名称
    
    Returns:
        ExecutionOrchestrator 实例（包装了 OrchestratorRuntime）
    """
    return ExecutionOrchestrator(db, user_id, model_name)


# ============================================================================
# 4. 测试演示
# ============================================================================

async def demo():
    """演示集成效果"""
    print("\n" + "="*60)
    print("执行链路集成演示")
    print("="*60 + "\n")
    
    # 创建编排器
    orchestrator = create_execution_orchestrator(user_id=123)
    
    # 启动
    await orchestrator.start()
    
    # 执行流式请求
    print("执行流式请求...\n")
    async for event in orchestrator.execute_stream(
        query="What is the capital of France?",
        session_id="session_123"
    ):
        print(f"  Event: {event}")
    
    print("\n查看可观测性数据...")
    metrics = orchestrator.observability.metrics.get_summary()
    print(f"  指标：{metrics}")
    
    # 停止
    await orchestrator.stop()
    
    print("\n" + "="*60)
    print("演示完成！")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(demo())
