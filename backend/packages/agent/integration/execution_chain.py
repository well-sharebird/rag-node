"""
执行链路集成：将 Phase 1-5 的优化系统集成到 /execute/stream

设计模式：装饰器 (Decorator Pattern)
- ExecutionOrchestrator 包装 Orchestrator
- 提供横切关注点支持（事件/服务/错误/观测/热更新）
- 业务逻辑仍由 Orchestrator 负责
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
    
    包装 Orchestrator，提供横切关注点支持：
    - 事件驱动扩展
    - 服务容器管理
    - 统一错误处理
    - 完整可观测性
    - 热更新能力
    
    业务逻辑仍由 Orchestrator 负责
    """
    
    def __init__(self, db, user_id: int, model_name: str = "deepseek-v3"):
        self.db = db
        self.user_id = user_id
        self.model_name = model_name
        
        # 初始化优化系统（横切关注点）
        self._init_cross_cutting_systems()
        
        # 包装现有的业务运行时（被装饰者）
        self._init_business_runtime()
        
        # LLM 将在 execute_stream 中异步初始化（因为需要从数据库加载配置）
        self._llm = None
        
        # Step 执行包装器（StepDrivenEngine：结构化事件流 + 钩子 + 检查点）
        from packages.agent.execution.step_engine import StepDrivenEngine
        self._step_runtime: Optional[StepDrivenEngine] = None
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
        """初始化业务运行时（立即创建，Orchestrator 作为稳定的图节点编排器）"""
        from packages.agent.orchestrator.graph import Orchestrator
        self._runtime = Orchestrator(
            db=self.db,
            model_name=self.model_name,
            user_id=self.user_id
        )
    
    async def _create_llm(self, model_name: str):
        """
        根据模型名称从数据库动态加载配置并创建 LLM 实例
        
        Args:
            model_name: 模型名称（如 "qwen3.5-397b-a17b"）
        
        Returns:
            LLM 实例
        
        动态配置流程：
        1. 从 ModelProvider 表查询匹配的供应商配置
        2. 从 ModelRoutingRule 表查询路由规则
        3. 使用配置创建 CompatibleChatModel 实例
        """
        from packages.agent.llm.compatible_llm import create_compatible_llm
        
        # 从数据库动态加载模型配置
        provider_config = await self._load_model_config_from_db(model_name)
        
        if not provider_config:
            # 降级：如果数据库中没有配置，使用默认配置
            logger.warning("[ExecutionOrchestrator] Model config not found in DB, using default: %s", model_name)
            provider_config = {
                "base_url": f"http://1.181.141.96:6018/{model_name}/v1",
                "api_key": "sk-no-key",
                "temperature": 0.3,
            }
        
        logger.info(
            "[ExecutionOrchestrator] Creating LLM: %s (base_url=%s, provider=%s)",
            model_name,
            provider_config.get("base_url", "N/A"),
            provider_config.get("provider_name", "N/A"),
        )
        
        return create_compatible_llm(
            model_name=model_name,
            base_url=provider_config["base_url"],
            api_key=provider_config.get("api_key", "sk-no-key"),
            temperature=provider_config.get("temperature", 0.3),
            max_tokens=None,  # 不限制输出长度
        )
    
    async def _load_model_config_from_db(self, model_name: str) -> dict:
        """
        从数据库加载模型配置
        
        Args:
            model_name: 模型名称
        
        Returns:
            配置字典，包含 base_url, api_key, temperature 等
        
        查询逻辑：
        1. 先查 ModelRoutingRule 匹配模型名称
        2. 关联查询 ModelProvider 获取供应商配置
        3. 返回合并后的配置
        """
        if not self.db:
            return None
        
        try:
            from sqlalchemy import select
            from packages.model_gateway.models.model_gateway import ModelProvider, ModelRoutingRule
            
            # 查询路由规则（匹配模型名称）
            stmt = (
                select(ModelRoutingRule, ModelProvider)
                .join(ModelProvider, ModelRoutingRule.provider_id == ModelProvider.id)
                .where(
                    ModelRoutingRule.match_conditions['models'].as_string().contains(model_name),
                    ModelProvider.is_enabled == True,
                )
                .order_by(ModelRoutingRule.priority)
                .limit(1)
            )
            
            result = await self.db.execute(stmt)
            row = result.first()
            
            if row:
                routing_rule, provider = row[0], row[1]
                
                # 合并配置
                config = {
                    "provider_name": provider.name,
                    "provider_code": provider.code,
                    "base_url": provider.base_url,
                    "api_key": provider.api_key,
                    "temperature": 0.3,  # 默认温度，可从 provider.config 扩展
                }
                
                # 如果有额外配置，合并
                if provider.config:
                    config.update(provider.config)
                
                logger.info(
                    "[ExecutionOrchestrator] Loaded model config from DB: %s -> %s",
                    model_name,
                    provider.name,
                )
                
                return config
            else:
                logger.warning(
                    "[ExecutionOrchestrator] No matching routing rule found for model: %s",
                    model_name,
                )
                return None
                
        except Exception as e:
            logger.error(
                "[ExecutionOrchestrator] Failed to load model config from DB: %s",
                e,
                exc_info=True,
            )
            return None
    
    @property
    def runtime(self):
        """获取业务运行时（Orchestrator，图驱动核心编排器）"""
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
        
        包装 Orchestrator.run_stream()，添加横切关注点支持：
        - 事件发布
        - 指标记录
        - 分布式追踪
        - 审计日志
        - 错误处理
        
        业务逻辑（Agent 调度、状态管理、RAG 等）仍由 Orchestrator 负责
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
            
            # 3. 初始化 LLM（异步从数据库加载配置）
            if self._llm is None:
                self._llm = await self._create_llm(self.model_name)
            
            # 4. 委托给 StepDrivenEngine（执行包装器）
            #    产出结构化 step/turn 事件、执行钩子、写入会话日志、保存检查点。
            from packages.agent.execution.step_engine import StepDrivenEngine
            from packages.agent.core.harness.security.permission import PermissionEngine
            
            # 使用已初始化的 LLM 实例
            llm = self._llm
            tools = []
            # 创建权限引擎（用于工具调用审批）
            try:
                permission_engine = PermissionEngine(
                    db=self.db,
                    user_id=self.user_id,
                    policy={
                        "blocked_tools": [],  # 可从配置加载
                        "allowed_tools": [],  # 可从配置加载
                    }
                )
            except Exception as e:
                logger.warning("[ExecutionOrchestrator] PermissionEngine 初始化失败：%s", e)
                permission_engine = None
            # 创建 HookRegistry（P1 横切关注点）
            from packages.agent.execution.hooks import HookRegistry
            hook_registry = HookRegistry()
            
            self._step_runtime = StepDrivenEngine(
                llm=llm,
                tools=tools,
                hooks=hook_registry,
                session_id=session_id,
                user_id=self.user_id,
                permission_engine=permission_engine,
            )
            # 透传用户自定义钩子（若已注册）
            if getattr(self, "_execution_hooks", None):
                hook_registry.pre_step.extend(self._execution_hooks.pre_step)
                hook_registry.post_step.extend(self._execution_hooks.post_step)
                for ev, transforms in (self._execution_hooks.waterfalls or {}).items():
                    for t in transforms:
                        hook_registry.add_waterfall(ev, t)

            token_count = 0
            try:
                async for event in self._step_runtime.execute(
                    query=query,
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
            except Exception as e:
                # 检查是否是审批中断
                from langgraph.errors import GraphInterrupt
                if isinstance(e, GraphInterrupt):
                    logger.info("[ExecutionOrchestrator] 捕获 GraphInterrupt，转换为 approval_required 事件")
                    # 提取审批请求
                    approvals = self._extract_approvals(e)
                    if approvals:
                        # 产出 approval_required 事件
                        yield {
                            "type": "approval_required",
                            "data": {
                                "pending": approvals,
                                "session_id": session_id,
                            }
                        }
                    return  # 中断执行，等待用户审批
                else:
                    # 其他异常，重新抛出
                    raise
            
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
    
    @staticmethod
    def _extract_approvals(state_or_exc: Any) -> list[dict]:
        """从 GraphInterrupt 异常中提取审批请求"""
        try:
            # GraphInterrupt 的 interrupts 属性包含审批数据
            intr = getattr(state_or_exc, "interrupts", None) or getattr(state_or_exc, "value", None)
            if intr:
                pending = intr.get("pending") or []
                if isinstance(pending, list):
                    return [dict(p) if isinstance(p, dict) else {"tool": str(p)} for p in pending]
        except Exception as e:
            logger.debug("[ExecutionOrchestrator] 提取审批请求失败：%s", e)
        return []
    
    async def resume_after_approval(self, thread_id: str, approval_status: str = "approved") -> Any:
        """
        用户审批后恢复执行（HITL 断点续跑）
        
        Args:
            thread_id: 线程 ID（用于从 checkpointer 恢复）
            approval_status: 审批状态（"approved" 或 "rejected"）
        
        Returns:
            执行结果或审批请求列表
        """
        from langgraph.errors import GraphInterrupt
        
        if not self._step_runtime:
            raise RuntimeError("StepDrivenEngine 未初始化，无法恢复执行")
        
        # 设置审批状态
        approval_state = {
            "approval_status": approval_status,
            "thread_id": thread_id,
        }
        
        try:
            # 从 checkpointer 恢复并继续执行
            async for event in self._step_runtime._graph.astream(
                approval_state,
                config={"configurable": {"thread_id": thread_id}}
            ):
                yield self._step_runtime._transform_event(event, "resume_step", f"resume_{thread_id}")
        except GraphInterrupt as e:
            # 仍有待审批的工具
            logger.info("[ExecutionOrchestrator] 恢复执行时仍有审批请求")
            raise
        except Exception as e:
            logger.error("[ExecutionOrchestrator] 恢复执行失败：%s", e, exc_info=True)
            raise


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
        db: 数据库会话（用于 Orchestrator）
        user_id: 用户 ID
        model_name: 模型名称
    
    Returns:
        ExecutionOrchestrator 实例（包装了 Orchestrator）
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
