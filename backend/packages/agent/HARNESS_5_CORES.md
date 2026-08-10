# Harness 5 大核心子系统映射文档

> 将 Harness 架构理论与当前代码实现进行映射

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

---

## 一、运行时引擎 (Runtime Engine)

**职责**: 智能体循环、状态管理、流式处理

### 1.1 智能体循环 (Agent Loop)

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| TAO 循环引擎 | `runtime_engine/tao_graph.py` | ✅ 已实现 |
| Think 节点 | `build_tao_graph() → think_node` | ✅ |
| Act 节点 | `build_tao_graph() → ToolNode` | ✅ |
| Observe 节点 | `build_tao_graph() → observe_node` | ✅ |
| 终止条件检查 | `should_act()` 路由函数 | ✅ |

**核心代码**:
```python
# runtime_engine/tao_graph.py
def build_tao_graph(llm, tools, max_iterations=10):
    graph = StateGraph(TAOState)
    graph.add_node("think", create_think_node(llm))
    graph.add_node("act", ToolNode(tools))
    graph.add_node("observe", create_observe_node())
    
    # 条件边：Think 后决定是 Act 还是结束
    graph.add_conditional_edges("think", should_act, {"act": "act", "end": END})
    graph.add_edge("act", "observe")
    graph.add_edge("observe", "think")  # 自环
    
    return graph.compile()
```

### 1.2 状态管理 (State Management)

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| 状态定义 | `runtime_engine/tao_graph.py → TAOState` | ✅ |
| 状态快照 | `runtime/agent_runtime.py → get_state()` | ✅ |
| 状态修补 | `runtime/agent_runtime.py → patch_state()` | ✅ |
| Checkpoint | `services/agent_checkpoint_service.py` | ✅ |

**核心代码**:
```python
# runtime/agent_runtime.py
class AgentRuntime:
    async def get_state(self, graph, thread_id):
        """获取状态快照 (时间旅行)"""
        config = {"configurable": {"thread_id": thread_id}}
        state = await graph.aget_state(config)
        return state.values if state else None
    
    async def patch_state(self, graph, thread_id, values):
        """修补状态 (时间旅行修改)"""
        config = {"configurable": {"thread_id": thread_id}}
        await graph.aupdate_state(config, values)
```

### 1.3 流式处理 (Streaming)

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| 流式执行 | `runtime/agent_runtime.py → execute_stream()` | ✅ |
| 事件格式化 | `runtime/agent_runtime.py → _format_event()` | ✅ |
| Stream Mode | LangGraph `astream(stream_mode="messages")` | ✅ |

**核心代码**:
```python
# runtime/agent_runtime.py
async def execute_stream(self, graph, state, thread_id):
    async for event, metadata in graph.astream(
        state, config=config, stream_mode="messages"
    ):
        yield self._format_event(event, metadata)
```

---

## 二、工具层 (Tools Layer)

**职责**: 注册、发现、执行、权限

### 2.1 工具注册 (Registration)

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| 工具注册接口 | `runtime_engine/action.py → ActionEngine.register_tool()` | ⚠️ 已弃用 |
| LangGraph ToolNode | `langgraph.prebuilt.ToolNode` | ✅ 推荐 |
| MCP 工具加载 | `mcp/client.py → MCPClient` | ✅ |
| 技能工具加载 | `services/skill_registry.py` | ✅ |

**核心代码**:
```python
# mcp/client.py
class MCPClient:
    async def get_all_langchain_tools(self) -> List[Any]:
        """获取所有 MCP 工具"""
        tools = []
        for tool_def in self._tools:
            langchain_tool = await self.create_langchain_tool(tool_def)
            tools.append(langchain_tool)
        return tools
```

### 2.2 工具发现 (Discovery)

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| MCP 工具发现 | `mcp/tools/` (kb/model/prompt/agent) | ✅ |
| 技能发现 | `skills/` (knowledge_base/model/prompt) | ✅ |
| 内置工具 | `tools/builtins.py` | ✅ |

**工具来源**:
```
┌─────────────────────────────────────────────┐
│            AgentFactory._load_tools()       │
│                                             │
│  1. 基础工具 → tools/builtins.py            │
│  2. MCP 工具 → mcp/client.py                │
│  3. 技能工具 → skills/*.py                  │
│  4. RAG 工具 → services/retrieval_service   │
│  5. Task 工具 → multi-agent 场景            │
└─────────────────────────────────────────────┘
```

### 2.3 工具执行 (Execution)

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| 工具执行引擎 | `langgraph.prebuilt.ToolNode` | ✅ 推荐 |
| 旧执行引擎 | `runtime_engine/action.py` | ⚠️ 已弃用 |
| 代码沙箱执行 | `sandbox/nsjail.py` | ✅ |

**核心代码**:
```python
# 使用 LangGraph ToolNode (推荐)
from langgraph.prebuilt import ToolNode

tool_node = ToolNode(tools)
graph.add_node("tools", tool_node)
```

### 2.4 工具权限 (Permission)

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| 权限检查 | `runtime_engine/permission.py → PermissionEngine` | ✅ |
| 梯度权限 | FREE / ASK_FIRST / APPROVE_ONCE | ✅ |
| 权限缓存 | `PermissionEngine._permission_cache` | ✅ |

**核心代码**:
```python
# runtime_engine/permission.py
class PermissionEngine:
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

## 三、记忆系统 (Memory System)

**职责**: 工作记忆、短期记忆、长期记忆

### 3.1 工作记忆 (Working Memory)

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| 对话历史 | `models/agent.py → AgentMemory` | ✅ |
| 会话消息 | `models/session.py → AgentSessionMessage` | ✅ |
| 上下文管理 | `services/agent_memory_service.py` | ✅ |

**核心代码**:
```python
# services/agent_memory_service.py
class AgentMemoryService:
    async def get_conversation(self, agent_id, user_id, thread_id):
        """获取对话历史 (工作记忆)"""
        result = await self.db.execute(
            select(AgentMemory)
            .where(AgentMemory.thread_id == thread_id)
            .order_by(AgentMemory.created_at.desc())
            .limit(50)
        )
        return [m.content for m in result.scalars().all()]
```

### 3.2 短期记忆 (Short-term Memory)

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| 对话摘要 | `services/agent_memory_service.py → create_summary()` | ✅ |
| Token 预算 | `runtime_engine/token_budget.py → TokenBudgetManager` | ✅ |
| 上下文压缩 | `TokenBudgetManager._compress_if_needed()` | ✅ |

**核心代码**:
```python
# runtime_engine/token_budget.py
class TokenBudgetManager:
    async def _compress_if_needed(self):
        """上下文压缩"""
        strategy = self.config.compression_strategy
        
        if strategy == CompressionStrategy.SUMMARIZE:
            return self._summarize_oldest()  # 摘要压缩
        
        if strategy == CompressionStrategy.SLIDING_WINDOW:
            return self._sliding_window_compress()  # 滑动窗口
```

### 3.3 长期记忆 (Long-term Memory)

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| 向量记忆 | `models/agent.py → AgentMemory (memory_type=vector)` | ✅ |
| Milvus 集成 | `services/retrieval_service.py` | ✅ |
| 记忆检索 | `services/retrieval_service.py → search_chunks()` | ✅ |

**核心代码**:
```python
# services/agent_service.py (RAG 工具)
async def _create_rag_tool(kb_ids, top_k):
    @tool
    async def search_knowledge_base(query: str) -> str:
        """搜索知识库 (长期记忆检索)"""
        milvus = get_milvus_client()
        for kb_id in kb_ids:
            response = await search_chunks(milvus, query, top_k)
        return formatted_results
```

---

## 四、输出治理 (Output Governance)

**职责**: 模型抽象、结构化校验、幻觉检测

### 4.1 模型抽象 (Model Abstraction)

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| LLM 工厂 | `services/agent_runtime_service.py → create_langchain_llm()` | ✅ |
| 多供应商支持 | Anthropic/OpenAI/Google/Ollama/Local | ✅ |
| 统一接口 | LangChain `BaseChatModel` | ✅ |

**核心代码**:
```python
# services/agent_runtime_service.py
async def create_langchain_llm(model_config, db):
    """根据模型配置创建 LLM 实例"""
    provider = model_config.provider.lower()
    
    if provider == "anthropic":
        return ChatAnthropic(model=model_config.model, ...)
    elif provider == "openai":
        return ChatOpenAI(model=model_config.model, ...)
    elif provider == "local_qwen":
        return ChatOpenAI(
            base_url=model_config.base_url,
            api_key=model_config.api_key,
            streaming=True
        )
```

### 4.2 结构化校验 (Structured Validation)

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| 输出解析 | `runtime_engine/parser.py → OutputParser` | ✅ |
| Pydantic Schema | `schemas/*.py` | ✅ |
| 工具调用解析 | `langchain_core.messages.ToolCall` | ✅ |

**核心代码**:
```python
# runtime_engine/parser.py
class OutputParser:
    def parse(self, text: str) -> ParsedOutput:
        """解析 LLM 输出"""
        # 提取推理步骤
        reasoning_steps = self._extract_reasoning(text)
        
        # 提取工具调用
        tool_calls = self._extract_tool_calls(text)
        
        # 提取最终答案
        final_answer = self._extract_final_answer(text)
        
        return ParsedOutput(reasoning_steps, tool_calls, final_answer)
```

### 4.3 幻觉检测 (Hallucination Detection)

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| 注入检测 | `runtime_engine/memory.py → _detect_injection()` | ✅ |
| 内容过滤 | `runtime_engine/memory.py → _sanitize_content()` | ✅ |
| 引用验证 | RAG 检索结果对比 | ✅ |

**核心代码**:
```python
# runtime_engine/memory.py
class MemoryEngine:
    async def _detect_injection(self, content):
        """检测记忆注入攻击"""
        injection_patterns = [
            "ignore previous instructions",
            "forget all previous",
            "system instruction:",
            "you are now",
        ]
        
        for pattern in injection_patterns:
            if pattern in content.lower():
                return True
        return False
```

---

## 五、编排引擎 (Orchestration Engine)

**职责**: 工作流编排、多智能体、依赖管理

### 5.1 工作流编排 (Workflow Orchestration)

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| 状态图构建 | `runtime_engine/orchestration_graph.py` | ✅ |
| 条件边路由 | `graph.add_conditional_edges()` | ✅ |
| 流水线执行 | `OrchestrationMode.PIPELINE` | ✅ |

**核心代码**:
```python
# runtime_engine/orchestration_graph.py
class OrchestrationGraphBuilder:
    def _build_pipeline_graph(self):
        """流水线模式图"""
        graph = StateGraph(OrchestrationState)
        
        prev_node = None
        for worker in self.workers:
            node_name = f"worker_{worker['id']}"
            graph.add_node(node_name, self._create_worker_node(worker))
            
            if prev_node is None:
                graph.add_edge(START, node_name)
            else:
                graph.add_edge(prev_node, node_name)
            prev_node = node_name
        
        graph.add_edge(prev_node, END)
        return graph.compile()
```

### 5.2 多智能体协作 (Multi-Agent Collaboration)

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| Supervisor 模式 | `orchestration_graph.py → _build_supervisor_graph()` | ✅ |
| RoundRobin 模式 | `orchestration_graph.py → _build_round_robin_graph()` | ✅ |
| Voting 模式 | `orchestration_graph.py → _build_voting_graph()` | ✅ |
| Parallel 模式 | `orchestration_graph.py → _build_parallel_graph()` | ✅ |

**协作模式对比**:
```
┌─────────────────────────────────────────────────────────────┐
│ 模式           │ 执行方式        │ 适用场景                  │
├─────────────────────────────────────────────────────────────┤
│ supervisor     │ LLM 动态分配    │ 复杂任务分解              │
│ round_robin    │ 顺序执行        │ 流水线处理                │
│ voting         │ 并行执行后投票  │ 多方案对比                │
│ pipeline       │ 阶段式顺序      │ 研究→写作→审核            │
│ parallel       │ 完全并行        │ 独立子任务                │
└─────────────────────────────────────────────────────────────┘
```

### 5.3 依赖管理 (Dependency Management)

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| 工具依赖 | `services/agent_service.py → AgentFactory` | ✅ |
| 技能依赖 | `services/skill_registry.py` | ✅ |
| MCP 依赖 | `mcp/client.py → MCPClient` | ✅ |

---

## 六、两大基础保障

### 6.1 安全层 (Security)

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| 沙箱隔离 | `sandbox/nsjail.py` | ✅ |
| VM 隔离 | `sandbox/firecracker.py` | ✅ |
| 路径遍历防护 | `services/workspace_service.py` | ✅ |
| 权限门 | `runtime_engine/permission.py` | ✅ |

### 6.2 可观测性层 (Observability)

| 理论组件 | 代码实现 | 状态 |
|----------|----------|------|
| 全链路追踪 | `runtime_engine/governance_callback.py` | ✅ |
| 执行日志 | `models/agent.py → AgentCallLog` | ✅ |
| 调试模式 | `services/agent_monitoring_service.py` | ✅ |
| Token 统计 | `AgentCallLog.input_tokens/output_tokens` | ✅ |

---

## 七、5 大核心子系统完整映射表

| 子系统 | 理论组件 | 代码文件 | 状态 |
|--------|----------|----------|------|
| **运行时引擎** | 智能体循环 | `runtime_engine/tao_graph.py` | ✅ |
| | 状态管理 | `runtime/agent_runtime.py` | ✅ |
| | 流式处理 | `runtime/agent_runtime.py` | ✅ |
| **工具层** | 注册 | `langgraph.prebuilt.ToolNode` | ✅ |
| | 发现 | `mcp/client.py`, `skills/` | ✅ |
| | 执行 | `ToolNode`, `sandbox/nsjail.py` | ✅ |
| | 权限 | `runtime_engine/permission.py` | ✅ |
| **记忆系统** | 工作记忆 | `services/agent_memory_service.py` | ✅ |
| | 短期记忆 | `runtime_engine/token_budget.py` | ✅ |
| | 长期记忆 | `models/agent.py → AgentMemory` | ✅ |
| **输出治理** | 模型抽象 | `services/agent_runtime_service.py` | ✅ |
| | 结构化校验 | `runtime_engine/parser.py` | ✅ |
| | 幻觉检测 | `runtime_engine/memory.py` | ✅ |
| **编排引擎** | 工作流编排 | `runtime_engine/orchestration_graph.py` | ✅ |
| | 多智能体 | `OrchestrationGraphBuilder` | ✅ |
| | 依赖管理 | `services/agent_factory.py` | ✅ |
| **安全层** | 沙箱隔离 | `sandbox/nsjail.py` | ✅ |
| | 权限防护 | `runtime_engine/permission.py` | ✅ |
| **可观测性** | 追踪 | `runtime_engine/governance_callback.py` | ✅ |
| | 日志 | `models/agent.py → AgentCallLog` | ✅ |

---

## 八、架构成熟度评估

| 子系统 | 完成度 | 备注 |
|--------|--------|------|
| 运行时引擎 | 90% | TAO 循环已实现，部分细节待完善 |
| 工具层 | 85% | MCP/技能系统已实现，部分工具待扩展 |
| 记忆系统 | 80% | 对话/向量记忆已实现，摘要压缩待完善 |
| 输出治理 | 75% | 模型抽象/解析已实现，幻觉检测待加强 |
| 编排引擎 | 85% | 5 种协作模式已实现，依赖管理待完善 |
| 安全层 | 90% | NsJail 沙箱已实现，Firecracker 待验证 |
| 可观测性 | 85% | 追踪/日志已实现，可视化待完善 |

**整体成熟度**: 83% (良好)

---

## 九、下一步优化建议

1. **输出治理**: 加强幻觉检测，添加引用来源验证
2. **记忆系统**: 完善摘要压缩，优化 Token 预算管理
3. **可观测性**: 添加可视化 Dashboard，实时监控 Agent 执行
4. **编排引擎**: 增强依赖管理，支持动态子图加载
