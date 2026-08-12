# Harness 5 大核心子系统映射文档

> 将 Harness 架构理论与当前代码实现进行映射
>
> **本文件已按重构后的实际实现更新**（2026-08-12）。重构删除了 `runtime_engine/orchestration_graph.py`、`harness/engine.py` 与旧 hooks，编排统一收敛到 `orchestrator/graph.py`。下文所有文件路径均与当前代码一致。

---

## 5 大核心子系统总览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Harness 架构 5 大核心子系统                            │
│                                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 │
│  │ 运行时引擎   │  │   工具层     │  │   记忆系统   │                 │
│  │ Runtime      │  │   Tools      │  │   Memory     │                 │
│  └──────────────┘  └──────────────┘  └──────────────┘                 │
│                                                                         │
│  ┌──────────────┐  ┌──────────────┐                                    │
│  │ 输出治理     │  │  编排引擎    │                                    │
│  │ Governance   │  │ Orchestration│                                    │
│  └──────────────┘  └──────────────┘                                    │
│                                                                         │
│  + 两大基础保障：安全层 (Security) + 可观测性层 (Observability)          │
└─────────────────────────────────────────────────────────────────────────┘
```

> **统一执行入口**：`/api/v1/agents/{agent_id}/execute/stream`（`api/agents.py`）
> → `OrchestratorRuntime.run_stream`（`orchestrator/graph.py`）
> 直答走 TAO 图（`_direct_answer_stream`），多 Agent 走子任务派发（`_exec_sub_task`）+ 流式聚合（`_aggregate_stream`）。
> 主/子 Agent 均复用 `_build_agent_graph` 统一装配（TAO 图 + 中间件 + 权限引擎 + 输出治理 + PromptAssembler）。

---

## 一、运行时引擎 (Runtime Engine)

**职责**: 智能体循环、状态管理、流式处理

### 1.1 智能体循环 (Agent Loop)

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| TAO 循环引擎 | `runtime_engine/tao_graph.py → build_tao_graph()` | ✅ |
| Think 节点 | `tao_graph.py → create_think_node()` | ✅ |
| Act 节点 | `tao_graph.py → create_act_node()`（经 `ToolRegistry.safe_invoke` 执行） | ✅ |
| Observe 节点 | `tao_graph.py → create_observe_node()` | ✅ |
| 条件路由 | `think → (act / end)`，`act → observe → think` 自环 | ✅ |

**核心代码**:
```python
# runtime_engine/tao_graph.py
def build_tao_graph(llm, tools, permission_engine=None, output_governance_node=None,
                    on_token=None, middlewares=None, prompt_assembler=None):
    ...
    graph.add_node("think", create_think_node(llm, system_prompt, on_token, chain, prompt_assembler))
    if permission_engine and tools:
        graph.add_node("permission_check", create_permission_check_node(permission_engine))
    graph.add_node("act", create_act_node(tools, permission_engine))
    ...
```

### 1.2 流式处理 (Streaming)

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| 逐 token 回调 | `tao_graph.create_think_node(..., on_token=...)` | ✅ |
| 流式编排入口 | `orchestrator/graph.py → OrchestratorRuntime.run_stream()` (async generator) | ✅ |
| SSE 包装 | `api/agents.py → EventSourceResponse` (SSE) | ✅ |
| 直答流式 | `_direct_answer_stream()`（Queue 泵送 + PII 脱敏 + 取消清理） | ✅ |
| 聚合流式 | `_aggregate_stream(llm, results, main_prompt, redactor)` | ✅ |

### 1.3 状态与断点

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| 状态定义 | `tao_graph.py → TAOState` | ✅ |
| Checkpointer | `runtime/checkpointer.py`（`DatabaseCheckpointSaver`） | ⚠️ 默认关闭（`use_checkpointer=False`），因 JSONB 序列化未支持 LangChain 复杂消息 |
| 执行终止条件 | `max_iterations`（迭代上限） | ✅ |

**当前限制**：
- 主直答与子 Agent 串行执行**暂无硬超时**（`wait_for(..., timeout=0.1)` 仅为队列轮询，非执行超时）。
- 断点持久化因 CheckpointSaver 序列化限制暂未启用。

---

## 二、工具层 (Tools Layer)

**职责**: 注册、发现、执行、权限

### 2.1 工具注册 / 发现

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| 注册中心 | `tools/registry.py → ToolRegistry.get_all()/safe_invoke()` | ✅ |
| 业务工具注册 | `orchestrator/business_tools.py → ensure_business_tools()` | ✅ |
| 子 Agent 白名单加载 | `orchestrator/graph.py → _load_sub_tools()` | ✅ |
| MCP 工具 | `mcp/tools/*`（kb/model/prompt/agent） | ✅ |
| 技能工具 | `services/skill_registry.py` | ✅ |
| RAG 检索工具 | `mcp/tools/kb_tools.py`（原 `services/retrieval_service.py` 已并入） | ✅ |

### 2.2 工具执行

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| 执行引擎 | `tao_graph.create_act_node()` → `ToolRegistry.safe_invoke()`（进程内） | ✅ |
| 调用格式容错 | 缺失 name / args 非 JSON / 工具不存在 → 反馈并继续 | ✅ |

> **说明（实现已变更）**：工具执行**不再使用** `langgraph.prebuilt.ToolNode`，而是自研 `ToolRegistry.safe_invoke` 在进程内直接执行。因此**沙箱隔离未接入本执行路径**——`sandbox/nsjail.py`、`sandbox/firecracker.py` 独立存在，用于代码执行模块（`api/code_execution.py`），不在 `/execute/stream` 的工具调用链路上。

### 2.3 工具权限

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| 权限引擎 | `runtime_engine/permission.py → PermissionEngine(db, user_id, policy)` | ✅ |
| 梯度权限 | FREE / ASK_FIRST / APPROVE_ONCE / DENIED | ✅ |
| 权限检查节点 | `tao_graph.create_permission_check_node()`（act 之前） | ✅ |
| 人工审批 | `api/approvals.py`（GET /pending、POST approve/reject） | ✅ |
| 权限缓存 | `PermissionEngine._permission_cache` + DB 持久化 ASK_FIRST 批准 | ✅ |

---

## 三、记忆系统 (Memory System)

**职责**: 工作记忆、短期记忆、长期记忆

### 3.1 会话记忆（工作/短期）

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| 会话落库 | `orchestrator/graph.py → _save_conversation()`（`services/conversation_service.py`） | ✅ |
| 会话消息模型 | `models/agent.py → AgentMemory`、`models/session.py → AgentSessionMessage` | ✅ |
| 历史获取 | `services/agent_memory_service.py → get_conversation()` | ✅ |

> **说明（实现已变更）**：会话持久化由 `OrchestratorRuntime` 在**直答分支与多 Agent 编排分支统一调用** `_save_conversation`（本次已补齐编排分支）。但 **/execute/stream 目前不读取多轮历史回灌给 LLM**——每次仅传当前 query，历史记忆"只写不读"，多轮上下文需由前端自行拼接 session。

### 3.2 Token 预算 / 上下文管理

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| Token 预算 | `core/harness/context/token_budget.py → TokenBudgetManager` | ✅ |
| 上下文装配 | `core/harness/context/prompt_assembler.py → PromptAssembler` | ✅ |
| 上下文压缩保护 | `orchestrator/graph.py → _maybe_compress()`（超长输入硬截断） | ✅ |

### 3.3 长期记忆 / RAG

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| 向量记忆模型 | `models/agent.py → AgentMemory (memory_type=vector)` | ✅（表存在） |
| RAG 检索 | `mcp/tools/kb_tools.py`（Milvus 检索） | ✅ 工具化，由子 Agent 白名单/CDK 绑定 |

> **当前限制**：长期记忆的自动摘要压缩与向量回填检索策略未在 /execute/stream 主路径主动触发，依赖子 Agent 白名单显式绑定 RAG 工具。

---

## 四、输出治理 (Output Governance)

**职责**: 模型抽象、结构化校验、输出安全

### 4.1 模型抽象

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| LLM 工厂 | `services/agent_runtime_service.py → create_langchain_llm()` | ✅ |
| 多供应商 | Anthropic / OpenAI / Google / Ollama / Local | ✅ |
| 统一接口 | LangChain `BaseChatModel` | ✅ |

### 4.2 结构化解析

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| Plan 解析 | `orchestrator/graph.py → _parse_plan()`（主 Agent JSON plan） | ✅ |
| 输出治理节点 | `output/governance.py → OutputGovernanceNode` | ✅（`enable_structured=False` 时近旁路） |
| 内容抽取 | `_extract_final_content()` / `extract_reasoning()` / `extract_tool_calls()` | ✅ |

### 4.3 输出安全（PII 脱敏）

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| 脱敏器 | `output/filters.py → PIIFilter`（滑动窗口） | ✅ |
| 直答流脱敏 | `_direct_answer_stream()`（push/flush） | ✅ |
| 子 Agent 结果脱敏 | `_emit_events()` 经 `_redact_block()` | ✅（本次补齐） |
| 聚合流脱敏 | `_aggregate_stream(..., redactor)` | ✅（本次补齐） |

---

## 五、编排引擎 (Orchestration Engine)

**职责**: 工作流编排、多智能体、聚合

### 5.1 编排入口

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| 主编排决策 | `orchestrator/graph.py → _orchestrate()`（主 Agent LLM → JSON plan） | ✅ |
| 执行模式 | `serial` / `parallel`（主 Agent 决策，`run_stream` 可强制 `allow_sub_agents=False`） | ✅ |
| 执行模式 | ~~SUPERVISOR / ROUND_ROBIN / VOTING / PIPELINE / PARALLEL~~ | ❌ 已在重构中移除（旧 `orchestration_graph.py` 已删除），当前仅 serial/parallel |
| 子 Agent 执行 | `_exec_sub_task()`（复用 `_build_agent_graph` TAO 图） | ✅ |
| 目录解析 | `orchestrator/agent_loader.py → resolve_sub_agent_id()`（LLM 输出 id → 真实 id） | ✅ |
| 结果聚合 | `_aggregate_stream()`（LLM 聚合，失败降级为拼装汇总） | ✅ |

### 5.2 审批恢复

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| 审批事件 | `run_stream` 产出 `{"type":"approval_required"}` | ✅ |
| 审批接口 | `api/approvals.py`（approve/reject） | ✅ |

> **当前限制**：审批触发的中断当前在流内**不自动恢复续跑**——子任务返回"[需要审批]"占位，需客户端另调 `approvals.py` 批准后重新发起执行。审计审批闭环在接口外。

---

## 六、两大基础保障

### 6.1 安全层 (Security)

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| 梯度权限门 | `runtime_engine/permission.py` + `tao_graph.create_permission_check_node()` | ✅ |
| 人工审批 | `api/approvals.py` + `__interrupt__`（approval_required） | ✅ |
| 安全中间件 | `middlewares/builtin.py → SecurityGuardMiddleware`（观测/记录） | ✅（强制由权限节点负责） |
| 沙箱隔离 | `sandbox/nsjail.py`、`sandbox/firecracker.py` | ⚠️ 独立模块，**未接入 /execute/stream 工具执行链路** |
| 审计中间件 | `middlewares/builtin.py → AuditLoggerMiddleware` | ✅ |

> **安全策略作用域（实现要点）**：权限门**仅对传入 `security_policy` 的子 Agent 生效**（`allowed_tools` / `require_approval_tools`）。主 Agent 直答路径 `tools=[]` + `policy=None`，不做工具权限门（本身也不绑工具）。`SecurityGuardMiddleware` 仅观测记录，强制由 `permission_check` 图节点完成——"节点强制 / 中间件观测"分层。

### 6.2 可观测性层 (Observability)

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| 执行追踪 | `models/execution_trace.py → ExecutionTrace`，由 `_save_execution_trace()` 落库 | ✅ |
| 审计/工具日志 | `middlewares/builtin.py`（AuditLogger / ToolLogging） | ⚠️ 仅 logger，未持久化到审计表 |
| 全链路追踪回调 | `runtime_engine/governance_callback.py` | ✅（独立模块） |

> **当前限制**：追踪落库 `latency_ms` 固定为 0、`steps` 仅概要；独立聚合指标（P50/P95/P99）、错误率、告警未实现。

---

## 七、5 大核心子系统完整映射表（重构后）

| 子系统 | 理论组件 | 代码文件 | 状态 |
|--------|----------|----------|------|
| **运行时引擎** | 智能体循环 | `runtime_engine/tao_graph.py` | ✅ |
| | 流式编排 | `orchestrator/graph.py → run_stream` | ✅ |
| | 断点持久化 | `runtime/checkpointer.py` | ⚠️ 默认关闭 |
| **工具层** | 注册/发现 | `tools/registry.py`, `orchestrator/business_tools.py` | ✅ |
| | 执行 | `tao_graph.create_act_node` + `ToolRegistry.safe_invoke` | ✅ 进程内 |
| | 权限 | `runtime_engine/permission.py` | ✅ |
| **记忆系统** | 会话记忆 | `_save_conversation` + `services/conversation_service.py` | ✅ |
| | 上下文/Token | `core/harness/context/*` | ✅ |
| | 长期/RAG | `mcp/tools/kb_tools.py`, `AgentMemory(vector)` | ⚠️ 需显式绑定 |
| **输出治理** | 模型抽象 | `services/agent_runtime_service.py` | ✅ |
| | 结构化解析 | `_parse_plan`, `output/governance.py` | ✅ |
| | PII 脱敏 | `output/filters.py` + `_redact_block` | ✅ 全路径 |
| **编排引擎** | 编排 | `orchestrator/graph.py`（serial/parallel） | ✅ |
| | 子 Agent/聚合 | `_exec_sub_task`, `_aggregate_stream` | ✅ |
| **安全层** | 权限门/审批 | `permission.py`, `approvals.py` | ✅ 子 Agent 作用域 |
| | 沙箱 | `sandbox/nsjail.py`, `sandbox/firecracker.py` | ⚠️ 未接流式链路 |
| **可观测性** | 追踪 | `models/execution_trace.py` | ✅ 概要 |
| | 日志 | `middlewares/builtin.py` | ⚠️ 仅 logger |

---

## 八、架构/接口走查结论（/execute/stream）

针对 `/api/v1/agents/{agent_id}/execute/stream` 的走查结论：

| 项目 | 状态 | 备注 |
|------|------|------|
| 运行时引擎 | ✅ | TAO 循环 + 流式，直答/子 Agent 全装配 |
| 工具层 | ⚠️ | 注册/执行/权限齐备；沙箱未接；执行进程内 |
| 记忆系统 | ⚠️ | 会话"只写不读"；编排分支已补齐保存（本次修复） |
| 输出治理 | ✅ | Plan 解析 + 全路径 PII 脱敏（本次补齐子/聚合路径） |
| 编排引擎 | ✅ | serial/parallel + 聚合降级；审批需接口外恢复 |
| 安全层 | ⚠️ | 权限门限子 Agent 作用域；沙箱独立未接 |
| 可观测性 | ⚠️ | 追踪概要；无聚合指标/告警 |

> **本次修复清单**：
> 1. `api/agents.py`：`/execute` 与 `/execute/stream` 构造 `OrchestratorRuntime` 时传入 `user_id=current_user.id`；`run_stream(user_id=...)` 兜底覆盖 `self.user_id` → 会话/追踪/thread_id/权限引擎归属当前用户（原固定为 user=1）。
> 2. `orchestrator/graph.py`：多 Agent 编排分支聚合后统一 `_save_conversation` 落库（原仅直答分支）。
> 3. `orchestrator/graph.py`：为子 Agent 结果事件与聚合流接入 PII 脱敏（`_redact_block` / `_aggregate_stream(redactor)`）。
