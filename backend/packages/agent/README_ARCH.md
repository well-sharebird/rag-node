# Agent 架构文档

## 三层架构

本项目的 Agent 架构采用三层设计：

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: Harness (基础方案引擎) - 解决"怎么用"                │
│                                                             │
│ 提供开箱即用的完整方案：                                      │
│ - 内置默认提示词                                             │
│ - 工具调用处理                                               │
│ - 规划工具 (Plan/Solve/Reflect)                             │
│ - 文件系统访问                                               │
│ - 多 Agent 协作模式 (Supervisor/RoundRobin/Voting)           │
│                                                             │
│ 核心文件：                                                   │
│ - harness/engine.py → HarnessEngine                         │
│ - harness/config.py → HarnessConfig                         │
└─────────────────────────────────────────────────────────────┘
                            │ 使用
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: Runtime (运行时) - 解决"怎么跑"                      │
│                                                             │
│ 封装 LangGraph 执行能力：                                    │
│ - 统一执行入口 (execute/stream/interrupt/resume)            │
│ - 资源管理 (Token 预算/超时/重试)                           │
│ - 状态管理 (Checkpoint/恢复/时间旅行)                       │
│                                                             │
│ 核心文件：                                                   │
│ - runtime/agent_runtime.py → AgentRuntime                   │
│ - runtime/config.py → RuntimeConfig                         │
└─────────────────────────────────────────────────────────────┘
                            │ 构建于
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Framework (框架层) - 解决"怎么写"                   │
│                                                             │
│ LangChain + LangGraph 提供：                                │
│ - LLM 抽象 (ChatOpenAI/ChatAnthropic)                       │
│ - Tool 抽象 (BaseTool/StructuredTool)                      │
│ - StateGraph / ToolNode / CheckpointSaver                  │
│ - Callback 机制                                             │
│                                                             │
│ 核心组件：                                                   │
│ - runtime_engine/tao_graph.py → TAO 循环图                  │
│ - runtime_engine/orchestration_graph.py → 编排图            │
│ - runtime_engine/governance_callback.py → Governance        │
└─────────────────────────────────────────────────────────────┘
```

## 各层职责

### Layer 1: Framework (框架层)

**职责**: 提供抽象和标准化接口，解决"怎么写"的问题

**核心能力**:
- LLM 统一接口
- Tool 抽象
- Message 抽象
- Callback 机制

**使用方式**: 直接使用 LangChain/LangGraph 原生 API

### Layer 2: Runtime (运行时)

**职责**: 处理生产环境的基础设施需求，解决"怎么跑"的问题

**核心能力**:
- 持久化执行 (CheckpointSaver)
- 流式支持 (astream/stream_mode)
- 人机协作中断 (interrupt/resume)
- 线程级持久化 (thread_id 隔离)
- 状态快照 (get_state/patch_state)

**使用方式**: 通过 `AgentRuntime` 统一入口

### Layer 3: Harness (基础方案引擎)

**职责**: 更高层的封装，提供开箱即用的完整方案，解决"怎么用"的问题

**核心能力**:
- 内置提示词模板
- 内置规划工具
- 多 Agent 协作模式
- 领域特定逻辑 (RAG/代码执行)

**使用方式**: 通过 `HarnessEngine` 业务语义引擎

## 快速开始

### 使用 HarnessEngine (推荐)

```python
from packages.agent.harness import HarnessEngine, HarnessConfig
from packages.agent.runtime import RuntimeConfig

# 配置
config = HarnessConfig(
    runtime=RuntimeConfig(stream=True, token_budget=4096),
    enable_planning_tools=True,
    collaboration_modes=["supervisor"],
)

# 创建引擎
engine = HarnessEngine(db=db, config=config)

# 执行
result = await engine.execute(
    agent_type="single",
    messages=[{"role": "user", "content": "Hello"}],
    thread_id="user_1:agent_1:session_1",
)
```

### 使用 AgentRuntime

```python
from packages.agent.runtime import AgentRuntime, RuntimeConfig
from langgraph.graph import StateGraph, START, END

# 创建 Runtime
runtime = AgentRuntime(config=RuntimeConfig())

# 构建图
graph = StateGraph(State)
graph.add_node("agent", agent_node)
graph.add_edge(START, "agent")
graph.add_edge("agent", END)
compiled = graph.compile()

# 执行
result = await runtime.execute(
    graph=compiled,
    state={"messages": [...]},
    thread_id="user_1:session_1",
)
```

### 使用 TAO Graph

```python
from packages.agent.runtime_engine.tao_graph import build_tao_graph, create_tao_agent

# 创建 TAO Agent
tao_agent = await create_tao_agent(
    llm=llm,
    tools=tools,
    max_iterations=10,
)

# 执行
result = await tao_agent.ainvoke({
    "messages": [...],
})
```

### 使用 Orchestration Graph

```python
from packages.agent.runtime_engine.orchestration_graph import build_orchestration_graph

# 定义 Worker
workers = [
    {"id": "researcher", "role": "Research expert"},
    {"id": "writer", "role": "Content writer"},
]

# 构建 Supervisor 模式图
graph = build_orchestration_graph(
    workers=workers,
    mode="supervisor",
)

# 执行
result = await graph.ainvoke({
    "task": "Write a report",
    "workers": ["researcher", "writer"],
})
```

## 架构演进

### 重构前的问题

1. **层级混乱**: Harness 层直接实现了 Runtime 层的能力
2. **代码重复**: 多套执行引擎并存
3. **TAO Loop 独立**: 无法利用 LangGraph 的 Checkpoint/流式能力
4. **Governance 独立**: 需要手动在每个节点添加日志

### 重构后的优势

1. **层级清晰**: 每层解决不同问题，不越界
2. **代码复用**: 统一使用 LangGraph 原语
3. **TAO = LangGraph**: TAO 循环就是图的自环
4. **Governance = Callback**: 无侵入式自动追踪

## 相关文件

- `REFACTOR_PLAN.md` - 详细重构计划
- `harness/` - Harness 层代码
- `runtime/` - Runtime 层代码
- `runtime_engine/` - LangGraph 组件
