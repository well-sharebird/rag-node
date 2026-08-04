# 前后端包结构迁移 — 完成报告

## 一、迁移概述

将 RAG、Model Gateway、Prompt、Agent 四个业务模块在前后端各自拆分为独立 package，实现按业务域隔离。

### 迁移规模

| 维度 | 后端 | 前端 |
|------|------|------|
| 移动文件数 | 178 | 69 (+ 26 UI 组件 = 95) |
| Import 更新文件数 | 170+ | 69 (相对→绝对) + App.tsx + barrel |
| 向后兼容桩文件 | 0 (shell 模式) | 69 |
| 验证方式 | uvicorn 启动 + 161 API 路径 + 健康检查 | vite build + dev server HTTP 200 |

---

## 二、后端包结构（已完成验证）

```
backend/
├── packages/
│   ├── core/          # 共享基础设施（DB/auth/deps/config/infra/system）
│   ├── rag/           # RAG 模块（api/services/models/schemas/connectors/workers/preprocessing）
│   ├── model_gateway/ # 模型网关（api/services/models/schemas）
│   ├── prompt/        # 提示词工程（api/services/cli/models/schemas）
│   └── agent/         # 智能体（api/services/models/schemas/middlewares/skills/tools/mcp/workers）
├── app/               # 主应用壳（main.py + router.py + models/__init__.py）
├── alembic/           # 数据库迁移
└── tests/
```

**验证结果**：服务正常启动，161 条 API 路径注册，健康检查全部通过（postgres/redis/milvus/minio），0 条重复路由警告。

---

## 三、前端包结构（本次完成）

```
rag/                             # 项目根目录
├── packages/
│   ├── core/src/
│   │   ├── api/                 # fetchApi 基础封装 + auth/admin/users API
│   │   ├── lib/                 # app-context/auth-context/i18n/env/utils/mock-data
│   │   ├── system/
│   │   │   ├── components/      # Layout/DashboardView/MonitoringView/ApiExplorer/SystemSettings/Markdown
│   │   │   └── pages/          # Login/UserMgmt/RoleMgmt/DeptMgmt/MenuMgmt/KimiShowcase
│   │   ├── ui-kit/
│   │   │   ├── bird/           # 13 个 UI 组件
│   │   │   └── enterprise/     # 13 个 UI 组件
│   │   └── types.ts
│   ├── rag/src/
│   │   ├── api/                 # kb/documents/retrieval/dataSource/evaluation
│   │   ├── components/         # KBManager/Documents/RetrievalTest/DataIngestion/DocProgress/SourcePanel/Synonym/Desensitization
│   │   ├── pages/              # DataSourceManagement/EvaluationPage
│   │   └── hooks/              # useDocumentProgress
│   ├── model-gateway/src/
│   │   ├── api/                 # models/tokenUsage/quota
│   │   ├── components/         # ModelConfigForm
│   │   └── pages/              # ModelManagement/GatewayView/GatewayDashboard/RoutingView/TokenUsage/Quota
│   ├── prompt/src/
│   │   ├── api/                 # prompts
│   │   └── components/         # PromptTemplatesView/PromptTemplateDetail
│   └── agent/src/
│       ├── api/                 # agent-execute/tracing/conversation/feedback/conversationHistory/skills
│       ├── components/        # AgentChatWithDebug/AgentDebugPanel/ChatMessageList/QAChatView/ExecutionTracingView
│       ├── pages/              # AgentPlaza/AgentChat/ConversationHistory/SkillManagement
│       └── hooks/             # useAgentExecute
├── lib/
│   └── api-client.ts           # Barrel re-export（从 @packages/ 重导出所有 API）
├── src/
│   ├── App.tsx                 # 主壳，直接 import @packages/*
│   ├── main.tsx                # 入口
│   └── *.tsx (stubs)          # 69 个 re-export 桩文件
├── tsconfig.json               # 添加 @packages/* 路径别名
└── vite.config.ts              # 添加 @packages/* Vite alias
```

### 关键设计决策

1. **Barrel re-export 模式**：`lib/api-client.ts` 从 1393 行单文件瘦身为纯 re-export barrel，所有现有 `import { ... } from '@/lib/api-client'` 零改动继续工作。

2. **桩文件向后兼容**：69 个旧位置文件变为 re-export 桩（`export * from '@/packages/...'`），所有相对导入路径零改动继续工作。

3. **App.tsx 直接包导入**：主应用壳直接使用 `@packages/core/system/components/Layout` 等路径，包边界清晰可见。

4. **@packages/ 别名体系**：
   - `tsconfig.json`：`@packages/core/*` → `./packages/core/src/*`
   - `vite.config.ts`：`@packages/core` → `packages/core/src`
   - 包内 API 文件互相引用使用 `@packages/core/api/core`

---

## 四、验证结果

| 验证项 | 结果 |
|--------|------|
| TypeScript 类型检查 | 通过（无新增错误） |
| Vite 生产构建 | ✓ built in 5.03s |
| Dev 开发服务器 | HTTP 200，正常启动 |
| 包间导入解析 | 全部正确（@packages/ 别名） |
| 向后兼容性 | 69 个桩文件确保旧导入路径全部可用 |

---

## 五、后续可优化项

1. **渐进式移除桩文件**：将各组件/页面的导入逐步从旧路径切换到 `@packages/` 路径，然后删除对应桩文件。
2. **UI Kit 合并**：bird 和 enterprise 两套 UI 组件库可在 core 包内合并为一套。
3. **包间接口抽象**：参考后端的 port 模式，定义前端各包间的 TypeScript 接口。
4. **代码分割**：利用包结构做 lazy loading，减小主 chunk 体积（当前 2.6MB）。
