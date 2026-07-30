# Agent 分层架构设计

## 概述

本架构采用**工厂模式 + 分层设计**，所有智能体执行都始于统一的工厂函数，分为主智能体（Lead Agent）和子智能体（Subagent）两个层次。

## 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                    Client Request                            │
│         { query: "分析这个项目", plan_mode: true }           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              make_lead_agent() 工厂函数                      │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 每次执行都动态构建                                     │  │
│  │ - 动态模型选择                                         │  │
│  │ - 动态 MCP 工具加载                                     │  │
│  │ - 动态技能加载                                         │  │
│  │ - 中间件链（计划模式等）                               │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Lead Agent                                │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 核心协调者                                             │  │
│  │ - 理解用户意图                                         │  │
│  │ - 制定计划                                             │  │
│  │ - 决定是否需要调用子智能体                             │  │
│  │ - 整合子智能体结果                                     │  │
│  └───────────────────────────────────────────────────────┘  │
│                          │                                    │
│                          ▼                                    │
│              ┌───────────────────────┐                       │
│              │  delegate_to_subagent │ ◄─── task 工具        │
│              └───────────────────────┘                       │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
    ┌─────────────────┐ ┌─────────────┐ ┌─────────────┐
    │ Subagent #1     │ │ Subagent #2 │ │ Subagent #3 │
    │ (代码分析)      │ │ (文档写作)  │ │ (研究分析)  │
    └─────────────────┘ └─────────────┘ └─────────────┘
```

## 核心组件

### 1. Lead Agent Factory (`lead_agent_factory.py`)

**职责**: 每次执行时动态创建 Lead Agent

```python
class LeadAgentFactory:
    """Lead Agent 工厂"""

    async def create_lead_agent(...) -> AsyncGenerator[CompiledGraph, None]:
        """
        工厂函数 - 每次执行时被调用

        1. 解析配置 (AgentConfig + RuntimeConfig)
        2. 动态加载模型、工具、技能
        3. 构建中间件链
        4. 构建并编译 StateGraph
        """
```

**特性**:
- 每次执行都重新构建图
- 支持运行时配置覆盖
- 动态加载 MCP 工具和技能
- 中间件链（计划模式、日志等）

### 2. Subagent Service (`subagent_service.py`)

**职责**: 动态唤起和执行子智能体

```python
class SubagentService:
    """子智能体服务"""

    async def execute(
        subagent_type: str,
        task: str,
        expected_output: str,
        parent_context: dict,
    ) -> str:
        """执行子智能体任务"""
```

**预定义子智能体类型**:
- `code_analyzer`: 代码分析专家
- `doc_writer`: 技术文档专家
- `researcher`: 研究分析专家
- `data_analyst`: 数据分析专家
- `tester`: 测试专家
- `reviewer`: 代码审查专家

### 3. Agent Orchestration Service (`agent_orchestration_service.py`)

**职责**: 统一的智能体执行入口

```python
class AgentOrchestrationService:
    """智能体编排服务"""

    async def execute_lead_agent(
        agent_id: str,
        user_id: int,
        query: str,
        runtime_config: dict,
    ) -> dict:
        """执行主智能体 - 统一入口"""
```

## 执行流程

### 场景 1: 简单任务（无需子智能体）

```
Client → execute_lead_agent() → Lead Agent → 直接返回结果
```

### 场景 2: 复杂任务（需要子智能体）

```
Client → execute_lead_agent()
              │
              ▼
        Lead Agent 理解意图
              │
              ▼
        调用 delegate_to_subagent()
              │
              ▼
        SubagentService.execute()
              │
              ▼
        Subagent 执行任务
              │
              ▼
        返回结果给 Lead Agent
              │
              ▼
        Lead Agent 整合结果
              │
              ▼
        返回最终响应给 Client
```

## 使用示例

### 基本使用

```python
from app.services.agent_orchestration_service import AgentOrchestrationService

# 创建服务
orchestration = AgentOrchestrationService(
    db=db_session,
    model_gateway=model_gateway,
    skill_registry=skill_registry,
)

# 执行 Lead Agent
result = await orchestration.execute_lead_agent(
    agent_id="agent-123",
    user_id=1,
    query="分析这个 Python 项目的代码质量",
    runtime_config={
        "model_name": "claude-3-opus",
        "plan_mode": True,
        "skills": ["code_interpreter"],
    }
)

print(result["response"])
```

### 注册自定义子智能体

```python
# 注册自定义子智能体
await orchestration.register_custom_subagent(
    name="security_auditor",
    system_prompt="你是一位安全审计专家...",
    skills=["code_interpreter"],
    model_config={"provider": "anthropic", "model": "claude-3-opus"},
    user_id=1,
)

# 直接执行子智能体
result = await orchestration.execute_subagent_direct(
    subagent_type="security_auditor",
    task="审计这个代码库的安全漏洞",
    expected_output="详细的安全审计报告",
    user_id=1,
)
```

### 获取可用子智能体

```python
subagents = await orchestration.get_available_subagents()
for sub in subagents:
    print(f"{sub['type']}: {sub['name']}")
```

## 配置示例

### Lead Agent 配置（数据库）

```python
agent_config = AgentConfig(
    id="agent-123",
    name="智能编程助手",
    system_prompt="你是一位智能编程助手...",
    agent_type="single",
    default_model_config={
        "provider": "anthropic",
        "model": "claude-3-5-sonnet",
    },
    extensions_config={
        "plan_mode_enabled": True,
        "mcp_servers_enabled": ["filesystem"],
        "middleware_config": {
            "logging": {"level": "info"},
        }
    },
)
```

### 运行时配置覆盖

```python
runtime_config = {
    "model_name": "claude-3-opus",      # 动态切换模型
    "plan_mode": True,                  # 启用计划模式
    "skills": ["web_search"],           # 技能覆盖
    "mcp_servers": ["filesystem"],      # MCP 服务器
}
```

## 数据流

```
┌─────────────────────────────────────────────────────────────┐
│                    用户请求                                  │
│  { "query": "分析这个项目", "model": "claude-3-opus" }      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  AgentOrchestrationService.execute_lead_agent()            │
│  1. 获取 Agent 配置（数据库）                                │
│  2. 合并运行时配置                                          │
│  3. 调用 LeadAgentFactory                                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  LeadAgentFactory.create_lead_agent()                      │
│  1. 加载模型（动态选择）                                    │
│  2. 加载工具（MCP + Skills + task 工具）                    │
│  3. 构建中间件链                                            │
│  4. 构建 StateGraph                                         │
│  5. 编译并返回                                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Lead Agent 执行                                             │
│  1. 理解用户意图                                            │
│  2. 制定计划                                                │
│  3. 如需 specialized expertise → 调用 delegate_to_subagent │
│  4. 整合结果                                                │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
    ┌─────────────────┐ ┌─────────────┐ ┌─────────────┐
    │ 直接响应        │ │ Subagent #1 │ │ Subagent #2 │
    └─────────────────┘ └─────────────┘ └─────────────┘
```

## 文件清单

```
backend/app/services/
├── agent_orchestration_service.py    # 统一入口（新增）
├── lead_agent_factory.py             # Lead Agent 工厂（新增）
├── subagent_service.py               # 子智能体服务（新增）
├── agent_graph_factory.py            # 基础图工厂（已有）
└── agent_runtime_service.py          # 传统运行时（已有）
```

## 最佳实践

### 1. 何时使用 Lead Agent

- 需要理解复杂用户意图
- 需要制定多步计划
- 需要协调多个子智能体
- 需要整合多个来源的结果

### 2. 何时使用 Subagent

- 任务需要特定领域专业知识
- 任务可以独立执行
- 需要复用已有的专用 Agent

### 3. 配置建议

```python
# 推荐：使用运行时配置覆盖
runtime_config = {
    "model_name": "claude-3-opus",  # 按需切换
    "plan_mode": True,               # 复杂任务启用
}

# 不推荐：修改数据库中的 Agent 配置
# 应该保持配置稳定，通过 runtime_config 动态调整
```

## 性能考虑

| 层级 | 性能优化策略 |
|------|-------------|
| Lead Agent | 工厂模式每次重建，但图较小 |
| Subagent | 可选缓存，复用已创建的实例 |
| 模型 | 缓存 LLM 实例，避免重复创建 |
| 工具 | 懒加载 + 缓存 |

## 扩展性

### 添加新的子智能体类型

```python
# 1. 在 subagent_service.py 中添加配置
SUBAGENT_CONFIGS["new_type"] = {
    "name": "新专家",
    "system_prompt": "...",
    "default_skills": ["..."],
}

# 2. (可选) 注册为自定义子智能体
await orchestration.register_custom_subagent(
    name="custom_expert",
    system_prompt="...",
    skills=["..."],
    model_config={...},
    user_id=1,
)
```

### 添加新的中间件

```python
class CustomMiddleware(LeadAgentMiddleware):
    async def pre_process(self, state):
        # 预处理逻辑
        return state

    async def post_process(self, state):
        # 后处理逻辑
        return state

# 在 LeadAgentFactory._create_middlewares() 中添加
middlewares.append(CustomMiddleware())
```

## 总结

**核心设计理念**:

1. **统一入口**: 所有智能体执行都始于 `AgentOrchestrationService`
2. **工厂模式**: Lead Agent 每次执行都动态创建
3. **分层设计**: Lead Agent 协调，Subagent 执行专门任务
4. **工具调用**: 通过 `delegate_to_subagent` 工具唤起子智能体
5. **灵活配置**: 支持数据库配置 + 运行时覆盖
