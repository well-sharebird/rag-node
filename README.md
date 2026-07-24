<div align="center">

# KnowRAG - 企业级 RAG 知识平台

**企业级检索增强生成 (RAG) 平台 | 多源知识接入 | 智能问答 | AI 治理**

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-blue.svg)](https://react.dev)
[![Milvus](https://img.shields.io/badge/Milvus-2.6-orange.svg)](https://milvus.io)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## 📖 目录

- [功能特性](#-功能特性)
- [技术架构](#-技术架构)
- [快速开始](#-快速开始)
- [核心功能](#-核心功能)
- [API 文档](#-api-文档)
- [开发指南](#-开发指南)
- [部署](#-部署)

---

## ✨ 功能特性

### 🎯 核心能力

| 功能 | 描述 |
|------|------|
| **多源知识接入** | 支持网页抓取、数据库、API、本地文件、对象存储等多种数据源 |
| **智能网页抓取** | 基于 crawl4ai，支持 JavaScript 渲染页面，自动提取 Markdown |
| **向量检索** | Milvus 向量数据库，支持混合检索 (向量 +BM25) 和重排序 |
| **RAG 问答** | 基于检索结果的智能问答，支持引用溯源 |
| **Markdown 渲染** | 支持代码高亮、数学公式、Mermaid 图表、提示卡片等 |
| **AI 治理** | 多模型管理、Token 配额、使用分析、审计日志 |

### 📊 数据源支持

| 类型 | 连接器 | 状态 |
|------|--------|------|
| 网页抓取 | `WebConnector` (crawl4ai) | ✅ |
| MySQL/PostgreSQL | `DatabaseConnector` | ✅ |
| REST API | `APIConnector` | ✅ |
| 本地文件 | 上传处理 | ✅ |
| Confluence | `ConfluenceConnector` | ✅ |
| Notion | `NotionConnector` | ✅ |
| Git 仓库 | `GitConnector` | ✅ |

---

## 🏗️ 技术架构

### 前端技术栈

```
React 19 + Vite + TypeScript + TailwindCSS
├── 状态管理：React Context + Hooks
├── UI 组件：shadcn/ui + Radix UI
├── Markdown 渲染：react-markdown + rehype-katex + mermaid
├── 代码高亮：react-syntax-highlighter
└── 国际化：i18n (zh/en)
```

### 后端技术栈

```
FastAPI + Python 3.10+
├── 数据库：PostgreSQL (元数据) + Milvus (向量)
├── 缓存/队列：Redis + arq (异步任务)
├── 对象存储：MinIO
├── 网页抓取：crawl4ai (Chromium)
├── 文档解析：PyPDF2, python-docx, pdfplumber
├── 认证鉴权：JWT + 基于角色的访问控制 (RBAC)
└── 监控：Prometheus + 自定义指标
```

### 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                          Frontend (React)                        │
│  Dashboard | KB 管理 | 数据摄取 | AI 问答 | 模型管理 | 监控        │
└─────────────────────────────┬───────────────────────────────────┘
                              │ HTTP/REST
┌─────────────────────────────▼───────────────────────────────────┐
│                      FastAPI Backend                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │  API Routes │  │  Services   │  │  Workers    │              │
│  │  /chat      │  │  RAG        │  │  arq        │              │
│  │  /kb        │  │  Chunking   │  │  sync       │              │
│  │  /sources   │  │  Embedding  │  │  pipeline   │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────┬─────────────────┬─────────────────┬───────────────────┘
          │                 │                 │
    ┌─────▼─────┐   ┌──────▼──────┐   ┌─────▼─────┐
    │PostgreSQL │   │   Milvus    │   │   Redis   │
    │(元数据)    │   │  (向量 DB)  │   │ (缓存/队列)│
    └───────────┘   └─────────────┘   └───────────┘
                            │
                    ┌───────▼───────┐
                    │    MinIO      │
                    │  (对象存储)   │
                    └───────────────┘
```

---

## 🚀 快速开始

### 前置条件

- **Node.js** >= 18.x
- **Python** >= 3.10, < 3.13
- **Docker** & **Docker Compose** (用于基础设施)

### 1. 启动基础设施

```bash
docker-compose up -d
# 启动：Milvus, PostgreSQL, Redis, MinIO, etcd
```

### 2. 配置后端

```bash
cd backend

# 安装依赖
uv sync

# 配置环境变量
cp .env.example .env
# 编辑 .env 配置数据库连接、API 密钥等

# 数据库迁移
alembic upgrade head

# 启动后端服务
uv run python app/main.py
```

### 3. 启动前端

```bash
# 根目录
npm install
npm run dev
# 访问 http://localhost:3000
```

### 4. 启动 Worker (可选，用于后台任务)

```bash
cd backend
uv run arq app.workers.WorkerSettings
```

---

## 📦 核心功能

### 1. 知识库管理

创建和管理知识库，每个知识库是独立的文档和向量空间。

```bash
POST /api/v1/knowledge-bases
{
  "name": "工程文档",
  "description": "产品技术文档库"
}
```

### 2. 数据摄取

支持多种数据源类型，自动抓取和向量化。

```bash
POST /api/v1/data-sources
{
  "name": "产品文档站",
  "source_type": "web_page",
  "kb_id": "xxx-xxx-xxx",
  "web_page_config": {
    "urls": ["https://docs.example.com"],
    "max_depth": 2
  }
}
```

### 3. RAG 智能问答

基于知识库的检索增强生成，支持流式响应和引用溯源。

```bash
POST /api/v1/chat/completions
{
  "query": "如何配置 SSL 证书？",
  "kb_ids": ["xxx-xxx-xxx"],
  "stream": true
}
```

### 4. 模型管理

配置和管理各类 AI 模型 (LLM, Embedding, Rerank)。

```bash
POST /api/v1/models
{
  "name": "Qwen-2.5-72B",
  "type": "llm",
  "adapter_type": "api",
  "model_id": "qwen-2.5-72b",
  "api_url": "https://api.example.com/v1",
  "api_key": "sk-xxx"
}
```

### 5. Markdown 渲染

AI 助手支持丰富的 Markdown 格式渲染：

| 格式 | 语法 | 说明 |
|------|------|------|
| 代码块 | \`\`\`python ... \`\`\` | 语法高亮 + 复制按钮 |
| 数学公式 | $E=mc^2$ / $$...$$ | KaTeX 渲染 |
| 流程图 | \`\`\`mermaid ... \`\`\` | Mermaid 图表 |
| 提示卡片 | :::tip ... ::: | 警告/提示/注意卡片 |
| JSON 树 | \`\`\`json-tree ... \`\`\` | 可折叠树形视图 |
| 表格/列表 | 标准 Markdown | 自动样式 |

---

## 📡 API 文档

### 主要端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/v1/auth/login` | POST | 用户登录 |
| `/api/v1/knowledge-bases` | GET/POST | 知识库管理 |
| `/api/v1/data-sources` | GET/POST | 数据源管理 |
| `/api/v1/data-sources/{id}/sync` | POST | 触发同步 |
| `/api/v1/chat/completions` | POST | RAG 问答 |
| `/api/v1/models` | GET/POST | 模型管理 |
| `/api/v1/retrieval/test` | POST | 检索测试 |
| `/api/v1/dashboard/metrics` | GET | 监控指标 |

### API 文档访问

启动后端后访问：
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## 🛠️ 开发指南

### 项目结构

```
rag/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # API 路由
│   │   ├── connectors/       # 数据连接器
│   │   ├── core/             # 核心配置
│   │   ├── models/           # 数据模型
│   │   ├── schemas/          # Pydantic 模式
│   │   ├── services/         # 业务逻辑
│   │   ├── workers/          # arq 后台任务
│   │   └── utils/            # 工具函数
│   ├── tests/
│   ├── alembic/              # 数据库迁移
│   └── pyproject.toml
├── src/                      # React 前端
│   ├── components/
│   ├── pages/
│   ├── lib/
│   └── App.tsx
├── docker-compose.yml
├── CLAUDE.md                 # 开发指南
└── README.md
```

### 添加新的数据连接器

1. 创建连接器类继承 `BaseConnector`:

```python
# backend/app/connectors/my_connector.py
from app.connectors.base import BaseConnector

class MyConnector(BaseConnector):
    async def ingest(self) -> AsyncIterator[Document]:
        # 实现数据抓取逻辑
        yield Document(title="...", content="...")
```

2. 在工厂中注册:

```python
# backend/app/connectors/factory.py
CONNECTOR_REGISTRY["my_type"] = MyConnector
```

### 添加新的 API 端点

```python
# backend/app/api/v1/my_routes.py
from fastapi import APIRouter

router = APIRouter(prefix="/my-feature", tags=["My Feature"])

@router.get("")
async def list_items():
    return {"items": []}
```

---

## 📦 部署

### Docker 部署

```yaml
# docker-compose.yml
services:
  api:
    build: ./backend
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - milvus
      - redis

  worker:
    build: ./backend
    command: uv run arq app.workers.WorkerSettings
    depends_on:
      - redis

  frontend:
    build: .
    ports:
      - "3000:3000"
```

### 生产环境建议

1. **反向代理**: 使用 Nginx/Traefik 处理 HTTPS 和负载均衡
2. **数据库**: 使用托管 PostgreSQL (RDS/Cloud SQL)
3. **向量库**: Milvus 集群部署
4. **缓存**: Redis Sentinel 或 Cluster
5. **监控**: Prometheus + Grafana
6. **日志**: ELK Stack 或 Loki

---

## 🔧 配置

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATABASE_URL` | PostgreSQL 连接串 | - |
| `REDIS_URL` | Redis 连接串 | - |
| `MILVUS_HOST` | Milvus 主机 | localhost |
| `MINIO_ENDPOINT` | MinIO 端点 | localhost:9000 |
| `GEMINI_API_KEY` | Gemini API 密钥 | - |

---

## 📝 License

MIT License

---

<div align="center">

**KnowRAG** - 让知识触手可及

[开始使用](#-快速开始) · [API 文档](#-api-文档) · [开发指南](#-开发指南)

</div>
