# Agent 架构文档

> 版本：2.0 (重构后)
> 更新日期：2026-08-06

---

## 一、三层架构总览

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Layer 3: Harness (基础方案引擎) - 解决"怎么用"                           │
│                                                                         │
│ 提供开箱即用的完整方案：内置提示词、工具调用、规划工具、多 Agent 协作      │
│                                                                         │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ HarnessEngine (harness/engine.py)                                   │ │
│ │ └── 使用 → AgentRuntime (Layer 2)                                   │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
                                │ 使用
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Layer 2: Runtime (运行时) - 解决"怎么跑"                                 │
│                                                                         │
│ 封装 LangGraph 执行能力：持久化、流式、中断恢复、状态快照                 │
│                                                                         │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ AgentRuntime (runtime/agent_runtime.py)                             │ │
│ │ └── 封装 → LangGraph (Layer 1)                                      │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
                                │ 构建于
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Layer 1: Framework (框架层) - 解决"怎么写"                               │
│                                                                         │
│ LangChain + LangGraph 提供抽象：LLM、Tool、StateGraph、Callback          │
│                                                                         │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                     │
│ │ tao_graph.py │ │orchestration │ │ governance_  │                     │
│ │ (TAO 循环图)  │ │_graph.py     │ │ callback.py  │                     │
│ │              │ │ (编排图)     │ │ (追踪回调)   │                     │
│ └──────────────┘ └──────────────┘ └──────────────┘                     │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 二、目录结构

```
backend/packages/agent/
│
├── runtime/                        # Layer 2: Runtime 层
│   ├── __init__.py                 # 层入口
│   ├── config.py                   # RuntimeConfig, HarnessConfig
│   └── agent_runtime.py            # AgentRuntime 统一执行入口
│
├── harness/                        # Layer 3: Harness 层
│   ├── __init__.py                 # 层入口
│   ├── config.py                   # HarnessConfig 业务配置
│   └── engine.py                   # HarnessEngine 业务语义引擎
│
├── runtime_engine/                 # Layer 1: LangGraph 组件 (旧，已弃用)
│   ├── tao_graph.py                # TAO 循环图 (新)
│   ├── orchestration_graph.py      # 多 Agent 编排图 (新)
│   ├── governance_callback.py      # Governance Callback (新)
│   ├── orchestration.py            # 旧编排引擎 ⚠️ 已弃用
│   ├── agent_loop.py               # 旧循环引擎 ⚠️ 已弃用
│   ├── governance.py               # 旧管控引擎 ⚠️ 已弃用
│   ├── memory.py                   # 旧记忆引擎 ⚠️ 已弃用
│   └── action.py                   # 旧行动引擎 ⚠️ 已弃用
│
├── services/                       # 服务层
│   ├── harness_agent_service.py    # 新：Harness Agent 服务
│   ├── harness_adapter.py          # 适配器层 (过渡用)
│   ├── agent_service.py            # 现有：Agent 服务
│   └── harness_engine_service.py   # ⚠️ 已弃用，转发到 harness_agent_service
│
├── models/                         # 数据模型
│   ├── agent.py                    # Agent 配置/版本/记忆/日志
│   ├── runtime.py                  # Agent Runtime/Event
│   ├── session.py                  # Agent Session/Message
│   └── workspace.py                # Workspace/File
│
├── schemas/                        # Pydantic Schema
│   ├── chat.py                     # 聊天请求/响应
│   ├── manifest.py                 # Agent Manifest
│   └── conversation.py             # 会话 Schema
│
├── api/                            # FastAPI 路由
│   ├── agents.py                   # Agent 管理/执行
│   ├── conversations.py            # 会话管理
│   └── ...
│
└── tests/                          # 测试
    └── test_harness_arch.py        # 架构测试 (12 项)
```

---

## 三、核心组件详解

### 3.1 Layer 3: Harness 层

**职责**: 提供开箱即用的业务语义，解决"怎么用"的问题

| 组件 | 文件 | 职责 |
|------|------|------|
| **HarnessEngine** | `harness/engine.py` | 业务语义引擎，内置提示词/工具/协作模式 |
| **HarnessConfig** | `harness/config.py` | 业务配置 (协作模式/内置工具/领域配置) |

**核心能力**:
- 内置提示词模板 (单 Agent/多 Agent/Meta Agent)
- 内置规划工具 (Plan/Solve/Reflect)
- 多 Agent 协作模式 (Supervisor/RoundRobin/Voting/Pipeline/Parallel)
- RAG/代码执行领域集成

**使用示例**:
```python
from packages.agent.harness import HarnessEngine, HarnessConfig

engine = HarnessEngine(db=db, config=HarnessConfig())
result = await engine.execute(
    agent_type="single",
    messages=[{"role": "user", "content": "Hello"}],
    thread_id="user_1:session_1",
)
```

---

### 3.2 Layer 2: Runtime 层

**职责**: 封装 LangGraph 执行能力，解决"怎么跑"的问题

| 组件 | 文件 | 职责 |
|------|------|------|
| **AgentRuntime** | `runtime/agent_runtime.py` | 统一执行入口 (execute/stream/interrupt/resume) |
| **RuntimeConfig** | `runtime/config.py` | 运行时配置 (流式/超时/Token 预算/检查点) |

**核心能力**:
- 统一执行入口 (`execute()` / `execute_stream()`)
- 资源管理 (Token 预算/超时/重试)
- 状态管理 (Checkpoint/恢复/时间旅行)
- 人机协作中断 (`interrupt()` / `resume()`)

**使用示例**:
```python
from packages.agent.runtime import AgentRuntime, RuntimeConfig

runtime = AgentRuntime(config=RuntimeConfig())
result = await runtime.execute(
    graph=compiled_graph,
    state={"messages": [...]},
    thread_id="user_1:session_1",
)
```

---

### 3.3 Layer 1: Framework 层 (LangGraph 组件)

**职责**: 使用 LangGraph 原语构建可复用组件，解决"怎么写"的问题

| 组件 | 文件 | 职责 |
|------|------|------|
| **TAO Graph** | `runtime_engine/tao_graph.py` | Think-Act-Observe 循环图 |
| **Orchestration Graph** | `runtime_engine/orchestration_graph.py` | 多 Agent 编排图 |
| **Governance Callback** | `runtime_engine/governance_callback.py` | 无侵入式追踪回调 |

**核心设计**:

1. **TAO Loop = LangGraph 自环图**
   ```
   START → think → [有工具调用？] → act → observe → think → ... → END
   ```

2. **Orchestration = LangGraph 条件边**
   - Supervisor: 动态路由到 Worker
   - RoundRobin: 顺序边连接
   - Voting: 并行执行后汇总

3. **Governance = AsyncCallbackHandler**
   - `on_llm_start/end` - LLM 调用追踪
   - `on_tool_start/end` - 工具调用追踪
   - 无侵入式，通过 `config={"callbacks": [...]}`注入

---

## 四、执行流程

### 4.1 单 Agent 执行流程

```
用户请求
    │
    ▼
API Router (api/agents.py)
    │
    ▼
HarnessAgentService.execute()
    │
    ├─→ HarnessEngine.execute()           [Layer 3]
    │       │
    │       ├─→ 准备系统提示词
    │       ├─→ 准备工具
    │       └─→ 构建图
    │
    ├─→ AgentRuntime.execute()            [Layer 2]
    │       │
    │       ├─→ 构建 LangGraph 配置
    │       ├─→ 执行图 (ainvoke)
    │       └─→ 返回结果
    │
    └─→ LangGraph StateGraph.ainvoke()    [Layer 1]
            │
            ├─→ think 节点 (LLM 推理)
            ├─→ act 节点 (ToolNode 执行)
            └─→ observe 节点 (处理结果)
```

### 4.2 多 Agent 协作流程 (Supervisor 模式)

```
用户请求
    │
    ▼
HarnessAgentService.execute(execution_mode="multi")
    │
    ▼
HarnessEngine.execute(agent_type="multi")
    │
    ▼
OrchestrationGraphBuilder.build(mode="supervisor")
    │
    ├─→ Supervisor 节点 (LLM 决定下一个 Worker)
    │       │
    │       ├─→ 分析任务
    │       └─→ 路由到 Worker
    │
    ├─→ Worker 节点 (执行具体任务)
    │       │
    │       ├─→ researcher 节点
    │       ├─→ writer 节点
    │       └─→ reviewer 节点
    │
    └─→ 回到 Supervisor (继续决策或结束)
```

### 4.3 Meta Agent 执行流程

```
用户请求
    │
    ▼
HarnessAgentService.execute(execution_mode="meta")
    │
    ▼
HarnessEngine.execute(agent_type="meta")
    │
    ├─→ 分析用户需求
    ├─→ 决策：创建新 Agent or 使用现有 Agent
    ├─→ 调用 create_agent/execute_agent 工具
    └─→ 整合结果返回
```

---

## 五、数据模型

### 5.1 Agent 核心模型

```
models/agent.py
│
├── AgentConfig           # Agent 配置 (用户创建的智能体)
│   ├── id, name, description
│   ├── agent_type (single/multi)
│   ├── default_model_config
│   ├── system_prompt
│   ├── enabled_skills
│   ├── multi_agent_config
│   └── status, is_public
│
├── AgentVersion          # 版本快照
│   ├── agent_id, version
│   └── config_snapshot
│
├── AgentMemory           # 记忆存储
│   ├── agent_id, user_id, thread_id
│   ├── memory_type (conversation/vector/summary)
│   └── content, expires_at
│
└── AgentCallLog          # 执行日志
    ├── agent_id, run_id, user_id
    ├── latency_ms, tokens_used
    └── status, error_message
```

### 5.2 Runtime 核心模型

```
models/runtime.py
│
├── AgentRuntime          # 运行时环境
│   ├── agent_id, workspace_id
│   ├── sandbox_type (nsjail/firecracker)
│   ├── status (initializing/running/stopped/sleeping)
│   └── manifest, sandbox_config
│
└── AgentRuntimeEvent     # 运行时事件日志
    ├── runtime_id, event_type
    └── event_data, timestamp
```

---

## 六、安全层

### 6.1 沙箱隔离

| 组件 | 文件 | 职责 |
|------|------|------|
| **NsJail** | `sandbox/nsjail.py` | 轻量级进程隔离 |
| **Firecracker** | `sandbox/firecracker.py` | VM 级完全隔离 |

**NsJail 隔离维度**:
- 进程隔离 (PID namespace)
- 用户隔离 (uidmap → nobody)
- 文件系统 (只读系统目录 + 临时工作区)
- 资源限制 (CPU/内存/文件数)
- 系统调用过滤 (seccomp 白名单)

### 6.2 权限引擎

| 组件 | 文件 | 职责 |
|------|------|------|
| **PermissionEngine** | `runtime_engine/permission.py` | 梯度化权限管理 |

**权限级别**:
- `FREE` - 自由执行，无需审批
- `ASK_FIRST` - 首次询问，批准后缓存
- `APPROVE_ONCE` - 每次都需审批

---

## 七、可观测性层

### 7.1 执行追踪

| 组件 | 文件 | 职责 |
|------|------|------|
| **GovernanceEngine** | `runtime_engine/governance_callback.py` | 全链路追踪 |
| **AgentMonitoringService** | `services/agent_monitoring_service.py` | 调试模式/节点轨迹 |

**追踪内容**:
- LLM 调用 (开始/结束/Token 使用)
- 工具调用 (名称/参数/结果/耗时)
- 链式调用 (输入/输出)
- 检索操作 (查询/文档数)

### 7.2 日志记录

| 组件 | 文件 | 职责 |
|------|------|------|
| **AgentCallLog** | `models/agent.py` | 执行日志 |
| **AgentRuntimeEvent** | `models/runtime.py` | 运行时事件 |

---

## 八、API 路由

### 8.1 Agent 管理

```
POST   /api/v1/agents              # 创建 Agent
GET    /api/v1/agents              # 列表
GET    /api/v1/agents/{id}         # 详情
PUT    /api/v1/agents/{id}         # 更新
DELETE /api/v1/agents/{id}         # 删除

POST   /api/v1/agents/from-requirement  # 按需自动创建
```

### 8.2 Agent 执行

```
POST   /api/v1/agents/{id}/execute      # 非流式执行
POST   /api/v1/agents/{id}/execute/stream  # 流式执行 (SSE)

POST   /api/v1/agents/meta/execute      # Meta Agent 执行
POST   /api/v1/agents/meta/execute/stream  # Meta Agent 流式
```

### 8.3 会话管理

```
GET    /api/v1/conversations       # 会话列表
GET    /api/v1/conversations/{id}  # 会话详情
DELETE /api/v1/conversations/{id}  # 删除会话
```

---

## 九、测试

### 9.1 架构测试

**文件**: `tests/test_harness_arch.py`

| 测试类别 | 测试项 | 状态 |
|----------|--------|------|
| Runtime 层 | RuntimeConfig 创建 | ✅ |
| Runtime 层 | AgentRuntime 创建 | ✅ |
| Runtime 层 | 简单图执行 | ✅ |
| TAO Graph | TAOState 定义 | ✅ |
| TAO Graph | should_act 路由 | ✅ |
| Orchestration Graph | OrchestrationState 定义 | ✅ |
| Orchestration Graph | RoundRobin/Voting图构建 | ✅ |
| Governance | GovernanceEngine 创建 | ✅ |
| Governance | 追踪生命周期 | ✅ |
| Governance | CallbackHandler 创建 | ✅ |
| Harness 层 | HarnessConfig 创建 | ✅ |
| Harness 层 | 协作模式枚举 | ✅ |

**结果**: 12 passed, 0 failed

### 9.2 运行测试

```bash
cd backend
uv run python -m pytest packages/agent/tests/test_harness_arch.py -v
```

---

## 十、迁移指南

### 10.1 从旧架构迁移

**旧代码**:
```python
from packages.agent.runtime_engine import OrchestrationEngine, MemoryEngine

orchestration = OrchestrationEngine(db, config)
memory = MemoryEngine(db)
```

**新代码**:
```python
from packages.agent.runtime import AgentRuntime
from packages.agent.harness import HarnessEngine
from packages.agent.runtime_engine.orchestration_graph import build_orchestration_graph

# 使用 HarnessEngine (推荐)
engine = HarnessEngine(db=db)
result = await engine.execute(...)

# 或直接使用 Runtime
runtime = AgentRuntime()
result = await runtime.execute(graph=graph, state=state, thread_id="xxx")
```

### 10.2 弃用文件

| 文件 | 状态 | 替代 |
|------|------|------|
| `harness_engine_service.py` | ⚠️ 已弃用 | `harness_agent_service.py` |
| `runtime_engine/orchestration.py` | ⚠️ 已弃用 | `orchestration_graph.py` |
| `runtime_engine/agent_loop.py` | ⚠️ 已弃用 | `tao_graph.py` |
| `runtime_engine/governance.py` | ⚠️ 已弃用 | `governance_callback.py` |
| `runtime_engine/memory.py` | ⚠️ 已弃用 | `DatabaseCheckpointSaver` |
| `runtime_engine/action.py` | ⚠️ 已弃用 | `LangGraph ToolNode` |

---

## 十一、关键设计决策

| 问题 | 决策 | 理由 |
|------|------|------|
| TAO Loop 如何实现？ | LangGraph 条件边 + 自环 | 利用 Checkpoint/流式能力 |
| Orchestration 如何实现？ | LangGraph Send API + 条件边 | 动态任务分配语义 |
| Governance 如何实现？ | AsyncCallbackHandler | 无侵入式自动追踪 |
| Harness 价值？ | 业务语义层 | 开箱即用的完整方案 |

---

## 十二、相关文档

- `REFACTOR_PLAN.md` - 详细重构计划
- `README_HARNESS.md` - 使用指南
- `README_ARCH.md` - 架构说明
