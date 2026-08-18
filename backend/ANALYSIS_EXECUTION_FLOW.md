# Agent 执行入口与 Plan 策略分析

**分析时间**: 2026-08-18  
**分析范围**: 用户任务执行链路与编排策略

---

## 🎯 核心结论

### 问题：一个用户任务只会 Plan 一次吗？

**答案：是的，一个用户请求只会 Plan 一次。**

但需要区分两种场景：

| 场景 | Plan 次数 | 说明 |
|-----|---------|------|
| **单次请求** | 1 次 | 用户发起一次查询 → 编排一次 → 执行完成 |
| **多轮对话** | N 次 | 每轮对话都是独立请求 → 每轮都会重新 Plan |

---

## 📊 执行链路详解

### 完整执行流程

```
用户请求
    ↓
API: POST /execute/stream
    ↓
ExecutionOrchestrator.execute_stream()  [横切层]
    ├── 发布 PRE 事件
    ├── 记录指标
    └── 委托给 OrchestratorRuntime
    ↓
OrchestratorRuntime.run_stream()  [业务层]
    ↓
┌─────────────────────────────────────────────────┐
│  LangGraph Supervisor Graph（状态机）            │
│                                                 │
│  START → plan_node → router → [分支]           │
│                                   ├─ direct → END      │
│                                   └─ dispatch → aggregate → END │
└─────────────────────────────────────────────────┘
    ↓
流式返回给用户
```

---

## 🔍 Plan 节点详解

### 1. Plan 触发时机

**文件**: `packages/agent/orchestrator/supervisor.py:85-112`

```python
async def plan_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """编排节点：每个请求只执行一次"""
    
    # 1. 创建 LLM
    llm = await runtime._create_llm()
    
    # 2. 准备编排消息（包含记忆回灌）
    orchestration_msgs = [
        *([{"role": m.type, "content": m.content} for m in (history or [])]),
        {"role": "user", "content": query},  # 当前查询
    ]
    
    # 3. 调用主 Agent 进行编排决策（只调用一次！）
    plan: OrchestrationPlan = await runtime._orchestrate(
        llm, orchestration_msgs, main_prompt, catalog)
    
    # 4. 发布 orchestrator_plan 事件（只发布一次！）
    sink.put_nowait(ev_plan(
        need_sub_agents=plan.need_sub_agents,
        run_mode=plan.run_mode,
        plan=[t.model_dump() for t in tasks],
    ))
    
    return {"sub_tasks": [t.model_dump() for t in tasks]}
```

**关键点**:
- ✅ `plan_node` 是 LangGraph 状态机的第一个节点
- ✅ 每个请求只执行一次 `runtime._orchestrate()`
- ✅ 只发布一次 `orchestrator_plan` 事件
- ✅ Plan 结果缓存在 `ctx["plan"]` 供后续节点使用

---

### 2. 编排路由策略

**文件**: `packages/agent/orchestrator/supervisor.py:179-180`

```python
async def router(state: Dict[str, Any]) -> str:
    """路由器：根据 Plan 结果决定执行路径"""
    
    # 有子任务 → dispatch_node（派发执行）
    # 无子任务 → direct_node（直接回答）
    return "direct" if not (state.get("sub_tasks") or []) else "dispatch"
```

**执行路径**:
```
Plan
  ↓
Router 判断
  ├─ 无需子 Agent → direct_node → END
  └─ 需要子 Agent → dispatch_node → aggregate_node → END
```

---

### 3. 三种执行模式

#### 模式 A: 直接回答（无需子 Agent）

```
START → plan_node → router → direct_node → END
              ↓
         调用主 LLM
         判断无需子 Agent
         直接回答
```

**代码流程**:
```python
# supervisor.py:114-122
async def direct_node(state):
    if direct_strategy == "quick":
        # 非流式：直接用 plan.direct_answer
        return {"final_answer": ctx["plan"].direct_answer}
    else:
        # 流式：调用 _direct_answer_stream
        async for kind, tok in runtime._direct_answer_stream(...):
            sink.put_nowait(ev_token(content=tok))
```

---

#### 模式 B: 串行派发子 Agent

```
START → plan_node → router → dispatch_node → aggregate_node → END
              ↓              ↓                   ↓
         决定串行模式   依次执行子 Agent1,2,3    聚合结果
```

**代码流程**:
```python
# supervisor.py:153-160
else:  # serial
    for t in sub_tasks:
        sink.put_nowait(ev_sub_agent(sub_agent_id=t.sub_agent_id, status="running"))
        r = await runtime._exec_sub_task(None, t, main_prompt, state=state, history=history)
        results.append(r)
        for ev in _emit_events(t, r):
            sink.put_nowait(ev)
```

---

#### 模式 C: 并行派发子 Agent

```
START → plan_node → router → dispatch_node → aggregate_node → END
              ↓              ↓                   ↓
         决定并行模式   并发执行子 Agent1,2,3    聚合结果
```

**代码流程**:
```python
# supervisor.py:141-152
if mode == "parallel":
    gathered = await asyncio.gather(
        *[runtime._exec_sub_task(None, t, main_prompt, state=state, history=history)
          for t in sub_tasks]
    )
    for t, r in zip(sub_tasks, gathered):
        results.append(r)
        for ev in _emit_events(t, r):
            sink.put_nowait(ev)
```

---

## 📈 Plan 生命周期

### 一次请求的完整 Plan 过程

```
时间线：
T0: 用户发起请求 "帮我分析这份数据并写报告"
    ↓
T1: run_stream() 被调用
    ↓
T2: build_supervisor_graph() 创建编排图
    ↓
T3: 图执行开始
    ├─ plan_node 执行（仅此一次！）
    │   ├─ 调用主 LLM 进行编排
    │   ├─ 输出 Plan: {"need_sub_agents": true, "plan": [...]}
    │   └─ 发布 orchestrator_plan 事件
    ↓
T4: Router 判断有子任务 → 路由到 dispatch_node
    ↓
T5: dispatch_node 执行子 Agent（不再次 Plan！）
    ├─ 子 Agent 1: 数据分析
    ├─ 子 Agent 2: 图表生成
    └─ 子 Agent 3: 报告撰写
    ↓
T6: aggregate_node 聚合结果
    ↓
T7: 返回最终答案
```

**关键**: 子 Agent 执行阶段**不会重新 Plan**，而是按计划执行！

---

## 🔄 何时会重新 Plan？

### 场景 1: 多轮对话（每轮独立 Plan）

```
轮次 1:
  用户："帮我分析数据"
  → Plan 1: 需要数据分析和可视化子 Agent
  → 执行完成

轮次 2:
  用户："再写个总结报告"
  → Plan 2: 需要报告撰写子 Agent（重新 Plan！）
  → 执行完成

轮次 3:
  用户："翻译成英文"
  → Plan 3: 需要翻译子 Agent（重新 Plan！）
  → 执行完成
```

**原因**: 每轮对话都是独立的 HTTP 请求，会重新执行完整的 `run_stream()` 流程。

---

### 场景 2: 子 Agent 执行失败（不自动重试 Plan）

```
用户请求
  ↓
Plan: [子 Agent 1, 子 Agent 2]
  ↓
执行子 Agent 1 → 失败
  ↓
继续执行子 Agent 2（不重新 Plan！）
  ↓
聚合结果（包含失败信息）
```

**当前策略**: 子 Agent 失败不会触发重新 Plan，而是继续执行后续任务。

**优化建议**: 可以引入"Plan 重试"机制，在关键子 Agent 失败时重新编排。

---

### 场景 3: 人工审批后（不重新 Plan）

```
Plan: [子 Agent 1（需要审批）, 子 Agent 2]
  ↓
执行子 Agent 1 → 等待审批
  ↓
用户审批通过
  ↓
继续执行子 Agent 1（不重新 Plan！）
  ↓
执行子 Agent 2
```

**当前策略**: 审批通过后从断点续跑，不重新 Plan。

---

## 📊 Plan 输出格式

### Plan 数据结构

**文件**: `packages/agent/orchestrator/state.py`

```python
class OrchestrationPlan(BaseModel):
    """编排计划"""
    need_sub_agents: bool = False  # 是否需要子 Agent
    run_mode: Literal["serial", "parallel"] = "serial"  # 执行模式
    plan: List[SubTask] = []  # 子任务列表
    direct_answer: Optional[str] = None  # 直接回答（无需子 Agent 时）

class SubTask(BaseModel):
    """子任务"""
    sub_agent_id: str  # 子 Agent ID
    task_prompt: str   # 任务描述
```

### Plan 示例

#### 示例 1: 无需子 Agent

```json
{
  "need_sub_agents": false,
  "run_mode": "serial",
  "plan": [],
  "direct_answer": "这是一个简单的查询，我可以直接回答..."
}
```

#### 示例 2: 需要多个子 Agent（串行）

```json
{
  "need_sub_agents": true,
  "run_mode": "serial",
  "plan": [
    {
      "sub_agent_id": "data_analyst",
      "task_prompt": "分析销售数据，找出关键趋势"
    },
    {
      "sub_agent_id": "chart_generator",
      "task_prompt": "根据分析结果生成可视化图表"
    },
    {
      "sub_agent_id": "report_writer",
      "task_prompt": "撰写完整的分析报告"
    }
  ]
}
```

#### 示例 3: 需要多个子 Agent（并行）

```json
{
  "need_sub_agents": true,
  "run_mode": "parallel",
  "plan": [
    {
      "sub_agent_id": "data_analyst",
      "task_prompt": "分析销售数据"
    },
    {
      "sub_agent_id": "market_researcher",
      "task_prompt": "调研市场趋势"
    },
    {
      "sub_agent_id": "competitor_analyst",
      "task_prompt": "分析竞争对手情况"
    }
  ]
}
```

---

## 🎯 关键设计决策

### 1. 为什么只 Plan 一次？

**优点**:
- ✅ **性能**: 避免重复调用 LLM 进行编排（节省时间和 Token）
- ✅ **一致性**: 保证执行过程按计划进行，不会中途改变策略
- ✅ **可预测**: 用户可以清楚知道整个执行流程
- ✅ **可追溯**: 一次请求对应一个 Plan，便于调试和审计

**缺点**:
- ❌ **灵活性不足**: 子 Agent 失败后无法动态调整策略
- ❌ **容错性差**: Plan 质量问题会影响整个执行过程

---

### 2. 何时考虑多次 Plan？

**可能的优化场景**:

#### 场景 A: 子 Agent 执行失败重试

```python
# 当前：不重试
for t in sub_tasks:
    r = await runtime._exec_sub_task(...)
    results.append(r)  # 即使失败也继续

# 优化：失败时重新 Plan
for t in sub_tasks:
    r = await runtime._exec_sub_task(...)
    if not r.success and is_critical(t):
        # 关键任务失败，重新编排
        new_plan = await runtime._replan(t, r.error)
        r = await runtime._exec_sub_task(new_plan)
    results.append(r)
```

#### 场景 B: 迭代式任务

```python
# 复杂任务可能需要多轮编排
while not task_complete:
    plan = await runtime._orchestrate(...)
    results = await execute_plan(plan)
    if needs_adjustment(results):
        # 根据结果调整下一轮 Plan
        adjust_context(results)
    else:
        break
```

---

## 📝 总结

### Plan 策略总结

| 维度 | 策略 |
|-----|------|
| **单次请求** | 只 Plan 一次（在 plan_node） |
| **多轮对话** | 每轮独立 Plan |
| **子 Agent 失败** | 不重新 Plan，继续执行 |
| **人工审批** | 不重新 Plan，断点续跑 |
| **Plan 缓存** | 缓存在 `ctx["plan"]` 供后续使用 |

### 执行链路关键点

1. **Plan 节点**: `supervisor.py:plan_node` (85-112 行)
2. **编排调用**: `graph.py:_orchestrate` (163-183 行)
3. **事件发布**: `ev_plan()` (仅在 plan_node 发布一次)
4. **路由决策**: `supervisor.py:router` (179-180 行)
5. **执行模式**: serial（串行）或 parallel（并行）

### 优化建议

1. **Plan 质量监控**: 记录 Plan 准确率，优化编排提示词
2. **失败重试机制**: 关键子 Agent 失败时考虑重新 Plan
3. **迭代式编排**: 对复杂任务支持多轮 Plan-Execute 循环
4. **Plan 可视化**: 向用户展示编排计划，增加透明度

---

**结论**: 当前设计采用"一次请求，一次 Plan"策略，简单高效。未来可根据实际需求引入更灵活的编排机制。
