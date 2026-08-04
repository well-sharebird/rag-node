/**
 * API Client - Barrel Re-export
 *
 * This file re-exports all API functions and types from the modular files
 * under src/lib/api/. It exists for backward compatibility — all existing
 * imports of `@/lib/api-client` continue to work without changes.
 *
 * Module structure:
 *   - core.ts             : fetchApi, api, Dashboard, Settings, Health, Metrics
 *   - core-auth.ts        : login, register, menus, permissions, api-keys
 *   - core-admin.ts       : departments, menus (admin)
 *   - core-users.ts       : users, roles
 *   - rag-kb.ts           : knowledge base CRUD
 *   - rag-documents.ts    : document CRUD, upload, reprocess
 *   - rag-retrieval.ts    : search, history
 *   - rag-data-source.ts  : data source CRUD, sync
 *   - rag-evaluation.ts   : golden samples, evaluation runs
 *   - model-gateway-models.ts      : model CRUD, presets
 *   - model-gateway-token-usage.ts : token stats, personal quota
 *   - model-gateway-quota.ts       : admin quota management
 *   - agent-conversation.ts        : conversations, chat completions
 *   - agent-feedback.ts            : feedback CRUD
 *   - agent-conversation-history.ts: conversation history, archives
 *   - agent-skills.ts              : skill registry, versions, locks
 */

// ============================================================
// Core infrastructure
// ============================================================
export { fetchApi, api } from '@packages/core/api/core';
export type {
  DashboardData, QualityMetricsData, TopDocItem,
  HealthResponse, MetricsHealthResponse, MetricsSummaryResponse,
} from '@packages/core/api/core';
export {
  fetchDashboard, fetchQualityMetrics, fetchTopDocs,
  fetchSettings, updateSettings,
  getHealth, getMetricsHealth, getMetricsSummary, getMetricsJson, getMetricsErrors,
} from '@packages/core/api/core';

// ============================================================
// Auth
// ============================================================
export type {
  LoginRequest, TokenResponse, UserResponse,
  APIKeyResponse, APIKeyListResponse,
  MenuData, MenuTreeResponse, UserPermissionsResponse, UserDepartmentsResponse,
} from '@packages/core/api/core-auth';
export {
  login, register, refreshToken, getMe,
  getUserMenus, getUserPermissions, getUserDepartments,
  createApiKey, getApiKeys, deleteApiKey, getAuditLogs,
} from '@packages/core/api/core-auth';

// ============================================================
// Admin (Departments & Menus)
// ============================================================
export type {
  DepartmentData, DepartmentListResponse, DepartmentTreeResponse,
  MenuListResponse,
} from '@packages/core/api/core-admin';
export {
  fetchDepartments, fetchDepartmentTree,
  createDepartment, updateDepartment, deleteDepartment,
  getDepartmentUsers, addUserToDepartment, removeUserFromDepartment,
  fetchMenus, fetchMenuTree,
  createMenu, updateMenu, deleteMenu, assignMenusToRole,
} from '@packages/core/api/core-admin';

// ============================================================
// Users & Roles
// ============================================================
export type { RoleData, UserData, UserCreate } from '@packages/core/api/core-users';
export {
  fetchUsers, fetchRoles,
  createUser, updateUser, deleteUser, assignUserRoles,
  createRole, updateRole, deleteRole,
} from '@packages/core/api/core-users';

// ============================================================
// RAG - Knowledge Base
// ============================================================
export type { KBData, KBListResponse } from '@packages/rag/api/kb';
export {
  fetchKBs, fetchKnowledgeBases, fetchKB, createKB, deleteKB, updateKB,
} from '@packages/rag/api/kb';

// ============================================================
// RAG - Documents
// ============================================================
export type { DocData, ChunkPreviewRequest, ChunkPreviewResponse } from '@packages/rag/api/documents';
export {
  fetchDocs, deleteDoc, uploadDoc, fetchDocumentCategories, batchUploadDocs,
  fetchDoc, updateDocument, reprocessDocument, batchReprocessDocuments,
  previewChunks, listFailedDocuments, getDocumentVersions,
} from '@packages/rag/api/documents';

// ============================================================
// RAG - Retrieval
// ============================================================
export { searchChunks, fetchSearchHistory } from '@packages/rag/api/retrieval';

// ============================================================
// RAG - Data Source
// ============================================================
export type { DataSourceSnake, DataSourcePresetSnake, SyncJobSnake } from '@packages/rag/api/dataSource';
export {
  fetchDataSources, fetchDataSourcesPresets,
  syncDataSource, getSyncJobStatus,
  deleteDataSource, updateDataSource, createDataSource, getSyncHistory,
} from '@packages/rag/api/dataSource';

// ============================================================
// RAG - Evaluation
// ============================================================
export type {
  GoldenSampleCreate, GoldenSampleResponse,
  EvaluationRunCreate, EvaluationRunResponse,
} from '@packages/rag/api/evaluation';
export {
  createGoldenSample, listGoldenSamples, deleteGoldenSample,
  createEvaluationRun, getEvaluationRun, executeEvaluationRun, getEvaluationSummary,
} from '@packages/rag/api/evaluation';

// ============================================================
// Model Gateway - Models
// ============================================================
export type { ModelConfigSnake, ModelPresetSnake } from '@packages/model-gateway/api/models';
export {
  fetchModels, fetchModelPresets, testModelConnection,
  deleteModel, updateModel, createModel, getDefaultModel,
} from '@packages/model-gateway/api/models';

// ============================================================
// Model Gateway - Token Usage
// ============================================================
export type { TokenUsageStats, TokenUsageTrendItem, UserQuota } from '@packages/model-gateway/api/tokenUsage';
export {
  getMyTokenUsage, getMyTokenTrend, fetchMyQuota, getMyQuota,
} from '@packages/model-gateway/api/tokenUsage';

// ============================================================
// Model Gateway - Quota
// ============================================================
export { fetchAllQuotas, setUserQuota } from '@packages/model-gateway/api/quota';

// ============================================================
// Agent - Conversation
// ============================================================
export type {
  ChatCompletionRequest, ChatCompletionResponse,
  ConversationResponse, ConversationListResponse, ConversationCreate, ConversationUpdate,
} from '@packages/agent/api/conversation';
export {
  chatCompletions,
  createConversation, listConversations, updateConversation, deleteConversation,
  searchConversations, getConversation, addMessageToConversation,
} from '@packages/agent/api/conversation';

// ============================================================
// Agent - Feedback
// ============================================================
export type {
  FeedbackCreate, FeedbackResponse, FeedbackStats, FeedbackListResponse,
} from '@packages/agent/api/feedback';
export {
  submitFeedback, getFeedbackStats, getFeedbackList, deleteFeedback, processFeedback,
} from '@packages/agent/api/feedback';

// ============================================================
// Agent - Conversation History
// ============================================================
export type {
  ConversationHistoryItem, ConversationHistoryResponse, ChatMessageDetail,
} from '@packages/agent/api/conversationHistory';
export {
  fetchConversationHistory, fetchThreadMessages,
  restoreArchive, fetchArchiveDetail, deleteArchive, runArchiveJob,
  getConversationHistoryStats,
} from '@packages/agent/api/conversationHistory';

// ============================================================
// Agent - Skills
// ============================================================
export type {
  SkillResponse, SkillListResponse, VersionResponse, VersionListResponse,
} from '@packages/agent/api/skills';
export {
  listSkills, getSkill, createSkill,
  listSkillVersions, getSkillVersion, getSkillTags, addSkillTag,
  publishSkill, acquireSkillLock, releaseSkillLock,
  getSkillDependencies, downloadSkill,
} from '@packages/agent/api/skills';
