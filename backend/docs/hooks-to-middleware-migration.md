# Hooks 到中间件迁移方案

## 现状分析

### 现有 Hooks 系统
```python
# hooks.py
class HookRegistry:
    pre_step: List[Hook]      # async def hook(ctx, step) -> HookResult
    post_step: List[Hook]     # async def hook(ctx, step) -> HookResult
    waterfalls: Dict[str, List[Callable]]  # event 名 → [transform(payload)]

class ExecutionContext:
    session_id: Optional[str]
    user_id: Optional[int]
    step_index: int
    vars: Dict[str, Any]

class Step:
    step_id: str
    type: StepType
    input: Optional[Dict]
    output: Optional[Dict]
    status: StepStatus
```

### DeerFlow 中间件系统
```python
# middleware.py
class AgentMiddleware:
    async def before_agent(self, ctx: RuntimeContext, state: AgentState) -> AgentState
    async def after_agent(self, ctx: RuntimeContext, state: AgentState, response: AIMessage) -> AgentState
    async def wrap_tool_call(self, ctx: RuntimeContext, tool_call: Dict, tool_fn: Callable) -> Any

class RuntimeContext:
    thread_id: str
    user_id: Optional[int]
    sandbox_id: Optional[str]
    thread_data_path: Optional[str]
```

## 核心差异

| 维度 | Hooks 系统 | 中间件系统 |
|------|-----------|-----------|
| **生命周期** | pre_step / post_step | before_agent / after_agent / wrap_tool_call |
| **调用时机** | Step 级别（粗粒度） | Agent/Tool 级别（细粒度） |
| **状态管理** | ExecutionContext + Step | RuntimeContext + AgentState |
| **改写能力** | input/output | state / response / tool_result |
| **中止机制** | AbortStep 异常 | _force_end / _interrupt |

## 迁移策略

### 方案：适配器模式（向后兼容）

**核心思路**：
1. 保留 HookRegistry 作为兼容层
2. 创建 `HooksAdapterMiddleware` 包装旧 Hooks
3. 新代码使用中间件，旧代码继续用 Hooks
4. 最终完全迁移到中间件

### 实现步骤

#### Step 1: 创建 HooksAdapterMiddleware

```python
# runtime/adapters.py
class HooksAdapterMiddleware(AgentMiddleware):
    """将旧 Hooks 系统适配到中间件接口"""
    
    def __init__(self, hook_registry: HookRegistry):
        self.hooks = hook_registry
    
    async def before_agent(self, ctx: RuntimeContext, state: AgentState) -> AgentState:
        """映射 pre_step hook → before_agent"""
        if not self.hooks.pre_step:
            return state
        
        # 构建 Step 对象（兼容旧接口）
        from packages.agent.execution.steps import Step, StepType, StepStatus
        from packages.agent.execution.hooks import ExecutionContext, HookResult, AbortStep
        
        step = Step(
            step_id=f"agent_{ctx.thread_id}",
            type=StepType.MODEL,
            input={"state": state},
            status=StepStatus.PENDING,
        )
        
        exec_ctx = ExecutionContext(
            session_id=ctx.thread_id,
            user_id=ctx.user_id,
        )
        
        # 执行 pre-step hooks
        for hook in self.hooks.pre_step:
            try:
                result = await hook(exec_ctx, step)
                if result is None:
                    continue
                if result.aborted:
                    # 中间件中止机制
                    state["_force_end"] = True
                    state["_end_reason"] = result.reason
                    break
                if result.input:
                    state = result.input.get("state", state)
            except AbortStep as e:
                state["_force_end"] = True
                state["_end_reason"] = e.reason
                break
        
        return state
    
    async def after_agent(self, ctx: RuntimeContext, state: AgentState, response: AIMessage) -> AgentState:
        """映射 post_step hook → after_agent"""
        if not self.hooks.post_step:
            return state
        
        from packages.agent.execution.steps import Step, StepType, StepStatus
        from packages.agent.execution.hooks import ExecutionContext
        
        step = Step(
            step_id=f"agent_{ctx.thread_id}",
            type=StepType.MODEL,
            input={"state": state},
            output={"response": response, "state": state},
            status=StepStatus.COMPLETED,
        )
        
        exec_ctx = ExecutionContext(
            session_id=ctx.thread_id,
            user_id=ctx.user_id,
        )
        
        # 执行 post-step hooks
        for hook in self.hooks.post_step:
            try:
                result = await hook(exec_ctx, step)
                if result and result.output:
                    state = result.output.get("state", state)
            except Exception as e:
                logger.warning("[HooksAdapter] post-step hook 异常：%s", e)
        
        return state
    
    async def wrap_tool_call(self, ctx: RuntimeContext, tool_call: Dict, tool_fn: Callable) -> Any:
        """映射 waterfall hook → wrap_tool_call"""
        if not self.hooks.waterfalls:
            return await tool_fn(tool_call)
        
        # 执行 waterfall transforms
        payload = tool_call
        for transform in self.hooks.waterfalls.get("tools/pre-execute", []):
            try:
                payload = await _invoke(transform, payload)
            except Exception as e:
                logger.warning("[HooksAdapter] waterfall 异常：%s", e)
        
        return await tool_fn(payload)
```

#### Step 2: 修改 RuntimeEngine 集成适配器

```python
# runtime/engine.py
class RuntimeEngine:
    def __init__(
        self,
        middlewares: Optional[List[AgentMiddleware]] = None,
        hook_registry: Optional[HookRegistry] = None,  # 新增
        ...
    ):
        self._chain = MiddlewareChain()
        
        # 1. 添加 Hooks 适配器（向后兼容）
        if hook_registry:
            self._chain.add(HooksAdapterMiddleware(hook_registry))
        
        # 2. 添加新中间件
        for mw in middlewares or []:
            self._chain.add(mw)
```

#### Step 3: 更新 StepDrivenEngineV2

```python
# execution/step_engine_v2.py
class StepDrivenEngineV2:
    def __init__(
        self,
        orchestrator: Any,
        llm: Any,
        tools: List[Any],
        *,
        hooks: Optional[HookRegistry] = None,  # 保留
        middlewares: Optional[List[AgentMiddleware]] = None,  # 新增
        ...
    ):
        # 构建中间件链
        middleware_list = middlewares or []
        
        # 如果有旧 Hooks，添加适配器
        if hooks:
            from runtime.adapters import HooksAdapterMiddleware
            middleware_list.insert(0, HooksAdapterMiddleware(hooks))
        
        # 创建运行时引擎
        self._engine = RuntimeEngine(
            middlewares=middleware_list,
            ...
        )
```

#### Step 4: 迁移指南（文档）

**迁移 Checklist**：
- [ ] 将 `pre_step` hook 改写为 `before_agent` 中间件
- [ ] 将 `post_step` hook 改写为 `after_agent` 中间件
- [ ] 将 `waterfall` 改写为 `wrap_tool_call` 中间件
- [ ] 将 `ExecutionContext` 替换为 `RuntimeContext`
- [ ] 将 `Step` 对象替换为 `AgentState`
- [ ] 将 `AbortStep` 替换为 `state["_force_end"] = True`

**示例：迁移 pre_step hook**

```python
# 旧代码（Hooks）
async def security_check(ctx: ExecutionContext, step: Step) -> HookResult:
    if contains_sensitive_data(step.input):
        raise AbortStep("包含敏感数据")
    return HookResult(input=step.input)

hooks.add_pre_step(security_check)

# 新代码（中间件）
class SecurityMiddleware(AgentMiddleware):
    async def before_agent(self, ctx: RuntimeContext, state: AgentState) -> AgentState:
        if contains_sensitive_data(state["messages"]):
            state["_force_end"] = True
            state["_end_reason"] = "包含敏感数据"
        return state

engine.add_middleware(SecurityMiddleware())
```

## 迁移时间表

| 阶段 | 目标 | 时间 |
|------|------|------|
| **Phase 1** | 创建 HooksAdapterMiddleware | 1 天 |
| **Phase 2** | 集成到 RuntimeEngine | 0.5 天 |
| **Phase 3** | 迁移现有 Hooks 到中间件 | 2-3 天 |
| **Phase 4** | 移除 Hooks 兼容层 | 后续 |

## 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| 旧代码不兼容 | 保留 HookRegistry 作为兼容层 |
| 中间件顺序错误 | 文档明确执行顺序，提供默认链 |
| 状态管理混乱 | 统一使用 RuntimeContext + AgentState |
| 测试覆盖不足 | 为每个中间件编写单元测试 |

## 验收标准

- [ ] 现有 Hooks 代码无需修改即可工作
- [ ] 新中间件可与旧 Hooks 共存
- [ ] 迁移指南清晰易懂
- [ ] 单元测试覆盖适配器
- [ ] 端到端测试通过
