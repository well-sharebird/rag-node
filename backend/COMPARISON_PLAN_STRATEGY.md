# KnowRAG vs DeepSeek Harness 编排策略对比

**分析时间**: 2026-08-18  
**对比维度**: Plan 策略、执行流程、扩展性

---

## 🎯 核心结论

### KnowRAG vs DeepSeek Harness

| 维度 | KnowRAG | DeepSeek Harness |
|-----|---------|------------------|
| **Plan 策略** | 一次请求，一次 Plan | 每步动态决策（Step-by-Step） |
| **编排模式** | 集中式编排（Supervisor Graph） | 分布式编排（Agent Loop） |
| **执行单元** | Plan → 子 Agent 列表 | Turn → Step → Tool Call |
| **灵活性** | 低（按计划执行） | 高（每步可调整） |
| **复杂度** | 低（易于理解） | 高（需要管理状态） |

---

## 📊 KnowRAG 编排策略

### "一次 Plan，执行到底"

```
用户请求
    ↓
┌─────────────────────────────────┐
│ Plan Node（只执行一次）          │
│ 调用主 LLM 进行编排决策          │
│ 输出：Plan = [子 Agent1, 2, 3]  │
└─────────────────────────────────┘
    ↓
Router 判断
    ├─ 无需子 Agent → Direct → END
    └─ 需要子 Agent → Dispatch → Aggregate → END
         ↓
    按计划执行所有子 Agent
    （不重新 Plan）
```

**特点**:
- ✅ 简单高效（只调用一次编排 LLM）
- ✅ 可预测（执行路径清晰）
- ✅ 易于调试（一次请求对应一个 Plan）
- ❌ 灵活性差（子 Agent 失败不调整）
- ❌ 容错性低（Plan 质量影响全局）

---

## 📊 DeepSeek Harness 编排策略

### "每步动态决策"

**文件**: `docs/agent-lifecycle.md`

```
用户请求
    ↓
┌─────────────────────────────────┐
│ Turn Start                       │
│  ├─ Claim Input                  │
│  ├─ Pre-Step Hook（可改写/拒绝） │
│  └─ Assemble Prompt              │
└─────────────────────────────────┘
    ↓
┌─────────────────────────────────┐
│ Step 1: Model Request            │
│  ├─ Agent Request Hook           │
│  ├─ LLM Stream                   │
│  └─ Assistant Message            │
└─────────────────────────────────┘
    ↓
┌─────────────────────────────────┐
│ Tool Calls (0 或多个)            │
│  ├─ Tool Pre-Execute Hook        │
│  ├─ Tool Execute                 │
│  └─ Tool Result                  │
└─────────────────────────────────┘
    ↓
判断：是否需要下一步？
    ├─ 是 → Claim Next Input → Step 2（重新决策！）
    └─ 否 → Turn End
```

**特点**:
- ✅ 灵活性高（每步都可调整策略）
- ✅ 容错性强（失败后可重试/改写）
- ✅ 可扩展（Hook 机制）
- ❌ 复杂度高（需要管理状态）
- ❌ 性能开销（多步决策）

---

## 🔍 关键差异详解

### 1. Plan 触发时机

#### KnowRAG: 一次性 Plan

```python
# supervisor.py:85-112
async def plan_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """编排节点：每个请求只执行一次"""
    
    # 只调用一次 _orchestrate
    plan: OrchestrationPlan = await runtime._orchestrate(
        llm, messages, main_prompt, catalog)
    
    # 发布 orchestrator_plan 事件（只一次）
    sink.put_nowait(ev_plan(...))
    
    return {"sub_tasks": [...]}

# 后续节点直接使用 Plan，不再重新编排
async def dispatch_node(state):
    for task in state["sub_tasks"]:  # 按计划执行
        await runtime._exec_sub_task(task)
```

**优点**: 简单、高效、可预测  
**缺点**: 无法应对执行中的变化

---

#### DeepSeek Harness: 每步决策

```markdown
# docs/agent-lifecycle.md
A **step** is one model request plus the tools it calls.
A **turn** is zero or more steps: it opens before its first input 
is claimed and closes once nothing is owed.

Turn Flow:
  turn/start
    → claim next-step input
    → agent/pre-step (可改写/拒绝)
    → step/start
    → agent/request → LLM → assistant/message
    → tool/call* → tools/execute → tool/result*
    → step/end
    → 判断是否需要下一步？是 → 回到 claim
    → turn/end
```

**优点**: 灵活、容错、可扩展  
**缺点**: 复杂、需要状态管理

---

### 2. 错误处理策略

#### KnowRAG: 继续执行

```python
# supervisor.py:153-160
else:  # serial
    for t in sub_tasks:
        r = await runtime._exec_sub_task(...)
        results.append(r)  # 即使失败也继续
        for ev in _emit_events(t, r):
            sink.put_nowait(ev)
# 不重新 Plan，按计划执行到底
```

**问题**: 关键子 Agent 失败后无法调整策略

---

#### DeepSeek Harness: Hook 拦截

```markdown
# docs/agent-lifecycle.md
Driver->Hooks: agent/pre-step waterfall
Hooks-->>Driver: authoritative reject or enter(messages)

alt proposed step rejected or pre-step failed
  Driver->Driver: claimed batch stays removed, 
                   the open turn spends no step
```

**优势**: 可以在任意 Step 拦截、改写、拒绝

---

### 3. 扩展机制

#### KnowRAG: 事件拦截器

```python
# execution_chain.py
class ExecutionOrchestrator:
    async def execute_stream(self, query, ...):
        # PRE 事件拦截
        await self._publish_event("pre", context)
        
        # 执行
        async for event in self.runtime.run_stream(...):
            yield event
        
        # POST 事件拦截
        await self._publish_event("post", context)
```

**限制**: 只能在执行链路的关键节点拦截

---

#### DeepSeek Harness: 插件化 Hook

```markdown
# docs/architecture.md
New behavior attaches to a documented extension point.

| Goal | Mechanism |
|---|---|
| Intercept a request, tool, or turn | use its `agent/*` or `tools/*` event |
| Add model-facing context | call `agent.inject()` |
| Add a capability | register on `ctx.tools` |
| Add persistent state | extend `SessionEventMap` |
```

**优势**: 插件化架构，任意能力都可替换

---

## 📈 适用场景对比

### KnowRAG 适合

| 场景 | 说明 |
|-----|------|
| **明确的多 Agent 协作** | 任务可预先分解为子 Agent 列表 |
| **批处理任务** | 数据分析、报告生成等 |
| **简单问答** | 无需子 Agent，直接回答 |
| **性能敏感** | 减少 LLM 调用次数 |

**示例**:
```
用户："分析这份销售数据并生成报告"
Plan: [数据分析 Agent → 图表生成 Agent → 报告撰写 Agent]
执行：按计划依次执行 3 个子 Agent
```

---

### DeepSeek Harness 适合

| 场景 | 说明 |
|-----|------|
| **复杂对话** | 需要多轮交互和动态决策 |
| **探索性任务** | 无法预先规划完整路径 |
| **需要人工介入** | 审批、确认等 HITL 场景 |
| **高度可扩展** | 插件化架构，灵活替换能力 |

**示例**:
```
用户："帮我开发一个网站"
Step 1: 需求分析 → 调用需求收集工具
Step 2: 技术方案 → 调用架构设计工具
Step 3: 用户确认 → 等待人工反馈
Step 4: 代码生成 → 调用编码工具
Step 5: 测试 → 调用测试工具
...
每步都动态决策，可根据反馈调整
```

---

## 🎯 设计理念对比

### KnowRAG: "计划驱动执行"

```
Plan First → Execute Plan → Done
    ↓           ↓
  重预测     重效率
```

**哲学**: 好的计划是成功的一半

---

### DeepSeek Harness: "执行即决策"

```
Claim → Decide → Act → Observe → Loop
   ↓       ↓        ↓       ↓
  输入    决策     执行    反馈
```

**哲学**: 决策贯穿执行全程

---

## 💡 优化建议

### KnowRAG 可以借鉴 DeepSeek Harness

#### 1. 引入 Step 概念

```python
# 当前：一次性执行所有子 Agent
for task in plan.plan:
    await execute(task)

# 优化：每步动态决策
while not turn_complete:
    step_decision = await pre_step_hook()
    if step_decision.reject:
        break
    result = await execute_step(step_decision)
    await post_step_hook(result)
```

#### 2. 添加 Pre-Step Hook

```python
# 允许在执行前拦截/改写
async def pre_step(self, step: SubTask) -> StepDecision:
    """Pre-Step Hook（可拒绝/改写）"""
    # 插件可以实现此 Hook
    return StepDecision.approve(step)

# 使用
for task in plan.plan:
    decision = await self.pre_step(task)
    if decision.reject:
        logger.warning("Step 被拒绝：%s", decision.reason)
        continue
    await execute(task)
```

#### 3. 支持动态调整 Plan

```python
# 当前：Plan 固定不变
plan = await orchestrate()
execute_plan(plan)  # 执行到底

# 优化：支持 Plan 调整
plan = await orchestrate()
for task in plan.plan:
    result = await execute(task)
    if result.failed and is_critical(task):
        # 关键任务失败，重新编排
        new_plan = await replan(plan, result)
        plan = new_plan
```

---

### DeepSeek Harness 可以借鉴 KnowRAG

#### 1. 多 Agent 编排优化

```markdown
# 当前：单个 Agent Loop
Agent → Step → Tool → Loop

# 优化：引入多 Agent 编排
Agent (Main) → Plan → [Sub-Agent1, Sub-Agent2, ...] → Aggregate
```

#### 2. 简化执行模式

```markdown
# 对于简单场景，提供"快速路径"
if simple_query:
    return direct_answer()  # 不走完整 Step 循环
```

---

## 📊 总结对比表

| 维度 | KnowRAG | DeepSeek Harness |
|-----|---------|------------------|
| **Plan 次数** | 1 次/请求 | N 次/Turn（每步决策） |
| **执行单元** | Plan（子 Agent 列表） | Step（Model Request + Tools） |
| **灵活性** | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| **性能** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| **可扩展性** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **容错性** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **复杂度** | ⭐⭐（低） | ⭐⭐⭐⭐⭐（高） |
| **学习曲线** | 平缓 | 陡峭 |

---

## 🎯 结论

### KnowRAG 的优势

1. **简单高效** - 一次 Plan，执行到底
2. **易于理解** - 执行路径清晰
3. **性能优秀** - 减少 LLM 调用

### DeepSeek Harness 的优势

1. **灵活性强** - 每步动态决策
2. **可扩展** - 插件化 Hook 机制
3. **容错性好** - 支持拦截/改写/拒绝

### 建议

**KnowRAG 当前阶段**：
- ✅ 保持"一次 Plan"策略（简单高效）
- 📋 考虑添加 Pre-Step Hook（增加灵活性）
- 📋 考虑支持关键任务失败重试（增加容错）

**未来演进**：
- 如果业务需要更复杂的对话场景 → 借鉴 DeepSeek Harness 的 Step 模型
- 如果保持当前场景 → 优化 Plan 质量和执行效率

---

**总结**: 两种策略各有优劣，选择取决于业务场景。KnowRAG 的"一次 Plan"适合明确的多 Agent 协作，DeepSeek Harness 的"每步决策"适合复杂对话场景。
