# Agent Graph Factory 使用指南

基于 LangGraph ServerRuntime 的工厂函数模式，实现 Agent 图的运行时动态构建。

## 核心特性

1. **运行时动态构建图** - 每次执行时重新构建 LangGraph
2. **动态模型选择** - 无需重启服务即可切换模型
3. **MCP 工具动态加载** - 从配置文件自动发现并集成工具
4. **技能渐进式加载** - 仅在需要时加载技能模块
5. **中间件链** - 插件化功能扩展（如计划模式）

## 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                    Client Request                            │
│  { model: "claude-sonnet", plan_mode: true, skills: [...] } │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              AgentGraphFactory.create_graph()                │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 1. 解析配置 (AgentConfig + RuntimeConfig)             │  │
│  │ 2. 动态加载组件                                        │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
    ┌─────────────────┐ ┌─────────────┐ ┌─────────────┐
    │ DynamicModel    │ │ MCPServer   │ │ Skill       │
    │ Loader          │ │ Loader      │ │ Loader      │
    └─────────────────┘ └─────────────┘ └─────────────┘
              │               │               │
              └───────────────┼───────────────┘
                              ▼
                    ┌─────────────────┐
                    │ Middlewares     │
                    │ - TodoList      │
                    │ - Logging       │
                    └─────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              StateGraph 动态构建 & compile()                 │
└─────────────────────────────────────────────────────────────┘
```

## 快速开始

### 1. 配置 Agent

```python
from app.models.agent import AgentConfig

agent = AgentConfig(
    id="agent-123",
    name="智能助手",
    system_prompt="你是一个有帮助的助手。",
    agent_type="single",
    default_model_config={
        "provider": "anthropic",
        "model": "claude-3-5-sonnet",
        "temperature": 0.7,
    },
    enabled_skills=["web_search", "code_interpreter"],
    extensions_config={
        "plan_mode_enabled": True,
        "mcp_servers_enabled": ["filesystem", "github"],
        "middleware_config": {
            "logging": {"level": "info"},
        }
    }
)
```

### 2. 初始化 AgentRuntime（工厂模式）

```python
from app.services.agent_runtime_service import AgentRuntime

runtime = AgentRuntime(
    db=db_session,
    model_gateway_service=model_gateway,
    skill_registry=skill_registry,
    use_factory_mode=True,  # 启用工厂模式
)
```

### 3. 运行时配置覆盖

```python
from app.schemas.chat import ModelConfig

# 基础模型配置
base_model_config = ModelConfig(
    provider="anthropic",
    model="claude-3-5-sonnet",
    temperature=0.7,
)

# 运行时配置覆盖
runtime_config = {
    "model_name": "claude-3-opus",  # 动态切换模型
    "plan_mode": True,               # 启用计划模式
    "skills": ["web_search"],        # 技能覆盖
    "mcp_servers": ["filesystem"],   # MCP 服务器
}

# 运行 Agent
result = await runtime.run_with_factory(
    agent_id="agent-123",
    user_id=1,
    query="帮我分析一下这个项目",
    model_config=base_model_config,
    runtime_config=runtime_config,
)
```

## 配置详解

### extensions_config.json

```json
{
  "mcp_servers": {
    "filesystem": {
      "enabled": true,
      "name": "Filesystem MCP Server",
      "transport_type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/workspace"],
      "tools": ["read_file", "write_file", "list_directory"]
    },
    "github": {
      "enabled": false,
      "name": "GitHub MCP Server",
      "transport_type": "sse",
      "url": "https://github-mcp-server.example.com/sse",
      "tools": ["search_repos", "get_pull_request"]
    }
  },
  "custom_tools": {
    "code_executor": {
      "enabled": true,
      "type": "python",
      "entry_point": "app.tools.code_executor:execute_code",
      "sandbox": true,
      "timeout_seconds": 30
    }
  },
  "middleware_config": {
    "plan_mode": {
      "enabled_by_default": false,
      "auto_detect_tasks": true,
      "max_tasks": 10
    }
  }
}
```

### AgentConfig 扩展字段

```python
# 数据库模型扩展
class AgentConfig(Base):
    # ... 原有字段 ...

    # 扩展配置 - 用于工厂模式
    extensions_config: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True, default=dict
    )
    # {
    #   "plan_mode_enabled": false,
    #   "mcp_servers_enabled": ["server1", "server2"],
    #   "middleware_config": {...},
    # }
```

## 动态组件加载

### 1. 动态模型选择

```python
from app.services.agent_graph_factory import DynamicModelLoader

loader = DynamicModelLoader(model_gateway)

# 运行时选择模型
llm = await loader.load_model(
    requested_model_name="claude-3-opus",  # 用户请求的模型
    default_config={"provider": "anthropic", "model": "claude-3-5-sonnet"}
)
```

### 2. MCP 工具加载

```python
from app.services.agent_graph_factory import MCPToolLoader

loader = MCPToolLoader("extensions_config.json")

# 加载启用的 MCP 服务器
tools = await loader.load_tools(
    enabled_servers=["filesystem", "github"]
)
```

### 3. 技能渐进式加载

```python
from app.services.agent_graph_factory import SkillLoader

loader = SkillLoader(skill_registry, db)

# 按需加载技能
tools = await loader.load_skills(
    enabled_skill_ids=["skill-1", "skill-2"]
)
```

### 4. 中间件链构建

```python
from app.services.agent_graph_factory import (
    TodoListMiddleware,
    LoggingMiddleware,
)

# 计划模式中间件
if plan_mode_enabled:
    middlewares.append(TodoListMiddleware())

# 日志中间件（始终启用）
middlewares.append(LoggingMiddleware(agent_id, run_id))
```

## LangGraph ServerRuntime 集成

### 工厂函数模式

```python
from langchain_core.runnables import RunnableConfig
from langgraph_sdk.runtime import ServerRuntime
from langgraph.graph import StateGraph

async def make_graph(config: RunnableConfig, runtime: ServerRuntime):
    """
    LangGraph ServerRuntime 工厂函数

    每次运行时被调用，动态构建图
    """
    # 获取运行时配置
    configurable = config.get("configurable", {})
    user_id = configurable.get("user_id")
    plan_mode = configurable.get("plan_mode", False)

    # 获取用户上下文
    user = runtime.ensure_user()

    # 动态构建图
    graph = StateGraph(AgentState)
    # ... 添加节点和边 ...

    return graph.compile()
```

### langgraph.json 配置

```json
{
    "$schema": "https://langgra.ph/schema.json",
    "dependencies": ["."],
    "graphs": {
        "lead_agent": "my_project.agents:make_graph"
    }
}
```

## 中间件开发

### 自定义中间件

```python
from app.services.agent_graph_factory import BaseMiddleware, AgentState

class RateLimitMiddleware(BaseMiddleware):
    """限流中间件"""

    def __init__(self, requests_per_minute: int = 60):
        self.rpm = requests_per_minute
        self._counter = {}

    async def pre_process(self, state: AgentState) -> AgentState:
        user_id = state["metadata"].get("user_id")
        now = time.time()

        # 简单的限流逻辑
        if user_id not in self._counter:
            self._counter[user_id] = []

        # 清理旧请求
        self._counter[user_id] = [
            t for t in self._counter[user_id]
            if now - t < 60
        ]

        if len(self._counter[user_id]) >= self.rpm:
            raise Exception("Rate limit exceeded")

        self._counter[user_id].append(now)
        return state
```

## 最佳实践

### 1. 拓扑一致性

即使动态加载组件，图的节点名和边结构应保持一致：

```python
# 正确：拓扑一致
def build_graph(tools):
    graph = StateGraph(AgentState)
    graph.add_node("agent", create_agent_node(tools))  # 节点名始终为 "agent"
    graph.add_edge(START, "agent")
    graph.add_edge("agent", END)
    return graph.compile()

# 错误：拓扑不一致
def build_graph(tools):
    graph = StateGraph(AgentState)
    if tools:
        graph.add_node("agent_with_tools", ...)  # 节点名变化！
    else:
        graph.add_node("agent", ...)
    # 这会导致状态持久化问题
```

### 2. 资源懒加载

使用 `execution_runtime` 判断是否真正执行：

```python
from langgraph_sdk.runtime import ServerRuntime
from contextlib import asynccontextmanager

@asynccontextmanager
async def make_graph(runtime: ServerRuntime):
    if runtime.execution_runtime:
        # 只在执行时加载昂贵资源
        tools = await load_mcp_tools()
        yield build_graph(tools)
    else:
        # introspection 时返回最小图
        yield build_graph([])
```

### 3. 配置缓存

缓存数据库查询结果：

```python
from functools import lru_cache

class AgentGraphFactory:
    @lru_cache(maxsize=100)
    def _get_cached_config(self, agent_id: str) -> dict:
        # 缓存 Agent 配置
        pass
```

## 性能优化

| 优化点 | 策略 |
|--------|------|
| 模型加载 | 缓存 LLM 实例，避免重复创建 |
| MCP 连接 | 连接池复用，避免每次重建 |
| 技能加载 | 懒加载 + 缓存 |
| 中间件 | 按需启用，避免不必要开销 |

## 故障排查

### 日志配置

```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.services.agent_graph_factory")

# 启用详细日志
logger.setLevel(logging.DEBUG)
```

### 常见问题

1. **图构建失败**
   - 检查 Agent 配置是否完整
   - 确认 MCP 配置文件存在且格式正确

2. **技能加载失败**
   - 检查技能 ID 是否正确
   - 确认技能模块可导入

3. **中间件未生效**
   - 检查 `extensions_config` 配置
   - 确认中间件类正确实现

## API 参考

### AgentGraphFactory

```python
class AgentGraphFactory:
    def __init__(self, model_gateway, skill_registry, db)

    async def build_graph_for_run(
        agent_id: str,
        user_id: int,
        runtime_config: dict,
        run_id: str,
    ) -> CompiledStateGraph

    @asynccontextmanager
    async def create_graph(
        agent_config: Any,
        runtime_config: dict,
        run_id: str,
    ) -> AsyncGenerator[CompiledStateGraph, None]
```

### AgentRuntime（工厂模式）

```python
class AgentRuntime:
    async def run_with_factory(
        agent_id: str,
        user_id: int,
        query: str,
        model_config: ModelConfig,
        runtime_config: Optional[dict] = None,
        session_id: Optional[str] = None,
    ) -> dict

    async def run_stream_with_factory(
        agent_id: str,
        user_id: int,
        query: str,
        model_config: ModelConfig,
        runtime_config: Optional[dict] = None,
        session_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]
```
