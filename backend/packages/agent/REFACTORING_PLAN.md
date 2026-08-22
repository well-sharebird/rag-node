# Runtime 架构重构计划

**问题识别**: `ARCHITECTURE_ANALYSIS.md` 中识别的 3 个核心问题确实存在，需要重构。

---

## 问题 1: 命名混乱 ⚠️

### 问题描述

| 类名 | 实际职责 | 问题 |
|------|---------|------|
| `OrchestratorRuntime` | 主编排业务逻辑 | ⚠️ 名为 Runtime，实为**业务编排器** |
| `StepExecutionRuntime` | Step 执行门面 | ⚠️ 名为 Runtime，实为**门面** |

### 影响

- ❌ **理解成本高**: 新开发者需要理解"为什么叫 Runtime 但不是运行时"
- ❌ **语义混乱**: Runtime 通常指"运行时环境"，但这里指"业务逻辑"
- ❌ **搜索困难**: 搜索"Runtime"会找到多个不相关的类

### 重构方案

```python
# 方案 A: 渐进式重命名（推荐）
# 步骤 1: 创建新类，继承旧类（别名模式）
class Orchestrator(OrchestratorRuntime):
    """主编排器（向后兼容别名）"""
    pass

class StepExecutor(StepExecutionRuntime):
    """Step 执行器（向后兼容别名）"""
    pass

# 步骤 2: 更新新代码使用新名称
# 步骤 3: 旧类标记为 @deprecated
# 步骤 4: 下个版本移除旧类

# 方案 B: 一次性重命名（破坏性）
# 直接重命名类，更新所有 43 处引用
```

### 建议

✅ **采用方案 A（渐进式）**

**理由**:
- ✅ 向后兼容
- ✅ 风险低
- ✅ 可逐步迁移

---

## 问题 2: 继承 vs 组合混用 ⚠️

### 问题描述

```python
# GraphRuntime 是基类
class GraphRuntime: ...

# OrchestratorRuntime 继承 GraphRuntime
class OrchestratorRuntime(GraphRuntime): ...

# StepExecutionRuntime 不继承，而是组合
class StepExecutionRuntime:
    def __init__(self, orchestrator, ...):
        self._orchestrator = orchestrator

# StepDrivenEngine 也不继承，也是组合
class StepDrivenEngine:
    def __init__(self, runtime, ...):
        self._rt = runtime
```

### 影响

- ❌ **层次不清晰**: 不知道应该继承还是组合
- ❌ **一致性差**: 有的继承，有的组合，没有统一原则
- ❌ **扩展困难**: 新开发者不知道遵循哪个模式

### 重构方案

```python
# 方案 A: 统一为组合（推荐）
# 所有类都组合 GraphRuntime，不继承

class Orchestrator:
    def __init__(self, db, ...):
        self._graph_runtime = GraphRuntime(...)  # 组合
    
    async def _orchestrate(self, ...):
        # 业务逻辑

class StepExecutor:
    def __init__(self, orchestrator: Orchestrator, ...):
        self._orchestrator = orchestrator  # 组合

class StepDrivenEngine:
    def __init__(self, orchestrator: Orchestrator, ...):
        self._orchestrator = orchestrator  # 组合

# 方案 B: 统一为继承
# 所有类都继承 GraphRuntime（不推荐，会导致继承链过长）
```

### 建议

✅ **采用方案 A（统一组合）**

**理由**:
- ✅ 组合优于继承
- ✅ 职责清晰（每个类只做一件事）
- ✅ 易于测试（可以 Mock GraphRuntime）
- ✅ 符合当前趋势（StepExecutionRuntime 已经是组合）

---

## 问题 3: 职责重叠 ⚠️

### 问题描述

| 职责 | StepExecutionRuntime | StepDrivenEngine | 问题 |
|------|---------------------|------------------|------|
| Hooks | ✅ 注册 | ✅ 执行 | ⚠️ 重叠 |
| Checkpoints | ✅ 保存 | ✅ 保存/恢复 | ⚠️ 重叠 |
| 事件流 | ✅ 发布 | ✅ 发布 | ⚠️ 重叠 |

### 影响

- ❌ **职责不清**: 不知道应该在哪个类添加新功能
- ❌ **代码重复**: 两个类都有类似的 Hook/Checkpoint/Event 代码
- ❌ **维护困难**: 修改一个地方，可能需要修改另一个地方

### 重构方案

```python
# 方案 A: 明确职责分离（推荐）
# StepExecutionRuntime: 仅门面（注册/提供）
# StepDrivenEngine: 仅执行（使用）

class StepExecutor:
    """Step 执行门面（仅注册/提供）"""
    
    def __init__(self, orchestrator: Orchestrator, ...):
        self.hooks = HookRegistry()  # ✅ 注册中心
        self.store = MemoryStore()
        self.checkpoint = ExecutionCheckpoint(self.store)  # ✅ 实例提供者
        self._events = ExecutionEventStream()  # ✅ 实例提供者
    
    async def execute_stream(self, query, ...):
        # 创建引擎并执行
        engine = StepDrivenEngine(
            self._orchestrator,
            hooks=self.hooks,  # 传入注册中心
            checkpoint=self.checkpoint,  # 传入实例
            events=self._events,  # 传入实例
        )
        async for ev in engine.execute(query, ...):
            yield ev

class StepDrivenEngine:
    """Step 驱动引擎（仅执行/使用）"""
    
    def __init__(self, orchestrator, hooks, checkpoint, events, ...):
        self._orchestrator = orchestrator
        self.hooks = hooks  # ✅ 使用者
        self.checkpoint = checkpoint  # ✅ 使用者
        self.events = events  # ✅ 使用者
    
    async def execute(self, query, ...):
        # 执行 Hook
        await self.hooks.pre_step.run(step)
        
        # 保存 Checkpoint
        await self.checkpoint.save(...)
        
        # 发布 Event
        self.events.publish(...)

# 方案 B: 合并为一个类（不推荐，会导致类过大）
```

### 建议

✅ **采用方案 A（明确职责分离）**

**理由**:
- ✅ 职责单一
- ✅ 易于理解
- ✅ 易于测试
- ✅ 符合当前设计（已经是这样，只是需要文档澄清）

---

## 重构计划

### Phase 1: 重命名（1-2 天）

**目标**: 解决命名混乱

**步骤**:
1. ✅ 创建别名类（`Orchestrator`, `StepExecutor`）
2. ✅ 更新新代码使用新名称
3. ✅ 旧类标记为 `@deprecated`
4. ✅ 更新文档

**文件**:
- `packages/agent/orchestrator/graph.py`
- `packages/agent/execution/runner.py`
- `packages/agent/integration/execution_chain.py`

---

### Phase 2: 统一组合（2-3 天）

**目标**: 解决继承 vs 组合混用

**步骤**:
1. ✅ `Orchestrator` 改为组合 `GraphRuntime`
2. ✅ 更新所有引用
3. ✅ 测试验证

**文件**:
- `packages/agent/orchestrator/graph.py`
- `packages/agent/orchestrator/graph_runtime.py`

---

### Phase 3: 职责分离（1-2 天）

**目标**: 解决职责重叠

**步骤**:
1. ✅ 明确 `StepExecutor` 职责（注册/提供）
2. ✅ 明确 `StepDrivenEngine` 职责（执行/使用）
3. ✅ 移除重复代码
4. ✅ 测试验证

**文件**:
- `packages/agent/execution/runner.py`
- `packages/agent/execution/step_engine.py`

---

## 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 破坏现有代码 | 中 | 高 | 使用别名模式，向后兼容 |
| 测试失败 | 高 | 中 | 已有 8/8 测试，重构后重新运行 |
| 文档不同步 | 中 | 低 | 更新文档，添加迁移指南 |

---

## 决策

### 需要重构吗？

**答案**: ✅ **需要，但可以渐进式**

**理由**:
1. ✅ 问题确实存在（不是理解混乱）
2. ✅ 重构收益 > 成本
3. ✅ 可以渐进式（降低风险）

### 优先级

| 问题 | 优先级 | 理由 |
|------|--------|------|
| 命名混乱 | 🔴 高 | 影响理解成本 |
| 职责重叠 | 🟡 中 | 影响维护性 |
| 继承 vs 组合 | 🟢 低 | 当前设计已合理 |

### 建议顺序

1. **Phase 1: 重命名**（优先级最高，收益最大）
2. **Phase 3: 职责分离**（优先级中，清理代码）
3. **Phase 2: 统一组合**（优先级低，当前已合理）

---

## 附录：迁移指南

### 从 `OrchestratorRuntime` 迁移到 `Orchestrator`

```python
# 旧代码
from packages.agent.orchestrator.graph import OrchestratorRuntime
rt = OrchestratorRuntime(db, model_name, user_id)

# 新代码
from packages.agent.orchestrator.graph import Orchestrator
rt = Orchestrator(db, model_name, user_id)
```

### 从 `StepExecutionRuntime` 迁移到 `StepExecutor`

```python
# 旧代码
from packages.agent.execution.runner import StepExecutionRuntime
rt = StepExecutionRuntime(orchestrator, session_id, user_id, agent_id)

# 新代码
from packages.agent.execution.runner import StepExecutor
rt = StepExecutor(orchestrator, session_id, user_id, agent_id)
```

---

## 参考

- `ARCHITECTURE_ANALYSIS.md`: 架构分析报告
- `ARCHITECTURE_CLARIFICATIONS.md`: 架构澄清说明（**已推翻，此文档不再有效**）
- `HARNESS_5_CORES.md`: Harness 5 大核心子系统映射
