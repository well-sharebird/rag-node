# 配置驱动架构文档

> 版本：1.0
> 日期：2026-08-14
> 参考：DeepSeek Harness Cordis Patch 系统

---

## 一、什么是配置驱动

**配置驱动架构** 的核心思想是：

> **行为由配置定义，而非代码硬编码**

与传统代码驱动的区别：

| 代码驱动 | 配置驱动 |
|---------|---------|
| 修改行为需要改代码 | 修改配置即可 |
| 部署周期长 | 即时生效 |
| 多环境需要多套代码 | 同一代码，不同配置 |
| 用户无法自定义 | 用户可编辑配置 |
| 难以审计配置变更 | 配置版本化可追溯 |

---

## 二、为什么需要配置驱动

### 2.1 解决的问题

1. **部署周期长**
   - 问题：每次调整 Agent 行为需要重新部署
   - 解决：修改 YAML 配置，热加载生效

2. **多环境管理困难**
   - 问题：开发/测试/生产环境需要不同代码
   - 解决：同一代码，加载不同配置文件

3. **用户自定义需求**
   - 问题：用户想调整 Agent 行为
   - 解决：提供配置编辑界面

4. **A/B 测试**
   - 问题：无法快速测试不同策略
   - 解决：配置不同版本，动态切换

5. **配置审计**
   - 问题：不知道配置何时被谁修改
   - 解决：配置版本化 + 事件溯源

### 2.2 DeepSeek Harness 的启示

DeepSeek Harness 使用 **Cordis Patch** 系统：

```yaml
# cordis.patch.yml
- insert:
    - id: llm
      name: '@deepseek-ai/dsh-llm'
    
    - id: agent
      name: '@deepseek-ai/dsh-agent'
      config:
        provider: deepseek-official
        model: deepseek-v4-flash
    
    - id: hmr
      name: '@deepseek-ai/cordis-plugin-hmr'
      config:
        root: ['.']  # 热更新监听
```

我们的实现对齐这一设计，但使用 YAML/JSON 格式。

---

## 三、架构设计

### 3.1 配置层次

```
┌─────────────────────────────────────┐
│ 用户配置 (User Profile)             │
│ - ~/.knowrag/agents/my-agent.yaml   │
│ - 最高优先级，覆盖所有下层          │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│ 应用配置 (Application Config)       │
│ - /etc/knowrag/agents/default.yaml  │
│ - 应用默认配置                      │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│ 捆绑配置 (Bundle Config)            │
│ - packages/agent/config/bundle.yaml │
│ - 预定义的 Agent 捆绑包              │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│ 基础配置 (Base Config)              │
│ - 内置默认值                        │
│ - 最低优先级                        │
└─────────────────────────────────────┘
```

### 3.2 配置 Schema

```python
class AgentConfig(BaseModel):
    # 基础信息
    id: str
    name: str
    version: str
    description: Optional[str]
    
    # 类型和模式
    agent_type: AgentType  # single, supervisor, ...
    run_mode: RunMode      # serial, parallel
    
    # 模型配置
    model: ModelConfig
    # {provider, model, temperature, max_tokens}
    
    # 系统提示
    system_prompt: str
    
    # 工具配置
    tools: list[ToolConfig]
    # [{name, enabled, permission_mode}]
    
    # TAO 循环配置
    tao_loop: TAOLoopConfig
    # {max_iterations, enable_think, ...}
    
    # 主 Agent 配置（多 Agent）
    main_agent: Optional[MainAgentConfig]
    # {orchestrator_prompt, sub_agents: [...]}
    
    # 安全策略
    security: SecurityPolicy
    # {sandbox_type, network_enabled, ...}
    
    # 运行时配置
    runtime: RuntimeConfig
    # {timeout_seconds, enable_streaming, ...}
```

### 3.3 配置加载器

```python
class AgentConfigLoader:
    """配置加载器"""
    
    @staticmethod
    def from_yaml(yaml_str: str) -> AgentConfig
    @staticmethod
    def from_json(json_str: str) -> AgentConfig
    @staticmethod
    def from_file(file_path: str) -> AgentConfig
    @staticmethod
    def from_dict(data: dict) -> AgentConfig
    @staticmethod
    def to_yaml(config: AgentConfig) -> str
    @staticmethod
    def to_json(config: AgentConfig) -> str
```

### 3.4 配置驱动的图构建器

```python
class ConfigDrivenGraphBuilder:
    """配置驱动的图构建器"""
    
    async def build_graph(self, config: AgentConfig):
        """从配置构建执行图"""
        # 1. 创建 LLM
        llm = await self._create_llm(config.model)
        
        # 2. 加载工具
        tools = await self._load_tools(config.tools)
        
        # 3. 绑定工具
        if tools:
            llm = llm.bind_tools(tools)
        
        # 4. 根据 Agent 类型构建图
        if config.agent_type == AgentType.SINGLE:
            return self._build_single_agent_graph(config, llm, tools)
        elif config.agent_type == AgentType.SUPERVISOR:
            return self._build_supervisor_graph(config, llm, tools)
```

---

## 四、使用指南

### 4.1 定义 Agent 配置

**单 Agent 示例** (`single_agent.yaml`):

```yaml
id: "qa-agent-001"
name: "问答助手"
version: "1.0.0"

agent_type: "single"
model:
  provider: "deepseek"
  model: "deepseek-v4-flash"
  temperature: 0.7

system_prompt: |
  你是一个友好的 AI 助手。

tools:
  - name: "web_search"
    enabled: true
    permission_mode: "auto"

tao_loop:
  max_iterations: 10

runtime:
  timeout_seconds: 300
  enable_streaming: true
```

**多 Agent 示例** (`multi_agent.yaml`):

```yaml
id: "research-agent-001"
name: "研究助手"
agent_type: "supervisor"

main_agent:
  sub_agents:
    - id: "search-agent"
      task_prompt: "负责网络搜索"
      tools_whitelist: ["web_search"]
    
    - id: "analysis-agent"
      task_prompt: "负责分析信息"
      tools_whitelist: ["text_analysis"]

runtime:
  timeout_seconds: 600  # 多 Agent 需要更长时间
```

### 4.2 加载配置

```python
from packages.agent.config.agent_config import AgentConfigLoader

# 从文件加载
config = AgentConfigLoader.from_file("agents/my-agent.yaml")

# 从字符串加载
yaml_str = """
id: test-agent
name: Test
model:
  provider: openai
  model: gpt-4
system_prompt: You are helpful
"""
config = AgentConfigLoader.from_yaml(yaml_str)

# 从字典加载
data = {"id": "test", "name": "Test", ...}
config = AgentConfigLoader.from_dict(data)
```

### 4.3 构建执行图

```python
from packages.agent.orchestrator.config_graph_builder import ConfigDrivenGraphBuilder

# 创建构建器
builder = ConfigDrivenGraphBuilder(db=session, user_id=1)

# 从配置构建图
graph = await builder.build_graph(config)

# 执行
result = await graph.ainvoke({"messages": [...]})
```

### 4.4 集成到 API

```python
# backend/packages/agent/api/agents.py

@router.post("/{agent_id}/execute")
async def execute(
    agent_id: UUID,
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    # 1. 加载 Agent 配置
    config = await load_agent_config(db, agent_id)
    
    # 2. 从配置构建图
    builder = ConfigDrivenGraphBuilder(db, request.user_id)
    graph = await builder.build_graph(config)
    
    # 3. 执行
    result = await graph.ainvoke({...})
    
    return result
```

---

## 五、配置示例

### 5.1 简单问答 Agent

```yaml
id: simple-qa
name: 简单问答
agent_type: single
model:
  provider: deepseek
  model: deepseek-v4-flash
system_prompt: 回答用户问题
tools: []
runtime:
  timeout_seconds: 60
```

### 5.2 带工具的 Agent

```yaml
id: research-qa
name: 研究问答
agent_type: single
model:
  provider: deepseek
  model: deepseek-v4
  temperature: 0.5
system_prompt: 基于搜索结果回答问题
tools:
  - name: web_search
    enabled: true
  - name: calculator
    enabled: true
    permission_mode: hitl  # 需要审批
tao_loop:
  max_iterations: 15
```

### 5.3 多 Agent 系统

```yaml
id: multi-research
name: 多 Agent 研究系统
agent_type: supervisor
run_mode: parallel

main_agent:
  sub_agents:
    - id: searcher
      task_prompt: 搜索相关信息
      timeout_seconds: 60
    - id: analyst
      task_prompt: 分析信息
      timeout_seconds: 90
    - id: writer
      task_prompt: 撰写报告
      timeout_seconds: 120

runtime:
  timeout_seconds: 600
  enable_checkpointer: true
```

---

## 六、最佳实践

### 6.1 配置设计原则

1. **声明式**: 描述"是什么"，而非"怎么做"
2. **分层**: 基础配置 → 捆绑配置 → 用户配置
3. **验证**: Schema 验证 + 自定义验证器
4. **版本化**: 配置变更纳入版本控制
5. **文档化**: 每个字段都有清晰说明

### 6.2 配置管理

1. **配置文件组织**:
   ```
   config/
   ├── agent_config.py          # Schema 定义
   ├── examples/
   │   ├── single_agent.yaml    # 单 Agent 示例
   │   └── multi_agent.yaml     # 多 Agent 示例
   └── bundles/
       ├── qa-bundle.yaml       # 问答捆绑包
       └── research-bundle.yaml # 研究捆绑包
   ```

2. **配置验证**:
   ```python
   # 加载时自动验证
   config = AgentConfigLoader.from_file("agent.yaml")
   # Pydantic 会验证类型和约束
   ```

3. **配置热更新**:
   ```python
   # TODO: 实现配置文件监听
   # 文件变化时自动重新加载
   ```

### 6.3 安全考虑

1. **敏感信息**: 使用环境变量
   ```yaml
   model:
     provider: openai
     api_key: ${OPENAI_API_KEY}  # 从环境变量读取
   ```

2. **权限控制**: 工具权限分级
   ```yaml
   tools:
     - name: file_read
       permission_mode: auto    # 自动放行
     - name: file_write
       permission_mode: hitl    # 人工审批
     - name: network
       permission_mode: blocked # 完全禁止
   ```

---

## 七、与 DeepSeek Harness 对比

| 特性 | DeepSeek Harness | 我们的实现 | 状态 |
|------|-----------------|-----------|------|
| 配置格式 | YAML (Cordis Patch) | YAML/JSON | ✅ |
| 配置分层 | Bundle → Profile → Overlay | Base → Bundle → User | ✅ |
| Schema 验证 | TypeScript 类型 | Pydantic v2 | ✅ |
| 配置加载器 | Cordis Loader | AgentConfigLoader | ✅ |
| 图构建器 | 硬编码 | ConfigDrivenGraphBuilder | ✅ |
| 热更新 | chokidar 监听 | 待实现 | ⏳ |
| 配置版本化 | Git 追踪 | 待实现 | ⏳ |
| 配置 UI | 无 | 待实现 | ⏳ |

---

## 八、下一步

### 已完成
- [x] 配置 Schema 定义 (`config/agent_config.py`)
- [x] 配置加载器 (`AgentConfigLoader`)
- [x] 配置示例 (`config/examples/*.yaml`)
- [x] 配置驱动的图构建器 (`orchestrator/config_graph_builder.py`)
- [x] 配置测试 (`tests/test_config_driven.py`)

### 待完成
- [ ] 配置热更新（监听文件变化）
- [ ] 配置版本化（Git 集成）
- [ ] 配置管理 UI
- [ ] 配置模板系统
- [ ] 配置差异对比工具
- [ ] 配置回滚机制

---

## 九、参考文档

- [DeepSeek Harness Cordis Patch](../../../code/deepseek-harness/packages/bundle/base/cordis.patch.yml)
- [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [12-Factor App Config](https://12factor.net/config)
