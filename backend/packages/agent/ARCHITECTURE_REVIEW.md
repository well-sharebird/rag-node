# Orchestrator 与 TAO Graph 架构审查

**审查时间**: 2026-08-18  
**审查焦点**: 这是否是一个标准的 Agent 运行时？

---

## 当前设计分析

### 1. TAO Graph - 单个 Agent 的内部循环

**文件**: `packages/agent/runtime_engine/tao_graph.py`

```python
def build_tao_graph(
    llm: Any,
    tools: List[Any],
    max_iterations: int = 10,
    permission_engine: Optional[Any] = None,
    enable_output_governance: bool = True,
    ...
) -> CompiledStateGraph:
    """
    构建 TAO 循环图
    
    流程:
    1. Think 节点 - LLM 推理生成行动计划
    2. 权限检查节点 (可选)
    3. Act 节点 - ToolNode 执行工具
    4. Observe 节点 - 处理执行结果
    5. 输出治理节点 (可选)
    6. 条件边 - 决定是否继续循环
    """
```

**特点**:
- ✅ **标准 Agent 循环**: Think → Act → Observe
- ✅ **基于 LangGraph**: 使用 StateGraph + 条件边
- ✅ **工具支持**: ToolNode 执行
- ✅ **权限检查**: 工具执行前审批
- ✅ **输出治理**: 最终输出过滤
- ✅ **中间件**: Harness 管控中间件

**结论**: ✅ **TAO Graph 是标准的单 Agent 运行时**

---

### 2. Orchestrator - 多 Agent 编排器

**文件**: `packages/agent/orchestrator/graph.py`

```python
class Orchestrator:
    """主编排器：组合 GraphRuntime，专精主 Agent 编排。"""
    
    def __init__(self, db, model_name, user_id, config):
        self._graph_runtime = GraphRuntime(config)
        self.loader = AgentLoader(db)
        self._graph_builder = AgentGraphBuilder(db, user_id)
    
    async def _orchestrate(self, llm, messages, prompt, catalog):
        """主 Agent 决策：输出 JSON plan"""
    
    async def _exec_sub_task(self, llm, sub_task, prompt, ...):
        """子 Agent 执行：构建 TAO Graph 并执行"""
    
    async def _aggregate_stream(self, llm, results, prompt, ...):
        """结果聚合：生成最终回答"""
```

**特点**:
- ✅ **多 Agent 编排**: 主 Agent 决策 + 子 Agent 执行
- ✅ **任务分解**: JSON plan → 子任务列表
- ✅ **结果聚合**: 多个子 Agent 结果 → 最终回答
- ⚠️ **复用 TAO Graph**: 子 Agent 通过 `build_tao_graph()` 构建

**结论**: ⚠️ **Orchestrator 不是标准 Agent 运行时，而是"编排器"**

---

## 架构对比

### 标准 Agent 运行时架构

```
┌─────────────────────────────────────────┐
│          Agent Runtime                   │
│  ┌─────────────────────────────────┐    │
│  │  Agent Loop (Think-Act-Observe) │    │
│  │                                 │    │
│  │  ┌─────────┐  ┌─────────┐      │    │
│  │  │ Think   │→ │ Act     │      │    │
│  │  │ (LLM)   │  │ (Tools) │      │    │
│  │  └────┬────┘  └────┬────┘      │    │
│  │       │           │            │    │
│  │       └────←──────┘            │    │
│  │           Observe              │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

### 当前 KnowRAG 架构

```
┌─────────────────────────────────────────┐
│         Orchestrator (编排器)            │
│  ┌─────────────────────────────────┐    │
│  │  Main Agent (Think-Act-Observe) │    │
│  │         ↓                        │    │
│  │  Plan Decision (JSON)            │    │
│  │         ↓                        │    │
│  │  ┌──────────┐ ┌──────────┐      │    │
│  │  │ Sub Agent│ │ Sub Agent│      │    │
│  │  │ (TAO)    │ │ (TAO)    │      │    │
│  │  └────┬─────┘ └────┬─────┘      │    │
│  │       │            │             │    │
│  │       └─────←──────┘             │    │
│  │         Aggregate                │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────┐
│      TAO Graph (单 Agent 运行时)          │
│  Think → Act → Observe 循环              │
└─────────────────────────────────────────┘
```

---

## 设计问题识别

### 问题 1: Orchestrator 不是标准 Agent 运行时 ⚠️

**问题描述**:
- `Orchestrator` 本身**不直接执行** Think-Act-Observe 循环
- 它**委托**给 TAO Graph 执行（通过 `_build_agent_graph()`）
- 它的职责是**编排**（主 Agent 决策 → 子 Agent 派发 → 结果聚合）

**影响**:
- ⚠️ **职责不清**: Orchestrator 是"编排器"还是"运行时"？
- ⚠️ **命名混淆**: `OrchestratorRuntime` 暗示它是运行时，但实际是编排器

**建议**:
- ✅ **已重构**: `OrchestratorRuntime` → `Orchestrator`（去掉 Runtime 后缀）
- ✅ **职责清晰**: Orchestrator = 多 Agent 编排器，TAO Graph = 单 Agent 运行时

---

### 问题 2: 两层 Agent 循环 ⚠️

**问题描述**:
```
Layer 1: Orchestrator 的主 Agent 循环
  ↓ (决策)
Layer 2: 子 Agent 的 TAO Graph 循环
```

**Orchestrator 的主 Agent**:
```python
async def _orchestrate(self, llm, messages, prompt, catalog):
    """主 Agent 决策：输出 JSON plan"""
    # 调用 LLM → 解析 JSON plan
```

**子 Agent 的 TAO Graph**:
```python
async def _exec_sub_task(self, llm, sub_task, prompt, ...):
    """子 Agent 执行：构建 TAO Graph 并执行"""
    graph = build_tao_graph(llm, tools, ...)
    result = await graph.ainvoke(...)
```

**影响**:
- ⚠️ **复杂度**: 两层 Agent 循环，理解成本高
- ⚠️ **性能**: 主 Agent 决策 → 子 Agent 执行，额外开销
- ✅ **优势**: 职责分离（决策 vs 执行）

**建议**:
- ✅ **保持现状**: 两层循环是合理的（主从架构）
- ✅ **文档说明**: 清晰说明两层循环的职责

---

### 问题 3: TAO Graph 是标准 Agent 运行时 ✅

**分析**:
- ✅ **Think-Act-Observe 循环**: 标准 Agent 架构
- ✅ **工具支持**: ToolNode 执行
- ✅ **权限检查**: 工具执行前审批
- ✅ **输出治理**: 最终输出过滤
- ✅ **中间件**: Harness 管控中间件
- ✅ **基于 LangGraph**: 使用 StateGraph + 条件边

**结论**: ✅ **TAO Graph 是标准的单 Agent 运行时**

---

## 架构合理性评估

### 设计优势 ✅

1. **职责分离**
   - `Orchestrator` = 多 Agent 编排（决策层）
   - `TAO Graph` = 单 Agent 运行时（执行层）

2. **复用性强**
   - TAO Graph 可独立使用（单 Agent 场景）
   - Orchestrator 复用 TAO Graph（多 Agent 场景）

3. **符合 Harness 架构**
   - Turn/Step 建模（StepDrivenEngine）
   - 决策点（`_drain_send()`）
   - Hooks 系统（`HookRegistry`）
   - Checkpoints（`ExecutionCheckpoint`）

4. **易于扩展**
   - 新增子 Agent 类型（无需修改 Orchestrator）
   - 新增工具类型（无需修改 TAO Graph）

---

### 设计问题 ⚠️

1. **命名混淆**（已修复）
   - ❌ 旧：`OrchestratorRuntime`（暗示是运行时）
   - ✅ 新：`Orchestrator`（编排器）

2. **两层循环复杂度**
   - ⚠️ 理解成本高
   - ✅ 但职责清晰（决策 vs 执行）

3. **Orchestrator 不是标准运行时**
   - ⚠️ 但这是设计意图（编排器 vs 运行时）
   - ✅ 已通过文档澄清

---

## 结论

### 1. TAO Graph 是标准 Agent 运行时 ✅

**评估**: ✅ **完全符合标准 Agent 运行时架构**

**理由**:
- Think-Act-Observe 循环
- 工具执行支持
- 权限检查
- 输出治理
- 中间件支持
- 基于 LangGraph

---

### 2. Orchestrator 不是标准 Agent 运行时 ⚠️

**评估**: ⚠️ **不是运行时，而是"编排器"**

**理由**:
- 职责是多 Agent 编排（非单 Agent 循环）
- 委托给 TAO Graph 执行（非直接执行）
- 决策层 vs 执行层分离

**建议**:
- ✅ **已重构**: 改名 `Orchestrator`（去掉 Runtime 后缀）
- ✅ **文档澄清**: 说明 Orchestrator 是编排器，TAO Graph 是运行时

---

### 3. 整体架构合理性 ✅

**评估**: ✅ **架构合理，职责清晰**

**理由**:
- 两层架构（编排层 + 运行时层）
- 职责分离（决策 vs 执行）
- 符合 Harness 架构
- 易于扩展和维护

**建议**:
- ✅ **保持现状**: 当前设计是合理的
- ✅ **完善文档**: 清晰说明两层架构的职责

---

## 架构图

### 完整架构

```
┌────────────────────────────────────────────────────────────┐
│                    API Layer                                │
│              (/execute/stream)                              │
└────────────────────┬───────────────────────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────────────────────┐
│              ExecutionOrchestrator (装饰器)                  │
│   - 横切关注点：事件/错误/观测/热更新                        │
└────────────────────┬───────────────────────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────────────────────┐
│                StepDrivenEngine (Step 驱动)                  │
│   - Turn/Step 建模                                          │
│   - 决策点 (消费 agent.send)                                │
│   - Hooks/Checkpoints                                      │
└────────────────────┬───────────────────────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────────────────────┐
│                 Orchestrator (编排器) ⚠️ 非运行时             │
│   - 主 Agent 决策 (JSON plan)                               │
│   - 子 Agent 派发                                           │
│   - 结果聚合                                                │
└────────────────────┬───────────────────────────────────────┘
                     │
         ┌───────────┼───────────┐
         │           │           │
         ▼           ▼           ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ TAO Graph   │ │ TAO Graph   │ │ TAO Graph   │
│ (运行时) ✅  │ │ (运行时) ✅  │ │ (运行时) ✅  │
│ Think-Act-  │ │ Think-Act-  │ │ Think-Act-  │
│ Observe     │ │ Observe     │ │ Observe     │
└─────────────┘ └─────────────┘ └─────────────┘
```

---

## 参考文档

- `ARCHITECTURE_ANALYSIS.md`: 架构分析报告
- `REFACTORING_COMPLETE_SUMMARY.md`: 重构完成总结
- `OPTIMIZED_EXECUTION_FLOW.md`: 优化后的执行调用关系
- `HARNESS_5_CORES.md`: Harness 5 大核心子系统映射
