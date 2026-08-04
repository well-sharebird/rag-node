/**
 * API Client Utilities
 * 基础 API 客户端工具
 */

// 使用环境变量配置后端地址，支持直接连接后端 8000 端口
// 优先级：VITE_API_BASE_URL > 默认值
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// 通用 fetch 封装
export async function fetchApi<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;

  // 只有当 body 不是 FormData 时才设置 JSON Content-Type
  const isFormData = options.body instanceof FormData;
  const defaultHeaders: HeadersInit = {};

  if (!isFormData) {
    defaultHeaders['Content-Type'] = 'application/json';
  }

  // 添加认证 token
  const token = localStorage.getItem('auth_token');
  if (token) {
    defaultHeaders['Authorization'] = `Bearer ${token}`;
  }

  const config: RequestInit = {
    ...options,
    headers: {
      ...defaultHeaders,
      ...options.headers,
    },
  };

  const response = await fetch(url, config);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: '请求失败' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  // 处理 204 No Content
  if (response.status === 204) {
    return undefined as T;
  }

  // Check if response is JSON before parsing
  const contentType = response.headers.get('content-type');
  if (!contentType || !contentType.includes('application/json')) {
    const text = await response.text();
    console.error('Expected JSON but received:', text.substring(0, 200));
    throw new Error(`服务器返回了非 JSON 响应 (HTTP ${response.status})`);
  }

  return response.json();
}

// 便捷方法
export const api = {
  get: <T>(endpoint: string, options?: RequestInit) =>
    fetchApi<T>(endpoint, { ...options, method: 'GET' }),

  post: <T>(endpoint: string, body?: BodyInit, options?: RequestInit) =>
    fetchApi<T>(endpoint, { ...options, method: 'POST', body }),

  put: <T>(endpoint: string, body?: BodyInit, options?: RequestInit) =>
    fetchApi<T>(endpoint, { ...options, method: 'PUT', body }),

  delete: <T>(endpoint: string, options?: RequestInit) =>
    fetchApi<T>(endpoint, { ...options, method: 'DELETE' }),
};

// 文档管理相关 API
// KB types
export interface KBData {
  id: string;
  name: string;
  description: string;
  documentCount: number;
  document_count: number;
  vectorCount: number;
  vector_count: number;
  permissions: string;
  createdAt: string;
  created_at: string;
  updatedAt: string;
  updated_at: string;
  top_k?: number;
  min_score?: number;
  enable_rerank?: boolean;
}

export interface KBListResponse {
  items: KBData[];
  total: number;
}

export const fetchKBs = async (search?: string) => {
  const qs = search ? `?search=${encodeURIComponent(search)}` : '';
  return fetchApi<KBListResponse>(`/api/v1/knowledge-bases${qs}`);
};

export const fetchKnowledgeBases = async () => {
  return fetchApi<KBListResponse>('/api/v1/knowledge-bases');
};

export const fetchKB = async (id: string) => {
  return fetchApi<KBData>(`/api/v1/knowledge-bases/${id}`);
};

export const createKB = async (data: { name: string; description: string; permissions?: string }) => {
  return fetchApi<KBData>('/api/v1/knowledge-bases', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const deleteKB = async (id: string) => {
  return fetchApi<void>(`/api/v1/knowledge-bases/${id}`, { method: 'DELETE' });
};

export const updateKB = async (id: string, data: { top_k?: number; min_score?: number; enable_rerank?: boolean }) => {
  return fetchApi<KBData>(`/api/v1/knowledge-bases/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
};

export const fetchDocs = async (kbId: string) => {
  return fetchApi<{ items: DocData[]; categories?: string[] }>(`/api/v1/documents?kb_id=${kbId}`);
};

export const deleteDoc = async (docId: string) => {
  return fetchApi(`/api/v1/documents/${docId}`, { method: 'DELETE' });
};

export const uploadDoc = async (kbId: string, file: File) => {
  const formData = new FormData();
  formData.append('file', file);
  return fetchApi(`/api/v1/documents/upload?kb_id=${encodeURIComponent(kbId)}`, {
    method: 'POST',
    body: formData,
  });
};

export const fetchDocumentCategories = async (kbId: string) => {
  return fetchApi(`/api/v1/documents/categories?kb_id=${encodeURIComponent(kbId)}`);
};

// Dashboard
export interface DashboardData {
  total_knowledge_bases: number;
  total_documents: number;
  total_vectors: number;
  avg_latency_ms: number;
  services: Record<string, string>;
  // camelCase aliases for frontend compatibility
  totalKnowledgeBases: number;
  totalDocuments: number;
  totalVectors: number;
  avgLatencyMs: number;
}

export interface QualityMetricsData {
  avg_score_7d: number;
  avg_latency_7d: number;
  total_searches_7d: number;
  zero_result_rate: number;
  trend: { date: string; avg_score: number; search_count: number }[];
  // camelCase aliases for frontend compatibility
  avgScore7d: number;
  avgLatency7d: number;
  totalSearches7d: number;
  zeroResultRate: number;
}

export interface TopDocItem {
  doc_id: string;
  doc_name: string;
  kb_name: string;
  search_count: number;
  avg_score: number;
  // camelCase aliases for frontend compatibility
  docId: string;
  docName: string;
  kbName: string;
  searchCount: number;
  avgScore: number;
}

export const fetchDashboard = async () => {
  return fetchApi('/api/v1/dashboard/stats');
};

export const fetchQualityMetrics = async () => {
  return fetchApi('/api/v1/dashboard/quality');
};

export const fetchTopDocs = async () => {
  return fetchApi('/api/v1/dashboard/top-docs');
};

// Retrieval
export const searchChunks = async (params: {
  kb_id: string;
  query: string;
  top_k?: number;
  min_score?: number;
  enable_hybrid?: boolean;
  enable_rerank?: boolean;
}) => {
  return fetchApi('/api/v1/retrieval/search', {
    method: 'POST',
    body: JSON.stringify(params),
  });
};

export const fetchSearchHistory = async (limit?: number) => {
  const qs = limit ? `?limit=${limit}` : '';
  return fetchApi(`/api/v1/retrieval/history${qs}`);
};

// Settings
export const fetchSettings = async () => {
  return fetchApi('/api/v1/settings');
};

export const updateSettings = async (data: Record<string, any>) => {
  return fetchApi('/api/v1/settings', {
    method: 'PUT',
    body: JSON.stringify(data),
  });
};

// Batch upload
export const batchUploadDocs = async (kbId: string, files: File[]) => {
  const formData = new FormData();
  files.forEach(f => formData.append('files', f));
  return fetchApi(`/api/v1/documents/batch-upload?kb_id=${encodeURIComponent(kbId)}`, {
    method: 'POST',
    body: formData,
  });
};

// Document types and operations
export interface DocData {
  id: string;
  kbId: string;
  kb_id: string;
  name: string;
  format: string;
  size: number;
  file_size: number;
  status: string;
  uploadedAt: string;
  uploaded_at: string;
  chunk_count?: number;
  category?: string;
  tags?: string[];
  errorMessage?: string | null;
  error_message?: string | null;
}

export const fetchDoc = async (id: string) => {
  return fetchApi(`/api/v1/documents/${id}`);
};

export const updateDocument = async (id: string, data: { tags?: string[]; category?: string }) => {
  return fetchApi(`/api/v1/documents/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
};

export const reprocessDocument = async (id: string, force: boolean = false) => {
  return fetchApi(`/api/v1/documents/${id}/reprocess${force ? '?force=true' : ''}`, {
    method: 'POST',
  });
};

export const batchReprocessDocuments = async (kb_id: string, failed_only: boolean = true, doc_ids?: string[]) => {
  const params = new URLSearchParams();
  params.append('kb_id', kb_id);
  params.append('failed_only', String(failed_only));
  if (doc_ids && doc_ids.length > 0) {
    for (const id of doc_ids) {
      params.append('doc_ids', id);
    }
  }
  return fetchApi(`/api/v1/documents/batch-reprocess?${params.toString()}`, {
    method: 'POST',
  });
};

// User Management types and functions
export interface RoleData {
  id: number;
  name: string;
  description?: string;
  isSystem?: boolean;
}

export interface UserData {
  id: number;
  email: string;
  username: string;
  full_name?: string;
  is_active?: boolean;
  created_at?: string;
  roles?: RoleData[];
}

export interface UserCreate {
  email: string;
  username: string;
  password: string;
  full_name?: string;
  role_ids?: number[];
}

export const fetchUsers = async (search?: string, role?: string) => {
  const params = new URLSearchParams();
  if (search) params.set('search', search);
  if (role) params.set('role', role);
  const qs = params.toString();
  return fetchApi(`/api/v1/users${qs ? `?${qs}` : ''}`);
};

export const fetchRoles = async () => {
  return fetchApi('/api/v1/users/roles');
};

export const createUser = async (data: UserCreate) => {
  return fetchApi('/api/v1/users', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const updateUser = async (id: number, data: Partial<UserData>) => {
  return fetchApi(`/api/v1/users/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
};

export const deleteUser = async (id: number) => {
  return fetchApi(`/api/v1/users/${id}`, { method: 'DELETE' });
};

export const assignUserRoles = async (id: number, roleIds: number[]) => {
  return fetchApi(`/api/v1/users/${id}/roles`, {
    method: 'POST',
    body: JSON.stringify({ role_ids: roleIds }),
  });
};

export const createRole = async (name: string, description?: string) => {
  const qs = description ? `?description=${encodeURIComponent(description)}` : '';
  return fetchApi(`/api/v1/users/roles?role_name=${encodeURIComponent(name)}${qs}`, {
    method: 'POST',
  });
};

export const updateRole = async (id: number, data: { name?: string; description?: string }) => {
  return fetchApi(`/api/v1/users/roles/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
};

export const deleteRole = async (id: number) => {
  return fetchApi(`/api/v1/users/roles/${id}`, { method: 'DELETE' });
};

// Model Management types and functions
export interface ModelConfigSnake {
  id: number;
  name: string;
  model_id: string;
  model_type: string;
  adapter_type: string;
  provider: string;
  description?: string;
  api_url?: string;
  status: string;
  is_default: boolean;
  is_enabled: boolean;
  embedding_dim?: number;
  created_at: string;
  updated_at: string;
}

export interface ModelPresetSnake {
  id: string;
  name: string;
  description: string;
  model_type: string;
  adapter_type: string;
  provider: string;
  model_id: string;
  default_config: Record<string, any>;
  recommended_for: string[];
}

export const fetchModels = async () => {
  return fetchApi('/api/v1/models');
};

export const fetchModelPresets = async (modelType?: string) => {
  const qs = modelType ? `?model_type=${modelType}` : '';
  return fetchApi(`/api/v1/models/presets${qs}`);
};

export const testModelConnection = async (id: number) => {
  return fetchApi(`/api/v1/models/${id}/test`, { method: 'POST' });
};

export const deleteModel = async (id: number) => {
  return fetchApi(`/api/v1/models/${id}`, { method: 'DELETE' });
};

export const updateModel = async (id: number, data: Partial<ModelConfigSnake>) => {
  return fetchApi(`/api/v1/models/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
};

export const createModel = async (data: Partial<ModelConfigSnake>) => {
  return fetchApi('/api/v1/models', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

// Token Usage & Quota types and functions
export interface UserQuota {
  id: number;
  user_id: number;
  daily_token_limit?: number;
  daily_cost_limit?: number;
  monthly_token_limit?: number;
  monthly_cost_limit?: number;
  used_daily_tokens?: number;
  used_daily_cost?: number;
  used_monthly_tokens?: number;
  used_monthly_cost?: number;
  is_active?: boolean;
}

export const fetchAllQuotas = async () => {
  return fetchApi('/api/v1/token-usage/admin/quotas');
};

export const setUserQuota = async (userId: number, data: Partial<UserQuota>) => {
  return fetchApi(`/api/v1/token-usage/admin/quota/${userId}`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

// Data Source types and functions
export interface DataSourceSnake {
  id: number;
  name: string;
  source_type: string;
  description?: string;
  kb_id: number | string;
  sync_mode: string;
  cron_expression?: string;
  auto_process: boolean;
  enabled: boolean;
  status: string;
  last_sync_at?: string;
  last_sync_status?: string;
  sync_message?: string;
  items_synced: number;
  items_failed: number;
  config_json: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface DataSourcePresetSnake {
  id: string;
  name: string;
  description: string;
  source_type: string;
  icon: string;
  config_template: Record<string, any>;
  use_cases: string[];
}

export interface SyncJobSnake {
  id: number;
  data_source_id: number;
  status: string;
  trigger_by: string;
  items_synced: number;
  items_failed: number;
  progress_percent: number;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
  created_at: string;
}

export const fetchDataSources = async () => {
  return fetchApi('/api/v1/data-sources');
};

export const fetchDataSourcesPresets = async () => {
  return fetchApi('/api/v1/data-sources/presets');
};

export const syncDataSource = async (id: number, fullSync?: boolean) => {
  const qs = fullSync ? '?full_sync=true' : '';
  return fetchApi(`/api/v1/data-sources/${id}/sync${qs}`, { method: 'POST' });
};

export const getSyncJobStatus = async (jobId: number) => {
  return fetchApi(`/api/v1/data-sources/sync/${jobId}`);
};

export const deleteDataSource = async (id: number) => {
  return fetchApi(`/api/v1/data-sources/${id}`, { method: 'DELETE' });
};

export const updateDataSource = async (id: number, data: Partial<DataSourceSnake>) => {
  return fetchApi(`/api/v1/data-sources/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
};

export const createDataSource = async (data: Partial<DataSourceSnake>) => {
  return fetchApi('/api/v1/data-sources', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const getSyncHistory = async (id: number) => {
  return fetchApi(`/api/v1/data-sources/${id}/sync-history`);
};

// ============================================================
// Auth & Authentication
// ============================================================

export interface LoginRequest {
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user?: UserData;
}

export interface UserResponse {
  id: number;
  email: string;
  username: string;
  full_name?: string;
  is_active: boolean;
  created_at: string;
  last_login_at?: string;
  roles?: RoleData[];
}

export interface APIKeyResponse {
  id: number;
  key: string;
  name: string;
  created_at: string;
  expires_at?: string;
  is_active: boolean;
}

export interface APIKeyListResponse {
  items: APIKeyResponse[];
  total: number;
}

export const login = async (data: LoginRequest) => {
  return fetchApi<TokenResponse>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const register = async (data: { email: string; username: string; password: string; full_name?: string }) => {
  return fetchApi<UserResponse>('/api/v1/auth/register', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const refreshToken = async (refresh_token: string) => {
  return fetchApi<TokenResponse>('/api/v1/auth/refresh', {
    method: 'POST',
    body: JSON.stringify({ refresh_token }),
  });
};

export const getMe = async () => {
  return fetchApi<UserResponse>('/api/v1/auth/me');
};

export interface MenuData {
  id: number;
  name: string;
  name_i18n?: string;
  menu_type: string;
  path: string;
  component?: string;
  redirect?: string;
  icon?: string;
  order: number;
  parent_id?: number;
  level: number;
  tree_path: string;
  permission?: string;
  is_visible: boolean;
  is_hidden: boolean;
  is_external: boolean;
  external_url?: string;
  keep_alive: boolean;
  is_active: boolean;
  children?: MenuData[];
}

export interface MenuTreeResponse {
  items: MenuData[];
  total: number;
}

export interface UserPermissionsResponse {
  permissions: string[];
  roles: string[];
}

export interface UserDepartmentsResponse {
  items: any[];
  primary_department: any | null;
}

export const getUserMenus = async () => {
  return fetchApi<MenuTreeResponse>('/api/v1/auth/me/menus');
};

export const getUserPermissions = async () => {
  return fetchApi<UserPermissionsResponse>('/api/v1/auth/me/permissions');
};

export const getUserDepartments = async () => {
  return fetchApi<UserDepartmentsResponse>('/api/v1/auth/me/departments');
};

// ============================================================
// Admin - Department Management
// ============================================================

export const fetchDepartments = async () => {
  return fetchApi<DepartmentListResponse>('/api/v1/admin/departments');
};

export const fetchDepartmentTree = async () => {
  return fetchApi<DepartmentTreeResponse>('/api/v1/admin/departments/tree');
};

export const createDepartment = async (data: { name: string; description?: string; parent_id?: number }) => {
  return fetchApi('/api/v1/admin/departments', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const updateDepartment = async (deptId: number, data: { name?: string; description?: string; parent_id?: number }) => {
  return fetchApi(`/api/v1/admin/departments/${deptId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
};

export const deleteDepartment = async (deptId: number) => {
  return fetchApi(`/api/v1/admin/departments/${deptId}`, { method: 'DELETE' });
};

export const getDepartmentUsers = async (deptId: number) => {
  return fetchApi(`/api/v1/admin/departments/${deptId}/users`);
};

export const addUserToDepartment = async (deptId: number, userId: number, dept_role?: string, is_primary?: boolean) => {
  return fetchApi(`/api/v1/admin/departments/${deptId}/users`, {
    method: 'POST',
    body: JSON.stringify({ user_id: userId, dept_role, is_primary }),
  });
};

export const removeUserFromDepartment = async (deptId: number, userId: number) => {
  return fetchApi(`/api/v1/admin/departments/${deptId}/users/${userId}`, { method: 'DELETE' });
};

export interface DepartmentData {
  id: number;
  name: string;
  code: string;
  description?: string;
  parent_id?: number;
  level: number;
  tree_path?: string;
  dept_type?: string;
  sort_order?: number;
  is_active?: boolean;
  created_at?: string;
  updated_at?: string;
  children?: DepartmentData[];
}

export interface DepartmentListResponse {
  items: DepartmentData[];
  total: number;
}

export interface DepartmentTreeResponse {
  items: DepartmentData[];
  total: number;
}

// ============================================================
// Admin - Menu Management
// ============================================================

export const fetchMenus = async () => {
  return fetchApi<MenuListResponse>('/api/v1/admin/menus');
};

export const fetchMenuTree = async () => {
  return fetchApi<MenuTreeResponse>('/api/v1/admin/menus/tree');
};

export const createMenu = async (data: {
  name: string;
  name_i18n?: string;
  menu_type: string;  // 'menu' | 'sub_menu' | 'button'
  path: string;
  component?: string;
  icon?: string;
  order?: number;
  parent_id?: number;
  permission?: string;
  is_visible?: boolean;
  is_active?: boolean;
}) => {
  return fetchApi('/api/v1/admin/menus', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const updateMenu = async (menuId: number, data: {
  name?: string;
  name_i18n?: string;
  path?: string;
  component?: string;
  icon?: string;
  order?: number;
  permission?: string;
  is_visible?: boolean;
  is_active?: boolean;
}) => {
  return fetchApi(`/api/v1/admin/menus/${menuId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
};

export const deleteMenu = async (menuId: number) => {
  return fetchApi(`/api/v1/admin/menus/${menuId}`, { method: 'DELETE' });
};

export const assignMenusToRole = async (roleId: number, menuIds: number[]) => {
  return fetchApi(`/api/v1/admin/roles/${roleId}/menus`, {
    method: 'PUT',
    body: JSON.stringify({ menu_ids: menuIds }),
  });
};

export interface MenuListResponse {
  items: MenuData[];
  total: number;
}

export const createApiKey = async (data: { name: string; expires_days?: number }) => {
  return fetchApi<APIKeyResponse>('/api/v1/auth/api-keys', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const getApiKeys = async () => {
  return fetchApi<APIKeyListResponse>('/api/v1/auth/api-keys');
};

export const deleteApiKey = async (key_id: number) => {
  return fetchApi<void>(`/api/v1/auth/api-keys/${key_id}`, { method: 'DELETE' });
};

export const getAuditLogs = async (params?: { limit?: number; offset?: number; action?: string }) => {
  const qs = new URLSearchParams(params as Record<string, string>).toString();
  return fetchApi(`/api/v1/auth/audit-logs${qs ? `?${qs}` : ''}`);
};

// ============================================================
// Chat Completions
// ============================================================

export interface ChatCompletionRequest {
  query: string;
  kb_ids: string[];
  session_id?: string;
  stream?: boolean;
  top_k?: number;
  min_score?: number;
  enable_rerank?: boolean;
  enable_expansion?: boolean;
  enable_hybrid?: boolean;
}

export interface ChatCompletionResponse {
  answer: string;
  reasoning?: string;
  citations: Array<{ index: number; doc_name: string; chunk_id: string }>;
  hallu_score?: number;
  chunks_used?: number;
}

export const chatCompletions = async (data: ChatCompletionRequest) => {
  return fetchApi<ChatCompletionResponse>('/api/v1/chat/completions', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

// ============================================================
// Feedback
// ============================================================

export interface FeedbackCreate {
  session_id: string;
  message_id: string;
  feedback_type: 'thumbs_up' | 'thumbs_down';
  reason_category?: string;
  reason_text?: string;
  comment?: string;
  query?: string;
  response?: string;
  referenced_docs?: string[];
}

export interface FeedbackResponse {
  id: number;
  session_id: string;
  message_id: string;
  feedback_type: string;
  rating?: number;
  reason_category?: string;
  reason_text?: string;
  comment?: string;
  query?: string;
  response?: string;
  referenced_docs?: string[];
  user_id?: number;
  kb_id?: string;
  created_at: string;
  is_positive: boolean;
}

export interface FeedbackStats {
  total: number;
  positive: number;
  negative: number;
  positive_rate: number;
}

export interface FeedbackListResponse {
  items: FeedbackResponse[];
  total: number;
}

export const submitFeedback = async (data: FeedbackCreate) => {
  return fetchApi<FeedbackResponse>('/api/v1/feedback', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const getFeedbackStats = async (params?: { kb_id?: string; start_date?: string; end_date?: string }) => {
  const qs = new URLSearchParams(params as Record<string, string>).toString();
  return fetchApi<FeedbackStats>(`/api/v1/feedback/stats${qs ? `?${qs}` : ''}`);
};

export const getFeedbackList = async (params?: { limit?: number; offset?: number }) => {
  const qs = new URLSearchParams(params as Record<string, string>).toString();
  return fetchApi<FeedbackListResponse>(`/api/v1/feedback${qs ? `?${qs}` : ''}`);
};

export const deleteFeedback = async (feedback_id: number) => {
  return fetchApi<void>(`/api/v1/feedback/${feedback_id}`, { method: 'DELETE' });
};

export const processFeedback = async (feedback_id: number) => {
  return fetchApi(`/api/v1/feedback/${feedback_id}/process`, { method: 'POST' });
};

// ============================================================
// Conversations
// ============================================================

export interface ConversationResponse {
  id: string;
  user_id?: string;
  title: string;
  kb_ids?: string[];
  is_active: boolean;
  is_archived: boolean;
  message_count: number;
  last_message_at?: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationListResponse {
  items: ConversationResponse[];
  total: number;
}

export interface ConversationCreate {
  title?: string;
  kb_ids?: string[];
}

export interface ConversationUpdate {
  title?: string;
  kb_ids?: string[];
  is_active?: boolean;
  is_archived?: boolean;
}

export const createConversation = async (data: ConversationCreate, user_id?: string) => {
  const qs = user_id ? `?user_id=${user_id}` : '';
  return fetchApi<ConversationResponse>('/api/v1/conversations' + qs, {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const listConversations = async (params?: { user_id?: string; limit?: number; offset?: number; include_archived?: boolean }) => {
  const qs = new URLSearchParams(params as Record<string, string>).toString();
  return fetchApi<ConversationListResponse>(`/api/v1/conversations${qs ? `?${qs}` : ''}`);
};

export const updateConversation = async (conv_id: string, data: ConversationUpdate) => {
  return fetchApi<ConversationResponse>(`/api/v1/conversations/${conv_id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
};

export const deleteConversation = async (conv_id: string) => {
  return fetchApi<void>(`/api/v1/conversations/${conv_id}`, { method: 'DELETE' });
};

export const searchConversations = async (query: string) => {
  return fetchApi(`/api/v1/conversations/search/${encodeURIComponent(query)}`);
};

export const getConversation = async (conv_id: string) => {
  return fetchApi(`/api/v1/conversations/${conv_id}`);
};

export const addMessageToConversation = async (
  conv_id: string,
  data: { role: string; content: string; sources?: any[]; model_used?: string; latency_ms?: number }
) => {
  return fetchApi(`/api/v1/conversations/${conv_id}/messages`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

// ============================================================
// Evaluation
// ============================================================

export interface GoldenSampleCreate {
  kb_id: string;
  question: string;
  expected_answer: string;
  expected_context_ids?: string[];
  metadata?: Record<string, any>;
}

export interface GoldenSampleResponse {
  id: string;
  kb_id: string;
  question: string;
  expected_answer: string;
  expected_context_ids?: string[];
  metadata?: Record<string, any>;
}

export interface EvaluationRunCreate {
  kb_id: string;
  name?: string;
  sample_ids?: string[];
  metrics?: string[];
}

export interface EvaluationRunResponse {
  id: string;
  kb_id: string;
  name?: string;
  status: string;
  results?: any[];
  created_at: string;
  completed_at?: string;
}

export const createGoldenSample = async (data: GoldenSampleCreate) => {
  return fetchApi<GoldenSampleResponse>('/api/v1/evaluation/golden-samples', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const listGoldenSamples = async (kb_id?: string, limit?: number) => {
  const params = new URLSearchParams();
  if (kb_id) params.set('kb_id', kb_id);
  if (limit) params.set('limit', String(limit));
  const qs = params.toString();
  return fetchApi<GoldenSampleResponse[]>(`/api/v1/evaluation/golden-samples${qs ? `?${qs}` : ''}`);
};

export const deleteGoldenSample = async (sample_id: string) => {
  return fetchApi<void>(`/api/v1/evaluation/golden-samples/${sample_id}`, { method: 'DELETE' });
};

export const createEvaluationRun = async (data: EvaluationRunCreate) => {
  return fetchApi<EvaluationRunResponse>('/api/v1/evaluation/runs', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const getEvaluationRun = async (run_id: string) => {
  return fetchApi<EvaluationRunResponse>(`/api/v1/evaluation/runs/${run_id}`);
};

export const executeEvaluationRun = async (run_id: string) => {
  return fetchApi(`/api/v1/evaluation/runs/${run_id}/execute`, { method: 'POST' });
};

export const getEvaluationSummary = async () => {
  return fetchApi('/api/v1/evaluation/summary');
};

// ============================================================
// Skills
// ============================================================

export interface SkillResponse {
  id: number;
  name: string;
  description?: string;
  category?: string;
  owner?: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface SkillListResponse {
  items: SkillResponse[];
  total: number;
}

export interface VersionResponse {
  id: number;
  skill_name: string;
  version: string;
  content: string;
  is_released: boolean;
  released_at?: string;
  created_at: string;
}

export interface VersionListResponse {
  skill_name: string;
  items: VersionResponse[];
  total: number;
}

export const listSkills = async (params?: { search?: string; category?: string; limit?: number; offset?: number }) => {
  const qs = new URLSearchParams(params as Record<string, string>).toString();
  return fetchApi<SkillListResponse>(`/api/v1/skills${qs ? `?${qs}` : ''}`);
};

export const getSkill = async (skill_name: string) => {
  return fetchApi(`/api/v1/skills/${encodeURIComponent(skill_name)}`);
};

export const createSkill = async (data: { name: string; description?: string; category?: string; owner?: string }) => {
  return fetchApi<SkillResponse>('/api/v1/skills', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const listSkillVersions = async (skill_name: string) => {
  return fetchApi<VersionListResponse>(`/api/v1/skills/${encodeURIComponent(skill_name)}/versions`);
};

export const getSkillVersion = async (skill_name: string, version: string) => {
  return fetchApi(`/api/v1/skills/${encodeURIComponent(skill_name)}/versions/${version}`);
};

export const getSkillTags = async (skill_name: string) => {
  return fetchApi(`/api/v1/skills/${encodeURIComponent(skill_name)}/tags`);
};

export const addSkillTag = async (skill_name: string, tag: string) => {
  return fetchApi(`/api/v1/skills/${encodeURIComponent(skill_name)}/tags`, {
    method: 'POST',
    body: JSON.stringify({ tag }),
  });
};

export const publishSkill = async (data: { skill_name: string; version?: string }) => {
  return fetchApi('/api/v1/skills/publish', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const acquireSkillLock = async (skill_name: string, user_id: number) => {
  return fetchApi(`/api/v1/skills/${encodeURIComponent(skill_name)}/locks`, {
    method: 'POST',
    body: JSON.stringify({ user_id }),
  });
};

export const releaseSkillLock = async (skill_name: string, user_id: number) => {
  return fetchApi(`/api/v1/skills/${encodeURIComponent(skill_name)}/locks/${user_id}`, { method: 'DELETE' });
};

export const getSkillDependencies = async (skill_name: string) => {
  return fetchApi(`/api/v1/skills/${encodeURIComponent(skill_name)}/deps`);
};

export const downloadSkill = async (skill_name: string) => {
  return fetchApi(`/api/v1/skills/${encodeURIComponent(skill_name)}/download`);
};

// ============================================================
// Token Usage - Personal
// ============================================================

export interface TokenUsageStats {
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  total_cost: number;
  request_count: number;
  period_days: number;
}

export interface TokenUsageTrendItem {
  date: string;
  total_tokens: number;
  cost: number;
  requests: number;
}

export const getMyTokenUsage = async (days?: number, model_type?: string) => {
  const params = new URLSearchParams();
  if (days) params.set('days', String(days));
  if (model_type) params.set('model_type', model_type);
  const qs = params.toString();
  return fetchApi<TokenUsageStats>(`/api/v1/token-usage/my-stats${qs ? `?${qs}` : ''}`);
};

export const getMyTokenTrend = async (days?: number, model_type?: string) => {
  const params = new URLSearchParams();
  if (days) params.set('days', String(days));
  if (model_type) params.set('model_type', model_type);
  const qs = params.toString();
  return fetchApi<{ items: TokenUsageTrendItem[] }>(`/api/v1/token-usage/my-trend${qs ? `?${qs}` : ''}`);
};

export const fetchMyQuota = async () => {
  return fetchApi<UserQuota>('/api/v1/token-usage/my-quota');
};

// Alias for backward compatibility
export const getMyQuota = fetchMyQuota;

// ============================================================
// Documents - Advanced Operations
// ============================================================

export interface ChunkPreviewRequest {
  file_content: string;
  chunk_size?: number;
  chunk_overlap?: number;
}

export interface ChunkPreviewResponse {
  chunks: string[];
  total_chunks: number;
}

export const previewChunks = async (data: ChunkPreviewRequest) => {
  return fetchApi<ChunkPreviewResponse>('/api/v1/documents/preview-chunks', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const listFailedDocuments = async (kb_id?: string) => {
  const qs = kb_id ? `?kb_id=${kb_id}` : '';
  return fetchApi<{ items: DocData[]; total: number }>(`/api/v1/documents/failed${qs}`);
};

export const getDocumentVersions = async (doc_id: string) => {
  return fetchApi(`/api/v1/documents/${doc_id}/versions`);
};

// ============================================================
// Models - Additional Operations
// ============================================================

export const getDefaultModel = async (model_type: string) => {
  return fetchApi(`/api/v1/models/default/${model_type}`);
};

// ============================================================
// Metrics & Health
// ============================================================

export interface HealthResponse {
  status: string;
  version: string;
  services: Record<string, string>;
}

export interface MetricsHealthResponse {
  milvus: { status: string; latency_ms?: number };
  postgres: { status: string; latency_ms?: number };
  redis: { status: string; latency_ms?: number };
  minio: { status: string; latency_ms?: number };
}

export interface MetricsSummaryResponse {
  total_requests: number;
  avg_latency_ms: number;
  error_rate: number;
  period: string;
}

export const getHealth = async () => {
  return fetchApi<HealthResponse>('/api/v1/health');
};

export const getMetricsHealth = async () => {
  return fetchApi<MetricsHealthResponse>('/api/v1/metrics/health');
};

export const getMetricsSummary = async () => {
  return fetchApi<MetricsSummaryResponse>('/api/v1/metrics/summary');
};

// ============================================================
// Conversation History APIs
// ============================================================

export interface ConversationHistoryItem {
  thread_id: string;
  agent_id: string | null;
  agent_name: string | null;
  message_count: number;
  last_message_at: string;
  source: 'hot' | 'archive';
  archive_tier?: 'warm' | 'cold';
  summary?: string;
}

export interface ConversationHistoryResponse {
  items: ConversationHistoryItem[];
  total: number;
}

export const fetchConversationHistory = async (params?: {
  limit?: number;
  offset?: number;
  agent_id?: string;
}) => {
  const qs = new URLSearchParams();
  if (params?.limit) qs.append('limit', String(params.limit));
  if (params?.offset) qs.append('offset', String(params.offset));
  if (params?.agent_id) qs.append('agent_id', params.agent_id);
  const query = qs.toString();
  return fetchApi<ConversationHistoryResponse>(`/api/v1/conversation-history${query ? `?${query}` : ''}`);
};

export interface ChatMessageDetail {
  role: string;
  content: string;
  timestamp?: string;
  [key: string]: unknown;
}

export const fetchThreadMessages = async (threadId: string) => {
  return fetchApi<{ messages: ChatMessageDetail[]; source: string; archive_tier?: string }>(
    `/api/v1/conversation-history/${threadId}/messages`
  );
};

export const restoreArchive = async (archiveId: string) => {
  return fetchApi<{ message: string; thread_id: string }>(
    `/api/v1/conversation-history/archive/${archiveId}/restore`,
    { method: 'POST' }
  );
};

export const fetchArchiveDetail = async (archiveId: string) => {
  return fetchApi<{
    id: string;
    thread_id: string;
    agent_id: string;
    agent_name: string;
    archive_tier: string;
    message_count: number;
    archive_size_bytes: number;
    date_range_start: string;
    date_range_end: string;
    summary: string;
    last_message_at: string;
    archived_at: string;
    is_restored: boolean;
  }>(`/api/v1/conversation-history/archive/${archiveId}`);
};

export const deleteArchive = async (archiveId: string) => {
  return fetchApi<{ message: string }>(
    `/api/v1/conversation-history/archive/${archiveId}`,
    { method: 'DELETE' }
  );
};

export const runArchiveJob = async () => {
  return fetchApi<{ message: string; result: Record<string, number> }>(
    '/api/v1/conversation-history/archive/run',
    { method: 'POST' }
  );
};

// 会话历史统计
export const getConversationHistoryStats = async (agent_id?: string) => {
  const qs = agent_id ? `?agent_id=${encodeURIComponent(agent_id)}` : '';
  return fetchApi<{
    last_7d: number;
    last_30d: number;
    months: Record<string, number>;
  }>(`/api/v1/conversation-history/stats${qs}`);
};

export const getMetricsJson = async () => {
  return fetchApi('/api/v1/metrics/json');
};

export const getMetricsErrors = async () => {
  return fetchApi('/api/v1/metrics/errors');
};
