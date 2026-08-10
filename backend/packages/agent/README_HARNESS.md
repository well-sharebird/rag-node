# Harness 架构使用指南

## 快速开始

### 1. 使用 HarnessAgentService (推荐)

```python
from packages.agent.services.harness_agent_service import HarnessAgentService

# 创建服务
service = HarnessAgentService(
    db=db,
    model_gateway=model_gateway,
    skill_registry=skill_registry,
    use_harness=True,  # 启用新架构
)

# 执行
result = await service.execute(
    agent_id="agent-xxx",
    query="Hello, how can I help you?",
    user_id=1,
    tenant_id="default",
    execution_mode="single",  # single, multi, meta
)

print(result.response)
```

### 2. 流式执行

```python
async for chunk in service.execute_stream(
    agent_id="agent-xxx",
    query="Hello",
    user_id=1,
    tenant_id="default",
):
    # 解析 SSE 格式
    data = json.loads(chunk)
    if data["type"] == "token":
        print(data["content"], end="")
```

### 3. 直接使用 Runtime 层

```python
from packages.agent.runtime import AgentRuntime, RuntimeConfig
from langgraph.graph import StateGraph, START, END
from typing import TypedDict, Annotated, List
from langgraph.graph.message import add_messages

# 定义状态
class SimpleState(TypedDict):
    messages: Annotated[List[str], add_messages]

# 构建图
def agent_node(state: SimpleState):
    return {"messages": [f"Response: {state['messages'][-1]}"]}

graph = StateGraph(SimpleState)
graph.add_node("agent", agent_node)
graph.add_edge(START, "agent")
graph.add_edge("agent", END)
compiled = graph.compile()

# 执行
runtime = AgentRuntime(config=RuntimeConfig())
result = await runtime.execute(
    graph=compiled,
    state={"messages": ["Hello"]},
    thread_id="user_1:session_1",
)
```

### 4. 使用 TAO Graph

```python
from packages.agent.runtime_engine.tao_graph import create_tao_agent

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

### 5. 使用 Orchestration Graph

```python
from packages.agent.runtime_engine.orchestration_graph import build_orchestration_graph

workers = [
    {"id": "researcher", "role": "Research expert"},
    {"id": "writer", "role": "Content writer"},
]

# Supervisor 模式
graph = build_orchestration_graph(
    workers=workers,
    mode="supervisor",
)

result = await graph.ainvoke({
    "task": "Write a report",
    "workers": ["researcher", "writer"],
})
```

## 三层架构

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: Harness (基础方案引擎) - 解决"怎么用"                │
│ ├── HarnessEngine - 业务语义引擎                             │
│ └── HarnessConfig - 业务配置                                 │
└─────────────────────────────────────────────────────────────┘
                            │ 使用
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: Runtime (运行时) - 解决"怎么跑"                      │
│ ├── AgentRuntime - 统一执行入口                              │
│ └── RuntimeConfig - 运行时配置                               │
└─────────────────────────────────────────────────────────────┘
                            │ 构建于
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Framework (框架层) - 解决"怎么写"                   │
│ ├── tao_graph.py - TAO 循环图                                │
│ ├── orchestration_graph.py - 编排图                          │
│ └── governance_callback.py - Governance Callback            │
└─────────────────────────────────────────────────────────────┘
```

## 执行模式

| 模式 | 说明 | 使用场景 |
|------|------|----------|
| `single` | 单智能体执行 | 简单问答、任务处理 |
| `multi` | 多智能体协作 | 复杂任务分解 |
| `meta` | Meta Agent | 自主决策创建/调度智能体 |

## 协作模式 (多智能体)

| 模式 | 说明 | 使用场景 |
|------|------|----------|
| `supervisor` | 主管分配 | 需要任务分解和协调 |
| `round_robin` | 轮流处理 | 流水线式任务 |
| `voting` | 投票决策 | 需要多方案对比 |
| `pipeline` | 顺序流水线 | 多阶段任务 |
| `parallel` | 并行执行 | 独立子任务并发处理 |

## 配置示例

### RuntimeConfig

```python
from packages.agent.runtime import RuntimeConfig

config = RuntimeConfig(
    stream=True,                    # 流式输出
    recursion_limit=50,             # LangGraph 递归限制
    timeout_seconds=300,            # 执行超时 (秒)
    token_budget=4096,              # Token 预算
    checkpointer="database",        # 检查点类型
    interrupt_before=["human"],     # 在人机协作节点前中断
)
```

### HarnessConfig

```python
from packages.agent.harness import HarnessConfig
from packages.agent.harness.config import CollaborationMode

config = HarnessConfig(
    enable_planning_tools=True,     # 启用规划工具
    enable_rag_tools=True,          # 启用 RAG 工具
    enable_code_tools=False,        # 启用代码工具
    collaboration_modes=[
        CollaborationMode.SUPERVISOR,
        CollaborationMode.VOTING,
    ],
)
```

## 文件结构

```
backend/packages/agent/
├── runtime/                        # Layer 2: Runtime 层
│   ├── __init__.py
│   ├── config.py                   # RuntimeConfig, HarnessConfig
│   └── agent_runtime.py            # AgentRuntime
│
├── harness/                        # Layer 3: Harness 层
│   ├── __init__.py
│   ├── config.py                   # HarnessConfig
│   └── engine.py                   # HarnessEngine
│
├── runtime_engine/                 # Layer 1: LangGraph 组件
│   ├── tao_graph.py                # TAO 循环图
│   ├── orchestration_graph.py      # 编排图
│   └── governance_callback.py      # Governance Callback
│
└── services/
    ├── harness_agent_service.py    # 新：Harness Agent 服务
    └── agent_service.py            # 现有：Agent 服务
```

## 测试

```bash
cd backend
uv run python -m pytest packages/agent/tests/test_harness_arch.py -v
```

## 相关文档

- `REFACTOR_PLAN.md` - 详细重构计划
- `README_ARCH.md` - 架构文档
- `tests/test_harness_arch.py` - 架构测试
