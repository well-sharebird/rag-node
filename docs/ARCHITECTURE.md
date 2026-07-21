# RAG 平台架构与模块文档

## 目录
- [系统总览](#系统总览)
- [1. 文档处理管道](#1-文档处理管道)
- [2. 向量存储与检索](#2-向量存储与检索)
- [3. 对话生成](#3-对话生成)
- [4. 知识库管理](#4-知识库管理)
- [5. 模型管理](#5-模型管理)
- [6. 用户与权限](#6-用户与权限)
- [7. 技能仓库](#7-技能仓库)
- [8. 数据源集成](#8-数据源集成)
- [9. 监控与可观测性](#9-监控与可观测性)
- [10. 前端页面结构](#10-前端页面结构)

---

## 系统总览

```
┌────────────────────────────────────────────────────────────────────┐
│                         Frontend (React 19)                        │
│  Dashboard │ Q&A │ KBs │ Documents │ Search │ Skills │ Models │ Users │
└────────────────────────────┬───────────────────────────────────────┘
                             │ REST API + SSE Streaming
┌────────────────────────────┴───────────────────────────────────────┐
│                     Backend (FastAPI)                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│  │ Document │ │ Retrieval│ │  Chat    │ │  Skills  │ │  Users  │ │
│  │ Pipeline │ │ Service  │ │ Service  │ │ Registry  │ │  RBAC   │ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬────┘ │
└───────┼────────────┼─────────────┼─────────────┼─────────────┼─────┘
        │            │             │             │             │
┌───────┴────────────┴─────────────┴─────────────┴─────────────┴─────┐
│                        Infrastructure                              │
│  PostgreSQL │ Milvus │ Elasticsearch │ Redis │ MinIO │ Neo4j │ Kafka │
└────────────────────────────────────────────────────────────────────┘
```

### 基础设施依赖

| 服务 | 用途 |
|------|------|
| PostgreSQL 16 | 业务元数据（文档、知识库、用户、设置、技能仓库） |
| Milvus 2.2 | 向量存储（dense embeddings） |
| Elasticsearch 8.11 | 全文检索（BM25） |
| Redis 6 | 缓存 + 会话存储 + arq 任务队列 |
| MinIO | 文档对象存储 |
| Neo4j 5.14 | 知识图谱 |
| Kafka 7.5 | 消息队列 |

---

## 1. 文档处理管道

### 1.1 模块列表

```
backend/app/
├── api/v1/documents.py          # 文档上传/列表/删除/重新处理 API
├── services/document_service.py # 文档 CRUD + 格式校验
├── services/parsing_service.py  # 13 种格式解析器 + OCR + 表格提取
├── services/chunking_service.py # 5 种分块策略
├── services/embedding_service.py# API-based 文本向量化
├── services/vector_store_service.py # Milvus 读写
├── workers/document_pipeline.py # arq 后台处理管道
└── schemas/document.py          # Pydantic 数据模型
```

### 1.2 处理时序图

```
用户上传文件
     │
     ▼
┌──────────────────────────────────────────────────────────────────┐
│ POST /api/v1/documents/upload?kb_id=xxx                           │
│   │                                                               │
│   ├─ validate_file()        格式校验 (14 种, 50MB 限制)            │
│   ├─ upload_document()      存入 MinIO                            │
│   ├─ DB INSERT              documents 表 (status=pending)         │
│   └─ arq.enqueue()          → process_document(doc_id)            │
└──────────────────────────────────────────────────────────────────┘
     │ (async background)
     ▼
┌──────────────────────────────────────────────────────────────────┐
│ workers/document_pipeline.py :: process_document()                │
│                                                                    │
│  Stage 1: PARSE                                                   │
│    parse_document_structured(content, format)                     │
│      ├─ PDF   → pdfplumber (text + table + image OCR)            │
│      ├─ DOCX  → python-docx (paragraph + table)                  │
│      ├─ XLSX  → openpyxl (sheet → table)                         │
│      ├─ PPTX  → python-pptx (slide + table + notes)              │
│      ├─ TXT/MD/HTML → text extraction                             │
│      └─ Image → PaddleOCR → Tesseract fallback                   │
│    → ParsedDocument { elements: [ContentElement], content_types } │
│                                                                    │
│  Stage 2: CLEAN                                                    │
│    text_cleaner.clean(text)                                       │
│      ├─ PII 检测 (presidio)                                       │
│      ├─ 语言检测 (langdetect)                                      │
│      ├─ 去重 (simhash)                                            │
│      └─ 质量评分                                                   │
│                                                                    │
│  Stage 3: CHUNK (per content_type)                                │
│    chunk_text(text, strategy=semantic, content_type=text)         │
│    ├─ 5 种策略: fixed | semantic | recursive | agentic | small_to_big │
│    └─ 表格保持整表不分块, 图片单 chunk                             │
│                                                                    │
│  Stage 4: EMBED                                                    │
│    embed_service.embed_texts(chunk_texts)                         │
│    ├─ API provider (Xinference / OpenAI-compatible)               │
│    ├─ 500 字符截断保护                                             │
│    └─ 3 次重试 + 指数退避                                          │
│                                                                    │
│  Stage 5: VALIDATE                                                 │
│    ingestion_validator.validate_document()                        │
│    ├─ chunk 质量检查                                               │
│    ├─ embedding 维度验证                                           │
│    └─ 索引召回验证                                                 │
│                                                                    │
│  Stage 6: STORE                                                    │
│    insert_chunks(milvus, collection, chunks, embeddings)          │
│    └─ 写入 Milvus (chunk_id, doc_id, text, vector, content_type)  │
│                                                                    │
│  Update: status=completed, chunk_count, content_types             │
└──────────────────────────────────────────────────────────────────┘
```

### 1.3 支持的格式

| 类别 | 格式 | 解析器 | content_type |
|------|------|--------|-------------|
| 文档 | pdf, docx, pptx, txt, md | 专属解析器 | text / table / image |
| 表格 | xlsx | openpyxl | table |
| 网页 | html, htm | BeautifulSoup | text / table |
| 图片 | jpg, png, tiff, bmp 等 6 种 | PaddleOCR → Tesseract | image |

### 1.4 分块策略

| 策略 | 说明 |
|------|------|
| `fixed` | 按 token 数固定大小，以段落为边界 |
| `semantic` | 按语义分隔符切分（\n\n → \n → .） |
| `recursive` | LangChain 风格层级分隔符 |
| `agentic` | LLM 决定最优切分点 |
| `small_to_big` | 父子 chunk，层级检索 |

---

## 2. 向量存储与检索

### 2.1 模块列表

```
backend/app/
├── api/v1/retrieval.py          # 检索 API + 搜索历史
├── services/retrieval_service.py# 检索引擎
├── services/vector_store_service.py # Milvus 读写
├── services/rrf_fusion.py       # RRF 多路融合
├── services/mmr_service.py      # MMR 多样性采样
├── services/multi_modal_retrieval.py # 多模态并行检索
└── services/multi_index_service.py   # 5 索引混合存储
```

### 2.2 检索时序图

```
用户搜索请求
     │
     ▼
┌──────────────────────────────────────────────────────────────────┐
│ POST /api/v1/retrieval/search                                     │
│   { kb_id, query, top_k, min_score, enable_rerank, enable_multimodal } │
└──────────────────────────────────────────────────────────────────┘
     │
     ▼
┌──────────────────────────────────────────────────────────────────┐
│ search_chunks()                                                   │
│                                                                    │
│  Step 1: Resolve embedding model from model_configs               │
│    ├─ Priority: default model → any enabled model → error         │
│    └─ Returns { provider, model_name, api_url, dim }             │
│                                                                    │
│  Step 2: Generate query embedding                                 │
│    embed_service.embed_query(query) → [1024] float vector        │
│                                                                    │
│  Step 3: Vector Search (dense)                                    │
│    search_vectors(milvus, collection, embedding, top_k)           │
│    └─ IP (Inner Product) metric, FLAT index                       │
│                                                                    │
│  Step 4 (optional): Multi-modal search                            │
│    multi_modal_search()                                           │
│    ├─ Parallel: text + table + image 类型过滤搜索                  │
│    └─ 去重合并, 按 score 排序                                      │
│                                                                    │
│  Step 5 (optional): Rerank                                        │
│    _rerank_results(query, hits, top_n=3)                         │
│    ├─ Cross-encoder via rerank API                                │
│    └─ Re-score → Re-order                                         │
│                                                                    │
│  Step 6: Apply min_score filter                                   │
│  Step 7: Record metrics to Redis                                  │
│    ├─ latency, search count, zero_result count                    │
│    ├─ Search history (last 200)                                   │
│    └─ Top docs by access count                                    │
│                                                                    │
│  Return: SearchResponse { results[], query, search_time_ms }     │
└──────────────────────────────────────────────────────────────────┘
```

### 2.3 检索增强能力

| 能力 | 实现 |
|------|------|
| RRF 多路融合 | `rrf_fusion.py` — dense + BM25 + sparse 三路融合 |
| MMR 多样性 | `mmr_service.py` — λ 参数平衡相关性与多样性 |
| 混合搜索 | `multi_index_service.py` — 5 索引并行写入 |
| 多模态检索 | `multi_modal_retrieval.py` — text/table/image 并行搜索 |

---

## 3. 对话生成

### 3.1 模块列表

```
backend/app/
├── api/v1/chat.py                # Chat completions API (SSE streaming)
├── services/llm_service.py       # LLM 生成 + 幻觉检测
├── services/query_expansion.py   # HyDE + 关键词扩展
├── services/conversation_memory.py # Redis-based 多轮记忆
├── schemas/chat.py               # ChatRequest / ChatResponse / CitationInfo
└── schemas/retrieval.py          # SearchRequest / SearchResultItem
```

### 3.2 对话时序图

```
用户: "丁敬凯的测评结果？"
     │
     ▼
┌──────────────────────────────────────────────────────────────────┐
│ POST /api/v1/chat/completions                                     │
│   { query, kb_ids, top_k, stream, enable_rerank, enable_expansion } │
└──────────────────────────────────────────────────────────────────┘
     │
     ▼
┌──────────────────────────────────────────────────────────────────┐
│ chat_completions()                                                │
│                                                                    │
│  Step 1: Build conversation context (if multi-turn)               │
│    ConversationMemory(redis).get_context_window(max=6)            │
│                                                                    │
│  Step 2: Query Expansion (HyDE)                                   │
│    expand_query(query)                                            │
│    ├─ hyde_expand(): LLM 生成假设文档 → embed 假设文档             │
│    └─ keyword_expand(): LLM 生成 2-3 个变体查询                    │
│                                                                    │
│  Step 3: Retrieve from each KB                                    │
│    search_chunks() × N KBs                                        │
│                                                                    │
│  Step 4: Deduplicate (by chunk_id) + Sort (by score desc)        │
│                                                                    │
│  Step 5 (optional): Rerank top 20 → top_k                         │
│                                                                    │
│  Step 6: Generate RAG response                                    │
│    generate_rag_response(query, chunks, stream=True/False)        │
│    │                                                               │
│    ├─ _get_llm_config() → model_configs DB (default LLM)         │
│    ├─ _build_rag_prompt()                                         │
│    │   ├─ [文本证据] section (text chunks)                        │
│    │   ├─ [表格数据] section (table chunks + analysis hint)       │
│    │   └─ [图片描述] section (image OCR chunks)                   │
│    │                                                               │
│    ├─ Call LLM API (OpenAI-compatible /v1/chat/completions)       │
│    │   ├─ Non-stream: return { answer, reasoning, citations }     │
│    │   └─ Stream: return { stream, client, type, citations }      │
│    │                                                               │
│    └─ _detect_hallucination(answer, chunks)                       │
│        ├─ 数值声明核验                                            │
│        └─ 绝对化断言检测 ("always", "never", "all", "none")       │
│                                                                    │
│  Step 7 (streaming): SSE 返回                                     │
│    _stream_rag_response()                                         │
│    ├─ Sent: citations event                                       │
│    ├─ Send: role="assistant" chunk                                │
│    ├─ Send: reasoning_content chunks (→ 思考过程面板)              │
│    ├─ Send: content chunks (→ 答案面板, 同步流式)                  │
│    ├─ Send: finish_reason="stop"                                  │
│    └─ Send: [DONE]                                                │
│                                                                    │
│  Return: ChatResponse { answer, reasoning, citations, hallu_score } │
└──────────────────────────────────────────────────────────────────┘
```

---

## 4. 知识库管理

### 4.1 模块列表

```
backend/app/
├── api/v1/knowledge_bases.py    # KB CRUD API
├── services/kb_service.py       # KB + Milvus collection 管理
└── models/knowledge_base.py     # KnowledgeBase ORM
```

### 4.2 处理逻辑

```
Create KB
  ├─ DB: INSERT knowledge_bases (name, description, collection_name)
  └─ Milvus: create_collection(collection_name, dim=1024, metric=IP)
       └─ 字段: chunk_id, doc_id, kb_id, vector, text, page, chapter, doc_name, content_type

Delete KB
  ├─ DB: DELETE knowledge_bases (CASCADE → documents)
  ├─ Milvus: drop_collection(collection_name)
  └─ MinIO: 删除相关对象

Document Count: 统计聚合
Vector Count: KB 级别计数器 (每次 insert_chunks 递增)
```

---

## 5. 模型管理

### 5.1 模块列表

```
backend/app/
├── api/v1/models.py              # Model CRUD + test connection API
├── services/model_service.py     # Model config management
├── services/model_config_service.py # Embedding/Rerank resolution
├── models/model_config.py        # ModelConfig ORM
└── schemas/model.py              # ModelType, AdapterType, presets
```

### 5.2 模型类型

| ModelType | 说明 |
|-----------|------|
| llm | 大语言模型（chat/completion） |
| embedding | 文本向量化 |
| rerank | 交叉编码器重排序 |
| vision | 图像理解 |
| speech_to_text | 语音转文字 |
| text_to_speech | 文字转语音 |

### 5.3 Adapter 类型

| AdapterType | 说明 |
|-------------|------|
| api | REST API (OpenAI-compatible) |
| ollama | Ollama 本地推理 |
| vllm | vLLM 推理服务器 |
| triton | NVIDIA Triton |
| custom | 自定义端点 |

### 5.4 模型解析优先级

```
resolve_embedding_config(session):
  1. model_configs 表中 is_default=True + is_enabled=True
  2. model_configs 表中任意 is_enabled=True 的 embedding 模型
  3. 抛出异常 → fallback 到 rag_config 默认值

resolve_rerank_config(session):
  同 embedding，但查询 model_type="rerank"
```

---

## 6. 用户与权限

### 6.1 模块列表

```
backend/app/
├── api/v1/users.py              # User CRUD + Role assignment API
├── api/v1/auth.py               # Login/Token API
├── core/auth.py                 # JWT + 认证中间件
├── core/security.py             # 密码哈希
├── models/user.py               # User, Role, Permission, APIKey ORMs
└── schemas/user.py / auth.py    # Pydantic schemas
```

### 6.2 RBAC 角色

| 角色 | 权限 |
|------|------|
| Admin | 全量控制: 用户管理, 角色分配, 系统配置, 审计 |
| Editor | 知识库运营: 上传文档, 管理连接器, 评估测试 |
| Viewer | 纯查询: 提问, 查看引用, 反馈 |
| Developer | 程序化集成: API Keys, 构建自定义应用 |

### 6.3 认证流程

```
POST /api/v1/auth/login { username, password }
  → JWT access_token (30min) + refresh_token (7d)
  → All API calls: Authorization: Bearer <token>
  → Middleware: get_current_user() 验证 token → User ORM
```

---

## 7. 技能仓库

### 7.1 模块列表

```
backend/app/
├── api/v1/skills.py              # Skill CRUD + Publish + Tag + Lock + Download API
├── services/skill_registry.py    # RegistryService, TagService, DependencyResolver, LockService
├── services/skill_storage.py     # blob 文件存储 + SHA256 哈希
├── models/skill.py               # Skill, Version, Tag, UserLock, DeclaredDep, LockedDep ORMs
└── schemas/skill.py              # Pydantic schemas
```

### 7.2 数据模型

```
Skill (技能) 1──* Version (版本)
                   │
                   ├──* Tag (标签/可变指针: stable, beta, latest)
                   ├──* DeclaredDep (依赖声明: dep_skill_name + constraint)
                   └──* LockedDep (依赖锁定: dep_skill_name + resolved_version)

UserLock: user_id + skill_id + version_id (用户级别版本固定)
```

### 7.3 核心流程

```
Publish:
  1. 解析 SemVer → 验证格式
  2. 上传文件 → blob 存储 /blobs/{name}/{version}/
  3. SHA256 校验 → 写入 versions 表
  4. 依赖解析 → DependencyResolver.resolve()
      ├─ BFS 遍历 declared_deps
      ├─ SemVer 约束匹配 → 选最高满足版本
      └─ 写入 locked_deps 表

Resolve (版本决策):
  Priority: User Lock > Tag (stable) > Latest released version

Download:
  GET /skills/{name}/download?version=1.0.0
  → 读取 blob 文件 → 打包 zip → StreamingResponse
```

---

## 8. 数据源集成

### 8.1 模块列表

```
backend/app/
├── api/v1/data_sources.py       # DataSource CRUD + Sync API
├── services/data_source_service.py # DataSource management
├── connectors/                   # 连接器实现
│   ├── web_connector.py          # 网页爬虫
│   ├── api_connector.py          # REST API
│   ├── database_connector.py     # 数据库
│   ├── confluence_connector.py   # Confluence Wiki
│   ├── notion_connector.py       # Notion
│   └── git_connector.py          # Git 仓库
├── workers/sync_engine.py        # 数据源同步引擎
└── models/data_source.py         # DataSource, SyncJob, SyncedItem ORMs
```

### 8.2 支持的连接器

| 连接器 | 说明 |
|--------|------|
| Local File | 本地文件上传 |
| Web Page | 网页爬取 (HTML 解析) |
| WeChat Official | 微信公众号 |
| Database | 数据库直连 (SQL) |
| REST API | HTTP API 集成 |
| Object Storage | S3/MinIO 兼容 |
| SharePoint | Microsoft SharePoint |
| Confluence | Atlassian Confluence Wiki |
| Notion | Notion 页面 |

---

## 9. 监控与可观测性

### 9.1 模块列表

```
backend/app/
├── api/v1/metrics.py             # 检索指标 API
├── api/v1/prometheus.py          # Prometheus 指标导出
├── api/v1/dashboard.py           # Dashboard 统计 API
├── core/observability.py         # 请求中间件 (慢请求告警, trace_id)
├── core/prometheus_client.py     # Prometheus 指标注册
├── services/stats_service.py     # 统计聚合
├── services/token_usage_service.py # Token 用量统计
└── models/token_usage.py         # TokenUsage ORM
```

### 9.2 监控指标

| 指标 | 说明 |
|------|------|
| 搜索延迟 (P50/P95/P99) | Redis: rag:latency:recent |
| 搜索次数 | Redis: rag:stats:{date}.searches |
| 零结果搜索 | Redis: rag:stats:{date}.zero_results |
| 热门文档 | Redis: rag:top_docs (ZSET) |
| Token 用量 | DB: token_usages (input/output/total) |
| 服务健康 | /health (postgres + redis + milvus + minio) |
| 慢请求告警 | observability middleware (>5s → WARNING) |

---

## 10. 前端页面结构

### 10.1 路由映射

```
App.tsx (MainAppContent)
├─ dashboard         → DashboardView       # 仪表盘
├─ qa-chat           → QAChatView          # AI 对话 (SSE 流式)
├─ knowledge-bases   → KnowledgeBasesView  # 知识库管理
├─ documents         → DocumentsView       # 文档上传/列表
├─ retrieval-test    → RetrievalTestView   # 检索测试
├─ data-ingestion    → DataIngestionView   # 数据源 + 模型管理
├─ model-management  → ModelManagement     # 模型配置
├─ skill-management  → SkillManagement     # 技能仓库
├─ users-roles       → UserManagement      # 用户管理
├─ settings          → SystemSettingsView  # 系统设置
├─ evaluation        → EvaluationPage      # RAG 评估
├─ monitoring        → MonitoringView      # 健康监控
├─ api-explorer      → ApiExplorerView     # API 文档
├─ token-usage       → TokenUsageAnalysis  # Token 用量
└─ quota-management  → QuotaManagement     # 配额管理
```

### 10.2 页面功能摘要

| 页面 | 核心功能 | 主要 API |
|------|---------|---------|
| DashboardView | 指标卡片, 健康状态, 热门文档 | /dashboard/* |
| QAChatView | 流式对话, 思考过程开关, 引用溯源 | /chat/completions |
| KnowledgeBasesView | KB 创建/删除, 权限设置 | /knowledge-bases |
| DocumentsView | 拖拽上传, 分类/标签, 状态追踪 | /documents/* |
| RetrievalTestView | 搜索测试, 参数调节, 历史记录 | /retrieval/search |
| SystemSettingsView | 分块/检索/安全配置 | /settings |
| ModelManagement | 模型 CRUD, 预设模板, 连接测试 | /models/* |
| SkillManagement | 版本发布, 标签, 依赖, 锁定, 下载 | /skills/* |
| UserManagement | 用户/角色 CRUD, RBAC | /users/* |
| DataSourceManagement | 9 种连接器, 同步调度 | /data-sources/* |
| MonitoringView | 服务健康状态 | /dashboard/stats |
| EvaluationPage | 黄金样本, 评估运行 | /evaluation/* |
| TokenUsageAnalysis | 用量统计, 趋势图 | /token-usage/my-* |
| QuotaManagement | 配额设置 (Admin) | /token-usage/admin/* |
