# Agent Graph Factory 实现总结

## 概述

基于 LangGraph ServerRuntime 的工厂函数模式，实现了 Agent 图的运行时动态构建能力。

## 已实现的功能

### 1. 核心服务层

#### `agent_graph_factory.py`
- **AgentState**: 运行时状态容器，支持动态扩展
- **BaseMiddleware**: 中间件基类
- **TodoListMiddleware**: 计划模式中间件
- **LoggingMiddleware**: 日志中间件
- **DynamicModelLoader**: 动态模型加载器
- **MCPToolLoader**: MCP 工具加载器
- **SkillLoader**: 技能渐进式加载器
- **AgentGraphFactory**: 图工厂核心类

#### `agent_runtime_service.py` (v2.0 更新)
- `AgentRuntime.__init__`: 新增 `use_factory_mode` 参数
- `AgentRuntime._get_or_build_graph`: 支持工厂模式
- `AgentRuntime.run_with_factory`: 工厂模式运行方法
- `AgentRuntime.run_stream_with_factory`: 工厂模式流式运行

### 2. 数据模型扩展

#### `agent.py`
```python
class AgentConfig(Base):
    # 新增字段
    extensions_config: Mapped[Optional[dict]]  # 扩展配置
```

### 3. 配置文件

#### `extensions_config.example.json`
- MCP 服务器配置
- 自定义工具配置
- 中间件配置

### 4. 数据库迁移

#### `006_add_extensions_config.py`
- 添加 `extensions_config` 字段到 `agent_configs` 表

### 5. 测试

#### `test_agent_graph_factory.py`
- AgentState 测试
- TodoListMiddleware 测试
- LoggingMiddleware 测试
- DynamicModelLoader 测试
- MCPToolLoader 测试
- AgentGraphFactory 测试
- 集成测试

### 6. 文档

#### `AGENT_GRAPH_FACTORY.md`
- 架构设计说明
- 快速开始指南
- 配置详解
- API 参考
- 最佳实践

## 架构图

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

## 使用示例

### 启用工厂模式

```python
from app.services.agent_runtime_service import AgentRuntime

runtime = AgentRuntime(
    db=db_session,
    model_gateway_service=model_gateway,
    skill_registry=skill_registry,
    use_factory_mode=True,  # 启用工厂模式
)
```

### 运行时配置覆盖

```python
runtime_config = {
    "model_name": "claude-3-opus",      # 动态模型选择
    "plan_mode": True,                  # 启用计划模式
    "skills": ["web_search"],           # 技能覆盖
    "mcp_servers": ["filesystem"],      # MCP 服务器
}

result = await runtime.run_with_factory(
    agent_id="agent-123",
    user_id=1,
    query="帮我分析这个项目",
    model_config=base_model_config,
    runtime_config=runtime_config,
)
```

## 核心特性

### 1. 运行时动态构建图
每次执行时重新构建 LangGraph，支持：
- 动态模型切换
- 动态工具装配
- 动态中间件链

### 2. 动态模型选择
```python
llm = await loader.load_model(
    requested_model_name="claude-3-opus",
    default_config={"provider": "anthropic", "model": "claude-3-5-sonnet"}
)
```

### 3. MCP 工具动态加载
从 `extensions_config.json` 自动发现并集成 MCP 服务器工具。

### 4. 技能渐进式加载
仅在需要时加载技能模块，减少内存占用。

### 5. 中间件链
```python
# 计划模式中间件
if extensions_config.get("plan_mode_enabled"):
    middlewares.append(TodoListMiddleware())

# 日志中间件（始终启用）
middlewares.append(LoggingMiddleware(agent_id, run_id))
```

## 文件清单

```
backend/
├── app/
│   ├── models/
│   │   └── agent.py                          # 添加 extensions_config 字段
│   ├── services/
│   │   ├── agent_runtime_service.py          # v2.0 更新
│   │   └── agent_graph_factory.py            # 新增
│   └── docs/
│       └── AGENT_GRAPH_FACTORY.md            # 新增文档
├── alembic/
│   └── versions/
│       └── 006_add_extensions_config.py      # 新增迁移
├── tests/
│   └── agent/
│       └── test_agent_graph_factory.py       # 新增测试
└── extensions_config.example.json            # 新增配置示例
```

## 待实现功能

1. **完整的 MCP 连接** - 当前为 stub 实现
2. **自定义中间件加载** - 从配置动态加载中间件
3. **技能 Python 函数加载** - 完整的动态导入逻辑
4. **连接池优化** - MCP 服务器连接复用
5. **配置缓存** - 减少数据库查询

## 最佳实践

1. **拓扑一致性** - 即使动态加载，图结构应保持一致
2. **资源懒加载** - 使用 `execution_runtime` 判断是否真正执行
3. **配置缓存** - 缓存数据库查询结果
4. **错误处理** - 每个加载器都有完善的错误处理

## 下一步

1. 实现完整的 MCP 连接逻辑
2. 添加更多中间件示例
3. 性能基准测试
4. 生产环境配置优化
