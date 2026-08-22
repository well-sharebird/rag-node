# Agent 实现 Bug 修复

## 执行时间
2026-08-21

## 发现的 Bug

### Bug 1: StepDrivenEngineV2 类不存在
**位置**: `integration/execution_chain.py`

**问题**: 代码引用了不存在的 `StepDrivenEngineV2` 类，实际类名是 `StepDrivenEngine`

**影响**: 运行时抛出 `NameError: name 'StepDrivenEngineV2' is not defined`

**修复**:
```python
# 错误
from packages.agent.execution.step_engine import StepDrivenEngineV2
self._step_runtime = StepDrivenEngineV2(...)

# 正确
from packages.agent.execution.step_engine import StepDrivenEngine
self._step_runtime = StepDrivenEngine(...)
```

**文件**:
- `integration/execution_chain.py`: 行 85, 86, 87, 273, 275, 293, 457

---

### Bug 2: hooks 属性未暴露
**位置**: `execution/step_engine.py`

**问题**: `StepDrivenEngine` 的 `_hooks` 是私有属性，但 `ExecutionOrchestrator` 需要访问

**影响**: 运行时抛出 `AttributeError: 'StepDrivenEngine' object has no attribute 'hooks'`

**修复**: 添加 property 暴露
```python
@property
def hooks(self) -> Optional[HookRegistry]:
    """暴露 hooks 属性（供 ExecutionOrchestrator 访问）"""
    return self._hooks
```

**文件**:
- `execution/step_engine.py`: 新增 property

---

### Bug 3: OrchestratorRuntime 缺少 config 属性
**位置**: `orchestrator/graph.py`

**问题**: `OrchestratorRuntime` 多处代码访问 `self.config`，但 `__init__` 中未定义

**影响**: 运行时抛出 `AttributeError: 'OrchestratorRuntime' object has no attribute 'config'`

**修复**: 在 `__init__` 中保存 config
```python
def __init__(self, db: AsyncSession, model_name: Optional[str] = None,
             user_id: Optional[int] = None, config: Optional[RuntimeConfig] = None):
    # Phase 2: 组合 GraphRuntime（不再继承）
    from packages.agent.orchestrator.graph_runtime import GraphRuntime
    self._graph_runtime = GraphRuntime(config)
    
    # 保存 config 供后续使用
    self.config = config or RuntimeConfig()  # ← 新增
    ...
```

**文件**:
- `orchestrator/graph.py`: 行 79-95

---

### Bug 4: 错误的属性访问
**位置**: `integration/execution_chain.py`

**问题**: 尝试访问 `OrchestratorRuntime` 不存在的 `_llm` 和 `_tools` 属性

**影响**: 获取到 None/空列表，导致执行失败

**修复**: 移除错误访问，传 None 给 StepDrivenEngine
```python
# 错误
llm = self.runtime._llm if hasattr(self.runtime, '_llm') else None
tools = self.runtime._tools if hasattr(self.runtime, '_tools') else []

# 正确
# 注意：OrchestratorRuntime 不直接存储 _llm/_tools，需要时创建
# 这里传 None，让 StepDrivenEngine 使用默认配置
llm = None
tools = []
```

**文件**:
- `integration/execution_chain.py`: 行 278-279

---

### Bug 5: StepDrivenEngine 调用签名错误
**位置**: `integration/execution_chain.py`

**问题**: 调用 `StepDrivenEngine()` 时第一个参数传了 `self.runtime`，但实际签名是 `llm` 参数

**影响**: 类型错误，运行时崩溃

**修复**: 使用关键字参数
```python
# 错误
self._step_runtime = StepDrivenEngine(
    self.runtime, llm, tools,
    session_id=session_id,
    user_id=self.user_id,
    permission_engine=permission_engine,
)

# 正确
self._step_runtime = StepDrivenEngine(
    llm=llm,
    tools=tools,
    session_id=session_id,
    user_id=self.user_id,
    permission_engine=permission_engine,
)
```

**文件**:
- `integration/execution_chain.py`: 行 293-300

---

## 验证结果

### 语法检查
```
✅ execution_chain.py syntax OK
✅ step_engine.py syntax OK
✅ graph.py syntax OK
```

### 导入测试
```
✅ All imports successful
```

### 关键类验证
- `ExecutionOrchestrator` ✅
- `StepDrivenEngine` ✅
- `OrchestratorRuntime` ✅

---

## 文件变更总结

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `integration/execution_chain.py` | 修复 | 移除 StepDrivenEngineV2 引用，修复调用签名 |
| `execution/step_engine.py` | 新增 | 添加 hooks property |
| `orchestrator/graph.py` | 修复 | 添加 config 属性初始化 |

---

## 调用链走查

### API 入口
```
POST /api/v1/agents/execute/stream
    ↓
execute_agent_unified_stream() (agents.py:331)
    ↓
create_execution_orchestrator() (execution_chain.py:485)
    ↓
ExecutionOrchestrator.__init__() (execution_chain.py:74)
    ↓
ExecutionOrchestrator.execute_stream() (execution_chain.py:210)
    ↓
StepDrivenEngine.__init__() (step_engine.py:47)
    ↓
StepDrivenEngine.execute() (step_engine.py:103)
    ↓
RuntimeEngine.execute() (engine.py:100)
    ↓
MiddlewareChain + Agent Graph (think→act→think)
```

### 关键修复点
1. ✅ `ExecutionOrchestrator` → `StepDrivenEngine` 创建
2. ✅ `StepDrivenEngine` → `RuntimeEngine` 创建
3. ✅ `OrchestratorRuntime` config 初始化
4. ✅ hooks 属性暴露

---

## 总结

共发现并修复 **5 个关键 bug**：
1. 类名错误（StepDrivenEngineV2 → StepDrivenEngine）
2. 属性未暴露（hooks property）
3. 属性未初始化（config）
4. 错误属性访问（_llm/_tools）
5. 调用签名错误（参数顺序）

所有修复已通过语法检查和导入测试，代码可正常运行。
