# 前后端包结构迁移规划

> 生成时间：2026-08-04
> 目标：将 RAG、Model Gateway、Prompt、Agent 四个业务模块在前后端各自拆分为独立 package，实现按业务域隔离。

---

## 一、现状与问题

### 1.1 当前结构

**后端**：单体 `backend/app/`，按技术层切分（api / services / models / schemas / core），所有业务模块代码混在同一层。

```
backend/app/
├── api/v1/          # 28 个路由文件，全部注册在一个 router.py
├── services/         # 54 个 service 文件 + prompt/ 子目录
├── models/          # 18 个 ORM 模型文件
├── schemas/         # 18 个 Pydantic schema 文件
├── core/            # 19 个基础设施文件（DB/ES/Milvus/Kafka/auth...）
├── agents/          # 仅 middlewares/plan_middleware.py
├── connectors/      # 7 个数据连接器
├── mcp_integration/ # MCP 集成
├── skills/          # 技能工具
├── tools/          # agent 工具
├── workers/        # 后台任务
├── preprocessing/  # 文本清洗
├── cli/            # prompt CLI
└── utils/          # 通用工具
```

**前端**：单 `package.json`，页面/组件在 `src/`，所有 API 调用堆在 `lib/api-client.ts`（1394 行单文件）。

```
src/
├── components/      # 25+ 业务组件 + bird/ + enterprise/ UI 库
├── pages/          # 18 个页面
├── hooks/          # 2 个 hooks
├── lib/api/        # 3 个独立 API 文件（agent-execute/prompts/tracing）
└── lib/            # auth-context / i18n / env
lib/
├── api-client.ts   # 1394 行，所有 API 调用混在一起
├── app-context.tsx
├── mock-data.tsx
└── utils.ts
```

### 1.2 核心问题

| 问题 | 说明 |
|------|------|
| 业务边界模糊 | 改 RAG 检索逻辑要在 services/ 50 个文件里找；改 Agent 要同时动 api/services/models/schemas 四个目录 |
| 前端 API 巨石 | `api-client.ts` 1394 行，RAG/Model/Prompt/Agent 的调用全混在一个文件 |
| 难以独立演进 | 想给 Agent 模块单独发版或独立测试，无法做到 |
| import 膨胀 | service 之间互相 import，形成隐式依赖网，重构风险高 |

---

## 二、四大模块定义与边界

### 模块 1：RAG（检索增强生成）

**职责**：知识库管理、文档摄取与处理、向量存储与检索、数据源同步、检索质量评估、同义词管理、数据脱敏。

**业务边界**：从「数据进入系统」到「检索出 chunk」的完整链路，不含 LLM 调用和对话编排。

### 模块 2：Model Gateway（模型网关）

**职责**：模型配置管理、LLM 调用封装、多模型 fallback 链、模型健康监控、Token 用量统计与配额。

**业务边界**：所有与外部 LLM/API 交互的统一出口。RAG 的 embedding 调用、Agent 的 LLM 调用都经过此网关。

### 模块 3：Prompt（提示词工程）

**职责**：提示词模板管理、注册/渲染/评估/发布/审计全生命周期。

**业务边界**：提示词的存储、版本、渲染。不含对话流程控制。

### 模块 4：Agent（智能体）

**职责**：智能体编排与运行时、图工厂、记忆与检查点、子智能体、会话管理、技能注册、执行追踪、工具调用。

**业务边界**：对话编排与执行。会调用 Model Gateway（LLM）、Prompt（渲染）、RAG（检索），但编排逻辑归属本模块。

---

## 三、当前代码分布梳理

### 3.1 后端 — 按模块归类

#### RAG 模块

| 层 | 当前路径 | 文件 |
|----|----------|------|
| api | `app/api/v1/` | `knowledge_bases.py` · `documents.py` · `retrieval.py` · `data_sources.py` · `evaluation.py` · `synonyms.py` · `desensitization.py` |
| services | `app/services/` | `kb_service.py` · `document_service.py` · `retrieval_service.py` · `chunking_service.py` · `embedding_service.py` · `vector_store_service.py` · `parsing_service.py` · `multi_index_service.py` · `mmr_service.py` · `rrf_fusion.py` · `query_expansion.py` · `keyword_extraction_service.py` · `multi_modal_retrieval.py` · `synonym_service.py` · `evaluation_service.py` · `data_source_service.py` · `document_enrichment.py` · `ingestion_validator.py` · `file_type_router.py` · `desensitization_service.py` |
| models | `app/models/` | `knowledge_base.py` · `document.py` · `data_source.py` · `synonym.py` · `evaluation.py` · `desensitization_config.py` |
| schemas | `app/schemas/` | `knowledge_base.py` · `document.py` · `retrieval.py` · `data_source.py` · `evaluation.py` · `parsing.py` |
| connectors | `app/connectors/` | `api_connector.py` · `base.py` · `confluence_connector.py` · `database_connector.py` · `factory.py` · `git_connector.py` · `notion_connector.py` · `web_connector.py`（整个目录） |
| core | `app/core/` | `rag_config.py` · `fts_engine.py` · `elasticsearch_client.py` · `es_client.py` · `milvus_client.py` |
| workers | `app/workers/` | `document_pipeline.py` · `sync_engine.py` |
| preprocessing | `app/preprocessing/` | `text_cleaner.py` |

#### Model Gateway 模块

| 层 | 当前路径 | 文件 |
|----|----------|------|
| api | `app/api/v1/` | `models.py` · `model_gateway.py` · `token_usage.py` |
| services | `app/services/` | `model_service.py` · `model_config_service.py` · `model_gateway_service.py` · `model_health_monitor.py` · `llm_service.py` · `llm_fallback_chain.py` · `token_usage_service.py` |
| models | `app/models/` | `model_config.py` · `model_gateway.py` |
| schemas | `app/schemas/` | `model.py` · `model_gateway.py` |

#### Prompt 模块

| 层 | 当前路径 | 文件 |
|----|----------|------|
| api | `app/api/v1/` | `prompts.py` |
| services | `app/services/` | `prompt_template_service.py` |
| services | `app/services/prompt/` | `registry.py` · `renderer.py` · `evaluator.py` · `publisher.py` · `audit.py` · `__init__.py`（整个目录） |
| cli | `app/cli/` | `prompt.py` |
| models | `app/models/` | `prompt_template.py` |
| schemas | `app/schemas/` | `prompt.py` |

#### Agent 模块

| 层 | 当前路径 | 文件 |
|----|----------|------|
| api | `app/api/v1/` | `agents.py` · `agent_runtime.py` · `conversations.py` · `conversation_history.py` · `feedback.py` · `tracing.py` · `chat.py`(废弃) · `skills.py` |
| services | `app/services/` | `agent_service.py` · `agent_bootstrap.py` · `agent_builder_service.py` · `agent_checkpoint_service.py` · `agent_config_service.py` · `agent_graph_factory.py` · `agent_memory_service.py` · `agent_monitoring_service.py` · `agent_runtime_service.py` · `lead_agent_factory.py` · `meta_agent_service.py` · `subagent_service.py` · `conversation_service.py` · `conversation_memory.py` · `conversation_archive_service.py` · `feedback_service.py` · `trace_service.py` · `skill_registry.py` · `skill_storage.py` · `version_manager.py` · `stats_service.py` · `intent_classifier.py` |
| models | `app/models/` | `agent.py` · `conversation.py` · `conversation_archive.py` · `feedback.py` · `skill.py` |
| schemas | `app/schemas/` | `chat.py` · `conversation.py` · `skill.py` |
| agents | `app/agents/middlewares/` | `plan_middleware.py` |
| skills | `app/skills/` | `agent_tools.py` · `create_agent_skill.py` · `knowledge_base_tools.py` · `model_tools.py` · `prompt_tools.py`（整个目录） |
| tools | `app/tools/` | `builtins.py` · `meta_agent_tools.py`（整个目录） |
| mcp | `app/mcp_integration/` | `client.py` · `config.py` · `server.py` · `tools/`（整个目录，归属待定，见 3.3） |
| workers | `app/workers/` | `archive_scheduler.py` · `arq_worker.py` |

#### 跨模块共享（归入 core 包）

| 层 | 当前路径 | 文件 | 说明 |
|----|----------|------|------|
| core | `app/core/` | `database.py` · `auth.py` · `deps.py` · `logging_config.py` · `observability.py` · `prometheus_client.py` · `kafka_client.py` · `message_queue.py` · `minio_client.py` · `neo4j_client.py` · `knowledge_graph.py` · `init_data.py` · `init_db.py` | 基础设施，所有模块共享 |
| api | `app/api/v1/` | `auth.py` · `admin.py` · `users.py` · `dashboard.py` · `health.py` · `metrics.py` · `prometheus.py` · `settings.py` · `router.py` | 系统级路由 |
| services | `app/services/` | `menu_service.py` · `department_service.py` · `settings_service.py` | RBAC/系统设置 |
| models | `app/models/` | `base.py` · `menu.py` · `department.py` · `system_setting.py` | 系统 ORM |
| schemas | `app/schemas/` | `auth.py` · `dashboard.py` · `department.py` · `menu.py` · `settings.py` | 系统 schema |
| utils | `app/utils/` | `error_handlers.py` · `exceptions.py` · `file_utils.py` | 通用工具 |

### 3.2 前端 — 按模块归类

#### RAG 模块

| 类型 | 当前路径 | 文件 |
|------|----------|------|
| pages | `src/pages/` | `DataSourceManagement.tsx` · `EvaluationPage.tsx` |
| components | `src/components/` | `KnowledgeBaseManager.tsx` · `DocumentsView.tsx` · `RetrievalTestView.tsx` · `DataIngestionView.tsx` · `DocumentProgressList.tsx` · `SourcePanel.tsx` · `SynonymManagement.tsx` · `DesensitizationManagement.tsx` |
| api | `lib/api-client.ts` 内 | KB 相关函数(fetchKBs/fetchKB/createKB/deleteKB/updateKB)、Document 相关(fetchDocs/deleteDoc/uploadDoc/batchUploadDocs/reprocessDocument/batchReprocessDocuments/listFailedDocuments/getDocumentVersions/previewChunks)、Retrieval 相关(searchChunks/fetchSearchHistory)、DataSource 相关(fetchDataSources/syncDataSource 等)、Evaluation 相关(createGoldenSample 等)、ChunkPreview |

#### Model Gateway 模块

| 类型 | 当前路径 | 文件 |
|------|----------|------|
| pages | `src/pages/` | `ModelManagement.tsx` · `ModelGatewayView.tsx` · `ModelGatewayDashboard.tsx` · `ModelRoutingView.tsx` · `TokenUsageAnalysis.tsx` · `QuotaManagement.tsx` |
| components | `src/components/` | `ModelConfigForm.tsx` |
| api | `lib/api-client.ts` 内 | Model 相关(fetchModels/fetchModelPresets/testModelConnection/deleteModel/updateModel/createModel/getDefaultModel)、TokenUsage 相关(getMyTokenUsage/getMyTokenTrend/fetchMyQuota)、Quota 相关(fetchAllQuotas/setUserQuota) |

#### Prompt 模块

| 类型 | 当前路径 | 文件 |
|------|----------|------|
| components | `src/components/` | `PromptTemplatesView.tsx` · `PromptTemplateDetail.tsx` |
| api | `src/lib/api/prompts.ts` | 独立文件，已是模块化状态 |

#### Agent 模块

| 类型 | 当前路径 | 文件 |
|------|----------|------|
| pages | `src/pages/` | `AgentPlaza.tsx` · `AgentChat.tsx` · `ConversationHistory.tsx` · `SkillManagement.tsx` |
| components | `src/components/` | `AgentChatWithDebug.tsx` · `AgentDebugPanel.tsx` · `ChatMessageList.tsx` · `QAChatView.tsx` · `ExecutionTracingView.tsx` |
| hooks | `src/hooks/` | `useAgentExecute.ts` |
| api | `src/lib/api/` | `agent-execute.ts` · `tracing.ts` |
| api | `lib/api-client.ts` 内 | Conversation 相关(createConversation/listConversations 等)、Feedback 相关(submitFeedback/getFeedbackStats 等)、ConversationHistory 相关(fetchConversationHistory/fetchThreadMessages 等) |

#### 跨模块共享（归入 core 包）

| 类型 | 当前路径 | 文件 |
|------|----------|------|
| app 壳 | `src/` | `App.tsx` · `main.tsx` · `types.ts` |
| 公共页面 | `src/pages/` | `Login.tsx` · `UserManagement.tsx` · `RoleManagement.tsx` · `DepartmentManagement.tsx` · `MenuManagement.tsx` · `KimiDesignShowcase.tsx` |
| 公共组件 | `src/components/` | `Layout.tsx` · `DashboardView.tsx` · `MonitoringView.tsx` · `ApiExplorerView.tsx` · `SystemSettingsView.tsx` · `MarkdownPreview.tsx` · `MarkdownRenderer.tsx` |
| UI 库 | `src/components/bird/` · `src/components/enterprise/` | 两套 UI 组件库（整个目录） |
| lib | `lib/` | `api-client.ts`(拆分后留基础 fetch 封装) · `app-context.tsx` · `mock-data.tsx` · `utils.ts` |
| lib | `src/lib/` | `auth-context.tsx` · `i18n.tsx` · `env.ts` |

### 3.3 归属待定 / 跨模块依赖说明

| 文件/目录 | 依赖情况 | 建议归属 |
|-----------|----------|----------|
| `app/mcp_integration/` | Agent 的 tools 依赖它，但 kb_tools/model_tools/prompt_tools 跨模块 | 归 Agent 包，各 tools 按需 import 各模块的 service 接口 |
| `app/skills/` | 含 `knowledge_base_tools.py`/`model_tools.py`/`prompt_tools.py`，跨模块 | 归 Agent 包（skill 是 agent 的能力扩展），跨模块调用走接口 |
| `llm_service.py` | RAG 的 embedding 和 Agent 的 LLM 都调用 | 归 Model Gateway，RAG/Agent 通过接口调用 |
| `intent_classifier.py` | 既用于 RAG 路由又用于 Agent | 归 Agent（语义理解属编排层），RAG 走接口 |
| `embedding_service.py` | RAG 核心，但依赖 llm_service | 归 RAG，通过 Model Gateway 接口获取 embedding |

---

## 四、目标包结构设计

### 4.1 后端目标结构

```
backend/
├── packages/
│   ├── core/                       # 共享基础设施
│   │   ├── __init__.py
│   │   ├── database.py             # SQLAlchemy 引擎/Session
│   │   ├── auth.py                 # JWT/权限
│   │   ├── deps.py                 # FastAPI 依赖注入
│   │   ├── config.py               # 全局配置
│   │   ├── logging_config.py
│   │   ├── observability.py
│   │   ├── exceptions.py
│   │   ├── error_handlers.py
│   │   ├── file_utils.py
│   │   ├── base_model.py           # ORM base
│   │   ├── system/                 # RBAC/菜单/部门/设置
│   │   │   ├── models/             # menu/department/system_setting
│   │   │   ├── schemas/
│   │   │   ├── services/           # menu/department/settings
│   │   │   └── api/                # auth/admin/users/dashboard/health/metrics
│   │   └── infra/                  # 基础设施客户端
│   │       ├── milvus_client.py
│   │       ├── elasticsearch_client.py
│   │       ├── es_client.py
│   │       ├── minio_client.py
│   │       ├── kafka_client.py
│   │       ├── message_queue.py
│   │       ├── neo4j_client.py
│   │       ├── knowledge_graph.py
│   │       └── prometheus_client.py
│   │
│   ├── rag/                        # RAG 模块
│   │   ├── __init__.py
│   │   ├── api/                    # knowledge_bases/documents/retrieval/data_sources/evaluation/synonyms/desensitization
│   │   ├── services/               # kb/document/retrieval/chunking/embedding/vector_store/parsing/mmr/rrf/query_expansion/...
│   │   ├── models/                 # knowledge_base/document/data_source/synonym/evaluation/desensitization_config
│   │   ├── schemas/                # knowledge_base/document/retrieval/data_source/evaluation/parsing
│   │   ├── connectors/             # 7 个数据连接器
│   │   ├── workers/                # document_pipeline/sync_engine
│   │   └── preprocessing/          # text_cleaner
│   │
│   ├── model_gateway/              # 模型网关模块
│   │   ├── __init__.py
│   │   ├── api/                    # models/model_gateway/token_usage
│   │   ├── services/               # llm_service/llm_fallback_chain/model_service/model_config_service/model_gateway_service/model_health_monitor/token_usage_service
│   │   ├── models/                 # model_config/model_gateway
│   │   └── schemas/                # model/model_gateway
│   │
│   ├── prompt/                     # 提示词模块
│   │   ├── __init__.py
│   │   ├── api/                    # prompts
│   │   ├── services/               # template_service + registry/renderer/evaluator/publisher/audit
│   │   ├── cli/                    # prompt CLI
│   │   ├── models/                 # prompt_template
│   │   └── schemas/                # prompt
│   │
│   └── agent/                      # Agent 模块
│       ├── __init__.py
│       ├── api/                    # agents/agent_runtime/conversations/conversation_history/feedback/tracing/skills
│       ├── services/               # agent_*/conversation_*/feedback/trace/skill_registry/skill_storage/version_manager/stats/intent_classifier
│       ├── models/                  # agent/conversation/conversation_archive/feedback/skill
│       ├── schemas/                # chat/conversation/skill
│       ├── middlewares/            # plan_middleware
│       ├── skills/                 # agent_tools/create_agent_skill/knowledge_base_tools/model_tools/prompt_tools
│       ├── tools/                  # builtins/meta_agent_tools
│       ├── mcp/                    # mcp_integration 全部
│       └── workers/                # archive_scheduler/arq_worker
│
├── app/                            # 主应用壳（仅组装）
│   ├── main.py                     # FastAPI 实例 + 注册各 package router
│   └── router.py                   # 聚合各 package 的 APIRouter
│
├── alembic/                        # 数据库迁移（保留原位）
├── tests/                          # 测试（可按模块拆分）
├── pyproject.toml                  # 各 package 作为本地依赖注册
└── requirements.txt
```

**包间依赖规则**（单向，禁止循环）：

```
core  ←  rag
core  ←  model_gateway
core  ←  prompt
core  ←  agent

rag       → model_gateway   (embedding 调用)
agent     → model_gateway   (LLM 调用)
agent     → prompt           (提示词渲染)
agent     → rag              (检索调用)
prompt    → model_gateway    (评估时调用 LLM)
```

> 用接口抽象切断直接依赖：如 `agent` 依赖 `rag` 的检索能力时，定义 `RetrievalPort` 接口在 core，rag 实现它，agent 只依赖接口。可后续优化，第一步先按包隔离。

### 4.2 前端目标结构

```
frontend/                          # 根目录（pnpm workspace）
├── pnpm-workspace.yaml
├── package.json                   # 根，仅管理 workspace + devDeps
├── tsconfig.json                  # 根 tsconfig，paths 指向各包
├── vite.config.ts                  # 根配置
├── packages/
│   ├── core/                       # 共享层
│   │   ├── package.json
│   │   ├── src/
│   │   │   ├── ui-kit/             # bird/ + enterprise/ 合并为一套
│   │   │   ├── api-client.ts       # 基础 fetch 封装（从 1394 行瘦身到 ~60 行）
│   │   │   ├── auth-context.tsx
│   │   │   ├── app-context.tsx
│   │   │   ├── i18n.tsx
│   │   │   ├── env.ts
│   │   │   ├── utils.ts
│   │   │   ├── types.ts
│   │   │   └── system/             # RBAC/菜单/部门/设置 页面与 API
│   │   │       ├── pages/          # Login/UserMgmt/RoleMgmt/DeptMgmt/MenuMgmt
│   │   │       ├── components/      # Layout/DashboardView/MonitoringView/ApiExplorer/SystemSettings
│   │   │       └── api/            # auth/admin/users/dashboard/metrics/health/settings
│   │   └── index.ts
│   │
│   ├── rag/
│   │   ├── package.json
│   │   ├── src/
│   │   │   ├── pages/              # DataSourceManagement/EvaluationPage
│   │   │   ├── components/         # KBManager/Documents/RetrievalTest/DataIngestion/DocProgress/SourcePanel/Synonym/Desensitization
│   │   │   └── api/                # kb.ts/documents.ts/retrieval.ts/dataSource.ts/evaluation.ts (从 api-client.ts 拆出)
│   │   └── index.ts
│   │
│   ├── model-gateway/
│   │   ├── package.json
│   │   ├── src/
│   │   │   ├── pages/              # ModelManagement/GatewayView/GatewayDashboard/RoutingView/TokenUsage/Quota
│   │   │   ├── components/         # ModelConfigForm
│   │   │   └── api/                # models.ts/tokenUsage.ts/quota.ts (从 api-client.ts 拆出)
│   │   └── index.ts
│   │
│   ├── prompt/
│   │   ├── package.json
│   │   ├── src/
│   │   │   ├── components/         # PromptTemplatesView/PromptTemplateDetail
│   │   │   └── api/                # prompts.ts (已独立，直接迁入)
│   │   └── index.ts
│   │
│   └── agent/
│       ├── package.json
│       ├── src/
│       │   ├── pages/              # AgentPlaza/AgentChat/ConversationHistory/SkillManagement
│       │   ├── components/        # AgentChatWithDebug/AgentDebugPanel/ChatMessageList/QAChatView/ExecutionTracingView
│       │   ├── hooks/             # useAgentExecute
│       │   └── api/               # agent-execute.ts/tracing.ts/conversation.ts/feedback.ts/conversationHistory.ts (后三个从 api-client.ts 拆出)
│       └── index.ts
│
└── src/                            # 主应用壳
    ├── App.tsx                     # 路由组装，import 各包导出的页面
    ├── main.tsx
    └── index.html
```

**包间依赖规则**：

```
core  ←  所有业务包（rag/model-gateway/prompt/agent 都依赖 core 的 ui-kit 和 api-client）
业务包之间不直接依赖（页面组合在 App.tsx 完成，不在包内互相 import）
```

---

## 五、迁移映射表（当前 → 目标）

### 5.1 后端迁移映射

| 当前文件 | → 目标位置 |
|----------|-----------|
| `app/core/database.py` `auth.py` `deps.py` `logging_config.py` `observability.py` `exceptions.py` `error_handlers.py` `file_utils.py` | `packages/core/` |
| `app/models/base.py` | `packages/core/base_model.py` |
| `app/core/milvus_client.py` `elasticsearch_client.py` `es_client.py` `minio_client.py` `kafka_client.py` `message_queue.py` `neo4j_client.py` `knowledge_graph.py` `prometheus_client.py` | `packages/core/infra/` |
| `app/core/rag_config.py` `fts_engine.py` | `packages/rag/services/` 或 `packages/rag/config.py` |
| `app/core/init_data.py` `init_db.py` | `packages/core/` (初始化脚本) |
| `app/api/v1/auth.py` `admin.py` `users.py` `dashboard.py` `health.py` `metrics.py` `prometheus.py` `settings.py` | `packages/core/system/api/` |
| `app/models/menu.py` `department.py` `system_setting.py` | `packages/core/system/models/` |
| `app/schemas/auth.py` `dashboard.py` `department.py` `menu.py` `settings.py` | `packages/core/system/schemas/` |
| `app/services/menu_service.py` `department_service.py` `settings_service.py` | `packages/core/system/services/` |
| `app/api/v1/knowledge_bases.py` `documents.py` `retrieval.py` `data_sources.py` `evaluation.py` `synonyms.py` `desensitization.py` | `packages/rag/api/` |
| `app/services/{kb,document,retrieval,chunking,embedding,vector_store,parsing,multi_index,mmr,rrf_fusion,query_expansion,keyword_extraction,multi_modal_retrieval,synonym,evaluation,data_source,document_enrichment,ingestion_validator,file_type_router,desensitization}_service.py` | `packages/rag/services/` |
| `app/models/{knowledge_base,document,data_source,synonym,evaluation,desensitization_config}.py` | `packages/rag/models/` |
| `app/schemas/{knowledge_base,document,retrieval,data_source,evaluation,parsing}.py` | `packages/rag/schemas/` |
| `app/connectors/` (全部) | `packages/rag/connectors/` |
| `app/workers/{document_pipeline,sync_engine}.py` | `packages/rag/workers/` |
| `app/preprocessing/text_cleaner.py` | `packages/rag/preprocessing/` |
| `app/api/v1/{models,model_gateway,token_usage}.py` | `packages/model_gateway/api/` |
| `app/services/{model_service,model_config_service,model_gateway_service,model_health_monitor,llm_service,llm_fallback_chain,token_usage_service}.py` | `packages/model_gateway/services/` |
| `app/models/{model_config,model_gateway}.py` | `packages/model_gateway/models/` |
| `app/schemas/{model,model_gateway}.py` | `packages/model_gateway/schemas/` |
| `app/api/v1/prompts.py` | `packages/prompt/api/` |
| `app/services/prompt_template_service.py` + `app/services/prompt/` (全部) | `packages/prompt/services/` |
| `app/cli/prompt.py` | `packages/prompt/cli/` |
| `app/models/prompt_template.py` | `packages/prompt/models/` |
| `app/schemas/prompt.py` | `packages/prompt/schemas/` |
| `app/api/v1/{agents,agent_runtime,conversations,conversation_history,feedback,tracing,chat,skills}.py` | `packages/agent/api/` |
| `app/services/{agent_*,conversation_*,conversation_archive_service,conversation_memory,feedback_service,trace_service,skill_registry,skill_storage,version_manager,stats_service,intent_classifier}.py` | `packages/agent/services/` |
| `app/models/{agent,conversation,conversation_archive,feedback,skill}.py` | `packages/agent/models/` |
| `app/schemas/{chat,conversation,skill}.py` | `packages/agent/schemas/` |
| `app/agents/middlewares/` | `packages/agent/middlewares/` |
| `app/skills/` (全部) | `packages/agent/skills/` |
| `app/tools/` (全部) | `packages/agent/tools/` |
| `app/mcp_integration/` (全部) | `packages/agent/mcp/` |
| `app/workers/{archive_scheduler,arq_worker}.py` | `packages/agent/workers/` |
| `app/api/v1/router.py` | `app/router.py` (改为聚合各 package 的 APIRouter) |
| `app/main.py` | `app/main.py` (保留，注册聚合 router) |

### 5.2 前端迁移映射

| 当前文件 | → 目标位置 |
|----------|-----------|
| `src/components/bird/` `src/components/enterprise/` | `packages/core/src/ui-kit/` |
| `lib/api-client.ts` (基础 fetch 封装部分) | `packages/core/src/api-client.ts` |
| `src/lib/auth-context.tsx` `lib/app-context.tsx` `src/lib/i18n.tsx` `src/lib/env.ts` `lib/utils.ts` `src/types.ts` `lib/mock-data.tsx` | `packages/core/src/` |
| `src/pages/{Login,UserManagement,RoleManagement,DepartmentManagement,MenuManagement}.tsx` | `packages/core/src/system/pages/` |
| `src/components/{Layout,DashboardView,MonitoringView,ApiExplorerView,SystemSettingsView,MarkdownPreview,MarkdownRenderer}.tsx` | `packages/core/src/system/components/` |
| `lib/api-client.ts` 内 KB/Doc/Retrieval/DataSource/Evaluation 函数 | `packages/rag/src/api/{kb,documents,retrieval,dataSource,evaluation}.ts` |
| `src/pages/{DataSourceManagement,EvaluationPage}.tsx` | `packages/rag/src/pages/` |
| `src/components/{KnowledgeBaseManager,DocumentsView,RetrievalTestView,DataIngestionView,DocumentProgressList,SourcePanel,SynonymManagement,DesensitizationManagement}.tsx` | `packages/rag/src/components/` |
| `lib/api-client.ts` 内 Model/TokenUsage/Quota 函数 | `packages/model-gateway/src/api/{models,tokenUsage,quota}.ts` |
| `src/pages/{ModelManagement,ModelGatewayView,ModelGatewayDashboard,ModelRoutingView,TokenUsageAnalysis,QuotaManagement}.tsx` | `packages/model-gateway/src/pages/` |
| `src/components/ModelConfigForm.tsx` | `packages/model-gateway/src/components/` |
| `src/components/{PromptTemplatesView,PromptTemplateDetail}.tsx` | `packages/prompt/src/components/` |
| `src/lib/api/prompts.ts` | `packages/prompt/src/api/prompts.ts` |
| `src/pages/{AgentPlaza,AgentChat,ConversationHistory,SkillManagement}.tsx` | `packages/agent/src/pages/` |
| `src/components/{AgentChatWithDebug,AgentDebugPanel,ChatMessageList,QAChatView,ExecutionTracingView}.tsx` | `packages/agent/src/components/` |
| `src/hooks/useAgentExecute.ts` | `packages/agent/src/hooks/` |
| `src/lib/api/{agent-execute,tracing}.ts` | `packages/agent/src/api/` |
| `lib/api-client.ts` 内 Conversation/Feedback/ConversationHistory 函数 | `packages/agent/src/api/{conversation,feedback,conversationHistory}.ts` |
| `src/App.tsx` `src/main.tsx` | `src/` (主壳，import 各包) |

---

## 六、共享/跨模块代码处理策略

### 6.1 前端 `api-client.ts` 拆分（最大工作量）

当前 1394 行单文件，按模块拆分后：

| 拆出文件 | 内容 | 行数估算 |
|----------|------|---------|
| `core/api-client.ts` | `fetchApi`/`api` 基础封装 + `API_BASE_URL` | ~60 行 |
| `core/system/api/auth.ts` | login/register/refreshToken/getMe/getUserMenus/getUserPermissions/getApiKeys/getAuditLogs | ~200 行 |
| `core/system/api/admin.ts` | department/menu CRUD | ~150 行 |
| `rag/api/kb.ts` | KB CRUD | ~60 行 |
| `rag/api/documents.ts` | Doc CRUD/上传/重处理/预览 | ~120 行 |
| `rag/api/retrieval.ts` | searchChunks/history | ~30 行 |
| `rag/api/dataSource.ts` | DataSource CRUD/sync | ~80 行 |
| `rag/api/evaluation.ts` | GoldenSample/EvaluationRun | ~60 行 |
| `model-gateway/api/models.ts` | Model CRUD/presets | ~60 行 |
| `model-gateway/api/tokenUsage.ts` | 个人/管理 token 统计 | ~60 行 |
| `model-gateway/api/quota.ts` | 配额管理 | ~30 行 |
| `agent/api/conversation.ts` | Conversation CRUD | ~80 行 |
| `agent/api/feedback.ts` | Feedback CRUD | ~60 行 |
| `agent/api/conversationHistory.ts` | 历史会话/归档 | ~80 行 |

### 6.2 后端跨模块接口抽象

第一步迁移先按包物理隔离，保留直接 import。后续优化为接口抽象：

| 跨模块调用 | 接口定义位置 | 实现方 | 调用方 |
|-----------|-------------|--------|--------|
| RAG → Model Gateway (embedding) | `core/ports/embedding_port.py` | `model_gateway` | `rag` |
| Agent → Model Gateway (LLM) | `core/ports/llm_port.py` | `model_gateway` | `agent` |
| Agent → Prompt (渲染) | `core/ports/prompt_port.py` | `prompt` | `agent` |
| Agent → RAG (检索) | `core/ports/retrieval_port.py` | `rag` | `agent` |

> 第一步可不做接口抽象，先把文件搬进对应包，import 路径改掉即可。接口抽象是第二阶段优化。

### 6.3 MCP / Skills 跨模块工具

`app/skills/` 下有 `knowledge_base_tools.py`/`model_tools.py`/`prompt_tools.py`，它们是 Agent 调用其他模块的桥接工具。归属 Agent 包，内部通过 import 其他包的 service 实现。迁移时保持功能不变，只改 import 路径。

---

## 七、迁移阶段建议

### 阶段 1：前端 API 拆分（低风险、高收益）

**目标**：把 `api-client.ts` 按模块拆成多个文件，不改包结构。

1. 创建 `src/lib/api/` 下按模块分文件
2. 从 `api-client.ts` 抽出各模块函数到对应文件
3. `api-client.ts` 只保留基础 `fetchApi`/`api` 封装
4. 全局替换 import 路径
5. 验证构建通过

**风险**：低。纯文件移动 + import 替换，不改逻辑。

### 阶段 2：后端按模块整理 services（中风险）

**目标**：后端 services 按模块分子目录，不改包结构。

1. 在 `app/services/` 下创建 `rag/` `model_gateway/` `prompt/` `agent/` `system/` 子目录
2. 移动对应 service 文件
3. 更新 `__init__.py` 和 import
4. 验证启动

**风险**：中。import 链较长，需要全局替换。

### 阶段 3：后端 packages 物理拆分（高风险、核心）

**目标**：创建 `backend/packages/` 多包结构。

1. 创建 `packages/core` `packages/rag` `packages/model_gateway` `packages/prompt` `packages/agent`
2. 按映射表移动文件
3. 每个包内创建 `__init__.py` 和对外暴露的接口
4. `pyproject.toml` 注册本地包依赖
5. `app/router.py` 改为聚合各包 router
6. 全量替换 import 路径
7. 验证启动 + 接口测试

**风险**：高。需一次性完成所有路径替换，建议在独立分支操作。

### 阶段 4：前端 pnpm workspace 化（高风险）

**目标**：前端拆分为 pnpm workspace 多包。

1. 根目录创建 `pnpm-workspace.yaml`
2. 创建 `packages/core` `packages/rag` `packages/model-gateway` `packages/prompt` `packages/agent`
3. 每个包创建 `package.json` + `index.ts` 对外导出
4. 移动文件按映射表
5. `tsconfig.json` 配置 paths 指向各包
6. `vite.config.ts` 配置别名
7. `src/App.tsx` 改为 import 各包导出的页面/组件
8. 验证构建 + 运行

**风险**：高。Vite 对 workspace 包的解析需调通，建议先在 core 一个包验证。

---

## 八、注意事项

1. **import 路径替换是最大工作量**：后端约 200+ 文件需改 import，前端约 40+ 文件。建议用脚本批量替换 + 人工校验。
2. **`router.py` 未注册的路由**：当前 `router.py` 只注册了 17 个 router，但 v1 目录有 28 个文件。`agent_runtime`/`conversations`/`desensitization`/`evaluation`/`feedback`/`model_gateway`/`synonyms`/`tracing` 等未在 router.py 中注册，需确认它们的注册方式（可能在 main.py 或其他地方单独注册），迁移时一并梳理。
3. **alembic 迁移**：ORM 模型移动后，alembic 的 import 路径需同步更新，否则迁移脚本失效。
4. **测试**：`backend/tests/` 下有 `agent/` `conversation_history/` `llm/` 子目录，迁移后需对齐。
5. **前端 UI 库合并**：bird 和 enterprise 两套组件库，建议在 core 包内合并为一套（enterprise 为主，bird 逐步废弃），但这属于独立优化项，不在本次包结构迁移范围内。
6. **渐进式迁移**：建议先做阶段 1（前端 API 拆分）和阶段 2（后端 services 分目录），这两个低风险高收益，做完再推进高风险的物理拆包。
