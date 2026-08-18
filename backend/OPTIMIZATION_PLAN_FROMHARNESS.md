# 参考 DeepSeek Harness 的 KnowRAG 优化方案

**分析时间**: 2026-08-18  
**分析基准**: DeepSeek Harness 架构（docs/architecture.md, docs/agent-lifecycle.md, docs/subsystems/*）

---

## 概览

基于对 DeepSeek Harness 架构的深度分析，KnowRAG 需要优化的功能分为 **4 大核心方向、14 个具体功能**：

| 优先级 | 优化方向 | 功能数 |
|-------|---------|--------|
| P0 | 执行模型重构（Step/Agent-Send） | 4 |
| P1 | 钩子系统（Hook/Waterfall） | 4 |
| P1 | 事件溯源（Event Sourcing） | 3 |
| P2 | 生命周期管理（Lifecycle） | 3 |

---

# P0: 执行模型重构

## 1. 引入 Step 概念（替代"一次 Plan 执行到底"）

### 现状问题（KnowRAG）

```python
# supervisor.py:153-160
else:  # serial
    for t in sub_tasks:
        r = await runtime._exec_sub_task(...)  # 按固定计划执行
        results.append(r)
```
- 无法在执行中调整策略
- 子 Agent 失败后只能继续执行
- 无法响应用户的实时反馈

### DeepSeek Harness 参考

```
docs/agent-lifecycle.md
A step is one model request plus the tools it calls.
A turn is zero or more steps: it opens before its first input
is claimed and closes once nothing is owed.
```

### 优化方案

```python
@dataclass
class ExecutionStep:
    """执行步骤：每个子任务或直接回答为一个 Step"""
    step_id: str
    kind: Literal["direct", "sub_agent", "aggregate"]
    sub_task: Optional[SubTask] = None
    status: Literal["pending", "running", "success", "failed"] = "pending"
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Any] = None

class ExecutorState:
    """执行状态机：管理 Turn → Step 生命周期"""
    steps: List[ExecutionStep] = []

    def next_step(self):
        for s in self.steps:
            if s.status == "pending":
                return s
        return None

    def mark_done(self, step_id: str, result: Any):
        ...

    def can_continue(self) -> bool:
        ...
```

**改造后流程**:
```python
async def plan_node(state):
    plan = await runtime._orchestrate(...)
    steps = []
    if plan.need_sub_agents:
        for t in plan.plan:
            steps.append(ExecutionStep(kind="sub_agent", sub_task=t))
        steps.append(ExecutionStep(kind="aggregate"))
    else:
        steps.append(ExecutionStep(kind="direct"))
    return {"steps": steps}

async def dispatch_node(state):
    for step in state["steps"]:
        # 每步执行前可拦截/改写（Hook 支持）
        decision = await pre_step_hook(step)
        if decision.reject:
            continue
        result = await execute_step(step)
        await post_step_hook(step, result)
```

---

## 2. Agent-Send 交互模式（替代"一次性同步执行"）

### 现状问题（KnowRAG）

```python
# ExecutionOrchestrator
async def execute_stream(self, query, ...):
    # 一次性发送，等待结果
    async for event in self.runtime.run_stream(...):
        yield event
```
- 用户发出请求后只能等待
- 无法在执行过程中追加指令
- 无法通知其他系统"正在处理"

### DeepSeek Harness 参考

```typescript
interface Agent {
  send(message, target, wakeup): void
  inject(message): void   // 注入上下文，下个请求生效
  steer(message): void    // 转向新的目标
  followup(message): void // 排队后续消息
}
```

### 优化方案

```python
class AgentHandle:
    """Agent 交互句柄"""
    def __init__(self, runtime, session_id):
        self.runtime = runtime
        self.session_id = session_id
        self._inbox = asyncio.Queue()
        self._running = False

    async def send(self, message: str, wakeup: bool = True):
        """发送消息（唤醒驱动）"""
        if wakeup and not self._running:
            asyncio.create_task(self._process())
        await self._inbox.put(message)

    async def inject(self, content: str):
        """注入上下文（下次请求生效）"""
        await self._load_injected_context(self.session_id, content)

    async def steer(self, message: str):
        """转向新目标：取消当前 Step + 注入转向指令"""
        self._current_step.cancel()
        await self.send(message, wakeup=True)

    async def followup(self, message: str):
        """排队后续消息"""
        await self._inbox.put(message)

    async def _process(self):
        """处理队列（Turn 循环）"""
        while True:
            message = await self._inbox.get()
            try:
                await self._run_turn(message)
            except Exception as e:
                await self._handle_error(e)
```

**API 使用示例**:
```python
agent = AgentHandle(runtime, session_id)

await agent.send("帮我分析数据")       # 用户发消息
await agent.followup("顺便生成图表")    # 用户追加速率
await agent.inject("当前时间：2026-08-18")  # 系统注入上下文
await agent.steer("先不管数据，帮我写个总结") # 用户转向
```

---

## 3. 支持执行中动态调整 Plan（边际调整）

### 现状问题（KnowRAG）

```python
# supervisor.py:95
ctx["plan"] = plan  # 缓存后不再更新
```
- 子 Agent 失败后无法重新编排
- 无法根据中间结果调整后续任务

### DeepSeek Harness 参考

```
docs/subsystems/core.md: async send(...)  随时可发送新输入
docs/agent-lifecycle.md: agent/pre-step waterfall  每步前可改写
```

### 优化方案

```python
class AdaptivePlanner:
    """可调整的编排器"""
    async def initial_plan(self, query, catalog) -> OrchestrationPlan:
        return await runtime._orchestrate(...)

    async def replan(self, current_plan, failed_task, error) -> OrchestrationPlan:
        # 将失败任务 + 错误注入上下文，重新编排
        messages = [
            *current_plan.messages,
            {"role": "system", "content": f"子任务 {failed_task} 失败：{error}"},
            {"role": "user", "content": "请调整计划"},
        ]
        return await runtime._orchestrate(messages, ...)

# supervisor.py 改造
async def dispatch_node(state):
    for task in state["sub_tasks"]:
        r = await runtime._exec_sub_task(...)
        results.append(r)

        if not r.success and is_critical(task):
            # 关键任务失败，重新编排
            new_plan = await planner.replan(state["plan"], task, r.error)
            state = {**state, "plan": new_plan, "sub_tasks": new_plan.plan}
            break  # 重新执行计划
```

---

## 4. Turn/Step 事件流（替代"一次性事件"）

### 现状问题（KnowRAG）

事件一次性产生，缺少 Turn/Step 边界：
```python
{"type": "orchestrator_plan", ...}  # 只发一次
{"type": "sub_agent", ...}          # 每个子 Agent 一次
{"type": "token", ...}              # Token
{"type": "done", ...}               # 结束
```

### DeepSeek Harness 参考

```
docs/subsystems/session.md
turn/start, turn/end, step/start, step/end
user/message, assistant/chunk, assistant/message
tool/call, tool/result
```

### 优化方案

```python
async def execute_with_steps(self, ...):
    # Turn 边界
    yield {"type": "turn/start", "turn": 1}

    for step_id, step in enumerate(self.steps):
        yield {"type": "step/start", "turn": 1, "step": step_id}

        if step.kind == "direct":
            async for event in self._direct_answer(step):
                yield event
        elif step.kind == "sub_agent":
            async for event in self._exec_sub_agent(step):
                yield event

        yield {"type": "step/end", "turn": 1, "step": step_id}

    yield {"type": "turn/end", "turn": 1, "reason": "completed"}
```

**支持断点恢复**: 记录最后一个完成的 Step，失败后可从断点续跑。

---

# P1: 钩子系统（Hook/Waterfall）

## 5. Pre-Step Hook（执行前拦截）

### 现状问题（KnowRAG）

只能在执行前后发布事件，无法改写/拒绝：
```python
# execution_chain.py:227
await event_bus.publish("execution.pre", pre_context)
```

### DeepSeek Harness 参考

```
docs/agent-lifecycle.md: agent/pre-step waterfall
"Listeners may rewrite the claimed messages or reject them outright"
```

### 优化方案

```python
class StepDecision:
    """Step 决策结果"""
    def __init__(self, action, reason=None, modified_step=None):
        self.action = action  # approve/reject
        self.reason = reason
        self.modified_step = modified_step

    @classmethod
    def approve(cls, step=None):
        return cls("approve", modified_step=step)

    @classmethod
    def reject(cls, reason):
        return cls("reject", reason=reason)

class PreStepHookChain:
    """Pre-Step 钩子链（Waterfall 模式）"""
    def register(self, hook):
        self._hooks.append(hook)

    async def run(self, step) -> StepDecision:
        for hook in self._hooks:
            decision = await hook.before_execute(step)
            if decision.action == "reject":
                return decision  # 拒绝执行
            if decision.modified_step:
                step = decision.modified_step  # 改写 Step
        return StepDecision.approve(step)

# 使用示例：权限校验
class PermissionHook:
    async def before_execute(self, step):
        if step.sub_task and step.sub_task.sub_agent_id not in self.allowed:
            return StepDecision.reject(f"无权调用 {step.sub_task.sub_agent_id}")
        return StepDecision.approve(step)
```

---

## 6. Post-Step Hook（执行后处理）

### 优化方案

```python
class PostStepHookChain:
    """Post-Step 钩子链"""
    def register(self, hook):
        ...

    async def run(self, step, result):
        for hook in self._hooks:
            result = await hook.after_execute(step, result)
            # 钩子可以：
            # 1. 修改结果（脱敏/格式化）
            # 2. 记录结果（审计/指标）
            # 3. 决定是否需要中断
        return result

# 使用示例：PII 脱敏
class PIIRedactHook:
    async def after_execute(self, step, result):
        if hasattr(result, "content"):
            result.content = redact_block(result.content)
        return result

# 使用示例：质量检查
class QualityGateHook:
    async def after_execute(self, step, result):
        if result.success and len(result.content) < 10:
            result.success = False
            result.error = "结果过短，可能需要重试"
        return result
```

---

## 7. Request/Response 拦截器（Waterfall 重构）

### 现状问题（KnowRAG）

事件驱动仅发布 PRE/POST，只能观察不能干预。

### DeepSeek Harness 参考

```
docs/architecture.md
agent/request     waterfall (可改写 model request)
tools/pre-execute waterfall (可改写 tool call)
tools/post-execute ordered
```

### 优化方案

```python
class RequestInterceptor:
    """请求拦截器（Waterfall）"""
    async def intercept(self, request_data) -> RequestData:
        for interceptor in self._interceptors:
            decision = await interceptor.before_request(request_data)
            if decision.reject:
                raise RequestRejected(decision.reason)
            if decision.modified:
                request_data = decision.data
        return request_data


class ResponseInterceptor:
    """响应拦截器（Waterfall）"""
    async def intercept(self, response_data) -> ResponseData:
        for interceptor in self._interceptors:
            decision = await interceptor.before_response(response_data)
            if decision.modified:
                response_data = decision.data
        return response_data
```

---

## 8. 插件化钩子注册（替代硬编码拦截）

### 现状问题

```python
# execution_chain.py:硬编码 PRE/POST
await self._publish_event("pre", context)
await self._publish_event("post", context)
await self._publish_event("error", context)
```

### DeepSeek Harness 参考

```
docs/architecture.md: "There is no privileged core to patch:
you extend dsh by mounting a plugin beside the others"
```

### 优化方案

```python
# 插件化注册
class HookRegistry:
    """钩子注册表（插件可动态注册）"""
    def __init__(self):
        self._pre_step_hooks = []
        self._post_step_hooks = []
        self._request_interceptors = []
        self._response_interceptors = []

    def register_pre_step(self, hook):
        self._pre_step_hooks.append(hook)

    # ... 其他注册方法

# 配置化启用/禁用
hooks_config = {
    "pre_step": ["permission", "prompt_rewrite"],
    "post_step": ["pii_redact", "audit"],
    "request": ["auth", "rate_limit"],
    "response": ["format"],
}
```

---

# P1: 事件溯源（Event Sourcing）

## 9. 会话日志（代替"一次性存储"）

### 现状问题（KnowRAG）

```python
# graph.py:246-260
async def _save_conversation(self, user_id, session_id, query, final_output, agent_id=None):
    """一次性保存"""
    await self._conversations.save(...)
```

- 只保存最终结果，丢失过程
- 无法重放/恢复执行过程
- 无法审计每个 Step

### DeepSeek Harness 参考

```
docs/subsystems/session.md
The log is the source of the context the model sees.
deriveMessages() projects model history from it.
```

### 优化方案

```python
# 新增会话日志表
CREATE TABLE session_log (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id INT NOT NULL,
    event_type TEXT NOT NULL,       -- turn/start, step/start, assistant/message, tool/result...
    payload JSONB NOT NULL,          -- 事件数据
    turn INT NOT NULL,
    step INT,
    created_at TIMESTAMP DEFAULT NOW()
);

# Python 实现
class SessionLog:
    """会话事件日志（Event Sourcing）"""
    async def append(self, session_id, event_type, payload, turn, step=None):
        await self._save_event(...)

    async def derive_messages(self, session_id) -> List[Message]:
        """从日志派生模型历史（而非独立存储）"""
        events = await self._load_events(session_id)
        messages = []
        for e in events:
            if e.event_type == "user/message":
                messages.append(HumanMessage(e.payload["content"]))
            elif e.event_type == "assistant/message":
                messages.append(AIMessage(e.payload["content"]))
            elif e.event_type == "tool/result":
                messages.append(ToolMessage(e.payload["content"]))
        return messages
```

**改造后流程**:
```python
# 执行时记录
async def run_stream(self, ...):
    await session_log.append(session_id, "turn/start", {...}, turn=1)
    for step in steps:
        await session_log.append(session_id, "step/start", {...}, turn=1, step=s.step_id)
        result = await execute_step(s)
        await session_log.append(session_id, "assistant/message", {...}, turn=1, step=s.step_id)
    await session_log.append(session_id, "turn/end", {...}, turn=1)

# 恢复时重放
async def resume(self, session_id):
    messages = await session_log.derive_messages(session_id)
    return messages
```

---

## 10. 事件溯源（替代"手动保存状态"）

### 现状问题

```python
# graph.py:600
self._last_orchestrator_state = dict(final_state)  # 手动保存
```

- 状态保存在内存，丢失后无法恢复
- 无法追踪状态变化历史

### DeepSeek Harness 参考

```
docs/subsystems/session.md
The in-memory, event-sourced model.
A Session is an append-only log of typed SessionEvents —
the single source of truth for an agent's whole interaction history.
```

### 优化方案

```python
class EventSourcedState:
    """事件溯源状态管理"""
    def __init__(self, log):
        self._log = log
        self._state = {}

    def apply(self, event_type, payload):
        """应用事件，更新状态"""
        if event_type == "sub_agent_done":
            self._state["sub_agent_results"].append(payload)
        elif event_type == "plan_created":
            self._state["plan"] = payload
        # ...

    async def replay(self, session_id):
        """重放日志重建状态"""
        events = await self._log.load_events(session_id)
        for e in events:
            self.apply(e.event_type, e.payload)
        return self._state
```

---

## 11. 检查点/断点恢复（Checkpoint/Resume）

### 现状问题

```python
# graph.py:359-360
use_checkpointer=bool(sub_security),
checkpointer=self._get_checkpointer() if sub_security else None,
```
- 仅在审批时有 checkpointer
- 普通执行崩溃后无法恢复
- 重启后丢失执行状态

### DeepSeek Harness 参考

```
docs/subsystems/session.md
dsh-session-checkpoint-policy owns the per-request durability checkpoint
resume() loads a persisted session first
```

### 优化方案

```python
class ExecutionCheckpoint:
    """执行检查点"""
    def __init__(self, persist):
        self._persist = persist

    async def save(self, session_id, state, last_step_id):
        """保存检查点"""
        checkpoint = {
            "session_id": session_id,
            "state": state,
            "last_step_id": last_step_id,
            "created_at": datetime.utcnow(),
        }
        await self._persist.save(f"checkpoint:{session_id}", checkpoint)

    async def restore(self, session_id):
        """恢复检查点"""
        return await self._persist.load(f"checkpoint:{session_id}")

    async def resume(self, session_id):
        """从检查点继续执行"""
        cp = await self.restore(session_id)
        if not cp:
            return None  # 没有检查点，从头开始
        
        # 从最后一个 Step 之后继续
        return {
            "state": cp["state"],
            "next_step_id": cp["last_step_id"] + 1,
        }
```

**改造后流程**:
```python
async def run_with_checkpoint(self, query, session_id, ...):
    # 尝试恢复
    resume = await checkpoint.restore(session_id)
    if resume:
        logger.info(f"从检查点恢复：last_step={resume['next_step_id']}")
    
    for step in steps:
        await checkpoint.save(session_id, state, step.step_id)
        result = await execute_step(step)
        # 崩溃后可从这里恢复
```

---

# P2: 生命周期管理

## 12. Agent 状态机（替代"无状态执行"）

### 现状问题

```python
# 无状态：每次执行都是"全新开始"
async def run_stream(self, query, ...):
    state: OrchestratorState = {...}  # 每次创建新状态
```

### DeepSeek Harness 参考

```
docs/subsystems/core.md: agent/status  transitions
AgentStatus: idle → running → idle
```

### 优化方案

```python
from enum import Enum

class AgentStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    FAILED = "failed"
    DISPOSED = "disposed"

class AgentState:
    """Agent 状态机"""
    def __init__(self):
        self.status = AgentStatus.IDLE
        self.current_turn = None
        self.inbox = asyncio.Queue()
        self._turn_id = 0

    @property
    def is_idle(self) -> bool:
        return self.status == AgentStatus.IDLE

    async def start_turn(self):
        """开始一个 Turn"""
        if not self.is_idle:
            raise RuntimeError(f"Agent is {self.status}")
        self.status = AgentStatus.RUNNING
        self.current_turn = self._turn_id
        self._turn_id += 1
        return self.current_turn

    async def end_turn(self, reason):
        """结束 Turn"""
        self.status = AgentStatus.IDLE
        self.current_turn = None

    async def cancel(self, cause):
        """取消当前 Turn"""
        if self.status == AgentStatus.RUNNING:
            self.status = AgentStatus.IDLE
            logger.info(f"Agent cancelled: {cause}")
```

---

## 13. 会话 Fork/Resume（替代"单一会话"）

### 现状问题

```python
# 仅支持串行对话，无法分叉
```
- 无法从一个会话分叉出多个分支
- 无法回到之前的会话状态

### DeepSeek Harness 参考

```
docs/subsystems/session.md: ctx.sessions.fork(source, boundary?, childSessionId?)
```

### 优化方案

```python
class SessionManager:
    """会话管理器"""
    async def fork(self, source_session_id, boundary_step=None, child_session_id=None):
        """从源会话分叉出新会话"""
        # 1. 获取源会话日志（到指定边界为止）
        events = await self._log.load_events(source_session_id, until=boundary_step)
        
        # 2. 创建新会话（继承源会话种子）
        child_id = child_session_id or f"{source_session_id}:fork:{uuid4()}"
        await self._log.append_events(child_id, events)
        
        # 3. 返回新会话
        return child_id

    async def resume(self, session_id):
        """恢复会话"""
        # 从日志重放会话状态
        return await self._log.replay(session_id)

    async def clear(self, session_id, boundary):
        """清除某边界前的历史"""
        ...
```

---

## 14. 并发 Agent 管理（替代"单 Agent 串行"）

### 现状问题

```python
# 当前：一个 session 同一时间只能跑一个请求
async for event in orchestrator.execute_stream(query, session_id):
    yield event
```

### DeepSeek Harness 参考

```
docs/subsystems/core.md
ctx.agents.create() 可创建多个 Agent
每个 Agent 有独立的 inbox/status/session
```

### 优化方案

```python
class AgentRegistry:
    """Agent 注册表"""
    _agents: Dict[str, AgentHandle] = {}

    def create(self, agent_id, config):
        """创建 Agent"""
        if agent_id in self._agents:
            raise ValueError(f"Agent {agent_id} already exists")
        handle = AgentHandle(config)
        self._agents[agent_id] = handle
        return handle

    def get(self, agent_id) -> AgentHandle:
        """获取 Agent"""
        return self._agents.get(agent_id)

    def dispose(self, agent_id):
        """销毁 Agent"""
        handle = self._agents.pop(agent_id)
        handle.dispose()

    async def dispose_all(self):
        """销毁全部 Agent"""
        for agent in self._agents.values():
            agent.dispose()
        self._agents.clear()

# 并发场景
registry = AgentRegistry()
agent1 = registry.create("analysis", config_A)
agent2 = registry.create("report", config_B)

# 可并发执行
await asyncio.gather(
    agent1.send("分析数据"),
    agent2.send("准备报告框架"),
)
```

---

# 优化实施路线图

## 阶段划分

| 阶段 | 内容 | 涉及功能 | 预计工时 |
|-----|------|---------|---------|
| **Phase A** | 执行模型重构 | 1-2 (Step/Agent-Send) | 2天 |
| **Phase B** | 钩子系统 | 5-8 (Hook) | 1.5天 |
| **Phase C** | 事件溯源 | 9-11 (Event Sourcing) | 2天 |
| **Phase D** | 生命周期管理 | 12-14 (Lifecycle) | 1.5天 |

## 依赖关系

```
Phase A (Step 模型)
    ↓
Phase B (Hook 系统) ← 依赖 Step
    ↓
Phase C (Event Sourcing) ← 依赖 Step/Hook
    ↓
Phase D (Lifecycle) ← 依赖前三个阶段
```

## 风险与注意事项

### 兼容性
- 向后兼容：保留现有 run_stream 接口（内部实现改造）
- 渐进迁移：先新增 Step 概念，再接入 Hook

### 性能
- Step 状态管理增加少量内存开销（可接受的）
- 事件日志增加存储（可用批量写入优化）

### 测试
- 为每个新功能添加单元测试
- 使用 Mock 避免依赖外部服务
- 验证与原功能兼容

---

# 总结

## 优化优先级

| 优先级 | 功能 | 收益 |
|-------|------|------|
| P0-1 | 引入 Step 概念 | 支持动态调整、增量执行 |
| P0-2 | Agent-Send 模式 | 支持异步交互、追加指令 |
| P0-3 | 动态调整 Plan | 失败重试、边际调整 |
| P0-4 | Turn/Step 事件流 | 可追踪、可恢复 |
| P1-5 | Pre-Step Hook | 权限拦截、内容改写 |
| P1-6 | Post-Step Hook | 脱敏、质量检查 |
| P1-7 | Waterfall 拦截器 | 可干预请求/响应 |
| P1-8 | 插件化注册 | 动态插拔功能 |
| P1-9 | 会话日志 | 可重放、可审计 |
| P1-10 | 事件溯源 | 状态可恢复 |
| P1-11 | 检查点 | 崩溃恢复 |
| P2-12 | Agent 状态机 | 状态清晰可管理 |
| P2-13 | 会话 Fork | 多分支探索 |
| P2-14 | 并发 Agent | 多任务并行 |

## 建议

1. **优先做 P0**：引入 Step 概念是基础，其他功能都依赖它
2. **渐进实施**：不要一次性改造所有功能，分阶段推进
3. **保持兼容**：现有接口保留，内部实现升级即可
4. **借鉴 Harness**：参考其事件模型和 Hook 机制，但不盲目复制

---

**总结**: 参考 DeepSeek Harness 架构，KnowRAG 最需要优化的是"执行模型"——从"一次 Plan，执行到底"升级为"Step 驱动、动态决策"的模型，同时引入 Hook 系统、事件溯源、生命周期管理等能力。
