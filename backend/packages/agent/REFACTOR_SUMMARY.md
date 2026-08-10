# Harness 架构重构总结

> 执行日期：2026-08-07
> 状态：已完成 Phase 1-4

---

## 执行概览

### 删除的废弃代码 (Phase 4)

| 文件/目录 | 原因 |
|----------|------|
| `runtime_engine/action.py` | ActionEngine 已弃用 |
| `runtime_engine/agent_loop.py` | AgentLoopEngine 已弃用 |
| `runtime_engine/governance.py` | 已迁移到 governance_callback.py |
| `runtime_engine/memory.py` | MemoryEngine 已弃用 |
| `runtime_engine/orchestration.py` | OrchestrationEngine 已弃用 |
| `services/harness_engine_service.py.bak` | 备份文件 |
| `services/harness_agent_adapter.py.bak` | 备份文件 |
| `services/lead_agent_factory.py` | 中间件系统与 Harness 架构割裂 |
| `services/agent_graph_factory.py` | 职责重叠 |
| `api/chat.py` | 已废弃路由 |
| `middlewares/` 目录 | 整体迁移到 hooks/ |

### 新建模块 (Phase 1-2)

| 模块 | 文件 | 职责 |
|------|------|------|
| **hooks/** | `registry.py`, `builtin.py` | 统一 Hook 注册机制 |
| **output/** | `schema.py`, `filters.py`, `governance.py` | 输出治理 (结构化/过滤) |
| **prompts/** | `builder.py`, `agent_prompt_loader.py`, `templates/` | 四模块化系统提示词 |
| **tools/registry.py** | 统一工具注册表 + 错误降级 |
| **runtime/state.py** | 标准化 Harness State 定义 |

### 修复的断链 (B1-B6)

| 编号 | 问题 | 修复方式 | 文件 |
|------|------|---------|------|
| B1 | Governance Callback 未集成 | `AgentRuntime.execute()` 增加 `callbacks` 参数 | `runtime/agent_runtime.py` |
| B2 | plan_middleware 未调用 | 迁移到 `hooks/builtin.py` | `hooks/builtin.py` |
| B3 | lead_agent_factory 中间件割裂 | 删除，逻辑迁移到 hooks | `hooks/builtin.py` |
| B4 | PermissionEngine 未接入 act 节点 | 新增 `create_permission_check_node()` | `runtime_engine/tao_graph.py` |
| B5 | 沙箱未注册为 Agent 工具 | `_get_code_tools()` 返回沙箱 @tool | `harness/engine.py` |
| B6 | RuntimeService 假沙箱 ID | 保留，待后续修复 (需要 SandboxService) | — |

---

## 新架构数据流

```
用户请求
  ↓
HarnessEngine.execute()
  ├── 意图分析 → 选择 Agent
  ├── _get_system_prompt() → PromptBuilder 四模块构建
  ├── _get_tools_for_agent() → 工具列表 (含沙箱工具)
  ↓
HarnessEngine.execute_with_agent()
  ├── _build_tao_graph()
  │   ├── build_tao_graph()
  │   │   ├── think 节点 (Hook: BEFORE_THINK/AFTER_THINK)
  │   │   ├── permission_check 节点 (B4 修复)
  │   │   ├── act 节点 (Hook: BEFORE_ACT/AFTER_ACT)
  │   │   ├── observe 节点
  │   │   └── output_governance 节点 (B1 修复)
  │   └── 编译时设置 interrupt_before=["permission_check"]
  ↓
AgentRuntime.execute(callbacks=[governance_engine.get_callback()])
  ├── graph.ainvoke(state, config={callbacks: [...]})
  ↓
TAO 循环执行
  ├── think → permission_check → act → observe → think → ...
  ↓
output_governance → END
  ↓
返回 ExecutionResult
  ↓
_save_execution_trace() → execution_traces 表
```

---

## 约束体系状态

### 硬约束 (4 层)

| 层 | 状态 | 说明 |
|---|------|------|
| 第 1 层 | ✅ 生效 | Manifest 安全策略 (工具白/黑名单) |
| 第 2 层 | ✅ 已集成 | PermissionEngine 接入 permission_check 节点 |
| 第 3 层 | ✅ 生效 | 代码安全检查 (api/code_execution.py) |
| 第 4 层 | ⚠️ 部分 | 沙箱工具已注册，但 SandboxService 待完善 |

### 软约束 (四模块)

| 模块 | 状态 | 文件 |
|------|------|------|
| 模块 1 Core Identity | ✅ 已实现 | `prompts/templates/core_identity.md` |
| 模块 2 Capabilities | ✅ 已实现 | `prompts/templates/capabilities.md` |
| 模块 3 Domain Knowledge | ✅ 已实现 | `prompts/templates/domain_knowledge.md` |
| 模块 4 Context-Specific | ✅ 已实现 | `PromptBuildContext` 动态生成 |

---

## 关键 API 变更

### AgentRuntime.execute()

```python
# 新增 callbacks 参数
async def execute(
    self,
    graph: CompiledStateGraph,
    state: dict,
    thread_id: str,
    run_id: Optional[str] = None,
    callbacks: Optional[list] = None,  # ← 新增
) -> ExecutionResult:
```

### HarnessEngine._get_system_prompt()

```python
# 从硬编码字符串改为模块化构建
def _get_system_prompt(
    self,
    agent_type: str,
    agent: Optional[AgentConfig] = None,
    tools: Optional[List[Any]] = None,
    user_input: str = "",
    user_id: str = "",
    session_id: str = "",
) -> str:
    from packages.agent.prompts.builder import PromptBuilder
    builder = PromptBuilder()
    ctx = PromptBuildContext(...)
    return builder.build(ctx)
```

---

## 待完成工作

### Phase 3 (架构补全)

| 任务 | 优先级 | 说明 |
|------|--------|------|
| 3.1 Plugin 管理器 | P2 | 动态加载/卸载能力包 |
| 3.2 Command 入口路由 | P2 | 统一命令路由 (`/help`, `/clear`) |
| 3.3 可观测性增强 | P2 | MetricsCollector 集成到 Callback |

### Phase 4 (测试补全)

| 测试文件 | 说明 |
|---------|------|
| `tests/test_output_governance.py` | 输出治理测试 |
| `tests/test_hook_registry.py` | Hook 注册测试 |
| `tests/test_tool_registry.py` | 工具注册表测试 |
| `tests/test_permission_integration.py` | 权限集成测试 |

---

## 文件统计

| 指标 | 数量 |
|------|------|
| 删除文件 | 11 个 |
| 新建文件 | 14 个 |
| 修改文件 | 5 个 |
| 剩余 Python 文件 | 105 个 |

---

## 验证清单

- [x] `hooks` 模块导入成功
- [x] `output` 模块导入成功
- [x] `prompts` 模块导入成功
- [x] `tools/registry.py` 导入成功
- [x] `runtime/state.py` 导入成功
- [x] `runtime_engine/tao_graph.py` 导入成功
- [x] `harness/engine.py` 导入成功
- [x] `runtime/agent_runtime.py` 导入成功

---

## 下一步

1. **验证权限审批流程** — 创建一个需要审批的工具调用，确认 `interrupt` 触发
2. **验证沙箱工具** — 让 Agent 自主请求执行代码，确认沙箱工具被调用
3. **创建 agent_prompt.md 示例** — 为测试 Agent 创建约束文件
4. **执行 Phase 3 任务** — Plugin 管理器、Command 路由、可观测性增强
