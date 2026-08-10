# Agent 平台设计文档

> 版本：2.0
> 更新日期：2026-08-06
> 状态：已实现

---

## 一、架构概述

### 1.1 三层架构

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

### 1.2 5 大核心子系统

| 子系统 | 职责 | 核心文件 |
|--------|------|----------|
| 运行时引擎 | 智能体循环、状态管理、流式处理 | `runtime/`, `runtime_engine/tao_graph.py` |
| 工具层 | 注册、发现、执行、权限 | `mcp/`, `skills/`, `runtime_engine/permission.py` |
| 记忆系统 | 工作/短期/长期记忆 | `services/agent_memory_service.py`, `models/agent.py` |
| 输出治理 | 模型抽象、结构化校验、幻觉检测 | `services/agent_runtime_service.py`, `runtime_engine/parser.py` |
| 编排引擎 | 工作流编排、多智能体、依赖管理 | `runtime_engine/orchestration_graph.py` |

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
├── runtime_engine/                 # Layer 1: LangGraph 组件
│   ├── tao_graph.py                # TAO 循环图
│   ├── orchestration_graph.py      # 多 Agent 编排图
│   ├── governance_callback.py      # Governance Callback
│   ├── permission.py               # 权限引擎
│   ├── parser.py                   # 输出解析器
│   └── token_budget.py             # Token 预算管理
│
├── services/                       # 服务层
│   ├── harness_agent_service.py    # 新：Harness Agent 服务
│   ├── agent_service.py            # 现有：Agent 服务
│   ├── agent_config_service.py     # Agent CRUD
│   ├── agent_memory_service.py     # 记忆管理
│   ├── agent_checkpoint_service.py # Checkpoint 持久化
│   ├── agent_monitoring_service.py # 监控/调试
│   ├── conversation_service.py     # 会话管理
│   ├── skill_registry.py           # 技能注册
│   └── harness_adapter.py          # 适配器 (过渡用)
│
├── models/                         # 数据模型
│   ├── agent.py                    # AgentConfig/Version/Memory/CallLog
│   ├── runtime.py                  # AgentRuntime/Event
│   ├── session.py                  # AgentSession/Message/Checkpoint
│   └── workspace.py                # Workspace/File/AuditLog
│
├── schemas/                        # Pydantic Schema
│   ├── chat.py                     # 聊天请求/响应
│   ├── manifest.py                 # Agent Manifest
│   └── conversation.py             # 会话 Schema
│
├── api/                            # FastAPI 路由
│   ├── agents.py                   # Agent 管理/执行
│   ├── conversations.py            # 会话管理
│   ├── runtimes.py                 # Runtime 管理
│   ├── sessions.py                 # Session 管理
│   └── code_execution.py           # 代码执行
│
├── mcp/                            # MCP 协议
│   ├── client.py                   # MCP 客户端
│   ├── server.py                   # MCP 服务端
│   └── tools/                      # MCP 工具
│       ├── kb_tools.py             # 知识库工具
│       ├── model_tools.py          # 模型工具
│       ├── prompt_tools.py         # 提示词工具
│       └── agent_tools.py          # Agent 工具
│
├── skills/                         # 技能系统
│   ├── agent_tools.py              # Agent 管理技能
│   ├── knowledge_base_tools.py     # KB 技能
│   ├── model_tools.py              # 模型技能
│   └── prompt_tools.py             # 提示词技能
│
├── tools/                          # 工具定义
│   └── builtins.py                 # 内置工具
│
├── sandbox/                        # 沙箱隔离
│   ├── nsjail.py                   # NsJail 沙箱
│   └── firecracker.py              # Firecracker VM
│
├── middlewares/                    # 中间件
│   └── plan_middleware.py          # 计划模式中间件
│
└── tests/                          # 测试
    └── test_harness_arch.py        # 架构测试 (12 项)
```

---

## 三、核心组件设计

### 3.1 HarnessEngine (Layer 3)

**职责**: 提供开箱即用的业务语义

```python
# harness/engine.py
class HarnessEngine:
    """Harness 引擎 - 业务语义层"""
    
    def __init__(self, db: AsyncSession, config: HarnessConfig):
        self.db = db
        self.config = config
        self.runtime = AgentRuntime(config=config.runtime)
    
    async def execute(
        self,
        agent_type: str,           # single/multi/meta
        messages: List[Dict],
        thread_id: str,
        tools: Optional[List[Any]] = None,
        system_prompt: Optional[str] = None,
        collaboration_mode: Optional[str] = None,
    ) -> ExecutionResult:
        """执行入口"""
        # 1. 准备系统提示词
        # 2. 准备工具
        # 3. 构建图
        # 4. 执行
        pass
    
    async def execute_stream(self, ...) -> AsyncGenerator:
        """流式执行入口"""
        pass
```

**核心流程**:
```
1. 加载系统提示词模板
   ↓
2. 加载工具 (内置+MCP+ 技能+RAG)
   ↓
3. 构建 LangGraph (StateGraph)
   ↓
4. 调用 AgentRuntime.execute()
   ↓
5. 返回结果
```

---

### 3.2 AgentRuntime (Layer 2)

**职责**: 封装 LangGraph 执行能力

```python
# runtime/agent_runtime.py
class AgentRuntime:
    """Agent 运行时 - 统一执行入口"""
    
    def __init__(self, checkpointer=None, config=None):
        self.checkpointer = checkpointer
        self.config = config or RuntimeConfig()
    
    async def execute(
        self,
        graph: CompiledStateGraph,
        state: dict,
        thread_id: str,
        run_id: Optional[str] = None,
    ) -> ExecutionResult:
        """批量执行"""
        config = await self._build_config(thread_id, run_id)
        result = await graph.ainvoke(state, config=config)
        return ExecutionResult(result=result)
    
    async def execute_stream(self, graph, state, thread_id):
        """流式执行"""
        async for event, metadata in graph.astream(...):
            yield self._format_event(event, metadata)
    
    async def interrupt(self, thread_id):
        """中断"""
        pass
    
    async def resume(self, graph, thread_id, values):
        """恢复"""
        return await graph.ainvoke(values, config=config)
```

**核心能力**:
- 统一执行入口 (`execute()` / `execute_stream()`)
- 资源管理 (Token 预算/超时/重试)
- 状态管理 (Checkpoint/恢复/时间旅行)
- 人机协作中断 (`interrupt()` / `resume()`)

---

### 3.2.1 智能体循环的概念模型：思考 - 行动 - 观察 (TAO)

**智能体循环（Agent Loop）**是智能体系统的核心执行模式。经典的**"思考 - 行动 - 观察"(Think-Act-Observe)**循环定义如下：

| 阶段 | 职责 | 实现 |
|------|------|------|
| **思考 (Think)** | Agent 基于当前上下文（历史、状态、工具信息）进行推理，生成意图和下一步行动计划 | `tao_graph.py → create_think_node()` |
| **行动 (Act)** | 模型发出工具调用意图，运行时验证、调度并由工具层执行，必要时改变外部世界状态 | `tao_graph.py → ToolNode` |
| **观察 (Observe)** | Agent 获得运行时返回的工具执行结果，更新内部认知模型，为下一轮思考做准备 | `tao_graph.py → create_observe_node()` |

**错误处理**：如果工具调用失败或返回意外结果，观察阶段会将其作为"负面证据"反馈给思考模块，触发错误恢复或备选方案。

**循环流程图**：
```
┌─────────────────────────────────────────────────────────────────────────┐
│                    图 4-1：思考 - 行动 - 观察循环                        │
│                                                                         │
│    ┌─────────────┐                                                      │
│    │   思考      │  ← 基于上下文推理，生成行动计划                       │
│    │   (Think)   │                                                      │
│    └──────┬──────┘                                                      │
│           │                                                             │
│           │ 工具调用意图                                                 │
│           ▼                                                             │
│    ┌─────────────┐                                                      │
│    │   行动      │  ← 运行时验证 → 工具执行 → 改变状态                   │
│    │   (Act)     │                                                      │
│    └──────┬──────┘                                                      │
│           │                                                             │
│           │ 执行结果/错误                                                │
│           ▼                                                             │
│    ┌─────────────┐                                                      │
│    │   观察      │  ← 更新认知模型，反馈给下一轮思考                     │
│    │   (Observe) │                                                      │
│    └──────┬──────┘                                                      │
│           │                                                             │
│           └──────────────┐                                              │
│                          │ (循环)                                        │
│                          ▼                                              │
│                     (回到思考)                                           │
└─────────────────────────────────────────────────────────────────────────┘
```

**为什么是循环而不是链？**

传统的**链式智能体**(Chain-of-Thought) 将思考和行动分开，形如：`提示 → 思考 → 规划 → 工具调用 → 输出`。这种设计的缺点是：

| 问题 | 说明 | 循环设计的解决方案 |
|------|------|-------------------|
| **缺乏适应性** | 一旦执行遇到问题（工具调用失败、输出超限），难以动态调整策略 | 每个循环迭代可获得反馈，动态调整策略 |
| **低效率** | 规划阶段必须预测所有可能的工具调用，容易过度规划或不足规划 | 逐步细化目标，按需调用工具 |
| **不可恢复** | 一旦规划失败，需要重新启动整个流程 | 错误作为负面证据反馈，触发恢复机制 |

**循环设计**允许智能体逐步细化目标，在每个循环迭代中获得反馈，动态调整策略。这更符合人类解决问题的过程。

---

### 3.3 TAO Graph (Layer 1)

**职责**: Think-Act-Observe 循环图

```python
# runtime_engine/tao_graph.py
def build_tao_graph(llm, tools, max_iterations=10):
    """构建 TAO 循环图"""
    graph = StateGraph(TAOState)
    
    # 节点
    graph.add_node("think", create_think_node(llm))
    graph.add_node("act", ToolNode(tools))
    graph.add_node("observe", create_observe_node())
    
    # 边
    graph.add_conditional_edges(
        "think", should_act,
        {"act": "act", "end": END}
    )
    graph.add_edge("act", "observe")
    graph.add_edge("observe", "think")  # 自环
    graph.add_edge(START, "think")
    
    return graph.compile()

def should_act(state):
    """路由函数 - 决定是否继续"""
    if state["tool_calls"]:
        return "act"
    elif state["iteration"] >= 10:
        return "end"
    else:
        return "end"
```

**循环流程**:
```
START → think → [有工具调用？]
                  ├─ 是 → act → observe → think → ...
                  └─ 否 → END
```

---

### 3.4 Orchestration Graph (Layer 1)

**职责**: 多 Agent 编排图

```python
# runtime_engine/orchestration_graph.py
class OrchestrationGraphBuilder:
    """编排图构建器"""
    
    def __init__(self, workers: List[Dict]):
        self.workers = workers
    
    def build(self, mode: str) -> CompiledStateGraph:
        """根据模式构建图"""
        if mode == "supervisor":
            return self._build_supervisor_graph()
        elif mode == "round_robin":
            return self._build_round_robin_graph()
        elif mode == "voting":
            return self._build_voting_graph()
        # ... 其他模式
```

**Supervisor 模式图结构**:
```
START → supervisor → [路由] → worker_1 → supervisor
                                  ↓
                           worker_2 → supervisor
                                  ↓
                           worker_N → supervisor → END
```

---

### 3.5 Governance Callback (Layer 1)

**职责**: 无侵入式执行追踪

```python
# runtime_engine/governance_callback.py
class GovernanceCallbackHandler(AsyncCallbackHandler):
    """Governance 回调处理器"""
    
    def __init__(self, trace_id, engine):
        self.trace_id = trace_id
        self.engine = engine
    
    async def on_llm_start(self, serialized, prompts, **kwargs):
        await self.engine.add_step(self.trace_id, "llm_call", {...})
    
    async def on_tool_start(self, serialized, input, **kwargs):
        await self.engine.add_step(self.trace_id, "tool_call", {...})
    
    async def on_chain_end(self, outputs, **kwargs):
        await self.engine.add_step(self.trace_id, "chain_end", {...})

# 使用方式
engine = GovernanceEngine()
callbacks = engine.get_callbacks(trace_id)
result = await graph.ainvoke(state, config={"callbacks": [callbacks]})
```

---

## 四、数据模型设计

### 4.1 AgentConfig

```python
# models/agent.py
class AgentConfig(Base):
    """Agent 配置表"""
    __tablename__ = "agent_configs"
    
    id: UUID                      # 主键
    user_id: int                  # 用户 ID (FK)
    tenant_id: str                # 租户 ID
    
    # 基本信息
    name: str                     # 名称
    description: str              # 描述
    icon: str                     # 图标
    
    # 类型
    agent_type: str               # single/multi/meta
    
    # 配置
    default_model_config: JSONB   # 默认模型配置
    system_prompt: str            # 系统提示词
    enabled_skills: JSONB         # 启用的技能
    mcp_servers: JSONB            # MCP 服务器
    
    # 记忆
    memory_type: str              # conversation/vector/hybrid
    memory_ttl_hours: int         # 记忆 TTL(小时)
    max_memory_turns: int         # 最大记忆轮数
    
    # 检索
    kb_ids: JSONB                 # 绑定知识库 ID
    retrieval_top_k: int          # 检索返回数量
    retrieval_enabled: bool       # 是否启用检索
    
    # 多 Agent 配置
    multi_agent_config: JSONB     # 多 Agent 配置
    
    # 状态
    status: str                   # draft/active/archived/disabled
    is_public: bool               # 是否公开
    current_version: str          # 版本号
    
    # 统计
    total_runs: int               # 总执行次数
    total_tokens: int             # 总 Token 使用
    
    # 时间戳
    created_at: datetime
    updated_at: datetime
    published_at: datetime
```

### 4.2 AgentMemory

```python
# models/agent.py
class AgentMemory(Base):
    """Agent 记忆表"""
    __tablename__ = "agent_memories"
    
    id: UUID                      # 主键
    agent_id: UUID                # Agent ID (FK)
    user_id: int                  # 用户 ID (FK)
    thread_id: str                # 线程 ID
    
    # 类型
    memory_type: str              # conversation/vector/summary
    
    # 内容
    content: JSONB                # 记忆内容
    
    # 向量引用
    milvus_collection: str        # Milvus 集合
    milvus_ids: JSONB             # Milvus ID 列表
    
    # 过期
    expires_at: datetime          # 过期时间
    created_at: datetime          # 创建时间
```

### 4.3 AgentCallLog

```python
# models/agent.py
class AgentCallLog(Base):
    """Agent 调用日志表"""
    __tablename__ = "agent_call_logs"
    
    id: UUID                      # 主键
    agent_id: UUID                # Agent ID (FK)
    user_id: int                  # 用户 ID (FK)
    
    # 追踪
    thread_id: str                # 线程 ID
    run_id: str                   # 运行 ID
    
    # 模型
    model_provider: str           # 模型供应商
    model_name: str               # 模型名称
    
    # Token
    input_tokens: int             # 输入 Token
    output_tokens: int            # 输出 Token
    total_tokens: int             # 总 Token
    
    # 性能
    latency_ms: int               # 延迟 (ms)
    first_token_latency_ms: int   # 首 Token 延迟
    
    # 状态
    status: str                   # success/error/timeout/cancelled
    error_message: str            # 错误信息
    
    # 摘要
    input_summary: JSONB          # 输入摘要
    output_summary: JSONB         # 输出摘要
    
    created_at: datetime          # 创建时间
```

---

## 五、执行流程

### 5.1 Harness 统一执行入口

Harness 架构采用**统一执行入口**，用户无需关心底层使用哪个 Agent：

```
┌─────────────────────────────────────────────────────────────────────────┐
│ API 入口                                                                │
│ POST /api/v1/agents/execute                                             │
│ POST /api/v1/agents/execute/stream                                      │
└─────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ HarnessEngine.execute()                                                 │
│                                                                         │
│  1. 意图分析 (_analyze_intent)                                          │
│     - 简单问答 → 直接用 LLM                                             │
│     - 指定 Agent → 使用配置 Agent                                       │
│     - 复杂任务 → 多 Agent 协作                                           │
│                                                                         │
│  2. Agent 选择 (_match_agent_by_keywords)                                 │
│     - 基于关键词匹配                                                    │
│     - 基于使用频率                                                      │
│                                                                         │
│  3. 准备工具 (_get_tools_for_agent)                                     │
│     - 内置工具 (规划/代码/RAG)                                          │
│     - MCP 工具                                                          │
│     - 技能工具                                                          │
│                                                                         │
│  4. 执行 TAO 循环                                                         │
└─────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 返回结果                                                                │
│ - run_id                                                                │
│ - response                                                              │
│ - agent_id (实际使用的 Agent)                                           │
│ - agents_used (多 Agent 场景)                                            │
└─────────────────────────────────────────────────────────────────────────┘
```

**意图分析示例**：
| 用户输入 | Harness 决策 |
|----------|--------------|
| "你好，你可以做什么？" | 简单问答 → 直接用 LLM 回答 |
| "帮我写个 Python 脚本" | 关键词"Python" → 代码助手 Agent |
| "分析这个项目的架构" | 复杂任务 → 多 Agent 协作 |
| 已选择 Agent 后提问 | 使用指定的 Agent |

---

### 5.2 单 Agent 执行

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. API 接收请求                                                         │
│    POST /api/v1/agents/{id}/execute/stream                              │
└─────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 2. AgentService.execute()                                               │
│    - 获取 AgentConfig                                                   │
│    - 构建 thread_id                                                     │
└─────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 3. AgentFactory.create_agent()                                          │
│    - 加载 LLM (create_langchain_llm)                                    │
│    - 加载工具 (基础/MCP/技能/RAG)                                       │
│    - 构建中间件 (计划模式/日志)                                         │
└─────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 4. LangGraph StateGraph.ainvoke()                                       │
│    - 加载对话历史 (AgentMemoryService)                                  │
│    - 注入系统提示词                                                     │
│    - 执行 TAO 循环                                                       │
└─────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 5. 保存会话 (ConversationService)                                       │
│ 6. 记录日志 (AgentCallLog)                                              │
│ 7. 返回响应 (SSE 流式)                                                   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 5.3 多 Agent 协作 (Supervisor 模式)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. 获取 AgentConfig (agent_type=multi)                                  │
│ 2. 读取 multi_agent_config.mode = "supervisor"                          │
└─────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 3. OrchestrationGraphBuilder.build("supervisor")                        │
│                                                                         │
│    START → supervisor → [条件边路由]                                     │
│                  ↓                                                      │
│            worker_1 → supervisor                                        │
│            worker_2 → supervisor                                        │
│            ... → supervisor → END                                       │
└─────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 4. graph.ainvoke() 执行                                                 │
│    - supervisor 节点：LLM 分析任务，决定下一个 worker                      │
│    - worker 节点：执行具体任务                                          │
│    - 循环直到任务完成                                                   │
└─────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 5. 汇总结果返回                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 5.4 Meta Agent 执行

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. MetaAgentFactory.create_meta_agent()                                 │
│                                                                         │
│    系统提示词：                                                         │
│    "你是 Meta Agent，可以创建和执行其他智能体..."                         │
│                                                                         │
│    工具：                                                               │
│    - create_agent (创建新智能体)                                        │
│    - execute_agent (执行现有智能体)                                     │
│    - list_agents (查询智能体列表)                                       │
│    - MCP 工具 (KB/Model/Prompt/Agent Hub)                               │
└─────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 2. meta_agent.ainvoke({"messages": [HumanMessage(query)]})              │
│                                                                         │
│    - 分析用户需求                                                       │
│    - 决策：创建新 Agent or 使用现有 Agent                               │
│    - 调用工具执行                                                       │
│    - 整合结果返回                                                       │
└─────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 3. 保存会话到 conversations 表 (用户可见)                                │
│ 4. 保存对话到 agent_memories (运行时记忆)                                │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 六、安全设计

### 6.1 沙箱隔离

```python
# sandbox/nsjail.py
class NsJailSandboxManager:
    """NsJail 沙箱管理器"""
    
    async def execute_code(self, code, language, workspace_path, config):
        """在沙箱中执行代码"""
        
        # 1. 准备代码文件
        code_file = await self._write_code_file(tmpdir, code, language)
        
        # 2. 构建 nsjail 命令
        cmd = [
            self.nsjail_bin,
            "--mode", "once",
            "--uidmap", "inside_id:1000:outside_id:65534",
            "--gidmap", "inside_id:1000:outside_id:65534",
            "--use_netns",  # 网络隔离
            "--robind", "/usr", "/usr",  # 只读系统目录
            "--bind", workspace_path, "/workspace",  # 可写工作区
            "--tmpfs", "/tmp",
            "--seccomp_string", seccomp_policy,  # 系统调用过滤
            "--", interpreter, code_file,
        ]
        
        # 3. 执行
        return await self._execute(cmd, config.timeout_seconds)
```

**隔离维度**:
- PID namespace (进程隔离)
- User namespace (用户隔离 → nobody)
- Mount namespace (文件系统隔离)
- Network namespace (网络隔离)
- seccomp (系统调用过滤)
- rlimit (资源限制)

### 6.2 权限引擎

```python
# runtime_engine/permission.py
class PermissionEngine:
    """权限引擎 - 梯度化权限管理"""
    
    _default_tool_permissions = {
        "knowledge_base_search": PermissionLevel.FREE,
        "code_interpreter": PermissionLevel.ASK_FIRST,
        "file_read": PermissionLevel.FREE,
        "file_write": PermissionLevel.ASK_FIRST,
        "file_delete": PermissionLevel.APPROVE_ONCE,
        "api_call": PermissionLevel.ASK_FIRST,
        "database_query": PermissionLevel.APPROVE_ONCE,
        "system_command": PermissionLevel.APPROVE_ONCE,
    }
    
    async def check_permission(self, tool_name, operation, parameters):
        """检查权限"""
        # 1. 确定权限级别
        permission_level = self._get_permission_level(tool_name)
        
        # 2. Free 级别直接允许
        if permission_level == PermissionLevel.FREE:
            return True, None
        
        # 3. 检查缓存
        if cache_key in self._permission_cache:
            return True, None
        
        # 4. 创建审批请求
        request = await self._create_permission_request(...)
        return False, request
```

---

## 七、可观测性设计

### 7.1 执行追踪

```python
# runtime_engine/governance_callback.py
class GovernanceCallbackHandler(AsyncCallbackHandler):
    """Governance 回调处理器"""
    
    async def on_llm_start(self, serialized, prompts, **kwargs):
        """LLM 调用开始"""
        await self.engine.add_step(
            self.trace_id,
            ExecutionStep(step_id=uuid(), action="llm_call", timestamp=now(), ...)
        )
    
    async def on_llm_end(self, response, **kwargs):
        """LLM 调用结束"""
        token_usage = response.llm_output.get("token_usage", {})
        await self.engine.add_step(
            self.trace_id,
            ExecutionStep(..., metadata={"token_usage": token_usage})
        )
    
    async def on_tool_start(self, serialized, input, **kwargs):
        """工具调用开始"""
        tool_name = serialized.get("name", "unknown")
        await self.engine.add_step(
            self.trace_id,
            ExecutionStep(action="tool_call", metadata={"tool": tool_name})
        )
```

### 7.2 日志记录

```python
# services/agent_service.py
async def _log_execution(self, request, result, run_id, start_time):
    """记录调用日志"""
    call_log = AgentCallLog(
        agent_id=result.agent_id,
        run_id=run_id,
        user_id=request.user_id,
        thread_id=f"{request.user_id}:{request.agent_id}:{request.session_id}",
        input_summary={"query": request.query[:500]},
        output_summary={"response": result.response[:500]},
        latency_ms=int((time.time() - start_time) * 1000),
        status="success",
    )
    self.db.add(call_log)
    await self.db.commit()
```

---

## 八、测试策略

### 8.1 单元测试

```python
# tests/test_harness_arch.py
class TestRuntime:
    def test_runtime_config_creation(self):
        config = RuntimeConfig(stream=True, timeout_seconds=300)
        assert config.stream is True
    
    def test_agent_runtime_creation(self):
        runtime = AgentRuntime(config=RuntimeConfig())
        assert runtime.config.timeout_seconds == 300

class TestTAOGraph:
    def test_should_act_router(self):
        router = create_should_act_router(max_iterations=10)
        assert router({"tool_calls": []}) == "end"
        assert router({"tool_calls": [{"name": "search"}]}) == "act"
```

### 8.2 集成测试

```python
# tests/test_agent_execution.py
async def test_single_agent_execution():
    service = HarnessAgentService(db, model_gateway, skill_registry)
    result = await service.execute(
        agent_id="test-agent",
        query="Hello",
        user_id=1,
        tenant_id="default",
    )
    assert result.success is True
    assert result.response != ""
```

---

## 九、部署架构

### 9.1 基础设施

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         用户请求                                         │
└─────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Nginx / Load Balancer                                                  │
└─────────────────────────────────────────────────────────────────────────┘
    │
    ├─────────────────┬─────────────────┬─────────────────┐
    ▼                 ▼                 ▼                 ▼
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│ Backend │     │ Backend │     │ Backend │     │ Backend │
│  Node 1 │     │  Node 2 │     │  Node 3 │     │  Node N │
└────┬────┘     └────┬────┘     └────┬────┘     └────┬────┘
     │               │               │               │
     └───────────────┴───────────────┴───────────────┘
                     │
     ┌───────────────┼───────────────┐
     ▼               ▼               ▼
┌─────────┐   ┌─────────┐   ┌─────────┐
│PostgreSQL│   │  Redis  │   │ Milvus  │
│  (RDS)  │   │ (Elasti)│   │(Self-host)│
└─────────┘   └─────────┘   └─────────┘
```

### 9.2 配置管理

```bash
# .env.example
DATABASE_URL=postgresql+asyncpg://postgres:xxx@localhost:5432/rag_db
REDIS_URL=redis://:xxx@localhost:6379
MILVUS_HOST=localhost
MILVUS_PORT=19530
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
```

---

## 十、附录

### 10.1 相关文档

- [AGENT_PRD.md](AGENT_PRD.md) - 需求文档
- [ARCHITECTURE.md](ARCHITECTURE.md) - 架构文档
- [HARNESS_5_CORES.md](HARNESS_5_CORES.md) - 5 大核心子系统
- [REFACTOR_PLAN.md](REFACTOR_PLAN.md) - 重构计划
- [README_HARNESS.md](README_HARNESS.md) - 使用指南

### 10.2 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0 | 2026-06-01 | 初始版本 |
| 2.0 | 2026-08-06 | 三层架构重构 |
