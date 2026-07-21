# RAG Backend - Development Guide

## Project Overview

Retrieval-Augmented Generation (RAG) system with:
- **Frontend**: React 19 + Vite + TypeScript + TailwindCSS
- **Backend**: Python FastAPI + SQLAlchemy (async)
- **Vector DB**: Milvus 2.6.x (etcd + MinIO storage)
- **Metadata**: PostgreSQL 16
- **Cache**: Redis 7.4.x
- **Task Queue**: arq (Redis-based)

## 1.3 角色定义 (RBAC)

平台采用基于角色的访问控制 (RBAC) 模型，定义四种核心角色：

| 角色 | 职责 | 典型用户 |
|------|------|----------|
| **Admin（管理员）** | 平台全量控制：用户管理、角色分配、系统配置、审计日志查看、告警管理 | IT 管理员、平台 Owner |
| **Editor（编辑者）** | 知识库内容运营：上传文档、管理连接器、审查分块质量、运行评估测试 | 知识管理专员、技术文档工程师 |
| **Viewer（查看者）** | 纯查询权限：在授权知识库范围内提问、查看引用来源、反馈答案质量 | 普通员工、团队成员 |
| **Developer（开发者）** | 程序化集成：通过 API 构建自定义应用、集成聊天机器人、管理 API Keys | 工程师、集成开发人员 |

**默认管理员账号**: `admin` / `admin123`（首次启动自动创建）

详细设计文档见：`docs/README.md`

## Quick Start

### Start Infrastructure
```bash
docker-compose up -d  # Starts etcd, MinIO, Milvus, PostgreSQL, Redis, Attu
```

### Start Backend
```bash
cd backend
uv run python app/main.py
```

### Start Frontend
```bash
npm run dev  # Vite on port 3000
```

## Key Ports

| Service  | Port  | Purpose                          |
|----------|-------|----------------------------------|
| Frontend | 3000  | Vite dev server                  |
| Backend  | 8000  | FastAPI (default, check main.py) |
| Milvus   | 19530 | gRPC API                         |
| Attu     | 8000  | Milvus UI (conflicts with backend)|
| MinIO    | 9001  | Console UI                       |
| Postgres | 5432  | Internal only (commented out)    |
| Redis    | 6379  | Internal only (commented out)    |

> **Note**: Attu (8000) conflicts with typical backend port. Either change Attu port or backend port.

## Project Structure

```
rag/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI routers
│   │   ├── core/         # Core config, security
│   │   ├── models/       # SQLAlchemy models
│   │   ├── schemas/      # Pydantic schemas
│   │   ├── services/     # Business logic
│   │   ├── utils/        # Utilities
│   │   └── workers/      # arq background tasks
│   ├── tests/
│   └── pyproject.toml
├── src/                  # React frontend
├── docker-compose.yml    # All services
└── .claude/settings.json # Claude Code config
```

## Development Commands

### Frontend
```bash
npm run dev      # Start dev server
npm run build    # Production build
npm run preview  # Preview production build
npm run lint     # Type check (tsc)
npm run clean    # Remove dist/server.js
```

### Backend
```bash
uv run python app/main.py      # Start server
uv run pytest                  # Run tests
uv add <package>               # Add dependency
uv sync                        # Sync dependencies
```

### Docker
```bash
docker-compose up -d           # Start all services
docker-compose down            # Stop all services
docker-compose logs -f milvus-standalone  # Follow logs
docker-compose ps              # List containers
```

## Database Migrations

```bash
cd backend
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
GEMINI_API_KEY=your_key
APP_URL=http://localhost:3000
```

Backend environment (in `backend/.env`):
```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres123@localhost:5432/rag_db
REDIS_URL=redis://:redis123@localhost:6379
MILVUS_HOST=localhost
MILVUS_PORT=19530
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
```

## Testing

```bash
# Backend tests
cd backend
uv run pytest
uv run pytest -v           # Verbose
uv run pytest tests/api/   # Specific directory

# Frontend type check
npm run lint
```

## Architecture Notes

1. **Milvus**: Vector storage for embeddings. Collections should be created programmatically in services.
2. **PostgreSQL**: Relational metadata (users, documents, sessions).
3. **Redis**: Caching + arq task queue for background jobs.
4. **MinIO**: Object storage for Milvus (internal) + document uploads.

## Common Tasks

### Add new API endpoint
1. Add route in `backend/app/api/`
2. Define Pydantic schema in `backend/app/schemas/`
3. Implement service logic in `backend/app/services/`
4. Add tests in `backend/tests/`

### Add new Milvus collection
1. Define collection schema in `backend/app/services/`
2. Create collection on startup or migration
3. Add CRUD operations in service layer

### Add background task
1. Create worker in `backend/app/workers/`
2. Enqueue task via arq from API endpoint
3. Task executes async via Redis queue
