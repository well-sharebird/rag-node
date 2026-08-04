# MCP Server 使用指南

## 概述

RAG Platform MCP Server 提供了 29 个工具，让 AI 助手（如 Claude Code）可以直接与 RAG 系统交互，执行知识库管理、模型配置、提示词工程和智能体操作等任务。

## 工具清单

### 知识库管理 (6 个工具)

| 工具名 | 描述 | 主要参数 |
|--------|------|----------|
| `list_knowledge_bases` | 获取知识库列表 | search, limit, offset |
| `get_knowledge_base` | 获取知识库详情 | kb_id |
| `create_knowledge_base` | 创建知识库 | name, description, permissions, top_k, min_score, enable_rerank |
| `update_knowledge_base` | 更新知识库 | kb_id, name, description, permissions, top_k, min_score, enable_rerank |
| `delete_knowledge_base` | 删除知识库 | kb_id |
| `search_knowledge_base` | 检索知识库内容 | query, kb_ids, top_k, min_score |

### 模型管理 (7 个工具)

| 工具名 | 描述 | 主要参数 |
|--------|------|----------|
| `list_models` | 获取模型列表 | model_type, adapter_type, enabled_only |
| `get_model` | 获取模型详情 | model_id |
| `create_model` | 创建模型配置 | name, model_id, model_type, adapter_type, provider, api_url, api_key |
| `update_model` | 更新模型配置 | model_id, name, api_url, api_key, max_tokens, temperature, is_enabled, is_default |
| `delete_model` | 删除模型 | model_id |
| `test_model` | 测试模型连接 | model_id, test_input |
| `get_default_model` | 获取默认模型 | model_type |

### 提示词工程 (8 个工具)

| 工具名 | 描述 | 主要参数 |
|--------|------|----------|
| `list_prompt_templates` | 获取模板列表 | status, category, limit, offset |
| `get_prompt_template` | 获取模板详情 | name |
| `create_prompt_template` | 创建模板 | name, content, description, category |
| `update_prompt_template` | 更新模板 | name, content, description, category |
| `render_prompt` | 渲染提示词 | name, variables |
| `create_prompt_version` | 创建版本 | template_name, content, change_summary |
| `release_prompt_version` | 发布版本 | template_name, version_id |
| `run_prompt_evaluation` | 运行评估 | template_name, test_case_ids |

### 智能体广场 (8 个工具)

| 工具名 | 描述 | 主要参数 |
|--------|------|----------|
| `list_agents` | 获取智能体列表 | status, agent_type, limit, offset |
| `list_public_agents` | 获取公开智能体广场 | limit, offset |
| `get_agent` | 获取智能体详情 | agent_id |
| `create_agent` | 创建智能体 | name, description, agent_type, config, is_public |
| `update_agent` | 更新智能体 | agent_id, name, description, config, is_public |
| `delete_agent` | 删除智能体 | agent_id |
| `execute_agent` | 执行智能体 | agent_id, query, session_id |
| `publish_agent` | 发布到广场 | agent_id |

## 配置方式

### 1. 编辑 `extensions_config.json`

在项目根目录创建或编辑 `extensions_config.json`:

```json
{
  "mcpServers": {
    "rag-platform": {
      "enabled": true,
      "type": "stdio",
      "command": "uv",
      "args": [
        "run",
        "python",
        "-m",
        "app.mcp.server"
      ],
      "env": {},
      "description": "RAG Platform MCP Server"
    }
  },
  "skills": {
    "knowledge-base-manager": { "enabled": true },
    "model-manager": { "enabled": true },
    "prompt-engineering": { "enabled": true },
    "agent-hub": { "enabled": true }
  }
}
```

### 2. 安装依赖

```bash
cd backend
uv sync
```

### 3. 测试连接

```bash
cd backend
uv run python -m app.mcp.server
```

## 在 AI 助手中使用

配置完成后，AI 助手（如 Claude Code）将自动发现并可以使用这些工具。

### 示例对话

**用户**: "帮我列出所有知识库"

**AI**: 调用 `list_knowledge_bases` 工具，返回知识库列表。

**用户**: "创建一个名为'产品文档'的知识库"

**AI**: 调用 `create_knowledge_base` 工具，参数: `{name: "产品文档", description: "产品技术文档库"}`

**用户**: "查询默认的 LLM 模型是什么"

**AI**: 调用 `get_default_model` 工具，参数: `{model_type: "LLM"}`

**用户**: "执行智能体 agent-123，询问'如何配置 SSL 证书？'"

**AI**: 调用 `execute_agent` 工具，参数: `{agent_id: "agent-123", query: "如何配置 SSL 证书？"}`

## 架构说明

```
┌─────────────────────────────────────────┐
│          AI Assistant (Claude)          │
│                  ↓ MCP Client           │
└─────────────────────────────────────────┘
                    ↓ stdio
┌─────────────────────────────────────────┐
│       MCP Server (app/mcp/server.py)    │
│  ┌───────────────────────────────────┐  │
│  │  Tool Router (call_tool_handler)  │  │
│  └───────────────────────────────────┘  │
│    ↓           ↓           ↓           ↓  │
│  KB Tools  Model Tools  Prompt Tools  Agent Tools
│    ↓           ↓           ↓           ↓  │
│  ┌───────────────────────────────────┐  │
│  │      Service Layer (Business Logic)│  │
│  └───────────────────────────────────┘  │
│                    ↓                     │
│  ┌───────────────────────────────────┐  │
│  │      Database (PostgreSQL)        │  │
│  │      Vector DB (Milvus)           │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

## 安全注意事项

1. **用户认证**: 当前 MCP 工具使用默认 `user_id=1`，生产环境应从认证上下文获取
2. **权限控制**: 工具调用应遵循 RBAC 权限模型
3. **敏感操作**: `delete_*` 类操作应添加二次确认
4. **速率限制**: 对频繁调用应实施速率限制

## 故障排除

### 工具未显示

1. 检查 `extensions_config.json` 格式是否正确
2. 确认 MCP server 已启动 (`enabled: true`)
3. 查看 MCP 日志输出

### 数据库连接错误

1. 确认 PostgreSQL 运行正常
2. 检查 `DATABASE_URL` 环境变量
3. 验证数据库迁移已完成 (`alembic upgrade head`)

### Milvus 连接错误

1. 确认 Milvus 服务运行在 `localhost:19530`
2. 检查 Docker 容器状态：`docker-compose ps`
