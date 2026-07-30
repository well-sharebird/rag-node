# DeerFlow 实现原理分析文档

## 1. 项目概述

### 1.1 项目定位

**DeerFlow** (Deep Exploration and Efficient Research Flow) 是一个开源的**超级智能体 harness**，用于编排子智能体、记忆和沙箱环境，通过可扩展的技能系统完成复杂任务。

- **GitHub**: https://github.com/bytedance/deer-flow
- **版本**: 2.0 (完全重写，与 1.x 无代码共享)
- **技术栈**: LangGraph + LangChain + Next.js + Docker

### 1.2 核心价值主张

DeerFlow 从 Deep Research 框架演变为**超级智能体 harness**：
- 不只是研究工具，而是**智能体运行时**
- 提供智能体所需的基础设施：文件系统、记忆、技能、沙箱执行
- 支持计划和生成子智能体处理复杂多步骤任务

---

## 2. 系统架构

### 2.1 整体架构图

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              Client (Browser)                             │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                          Nginx (Port 2026)                               │
│                    Unified Reverse Proxy Entry Point                      │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  /api/langgraph/*  →  LangGraph Server (2024)                      │  │
│  │  /api/*            →  Gateway API (8001)                           │  │
│  │  /*                →  Frontend (3000)                               │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
          ▼                       ▼                       ▼
┌─────────────────────┐ ┌─────────────────────┐ ┌─────────────────────┐
│   LangGraph Server  │ │    Gateway API      │ │     Frontend        │
│     (Port 2024)     │ │    (Port 8001)      │ │    (Port 3000)      │
│                     │ │                     │ │                     │
│  - Agent Runtime    │ │  - Models API       │ │  - Next.js App      │
│  - Thread Mgmt      │ │  - MCP Config       │ │  - React UI         │
│  - SSE Streaming    │ │  - Skills Mgmt      │ │  - Chat Interface   │
│  - Checkpointing    │ │  - File Uploads     │ │                     │
│                     │ │  - Artifacts        │ │                     │
└─────────────────────┘ └─────────────────────┘ └─────────────────────┘
          │                       │
          │     ┌─────────────────┘
          │     │
          ▼     ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         Shared Configuration                              │
│  ┌─────────────────────────┐  ┌────────────────────────────────────────┐ │
│  │      config.yaml        │  │      extensions_config.json            │ │
│  │  - Models               │  │  - MCP Servers                         │ │
│  │  - Tools                │  │  - Skills State                        │ │
│  │  - Sandbox              │  │                                        │ │
│  │  - Summarization        │  │                                        │ │
│  └─────────────────────────┘  └────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

### 2.2 组件职责

| 组件 | 端口 | 职责 |
|------|------|------|
| **Nginx** | 2026 | 统一反向代理入口 |
| **LangGraph Server** | 2024 | 智能体运行时、工作流编排 |
| **Gateway API** | 8001 | REST API (模型/MCP/技能/文件) |
| **Frontend** | 3000 | Next.js Web 界面 |
| **Provisioner** | 8002 | Kubernetes 沙箱编排 (可选) |

---

## 3. 核心模块分析

### 3.1 Harness / App 分层架构

```
deer-flow/
├── backend/
│   ├── packages/harness/deerflow/   # Harness 层 (可发布包)
│   │   ├── agents/          # LangGraph 智能体系统
│   │   ├── sandbox/         # 沙箱执行系统
│   │   ├── subagents/       # 子智能体委托系统
│   │   ├── tools/           # 内置工具
│   │   ├── mcp/             # MCP 集成
│   │   ├── models/          # 模型工厂
│   │   ├── skills/          # 技能系统
│   │   ├── config/          # 配置系统
│   │   ├── community/       # 社区工具
│   │   ├── reflection/      # 动态模块加载
│   │   └── client.py        # Python 嵌入式客户端
│   └── app/                 # App 层 (应用代码)
│       ├── gateway/         # FastAPI Gateway
│       └── channels/        # IM 渠道集成
```

**依赖规则**: App 可以导入 deerflow，但 deerflow 不能导入 app (由 CI 测试强制执行)

### 3.2 Lead Agent 架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           make_lead_agent(config)                        │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                            Middleware Chain                              │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ 1. ThreadDataMiddleware  - 初始化工作区/上传/输出目录             │   │
│  │ 2. UploadsMiddleware     - 注入上传文件列表                       │   │
│  │ 3. SandboxMiddleware     - 获取沙箱环境                           │   │
│  │ 4. DanglingToolCallMiddleware - 处理悬空工具调用                  │   │
│  │ 5. SummarizationMiddleware - 上下文压缩 (可选)                    │   │
│  │ 6. TodoListMiddleware    - 任务跟踪 (计划模式)                    │   │
│  │ 7. TitleMiddleware       - 自动生成标题                           │   │
│  │ 8. MemoryMiddleware      - 异步记忆更新                           │   │
│  │ 9. ViewImageMiddleware   - 视觉模型支持                           │   │
│  │ 10. SubagentLimitMiddleware - 限制并发子智能体数量                │   │
│  │ 11. ClarificationMiddleware - 处理澄清请求 (必须是最后一个)       │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              Agent Core                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐   │
│  │      Model       │  │      Tools       │  │    System Prompt     │   │
│  │  (from factory)  │  │  (configured +   │  │  (with skills)       │   │
│  │                  │  │   MCP + builtin) │  │                      │   │
│  └──────────────────┘  └──────────────────┘  └──────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.3 ThreadState 数据结构

```python
class ThreadState(AgentState):
    messages: list[BaseMessage]      # LangGraph 基础消息
    sandbox: dict                    # 沙箱环境信息
    artifacts: list[str]             # 生成的文件路径
    thread_data: dict                # {workspace, uploads, outputs} 路径
    title: str | None                # 自动生成的对话标题
    todos: list[dict]                # 任务跟踪 (计划模式)
    uploaded_files: dict             # 上传文件信息
    viewed_images: dict              # 视觉模型图像数据
```

---

## 4. 核心功能模块

### 4.1 沙箱系统

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Sandbox Architecture                           │
└─────────────────────────────────────────────────────────────────────────┘

                      ┌─────────────────────────┐
                      │    SandboxProvider      │ (Abstract)
                      │  - acquire()            │
                      │  - get()                │
                      │  - release()            │
                      └────────────┬────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                                         │
              ▼                                         ▼
┌─────────────────────────┐              ┌─────────────────────────┐
│  LocalSandboxProvider   │              │  AioSandboxProvider     │
│  (本地执行)              │              │  (Docker 隔离)            │
│                         │              │                         │
│  - 单例实例             │              │  - 基于 Docker           │
│  - 直接执行             │              │  - 隔离容器             │
│  - 开发使用             │              │  - 生产使用             │
└─────────────────────────┘              └─────────────────────────┘
```

**虚拟路径映射**:
| 虚拟路径 | 物理路径 |
|---------|---------|
| `/mnt/user-data/workspace` | `backend/.deer-flow/threads/{thread_id}/user-data/workspace` |
| `/mnt/user-data/uploads` | `backend/.deer-flow/threads/{thread_id}/user-data/uploads` |
| `/mnt/user-data/outputs` | `backend/.deer-flow/threads/{thread_id}/user-data/outputs` |
| `/mnt/skills` | `deer-flow/skills/` |

**沙箱工具**:
- `bash` - 执行命令 (带路径转换)
- `ls` - 目录列表 (树形格式，最多 2 层)
- `read_file` - 读取文件 (支持行范围)
- `write_file` - 写入文件 (自动创建目录)
- `str_replace` - 字符串替换

### 4.2 子智能体系统

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Subagent Architecture                             │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  Built-in Agents                                                        │
│  - general-purpose: 通用智能体 (使用除 task 外的所有工具)                │
│  - bash: 命令执行专家                                                   │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  SubagentExecutor                                                       │
│  - _scheduler_pool: 3 workers (调度池)                                  │
│  - _execution_pool: 3 workers (执行池)                                  │
│  - MAX_CONCURRENT_SUBAGENTS = 3                                         │
│  - 15 分钟超时                                                          │
└─────────────────────────────────────────────────────────────────────────┘

Flow: task() 工具调用 → SubagentExecutor → 后台线程 → 轮询 (5s) → SSE 事件 → 结果
```

**事件类型**:
- `task_started` - 任务开始
- `task_running` - 任务进行中
- `task_completed` / `task_failed` / `task_timed_out` - 任务完成/失败/超时

### 4.3 工具系统

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            Tool Sources                                  │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│   Built-in Tools    │  │  Configured Tools   │  │     MCP Tools       │
├─────────────────────┤  ├─────────────────────┤  ├─────────────────────┤
│ - present_file      │  │ - web_search        │  │ - github            │
│ - ask_clarification │  │ - web_fetch         │  │ - filesystem        │
│ - view_image        │  │ - bash              │  │ - postgres          │
│                     │  │ - read_file         │  │ - brave-search      │
│                     │  │ - write_file        │  │ - puppeteer         │
│                     │  │ - str_replace       │  │ - ...               │
│                     │  │ - ls                │  │                     │
└─────────────────────┘  └─────────────────────┘  └─────────────────────┘
                                   │
                                   ▼
                      ┌─────────────────────────┐
                      │   get_available_tools() │
                      └─────────────────────────┘
```

**社区工具** (`packages/harness/deerflow/community/`):
- `tavily/` - 网页搜索和抓取
- `jina_ai/` - Jina Reader API 网页抓取
- `firecrawl/` - Firecrawl API 网页抓取
- `image_search/` - DuckDuckGo 图片搜索

### 4.4 模型工厂

```
config.yaml
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ models:                                                                  │
│   - name: gpt-4                                                         │
│     display_name: GPT-4                                                 │
│     use: langchain_openai:ChatOpenAI                                    │
│     model: gpt-4                                                        │
│     api_key: $OPENAI_API_KEY                                            │
│     supports_thinking: false                                            │
│     supports_vision: true                                               │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
                      ┌─────────────────────────┐
                      │   create_chat_model()   │
                      │  - name: str            │
                      │  - thinking_enabled     │
                      │  - supports_vision      │
                      └────────────┬────────────┘
                                   │
                                   ▼
                      ┌─────────────────────────┐
                      │   resolve_class()       │
                      │  (反射系统)              │
                      └────────────┬────────────┘
                                   │
                                   ▼
                      ┌─────────────────────────┐
                      │   BaseChatModel         │
                      │  (LangChain 实例)        │
                      └─────────────────────────┘
```

**支持的供应商**:
- OpenAI (`langchain_openai:ChatOpenAI`)
- Anthropic (`langchain_anthropic:ChatAnthropic`)
- DeepSeek (`langchain_deepseek:ChatDeepSeek`)
- 自定义 CLI 驱动 (Codex, Claude Code OAuth)

### 4.5 MCP 集成

```
extensions_config.json
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ {                                                                        │
│   "mcpServers": {                                                       │
│     "github": {                                                         │
│       "enabled": true,                                                  │
│       "type": "stdio",                                                  │
│       "command": "npx",                                                 │
│       "args": ["-y", "@modelcontextprotocol/server-github"],           │
│       "env": {"GITHUB_TOKEN": "$GITHUB_TOKEN"}                          │
│     }                                                                   │
│   }                                                                     │
│ }                                                                       │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
                      ┌─────────────────────────┐
                      │  MultiServerMCPClient   │
                      │  (langchain-mcp-adapters)│
                      └────────────┬────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
              ▼                    ▼                    ▼
       ┌───────────┐        ┌───────────┐        ┌───────────┐
       │  stdio    │        │   SSE     │        │   HTTP    │
       │ transport │        │ transport │        │ transport │
       └───────────┘        └───────────┘        └───────────┘
```

**特性**:
- 懒加载：首次使用时加载工具
- 缓存失效：通过文件 mtime 检测配置变更
- OAuth 支持：HTTP/SSE MCP 服务器支持令牌刷新

### 4.6 技能系统

```
skills/
├── public/          # 公共技能 (已提交)
│   ├── pdf-processing/SKILL.md
│   ├── frontend-design/SKILL.md
│   └── ...
└── custom/          # 自定义技能 (gitignore)
    └── user-installed/SKILL.md
```

**SKILL.md 格式**:
```yaml
---
name: PDF Processing
description: Handle PDF documents efficiently
license: MIT
allowed-tools:
  - read_file
  - write_file
  - bash
---

# Skill Instructions
Content injected into system prompt...
```

**技能加载流程**:
1. 递归扫描 `skills/{public,custom}` 目录
2. 解析 `SKILL.md` 元数据
3. 从 `extensions_config.json` 读取启用状态
4. 将启用的技能注入系统提示词

### 4.7 记忆系统

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Memory Architecture                             │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ MemoryMiddleware│───▶│   UpdateQueue   │───▶│   LLM Updater   │
│ (过滤消息)       │    │ (去重/防抖 30s)  │    │ (事实提取)       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                   │
                                                   ▼
                                          ┌─────────────────┐
                                          │  memory.json    │
                                          │  (原子写入)      │
                                          └─────────────────┘
```

**数据结构** (`backend/.deer-flow/memory.json`):
- **User Context**: `workContext`, `personalContext`, `topOfMind`
- **History**: `recentMonths`, `earlierContext`, `longTermBackground`
- **Facts**: 离散事实 (`id`, `content`, `category`, `confidence`, `createdAt`, `source`)

**工作流程**:
1. MemoryMiddleware 过滤消息 (用户输入 + 最终 AI 响应)
2. 队列防抖 (30s)，批量更新，去重
3. 后台线程调用 LLM 提取上下文更新和事实
4. 原子写入 (临时文件 + 重命名)，跳过重复事实
5. 下次交互时将前 15 个事实注入 `<memory>` 标签

### 4.8 IM 渠道系统

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         IM Channels Architecture                         │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   Feishu     │  │    Slack     │  │   Telegram   │
│  (WebSocket) │  │(Socket Mode) │  │ (Bot API)    │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │
       └─────────────────┼─────────────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │    MessageBus       │
              │  (Async Pub/Sub)    │
              └──────────┬──────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │  ChannelManager     │
              │  (Dispatcher)       │
              └──────────┬──────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │  LangGraph Server   │
              │  (via langgraph-sdk)│
              └─────────────────────┘
```

**支持的渠道**:
| 渠道 | 传输方式 | 难度 |
|------|---------|------|
| Telegram | Bot API (长轮询) | 简单 |
| Slack | Socket Mode | 中等 |
| 飞书/Lark | WebSocket | 中等 |

---

## 5. 请求流程示例

### 5.1 用户发送消息流程

```
1. Client → Nginx
   POST /api/langgraph/threads/{thread_id}/runs
   {"input": {"messages": [{"role": "user", "content": "Hello"}]}}

2. Nginx → LangGraph Server (2024)
   代理到 LangGraph 服务器

3. LangGraph Server
   a. 加载/创建线程状态
   b. 执行中间件链:
      - ThreadDataMiddleware: 设置路径
      - UploadsMiddleware: 注入文件列表
      - SandboxMiddleware: 获取沙箱
      - SummarizationMiddleware: 检查 token 限制
      - TitleMiddleware: 生成标题 (如需要)
      - TodoListMiddleware: 加载待办 (如计划模式)
      - ViewImageMiddleware: 处理图像
      - MemoryMiddleware: 队列对话用于记忆更新
      - ClarificationMiddleware: 检查澄清请求
   c. 执行智能体:
      - 模型处理消息
      - 可能调用工具 (bash, web_search 等.)
      - 工具通过沙箱执行
      - 结果添加到消息
   d. 通过 SSE 流式返回响应

4. Client 接收流式响应
```

### 5.2 文件上传流程

```
1. Client 上传文件
   POST /api/threads/{thread_id}/uploads
   Content-Type: multipart/form-data

2. Gateway 接收文件
   - 验证文件
   - 存储在 .deer-flow/threads/{thread_id}/user-data/uploads/
   - 如是文档：通过 markitdown 转换为 Markdown

3. 返回响应
   {
     "files": [{
       "filename": "doc.pdf",
       "path": ".deer-flow/.../uploads/doc.pdf",
       "virtual_path": "/mnt/user-data/uploads/doc.pdf",
       "artifact_url": "/api/threads/.../artifacts/mnt/.../doc.pdf"
     }]
   }

4. 下次智能体运行
   - UploadsMiddleware 列出文件
   - 将文件列表注入消息
   - 智能体可通过 virtual_path 访问
```

---

## 6. 配置系统

### 6.1 配置优先级

1. 通过 `config_path` 参数显式指定
2. `DEER_FLOW_CONFIG_PATH` 环境变量
3. 当前工作目录中的 `config.yaml` (通常是 `backend/`)
4. 父目录中的 `config.yaml` (项目根目录 - **推荐位置**)

### 6.2 主要配置项

```yaml
# config.yaml
models:
  - name: gpt-4
    display_name: GPT-4
    use: langchain_openai:ChatOpenAI
    model: gpt-4
    api_key: $OPENAI_API_KEY
    supports_thinking: false
    supports_vision: true

tools:
  - name: web_search
    group: web
    use: deerflow.community.tavily.tools:web_search_tool

sandbox:
  use: deerflow.sandbox.local:LocalSandboxProvider  # 或 AioSandboxProvider

skills:
  path: /custom/path/to/skills
  container_path: /mnt/skills

memory:
  enabled: true
  storage_path: backend/.deer-flow/memory.json
  debounce_seconds: 30
  max_facts: 100
  fact_confidence_threshold: 0.7
```

---

## 7. 嵌入式 Python 客户端

DeerFlow 提供 `DeerFlowClient` 作为嵌入式 Python 库使用，无需运行 HTTP 服务：

```python
from deerflow.client import DeerFlowClient

client = DeerFlowClient()

# 聊天
response = client.chat("Analyze this paper for me", thread_id="my-thread")

# 流式 (LangGraph SSE 协议)
for event in client.stream("hello"):
    if event.type == "messages-tuple" and event.data.get("type") == "ai":
        print(event.data["content"])

# 配置管理
models = client.list_models()        # {"models": [...]}
skills = client.list_skills()        # {"skills": [...]}
client.update_skill("web-search", enabled=True)
client.upload_files("thread-1", ["./report.pdf"])
```

所有返回字典的方法都通过 Gateway Pydantic 响应模型验证，确保嵌入式客户端与 HTTP API 模式保持同步。

---

## 8. 安全考虑

### 8.1 沙箱隔离
- 智能体代码在沙箱边界内执行
- 本地沙箱：直接执行 (仅开发)
- Docker 沙箱：容器隔离 (推荐生产)
- 防止路径遍历攻击

### 8.2 API 安全
- 线程隔离：每个线程有独立的数据目录
- 文件验证：上传文件检查路径安全
- 环境变量解析：密钥不存储在配置中

### 8.3 MCP 安全
- 每个 MCP 服务器运行在独立进程中
- 环境变量在运行时解析
- 服务器可独立启用/禁用

---

## 9. 性能考虑

### 9.1 缓存
- MCP 工具缓存 (带 mtime 失效)
- 配置加载一次，文件变更时重新加载
- 技能在启动时解析，缓存在内存中

### 9.2 流式传输
- SSE 用于实时响应流式传输
- 减少首 token 时间
- 支持长操作进度可见性

### 9.3 上下文管理
- 总结中间件在接近限制时减少上下文
- 可配置的触发条件：tokens, messages, fraction
- 保留最近消息，同时总结较旧消息

---

## 10. 开发工作流

### 10.1 命令

**项目根目录**:
```bash
make check      # 检查系统依赖
make install    # 安装所有依赖
make dev        # 启动所有服务
make stop       # 停止所有服务
```

**后端目录**:
```bash
make install    # 安装后端依赖
make dev        # 运行 LangGraph 服务器
make gateway    # 运行 Gateway API
make test       # 运行测试
make lint       # 代码检查
make format     # 代码格式化
```

### 10.2 TDD 要求

**每个新功能或 bug 修复必须附带单元测试**:
- 在 `backend/tests/` 中编写测试
- 运行 `make test` 确保测试通过
- 测试通过前功能不视为完成

---

## 11. 推荐模型

DeerFlow 是模型无关的，适用于任何 OpenAI 兼容 API 的 LLM。最佳性能推荐：

- **长上下文窗口** (100k+ tokens) - 深度研究和多步骤任务
- **推理能力** - 自适应计划和复杂分解
- **多模态输入** - 图像理解和视频理解
- **强工具使用** - 可靠的函数调用和结构化输出

---

## 12. 总结

### 12.1 核心创新点

1. **Harness 架构**: 从研究框架演变为通用智能体运行时
2. **中间件链**: 可扩展的请求处理管道
3. **沙箱隔离**: 安全的代码执行环境
4. **子智能体委托**: 动态生成和协调多个智能体
5. **长期记忆**: 跨会话的用户偏好和知识积累
6. **技能系统**: 结构化的能力模块
7. **MCP 集成**: 统一的工具扩展协议

### 12.2 适用场景

- 深度研究和分析
- 多步骤任务自动化
- 文档处理和报告生成
- 代码开发和调试
- 数据管道构建
- 内容创作工作流

### 12.3 技术亮点

- 基于 LangGraph 的状态机编排
- LangChain 的工具和模型抽象
- Docker/Kubernetes 沙箱隔离
- SSE 实时流式传输
- 原子文件 I/O 保证数据一致性
- 防抖和去重的异步更新队列
