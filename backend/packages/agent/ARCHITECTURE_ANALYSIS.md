# Runtime 架构分析报告

## 四类核心组件关系梳理

### 1. GraphRuntime - 通用 LangGraph 运行时门面（基类）

**文件**: `orchestrator/graph_runtime.py`

**职责**: 提供通用图执行原语，与具体业务无关

```python
class GraphRuntime:
    """通用图执行原语：上下文压缩 + checkpointer + 重试 + 硬超时 + 状态/中断"""
    
    def execute(self, graph, state, thread_id, ...)      # 批量执行
    def get_state(self, graph, thread_id)                # 状态快照
    def patch_state(self, graph, thread_id, values)      # 修补状态
    def resume(self, graph, thread_id, values, ...)      # 恢复中断
    def interrupt(self, thread_id, run_id)               # 请求中断
```

**特点**:
- ✅ 通用门面，可复用于任意图
- ✅ 封装 LangGraph 底层 API（ainvoke/aget_state/aupdate_state）
- ✅ 增强能力：上下文压缩、重试、超时、断点恢复

---

### 2. OrchestratorRuntime - 主编排运行时（继承 GraphRuntime）

**文件**: `orchestrator/graph.py`

**职责**: 主编排业务逻辑（主 Agent 决策、子 Agent 派发、结果聚合）

```python
class OrchestratorRuntime(GraphRuntime):
    """主从编排运行时：继承通用图运行时门面，专精主 Agent 编排"""
    
    async def _orchestrate(self, llm, messages, prompt, catalog) -> OrchestrationPlan
    async def _direct_answer_stream(self, query, prompt, ...)
    async def _exec_sub_task(self, llm, sub_task, prompt, ...)
    async def _aggregate_stream(self, llm, results, prompt, ...)
    async def run_stream(self, query, ...)  # 流式执行入口
```

**特点**:
- ✅ 继承 GraphRuntime，获得通用图执行能力
- ✅ 专精主编排：主 Agent 决策、子 Agent 派发、结果聚合
- ✅ 提供构建块：_orchestrate/_direct_answer_stream/_exec_sub_task/_aggregate_stream
- ⚠️ 旧实现：固定流水线（plan→router→direct|dispatch→aggregate）

---

### 3. StepExecutionRuntime - Step 执行门面（独立类，组合模式）

**文件**: `execution/runner.py`

**职责**: Step 执行门面，内部委托给 StepDrivenEngine

```python
class StepExecutionRuntime:
    """Step 执行门面。内部委托给 StepDrivenEngine 执行"""
    
    def __init__(self, orchestrator, session_id, user_id, agent_id):
        self._orchestrator = orchestrator  # OrchestratorRuntime 实例
        self.hooks = HookRegistry()
        self.session_log = SessionLog(store)
        self.checkpoint = ExecutionCheckpoint(store)
        self._events = ExecutionEventStream()
    
    async def execute_stream(self, query, **kwargs):
        # 创建 StepDrivenEngine 并执行
        engine = StepDrivenEngine(
            self._orchestrator,
            hooks=self.hooks,
            signals=...,
        )
        async for ev in engine.execute(query, ...):
            yield ev
```

**特点**:
- ❌ 不继承 GraphRuntime，独立类
- ✅ 组合 OrchestratorRuntime（通过 `_orchestrator` 字段）
- ✅ Step 建模：Turn/Step 生命周期、钩子、检查点、事件溯源
- ✅ 委托执行：内部创建 StepDrivenEngine 并调用

---

### 4. StepDrivenEngine - Step 驱动引擎（独立类，组合模式）

**文件**: `execution/step_engine.py`

**职责**: Step 驱动的编排执行引擎（控制流程核心）

```python
class StepDrivenEngine:
    """Step 驱动的编排执行引擎"""
    
    def __init__(self, runtime, hooks, signals, session_id, user_id):
        self._rt = runtime  # OrchestratorRuntime 实例
        self.hooks = hooks
        self.signals = signals
        self.ctx: ExecutionContext
        self.turn: Turn
    
    async def execute(self, query, ...):
        # Step 驱动主循环
        # 1. Plan Step
        plan = await self._rt._orchestrate(...)
        
        # 2. 决策点
        injections = self._drain_send()
        
        # 3. 动态决策
        if not (need_sub_agents and has_tasks):
            async for tok in self._rt._direct_answer_stream(...):
                yield tok
        else:
            for task in plan:
                await self._rt._exec_sub_task(...)
            async for tok in self._rt._aggregate_stream(...):
                yield tok
```

**特点**:
- ❌ 不继承 GraphRuntime，独立类
- ✅ 组合 OrchestratorRuntime（通过 `_rt` 字段）
- ✅ 控制流程：决定何时调用哪个构建块
- ✅ 对齐 Harness：Turn/Step/Decision/Hooks/Checkpoints

---

## 完整调用关系图

```
用户请求 (/execute/stream)
       │
       ▼
┌─────────────────────────────────────┐
│ ExecutionOrchestrator (装饰器)       │
│ - 横切关注点：事件/错误/观测/服务    │
│ - runtime: OrchestratorRuntime       │
│ - _step_runtime: StepExecutionRuntime│
└────────────────┬────────────────────┘
                 │ execute_stream()
                 ▼
┌─────────────────────────────────────┐
│ StepExecutionRuntime (门面)          │
│ - _orchestrator: OrchestratorRuntime │
│ - hooks: HookRegistry                │
│ - session_log: SessionLog            │
│ - checkpoint: ExecutionCheckpoint    │
└────────────────┬────────────────────┘
                 │ 创建并调用
                 ▼
┌─────────────────────────────────────┐
│ StepDrivenEngine (执行引擎核心)      │
│ - _rt: OrchestratorRuntime           │
│ - hooks: HookRegistry                │
│ - signals: (checkpoint/session_log/ │
│            agent/inbox)              │
└────────────────┬────────────────────┘
                 │ 复用构建块
    ┌────────────┼────────────┐
    │            │            │
    ▼            ▼            ▼
┌─────────┐ ┌──────────┐ ┌──────────┐
│_orchestr│ │_direct_  │ │_exec_sub │
│ate()    │ │answer()  │ │_task()   │
│_aggrega │ │_stream() │ │_aggregate│
│te()     │ │          │ │()        │
└────┬────┘ └────┬─────┘ └────┬─────┘
     │           │            │
     └───────────┼────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│ OrchestratorRuntime (业务构建块)     │
│ - 继承 GraphRuntime (通用门面)       │
│ - _graph_builder: AgentGraphBuilder  │
│ - loader: AgentLoader                │
└────────────────┬────────────────────┘
                 │ 构建并执行
                 ▼
┌─────────────────────────────────────┐
│ TAO Graph (Think/Act/Observe 循环)   │
│ - build_tao_graph() → CompiledGraph │
│ - graph.ainvoke() / graph.astream() │
└─────────────────────────────────────┘
```

---

## 架构问题分析

### 问题 1: 命名混淆

| 类名 | 实际职责 | 问题 |
|------|---------|------|
| `GraphRuntime` | 通用 LangGraph 门面 | ✅ 名称准确 |
| `OrchestratorRuntime` | 主编排业务逻辑 | ⚠️ 名为 Runtime，实为**业务编排器** |
| `StepExecutionRuntime` | Step 执行门面 | ⚠️ 名为 Runtime，实为**装饰器/门面** |
| `StepDrivenEngine` | Step 驱动引擎 | ✅ 名称准确（Engine） |

**建议**:
- `OrchestratorRuntime` → `Orchestrator` 或 `AgentOrchestrator`
- `StepExecutionRuntime` → `StepExecutionFacade` 或 `StepExecutor`

---

### 问题 2: 继承 vs 组合混用

```python
# GraphRuntime 是基类
class GraphRuntime: ...

# OrchestratorRuntime 继承 GraphRuntime
class OrchestratorRuntime(GraphRuntime): ...

# StepExecutionRuntime 不继承，而是组合
class StepExecutionRuntime:
    def __init__(self, orchestrator, ...):
        self._orchestrator = orchestrator  # 组合 OrchestratorRuntime

# StepDrivenEngine 也不继承，也是组合
class StepDrivenEngine:
    def __init__(self, runtime, ...):
        self._rt = runtime  # 组合 OrchestratorRuntime
```

**问题**:
- ❌ `StepExecutionRuntime` 和 `StepDrivenEngine` 都不继承 `GraphRuntime`
- ❌ 但都依赖 `OrchestratorRuntime`（通过组合）
- ❌ 导致调用链：`StepExecutionRuntime` → `StepDrivenEngine` → `OrchestratorRuntime` → `GraphRuntime`

**建议**:
- 明确分层：`GraphRuntime`（底层）→ `Orchestrator`（中层）→ `StepDrivenEngine`（上层）
- 或者统一接口：所有 Runtime 实现统一 `execute()` / `execute_stream()` 方法

---

### 问题 3: 职责重叠

| 职责 | GraphRuntime | OrchestratorRuntime | StepExecutionRuntime | StepDrivenEngine |
|------|-------------|---------------------|---------------------|------------------|
| 图执行 | ✅ `execute()` | ✅ 继承 | ❌ | ❌ |
| 主编排 | ❌ | ✅ `_orchestrate()` | ❌ | ❌ |
| Step 驱动 | ❌ | ❌ | ✅ 门面 | ✅ 核心 |
| Hooks | ❌ | ❌ | ✅ 注册 | ✅ 执行 |
| Checkpoints | ✅ 惰性 | ✅ 继承 | ✅ 保存 | ✅ 保存/恢复 |
| 事件流 | ❌ | ❌ | ✅ 发布 | ✅ 发布 |

**问题**:
- ⚠️ `StepExecutionRuntime` 和 `StepDrivenEngine` 职责有重叠（都处理 Hooks、Checkpoints、事件）
- ⚠️ `OrchestratorRuntime` 既有通用图执行（继承），又有主编排业务

**建议**:
- 明确 `StepExecutionRuntime` 仅作为门面（转发 + Turn 建模）
- `StepDrivenEngine` 专注执行逻辑（Hooks、Checkpoints、决策）

---

## 架构演进路径

### Phase 1: 固定流水线（旧架构）

```
用户请求 → ExecutionOrchestrator → OrchestratorRuntime.run_stream()
                                       │
                                       ▼
                              build_supervisor_graph()
                                       │
                                       ▼
                              固定图执行：
                              plan → router → direct|dispatch → aggregate
```

**问题**:
- ❌ 无 Step/Turn 建模
- ❌ 无决策点（无法干预）
- ❌ 无 Hooks 系统
- ❌ 无 Checkpoints（无法恢复）
- ❌ 不符合 Harness 架构

---

### Phase 2: Step 驱动（当前架构）

```
用户请求 → ExecutionOrchestrator → StepExecutionRuntime.execute_stream()
                                       │
                                       ▼
                                  StepDrivenEngine.execute()
                                       │
                                       ▼
                                  Step 驱动主循环：
                                  1. Plan Step → _orchestrate()
                                  2. 决策点 → drain_send()
                                  3. Direct/Dispatch Step → _direct_answer_stream() / _exec_sub_task()
                                  4. Aggregate Step → _aggregate_stream()
                                       │
                                       ▼
                                  OrchestratorRuntime (提供构建块)
                                       │
                                       ▼
                                  TAO Graph (Think/Act/Observe)
```

**优势**:
- ✅ Step/Turn 建模
- ✅ 决策点（可干预、可注入）
- ✅ Hooks 系统（pre-step/post-step）
- ✅ Checkpoints（可恢复）
- ✅ 符合 Harness 架构

---

## 重构建议

### 方案 1: 统一接口（推荐）

```python
# 定义统一接口
class ExecutionEngine(Protocol):
    async def execute_stream(self, query, ...) -> AsyncGenerator

# StepDrivenEngine 实现接口
class StepDrivenEngine(ExecutionEngine): ...

# Orchestrator 改名并实现接口
class Orchestrator(ExecutionEngine):  # 去掉 Runtime
    def __init__(self, db, ...):
        self._graph_runtime = GraphRuntime(...)
    
    async def execute_stream(self, query, ...):
        # 旧 run_stream() 逻辑
```

**优势**:
- ✅ 统一接口，易于替换
- ✅ 职责清晰（Engine vs Orchestrator）
- ✅ 符合依赖倒置原则

---

### 方案 2: 明确分层

```python
# Layer 1: Graph 执行
class GraphRuntime: ...  # 保持不变

# Layer 2: 编排业务
class Orchestrator:  # 改名，去掉 Runtime
    def __init__(self, db, ...):
        self._graph_runtime = GraphRuntime(...)
    
    # 提供构建块
    async def _orchestrate(...)
    async def _direct_answer_stream(...)
    async def _exec_sub_task(...)
    async def _aggregate_stream(...)

# Layer 3: Step 驱动
class StepExecutor:  # 改名
    def __init__(self, orchestrator: Orchestrator, ...):
        self._orchestrator = orchestrator
    
    async def execute_stream(self, query, ...):
        engine = StepDrivenEngine(self._orchestrator, ...)
        async for ev in engine.execute(query, ...):
            yield ev

# 移除 StepExecutionRuntime（职责合并到 StepExecutor）
```

**优势**:
- ✅ 层次清晰（Graph → Orchestrator → StepExecutor）
- ✅ 职责单一
- ✅ 易于测试和维护

---

## 总结

### 当前架构问题

1. **命名混乱**: 多个 "Runtime"，但职责不同
2. **继承混组合**: 有的继承，有的组合，层次不清晰
3. **职责重叠**: `StepExecutionRuntime` vs `StepDrivenEngine`

### 当前架构优势

1. ✅ **Step 驱动**: 符合 Harness 架构（Turn/Step/Decision/Hooks/Checkpoints）
2. ✅ **横切关注点分离**: ExecutionOrchestrator 处理事件/错误/观测
3. ✅ **业务逻辑复用**: 复用 OrchestratorRuntime 构建块，无需重写
4. ✅ **可测试性**: 各组件独立，易于单元测试

### 下一步行动

1. **短期**: 保持当前架构，完善文档和测试
2. **中期**: 考虑重命名（OrchestratorRuntime → Orchestrator）
3. **长期**: 考虑统一接口或明确分层重构

---

## 附录：关键代码位置

| 组件 | 文件 | 关键行 |
|------|------|--------|
| GraphRuntime | `orchestrator/graph_runtime.py` | 20-155 |
| OrchestratorRuntime | `orchestrator/graph.py` | 69-400+ |
| StepExecutionRuntime | `execution/runner.py` | 34-134 |
| StepDrivenEngine | `execution/step_engine.py` | 42-313 |
| ExecutionOrchestrator | `integration/execution_chain.py` | 64-420+ |
