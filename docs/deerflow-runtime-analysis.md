# DeerFlow 运行时设计分析

## 1. 运行时架构概述

DeerFlow 的运行时基于 **LangGraph Agent Runtime** 构建，采用**中间件链** + **状态机**的设计模式。

### 1.1 核心设计模式

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         make_lead_agent(config)                          │
│                        (LangGraph Agent Factory)                         │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           Middleware Chain                               │
│                                                                          │
│  基础层 (build_lead_runtime_middlewares):                                │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ 1. ThreadDataMiddleware  - 线程数据路径初始化                       │ │
│  │ 2. UploadsMiddleware     - 注入上传文件列表                         │ │
│  │ 3. SandboxMiddleware     - 获取沙箱环境                             │ │
│  │ 4. DanglingToolCallMiddleware - 修补悬空工具调用                    │ │
│  │ 5. ToolErrorHandlingMiddleware - 工具异常转 ToolMessage             │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  功能层 (_build_middlewares):                                            │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ 6. SummarizationMiddleware - 上下文压缩 (可选)                      │ │
│  │ 7. TodoListMiddleware      - 任务跟踪 (计划模式)                    │ │
│  │ 8. TitleMiddleware         - 自动生成标题                           │ │
│  │ 9. MemoryMiddleware        - 异步记忆更新                           │ │
│  │ 10. ViewImageMiddleware    - 视觉模型支持                           │ │
│  │ 11. DeferredToolFilterMiddleware - 延迟工具过滤                     │ │
│  │ 12. SubagentLimitMiddleware - 限制并发子智能体                      │ │
│  │ 13. LoopDetectionMiddleware - 循环检测                              │ │
│  │ 14. ClarificationMiddleware - 澄清请求拦截 (必须是最后一个)         │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              Agent Core                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐   │
│  │      Model       │  │      Tools       │  │    System Prompt     │   │
│  │  create_chat_model│ │ get_available_tools│ │ apply_prompt_template│   │
│  └──────────────────┘  └──────────────────┘  └──────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 中间件设计

### 2.1 中间件执行顺序

中间件按照**严格顺序**执行，每个中间件可以：
- `before_agent()`: 在模型调用前修改状态
- `after_agent()`: 在模型调用后修改状态
- `wrap_tool_call()`: 包装工具调用

```python
# 中间件构建流程 (agent.py:207-259)
def _build_middlewares(config, model_name, agent_name=None):
    middlewares = build_lead_runtime_middlewares(lazy_init=True)  # 基础层
    
    # 功能层
    if summarization_enabled:
        middlewares.append(summarization_middleware)
    if is_plan_mode:
        middlewares.append(todo_list_middleware)
    middlewares.append(TitleMiddleware())
    middlewares.append(MemoryMiddleware(agent_name=agent_name))
    if model_supports_vision:
        middlewares.append(ViewImageMiddleware())
    if tool_search_enabled:
        middlewares.append(DeferredToolFilterMiddleware())
    if subagent_enabled:
        middlewares.append(SubagentLimitMiddleware())
    middlewares.append(LoopDetectionMiddleware())
    middlewares.append(ClarificationMiddleware())  # 必须是最后一个
    return middlewares
```

### 2.2 关键中间件详解

#### ThreadDataMiddleware
**职责**: 初始化线程数据目录路径

```python
class ThreadDataMiddleware(AgentMiddleware):
    def before_agent(self, state, runtime):
        thread_id = runtime.context["thread_id"]
        paths = self._get_thread_paths(thread_id)
        # 懒加载：只计算路径，不创建目录
        return {"thread_data": {"workspace_path": ..., "uploads_path": ..., "outputs_path": ...}}
```

**目录结构**:
```
backend/.deer-flow/threads/{thread_id}/user-data/
├── workspace/    # 智能体工作目录
├── uploads/      # 上传文件
└── outputs/      # 输出结果
```

#### SandboxMiddleware
**职责**: 获取和释放沙箱环境

```python
class SandboxMiddleware(AgentMiddleware):
    def before_agent(self, state, runtime):
        if self._lazy_init:
            return  # 懒加载：首次工具调用时才获取
        thread_id = runtime.context["thread_id"]
        sandbox_id = provider.acquire(thread_id)
        return {"sandbox": {"sandbox_id": sandbox_id}}
    
    def after_agent(self, state, runtime):
        # 注意：不立即释放，沙箱在同一线程内复用
        return
```

**生命周期**:
- 懒加载模式：首次工具调用时获取
- 沙箱在同一次线程执行中复用
- 应用关闭时统一清理

#### ToolErrorHandlingMiddleware
**职责**: 将工具异常转换为错误 ToolMessage

```python
class ToolErrorHandlingMiddleware(AgentMiddleware):
    def wrap_tool_call(self, request, handler):
        try:
            return handler(request)
        except GraphBubbleUp:
            raise  # 保留 LangGraph 控制流信号
        except Exception as exc:
            return ToolMessage(
                content=f"Error: Tool '{tool_name}' failed: {detail}",
                tool_call_id=tool_call_id,
                status="error"
            )
```

#### ClarificationMiddleware
**职责**: 拦截 `ask_clarification` 工具调用，中断执行

```python
class ClarificationMiddleware(AgentMiddleware):
    def after_agent(self, state, runtime):
        if model_called_ask_clarification:
            return Command(goto=END)  # 中断执行，等待用户回复
```

**为什么必须是最后一个**: 确保所有其他中间件处理完成后，才判断是否需要澄清。

---

## 3. 状态管理

### 3.1 ThreadState 设计

```python
class ThreadState(AgentState):
    # LangGraph 基础
    messages: list[BaseMessage]
    
    # DeerFlow 扩展
    sandbox: dict                    # 沙箱信息 {"sandbox_id": "..."}
    thread_data: dict                # 目录路径 {workspace, uploads, outputs}
    artifacts: list[str]             # 生成的文件路径
    title: str | None                # 对话标题
    todos: list[dict]                # 任务列表 (计划模式)
    uploaded_files: dict             # 上传文件信息
    viewed_images: dict              # 视觉模型图像
```

### 3.2 状态更新流程

```
用户消息
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Middleware Chain (before_agent)                            │
│  - 注入 thread_data, sandbox, uploaded_files 等到 state      │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Model (LLM)                                                │
│  - 接收 messages + 注入的上下文                              │
│  - 可能生成 tool_calls                                       │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Tool Execution                                             │
│  - 工具通过沙箱执行                                          │
│  - ToolErrorHandlingMiddleware 包装异常                      │
│  - 结果作为 ToolMessage 添加到 messages                      │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Middleware Chain (after_agent)                             │
│  - TitleMiddleware: 生成标题                                 │
│  - MemoryMiddleware: 队列对话用于记忆更新                    │
│  - ClarificationMiddleware: 检查是否需要澄清                 │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  SSE Stream Response                                        │
│  - event: values (完整状态)                                  │
│  - event: messages-tuple (单条消息更新)                      │
│  - event: end (执行结束)                                     │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. 工具执行流程

### 4.1 工具调用链

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Tool Execution Flow                               │
└─────────────────────────────────────────────────────────────────────────┘

LLM 生成 tool_call
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  wrap_tool_call() - ToolErrorHandlingMiddleware                         │
│  try:                                                                   │
│      handler(request)  # 执行工具                                        │
│  except Exception:                                                      │
│      return ToolMessage(status="error", content=...)                    │
└─────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  工具实现 (例如 bash 工具)                                                │
│  - 从 state 获取 sandbox_id                                             │
│  - 调用 sandbox.execute_command(command)                                │
│  - 虚拟路径转换 /mnt/... → 实际路径                                      │
└─────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Sandbox 执行                                                             │
│  - LocalSandbox: 直接执行命令                                            │
│  - AioSandbox: Docker 容器内执行                                         │
│  - 返回 stdout, stderr, return_code                                     │
└─────────────────────────────────────────────────────────────────────────┘
    │
    ▼
ToolMessage 添加到 messages
```

### 4.2 工具来源

```python
# tools/__init__.py:get_available_tools()
def get_available_tools(groups=None, include_mcp=True, model_name=None, subagent_enabled=False):
    tools = []
    
    # 1. 配置定义的工具 (config.yaml)
    tools.extend(resolve_config_tools(groups))
    
    # 2. MCP 工具 (懒加载，带缓存)
    if include_mcp:
        tools.extend(get_cached_mcp_tools())
    
    # 3. 内置工具
    tools.append(present_files_tool)
    tools.append(ask_clarification_tool)
    if model_supports_vision:
        tools.append(view_image_tool)
    
    # 4. 子智能体工具 (如启用)
    if subagent_enabled:
        tools.append(task_tool)
    
    return tools
```

---

## 5. 运行时配置

### 5.1 配置参数传递

```python
# LangGraph SDK 调用示例
client.runs.stream(
    thread_id,
    "lead_agent",
    input={"messages": [...]},
    config={
        "configurable": {
            "model_name": "gpt-4",      # 模型选择
            "thinking_enabled": True,   # 思考模式
            "is_plan_mode": True,       # 计划模式
            "subagent_enabled": True,   # 子智能体
            "max_concurrent_subagents": 3,
            "agent_name": "custom_agent"
        }
    }
)
```

### 5.2 模型解析

```python
# agent.py:25-37
def _resolve_model_name(requested_model_name=None):
    app_config = get_app_config()
    default_model = app_config.models[0].name if app_config.models else None
    
    # 优先级：请求的模型 > 默认模型
    if requested_model_name and app_config.get_model_config(requested_model_name):
        return requested_model_name
    
    return default_model
```

---

## 6. 流式响应

### 6.1 LangGraph SSE 协议

```
event: values
data: {"messages": [...], "title": "...", "artifacts": [...]}

event: messages-tuple
data: {"type": "ai", "content": "Hello! How can I help?"}

event: messages-tuple
data: {"type": "tool_call", "name": "bash", "args": {"command": "ls"}}

event: end
data: {}
```

### 6.2 流式处理流程

```python
# LangGraph Server 内部
async for event, metadata in graph.astream(
    initial_state,
    config=config,
    stream_mode=["values", "messages-tuple"],
):
    # event: 事件类型 (values, messages-tuple, etc.)
    # metadata: 元数据 (langgraph_step, langgraph_task, etc.)
    yield event
```

---

## 7. 内存与性能优化

### 7.1 懒加载策略

| 组件 | 懒加载时机 |
|------|----------|
| ThreadDataMiddleware | 只计算路径，目录按需创建 |
| SandboxMiddleware | 首次工具调用时获取 |
| MCP Tools | 首次使用时加载 |
| Skills | 启动时解析，缓存在内存 |

### 7.2 缓存策略

```python
# MCP 工具缓存
_mcp_tools_cache = None
_mcp_config_mtime = 0

def get_cached_mcp_tools():
    current_mtime = get_config_mtime()
    if current_mtime != _mcp_config_mtime:
        # 配置变更，重新加载
        _mcp_tools_cache = load_mcp_tools()
        _mcp_config_mtime = current_mtime
    return _mcp_tools_cache
```

### 7.3 上下文管理

```python
# SummarizationMiddleware 触发条件
trigger = [
    ("tokens", 100000),      # token 数超过 100k
    ("messages", 100),       # 消息数超过 100 条
    ("fraction", 0.8),       # 达到最大上下文的 80%
]
keep = ("last", 20)  # 保留最近 20 条消息
```

---

## 8. 子智能体运行时

### 8.1 子智能体架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      Subagent Runtime                                    │
└─────────────────────────────────────────────────────────────────────────┘

Lead Agent 调用 task() 工具
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  SubagentExecutor                                                       │
│  - _scheduler_pool: 3 workers (调度)                                    │
│  - _execution_pool: 3 workers (执行)                                    │
│  - MAX_CONCURRENT_SUBAGENTS = 3                                         │
│  - 15 分钟超时                                                           │
└─────────────────────────────────────────────────────────────────────────┘
    │
    ├──▶ Subagent 1: general-purpose (后台线程)
    │       - 独立的 LangGraph Agent
    │       - 使用除 task 外的所有工具
    │       - 独立的中间件链
    │
    ├──▶ Subagent 2: bash (后台线程)
    │       - 命令执行专家
    │       - 简化的中间件链
    │
    └──▶ Subagent 3: custom (后台线程)
            - 用户自定义智能体
            - 从 registry 加载
```

### 8.2 子智能体事件流

```
event: task_started
data: {"task_id": "...", "description": "..."}

event: task_running
data: {"task_id": "...", "update": "Working on..."}

event: task_completed  # 或 task_failed / task_timed_out
data: {"task_id": "...", "result": "..."}
```

---

## 9. 错误处理

### 9.1 错误类型与处理

| 错误类型 | 处理方式 |
|---------|---------|
| 工具异常 | ToolErrorHandlingMiddleware → ToolMessage |
| 模型调用失败 | LangGraph 重试机制 |
| 沙箱获取失败 | 抛出异常，中断执行 |
| 内存不足 | SummarizationMiddleware 压缩上下文 |
| 循环调用 | LoopDetectionMiddleware 检测并中断 |

### 9.2 GraphBubbleUp 保护

```python
def wrap_tool_call(self, request, handler):
    try:
        return handler(request)
    except GraphBubbleUp:
        # 保留 LangGraph 控制流信号 (interrupt/pause/resume)
        raise
    except Exception as exc:
        # 其他异常转为 ToolMessage
        return self._build_error_message(request, exc)
```

---

## 10. 总结

### DeerFlow 运行时核心设计原则

1. **中间件链**: 可扩展的请求处理管道，每个中间件职责单一
2. **懒加载**: 按需初始化，减少启动时间和资源消耗
3. **状态隔离**: 每个线程独立的状态空间
4. **沙箱执行**: 安全的代码执行环境
5. **流式响应**: SSE 实时返回，降低首 token 延迟
6. **错误隔离**: 工具异常不中断整体执行流
7. **上下文管理**: 智能压缩，保持长对话可用性

### 运行时扩展点

- **自定义中间件**: 继承 `AgentMiddleware` 实现新逻辑
- **自定义工具**: 通过 config.yaml 或 MCP 添加
- **自定义技能**: 添加 SKILL.md 到 skills 目录
- **自定义子智能体**: 注册到 subagents.registry
- **自定义模型**: config.yaml 添加新模型配置
