# 分层 Agent 架构实现总结

## 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                    Client Request                            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│         AgentOrchestrationService (统一入口)                │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│   Lead Agent Factory    │     │    Subagent Service     │
│  (动态创建主智能体)      │────▶│   (动态唤起子智能体)     │
│  make_lead_agent()      │     │  delegate_to_subagent() │
└─────────────────────────┘     └─────────────────────────┘
```

## 已实现的文件

| 文件 | 说明 | 状态 |
|------|------|------|
| `agent_orchestration_service.py` | 统一入口服务 | ✅ |
| `lead_agent_factory.py` | Lead Agent 工厂 | ✅ |
| `subagent_service.py` | 子智能体服务 | ✅ |
| `agent_graph_factory.py` | 基础图工厂 | ✅ |
| `AGENT_ARCHITECTURE.md` | 架构文档 | ✅ |

## 核心概念

### 1. Lead Agent (主智能体)

**特点**:
- 每次执行都通过 `make_lead_agent()` 工厂函数动态创建
- 负责理解用户意图、制定计划、协调子智能体
- 支持动态模型选择、MCP 工具加载、技能装配
- 支持中间件链（计划模式、日志等）

**工厂函数签名**:
```python
async def create_lead_agent(
    agent_config: AgentConfig,
    runtime_config: dict,
    run_id: str,
    user_id: int,
) -> AsyncGenerator[CompiledGraph, None]:
```

### 2. Subagent (子智能体)

**特点**:
- 由 Lead Agent 通过 `task` 工具动态唤起
- 专注于特定领域的任务执行
- 预定义 6 种类型，支持自定义扩展

**预定义类型**:
| 类型 | 职责 |
|------|------|
| `code_analyzer` | 代码分析专家 |
| `doc_writer` | 技术文档专家 |
| `researcher` | 研究分析专家 |
| `data_analyst` | 数据分析专家 |
| `tester` | 测试专家 |
| `reviewer` | 代码审查专家 |

**Task 工具签名**:
```python
@tool
async def delegate_to_subagent(
    task_description: str,
    subagent_type: str,
    expected_output: str,
    priority: str = "normal",
) -> str:
```

## 使用方式

### 1. 基本使用（推荐）

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
    }
)
```

### 2. 直接执行子智能体

```python
# 直接执行子智能体（不通过 Lead Agent）
result = await orchestration.execute_subagent_direct(
    subagent_type="code_analyzer",
    task="分析 src/目录的代码质量",
    expected_output="代码质量报告",
    user_id=1,
)
```

### 3. 注册自定义子智能体

```python
await orchestration.register_custom_subagent(
    name="security_auditor",
    system_prompt="你是一位安全审计专家...",
    skills=["code_interpreter"],
    model_config={"provider": "anthropic", "model": "claude-3-opus"},
    user_id=1,
)
```

## 执行流程示例

### 场景：分析项目代码质量

```
1. Client 请求
   └─> "分析这个项目的代码质量，并生成报告"

2. AgentOrchestrationService.execute_lead_agent()
   └─> 获取 Agent 配置
   └─> 合并运行时配置
   └─> 调用 LeadAgentFactory.create_lead_agent()

3. LeadAgentFactory
   └─> 加载模型（claude-3-opus）
   └─> 加载工具（code_interpreter + task 工具）
   └─> 构建中间件链（计划模式 + 日志）
   └─> 构建 StateGraph
   └─> 编译并返回

4. Lead Agent 执行
   └─> 理解用户意图
   └─> 制定计划：
       1. 分析代码结构
       2. 检查代码规范
       3. 识别潜在问题
       4. 生成报告

   └─> 调用 delegate_to_subagent("code_analyzer", ...)
       │
       └─> SubagentService.execute()
           └─> 获取 code_analyzer 配置
           └─> 执行代码分析
           └─> 返回分析结果

   └─> 调用 delegate_to_subagent("doc_writer", ...)
       │
       └─> SubagentService.execute()
           └─> 获取 doc_writer 配置
           └─> 生成报告
           └─> 返回报告

   └─> 整合结果
   └─> 返回最终响应

5. Client 接收结果
   └─> 代码质量分析报告
```

## 配置说明

### AgentConfig 扩展字段

```python
class AgentConfig(Base):
    # 扩展配置 - 用于工厂模式
    extensions_config: Mapped[Optional[dict]]
    # {
    #   "plan_mode_enabled": true,
    #   "mcp_servers_enabled": ["filesystem"],
    #   "middleware_config": {...},
    # }
```

### 运行时配置

```python
runtime_config = {
    "model_name": "claude-3-opus",      # 动态模型
    "plan_mode": True,                  # 计划模式
    "skills": ["code_interpreter"],     # 技能
    "mcp_servers": ["filesystem"],      # MCP 服务器
}
```

## 中间件

### 内置中间件

| 中间件 | 作用 |
|--------|------|
| `PlanMiddleware` | 计划模式，维护 TODO 列表 |
| `LoggingMiddleware` | 日志记录 |

### 自定义中间件

```python
class CustomMiddleware(LeadAgentMiddleware):
    async def pre_process(self, state):
        # 预处理逻辑
        return state

    async def post_process(self, state):
        # 后处理逻辑
        return state
```

## 数据库迁移

运行以下命令应用数据库迁移：

```bash
cd backend
alembic upgrade head
```

这将添加 `extensions_config` 字段到 `agent_configs` 表。

## 测试

```bash
# 运行测试
uv run pytest backend/tests/agent/test_agent_graph_factory.py -v

# 运行特定测试
uv run pytest backend/tests/agent/test_agent_graph_factory.py::TestAgentState -v
```

## 下一步

1. **完善 MCP 工具加载** - 实现完整的 MCP 连接逻辑
2. **添加更多子智能体类型** - 根据业务需求扩展
3. **性能优化** - 实现子智能体缓存
4. **监控和可观测性** - 添加详细的追踪和指标

## 总结

**核心设计理念**:

1. ✅ **统一入口**: `AgentOrchestrationService` 是唯一入口
2. ✅ **工厂模式**: Lead Agent 每次执行都动态创建
3. ✅ **分层设计**: Lead Agent 协调，Subagent 执行
4. ✅ **工具调用**: 通过 `delegate_to_subagent` 工具唤起子智能体
5. ✅ **灵活配置**: 数据库配置 + 运行时覆盖
