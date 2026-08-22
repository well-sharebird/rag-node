# 优化后的执行调用关系梳理

**更新时间**: 2026-08-18  
**重构状态**: ✅ Phase 1-3 完成

---

## 完整调用链（从 API 到 TAO Graph）

```
用户请求 (/execute/stream)
    │
    ▼
┌────────────────────────────────────────────────────────────┐
│ 1. API Layer (packages/agent/api/agents.py)                │
│    - 接收用户请求                                           │
│    - 创建 ExecutionOrchestrator                             │
└────────────────────┬───────────────────────────────────────┘
                     │ create_execution_orchestrator()
                     ▼
┌────────────────────────────────────────────────────────────┐
│ 2. ExecutionOrchestrator (装饰器)                           │
│    packages/agent/integration/execution_chain.py           │
│                                                            │
│    横切关注点：                                             │
│    - 事件总线 (EventBus)                                   │
│    - 服务容器 (ServiceContainer)                           │
│    - 错误处理 (ErrorHandler)                               │
│    - 可观测性 (ObservabilityService)                       │
│    - 热更新 (HotReloadService)                             │
│                                                            │
│    业务运行时：                                             │
│    - _runtime: Orchestrator (主编排器)                     │
│    - _step_runtime: StepExecutor (Step 执行器)             │
└────────────────────┬───────────────────────────────────────┘
                     │ execute_stream()
                     ▼
┌────────────────────────────────────────────────────────────┐
│ 3. StepExecutor (门面)                                      │
│    packages/agent/execution/runner.py                      │
│                                                            │
│    职责：注册/提供                                          │
│    - hooks: HookRegistry (钩子注册中心)                    │
│    - checkpoint: ExecutionCheckpoint (检查点提供)          │
│    - _events: ExecutionEventStream (事件流提供)            │
│    - session_log: SessionLog (会话日志提供)                │
│    - agent: AgentState (Agent 状态)                         │
│                                                            │
│    创建并委托给 StepDrivenEngine                            │
└────────────────────┬───────────────────────────────────────┘
                     │ 创建 StepDrivenEngine
                     │ 注入依赖 (hooks, checkpoint, events)
                     ▼
┌────────────────────────────────────────────────────────────┐
│ 4. StepDrivenEngine (执行引擎核心)                          │
│    packages/agent/execution/step_engine.py                 │
│                                                            │
│    职责：执行/使用                                          │
│    - _rt: Orchestrator (业务构建块提供者)                  │
│    - hooks: HookRegistry (使用者)                          │
│    - signals.checkpoint (使用者)                           │
│    - signals._events (使用者)                              │
│                                                            │
│    Step 驱动主循环：                                        │
│    1. Plan Step → _rt._orchestrate()                       │
│    2. 决策点 → _drain_send() (消费 agent.send)             │
│    3. Direct/Dispatch Step                                 │
│    4. Aggregate Step → _rt._aggregate_stream()             │
└────────────────────┬───────────────────────────────────────┘
                     │ 复用构建块
         ┌───────────┼───────────┬───────────┐
         │           │           │           │
         ▼           ▼           ▼           ▼
┌─────────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│_orchestrate │ │_direct_  │ │_exec_sub │ │_aggregate│
│()           │ │answer()  │ │_task()   │ │_stream() │
└──────┬──────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘
       │             │            │            │
       └─────────────┴────────────┴────────────┘
                     │
                     ▼
┌────────────────────────────────────────────────────────────┐
│ 5. Orchestrator (主编排器)                                  │
│    packages/agent/orchestrator/graph.py                    │
│                                                            │
│    Phase 2 重构：组合 GraphRuntime                          │
│    - _graph_runtime: GraphRuntime (通用图执行)             │
│    - db: AsyncSession                                      │
│    - loader: AgentLoader                                   │
│    - _graph_builder: AgentGraphBuilder                     │
│    - _conversations: ConversationRepository                │
│    - _traces: ExecutionTraceRepository                     │
│                                                            │
│    业务构建块：                                             │
│    - _orchestrate() → 主 Agent 决策 (LLM 输出 JSON plan)    │
│    - _direct_answer_stream() → 直接回答                    │
│    - _exec_sub_task() → 子 Agent 执行                       │
│    - _aggregate_stream() → 结果聚合                        │
└────────────────────┬───────────────────────────────────────┘
                     │ 构建并执行
                     ▼
┌────────────────────────────────────────────────────────────┐
│ 6. TAO Graph (Think/Act/Observe 循环)                       │
│    packages/agent/runtime_engine/tao_graph.py              │
│                                                            │
│    单个 Agent 的内部执行图：                                  │
│    - Think → 思考 (LLM 推理)                                │
│    - Act → 行动 (工具调用)                                  │
│    - Observe → 观察 (工具结果)                              │
│                                                            │
│    编译为 LangGraph CompiledGraph                           │
└────────────────────┬───────────────────────────────────────┘
                     │ graph.ainvoke() / graph.astream()
                     ▼
┌────────────────────────────────────────────────────────────┐
│ 7. GraphRuntime (通用 LangGraph 运行时门面)                  │
│    packages/agent/orchestrator/graph_runtime.py            │
│                                                            │
│    通用图执行原语：                                         │
│    - execute() → 批量执行                                   │
│    - get_state() → 状态快照                                 │
│    - patch_state() → 修补状态                               │
│    - resume() → 恢复中断                                    │
│    - interrupt() → 请求中断                                 │
│                                                            │
│    增强能力：                                               │
│    - 上下文压缩 (Token Budget)                             │
│    - 重试 (RetryPolicy)                                    │
│    - 超时 (Timeout)                                        │
│    - Checkpointer (断点持久化)                             │
└────────────────────────────────────────────────────────────┘
```

---

## 核心类职责对比

### 重构前 vs 重构后

| 类名 | 重构前 | 重构后 | 改进 |
|------|--------|--------|------|
| **OrchestratorRuntime** | 继承 GraphRuntime | 组合 GraphRuntime | ✅ 职责清晰 |
| **StepExecutionRuntime** | 命名混乱 | StepExecutor (门面) | ✅ 命名准确 |
| **StepDrivenEngine** | 职责重叠 | 执行/使用 | ✅ 职责分离 |

---

## 关键设计模式

### 1. 装饰器模式 (Decorator Pattern)

```
ExecutionOrchestrator (装饰器)
    │
    │ 包装
    ↓
Orchestrator (被装饰者)
```

**作用**: 添加横切关注点（事件/错误/观测），不修改业务逻辑

---

### 2. 门面模式 (Facade Pattern)

```
StepExecutor (门面)
    │
    │ 隐藏复杂性
    ↓
StepDrivenEngine (实现)
```

**作用**: 提供简单 API，隐藏 StepDrivenEngine 复杂性

---

### 3. 组合模式 (Composition Pattern)

```
Orchestrator
    │
    │ _graph_runtime 字段
    ↓
GraphRuntime (组合)
```

**作用**: 复用 GraphRuntime 能力，避免继承链过长

---

### 4. 依赖注入 (Dependency Injection)

```python
# StepExecutor 创建并注入依赖
engine = StepDrivenEngine(
    self._orchestrator,
    hooks=self.hooks,           # 注入 HookRegistry
    signals=signals_object,     # 注入 Checkpoint/Event 实例
)
```

**作用**: 解耦依赖，易于测试

---

## 数据流详解

### 用户请求 → 响应完整流程

```
1. 用户请求
   ↓
2. API Layer 接收
   ↓
3. ExecutionOrchestrator.start()
   - 启动事件总线
   - 初始化服务容器
   - 启动错误处理
   - 启动可观测性
   - 启动热更新
   ↓
4. ExecutionOrchestrator.execute_stream()
   - 开始追踪 (Observability)
   - 发布事件 (EventBus)
   ↓
5. StepExecutor.execute_stream()
   - 创建 Turn/Step
   - 发布 turn/start 事件
   - 记录会话日志
   ↓
6. StepDrivenEngine.execute()
   - Plan Step: _rt._orchestrate()
   - 决策点：_drain_send() (消费 agent.send)
   - Direct/Dispatch Step
   - Aggregate Step
   ↓
7. Orchestrator._orchestrate()
   - 调用 LLM (主 Agent 决策)
   - 解析 JSON plan
   ↓
8. Orchestrator._exec_sub_task()
   - 构建 TAO Graph (子 Agent)
   - 执行子任务
   ↓
9. TAO Graph 执行
   - Think → Act → Observe 循环
   - 工具调用
   ↓
10. GraphRuntime.execute()
    - 上下文压缩
    - 重试
    - 超时控制
    ↓
11. 返回结果
    - StepExecutor: 发布 turn/end 事件
    - ExecutionOrchestrator: 结束追踪
    - API Layer: 返回 SSE 流
```

---

## Harness 架构对齐

### 5 大核心子系统映射

| Harness 概念 | KnowRAG 实现 | 位置 |
|-------------|-------------|------|
| **Turn** | `Turn` 类 | `execution/steps.py` |
| **Step** | `Step` 类 | `execution/steps.py` |
| **Decision Point** | `_drain_send()` | `execution/step_engine.py` |
| **Hooks** | `HookRegistry` | `execution/hooks.py` |
| **Checkpoints** | `ExecutionCheckpoint` | `execution/sourcing.py` |
| **Event Stream** | `ExecutionEventStream` | `execution/events.py` |
| **Agent Send** | `agent.send()` → `_drain_send()` | `execution/runner.py` / `step_engine.py` |

### 2 大基础保障映射

| Harness 保障 | KnowRAG 实现 | 位置 |
|-------------|-------------|------|
| **安全层** | `SecurityPolicy` / `PermissionEngine` | `core/harness/security/` |
| **可观测性** | `ObservabilityService` | `observability/` |

---

## 关键改进点

### 1. 命名清晰 ✅

```python
# ❌ 改进前
OrchestratorRuntime  # 是 Runtime 还是 Orchestrator？
StepExecutionRuntime # 是 Runtime 还是门面？

# ✅ 改进后
Orchestrator  # 主编排器
StepExecutor  # Step 执行器
```

### 2. 组合优于继承 ✅

```python
# ❌ 改进前 (继承)
class OrchestratorRuntime(GraphRuntime):
    def __init__(self, ...):
        super().__init__(config)

# ✅ 改进后 (组合)
class OrchestratorRuntime:
    def __init__(self, ...):
        self._graph_runtime = GraphRuntime(config)
```

### 3. 职责分离 ✅

```python
# StepExecutor: 门面 (注册/提供)
class StepExecutor:
    def __init__(self, ...):
        self.hooks = HookRegistry()              # 注册中心
        self.checkpoint = ExecutionCheckpoint()  # 实例提供
        self._events = ExecutionEventStream()    # 实例提供

# StepDrivenEngine: 引擎 (执行/使用)
class StepDrivenEngine:
    def __init__(self, hooks, signals, ...):
        self.hooks = hooks              # 使用者
        self.signals = signals          # 使用者
```

---

## 测试验证点

### 单元测试

```python
# 1. 测试 Orchestrator 组合 GraphRuntime
def test_orchestrator_composition():
    orchestrator = Orchestrator(db, model_name, user_id)
    assert hasattr(orchestrator, '_graph_runtime')
    assert isinstance(orchestrator._graph_runtime, GraphRuntime)

# 2. 测试 StepExecutor 门面
def test_step_executor_facade():
    executor = StepExecutor(orchestrator, session_id, user_id, agent_id)
    assert hasattr(executor, 'hooks')
    assert hasattr(executor, 'checkpoint')
    assert hasattr(executor, '_events')

# 3. 测试 StepDrivenEngine 执行
def test_step_driven_engine():
    engine = StepDrivenEngine(orchestrator, hooks, signals)
    assert hasattr(engine, '_rt')
    assert hasattr(engine, 'hooks')
    assert hasattr(engine, 'signals')
```

### 集成测试

```python
# 测试完整调用链
async def test_full_execution_chain():
    orchestrator = create_execution_orchestrator(db, user_id, model_name)
    await orchestrator.start()
    
    events = []
    async for event in orchestrator.execute_stream(query="测试请求"):
        events.append(event)
    
    assert len(events) > 0
    assert any(e['type'] == 'turn/start' for e in events)
    assert any(e['type'] == 'turn/end' for e in events)
```

---

## 性能优化建议

### 1. 延迟初始化

```python
# ExecutionOrchestrator 已实现
def _init_business_runtime(self):
    """延迟创建 Orchestrator，避免循环依赖"""
    self._runtime = None

@property
def runtime(self):
    """延迟创建 Orchestrator"""
    if self._runtime is None:
        self._runtime = Orchestrator(...)
    return self._runtime
```

### 2. 连接池

```python
# GraphRuntime 已实现
def _get_checkpointer(self):
    """惰性初始化 checkpointer"""
    if self._checkpointer is None:
        self._checkpointer = create_async_checkpointer()
    return self._checkpointer
```

### 3. 事件批处理

```python
# ExecutionEventStream 可实现
def publish_batch(self, events: List[ExecutionEvent]):
    """批量发布事件，减少 I/O"""
    for event in events:
        self._queue.put(event)
    # 批量刷新
    self._flush_batch()
```

---

## 参考文档

- `ARCHITECTURE_ANALYSIS.md`: 架构分析报告
- `REFACTORING_COMPLETE_SUMMARY.md`: 重构完成总结
- `HARNESS_5_CORES.md`: Harness 5 大核心子系统映射
