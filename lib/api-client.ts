const API_BASE = '/api/v1';

// Get token from localStorage
function getAuthToken(): string | null {
  if (typeof window !== 'undefined') {
    return localStorage.getItem('auth_token');
  }
  return null;
}

// Build headers with auth token if available
function buildHeaders(customHeaders?: Record<string, string>): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...customHeaders,
  };
  const token = getAuthToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

function toCamelCase(str: string): string {
  return str.replace(/_([a-z])/g, (_, c) => c.toUpperCase());
}

function mapKeysToCamel(obj: any): any {
  if (Array.isArray(obj)) return obj.map(mapKeysToCamel);
  if (obj !== null && typeof obj === 'object') {
    const result: Record<string, any> = {};
    for (const [key, value] of Object.entries(obj)) {
      result[toCamelCase(key)] = mapKeysToCamel(value);
    }
    return result;
  }
  return obj;
}

function mapKeysToSnake(obj: any): any {
  const toSnake = (s: string) => s.replace(/([A-Z])/g, '_$1').toLowerCase();
  if (Array.isArray(obj)) return obj.map(mapKeysToSnake);
  if (obj !== null && typeof obj === 'object') {
    const result: Record<string, any> = {};
    for (const [key, value] of Object.entries(obj)) {
      result[toSnake(key)] = mapKeysToSnake(value);
    }
    return result;
  }
  return obj;
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, {
    headers: buildHeaders(options?.headers as Record<string, string>),
    ...options,
  });
  if (res.status === 204) return undefined as T;
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || err.detail || `HTTP ${res.status}`);
  }
  const data = await res.json();
  return mapKeysToCamel(data) as T;
}

// Raw request without camelCase conversion (for components that use snake_case)
async function requestRaw<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, {
    headers: buildHeaders(options?.headers as Record<string, string>),
    ...options,
  });
  if (res.status === 204) return undefined as T;
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || err.detail || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// --- Knowledge Bases ---
export interface KBData {
  id: string;
  name: string;
  description: string;
  documentCount: number;
  vectorCount: number;
  permissions: string;
  createdAt: string;
  updatedAt: string;
}

export interface KBListResponse {
  items: KBData[];
  total: number;
}

export function fetchKBs(search?: string) {
  const qs = search ? `?search=${encodeURIComponent(search)}` : '';
  return request<KBListResponse>(`/knowledge-bases${qs}`);
}

export function fetchKnowledgeBases() {
  return request<KBListResponse>('/knowledge-bases');
}

export function fetchKB(id: string) {
  return request<KBData>(`/knowledge-bases/${id}`);
}

export function createKB(data: { name: string; description: string; permissions: string }) {
  return request<KBData>('/knowledge-bases', {
    method: 'POST',
    body: JSON.stringify(mapKeysToSnake(data)),
  });
}

export function updateKB(id: string, data: Record<string, any>) {
  return request<KBData>(`/knowledge-bases/${id}`, {
    method: 'PUT',
    body: JSON.stringify(mapKeysToSnake(data)),
  });
}

export function deleteKB(id: string) {
  return request<void>(`/knowledge-bases/${id}`, { method: 'DELETE' });
}

// --- Documents ---
export interface DocData {
  id: string;
  kbId: string;
  name: string;
  format: string;
  size: number;
  status: string;
  errorMessage?: string | null;
  uploadedAt: string;
  processedAt?: string | null;
  kbName?: string | null;
  category?: string;
  tags?: string[];
}

export interface DocListResponse {
  items: DocData[];
  total: number;
}

export function fetchDocs(kbId?: string, search?: string) {
  const params = new URLSearchParams();
  if (kbId) params.set('kb_id', kbId);
  if (search) params.set('search', search);
  const qs = params.toString();
  return request<DocListResponse & { categories?: string[] }>(`/documents${qs ? `?${qs}` : ''}`);
}

export function fetchDocumentCategories(kbId?: string) {
  const qs = kbId ? `?kb_id=${kbId}` : '';
  return request<{ categories: string[] }>(`/documents${qs}`);
}

export function fetchDoc(id: string) {
  return request<DocData>(`/documents/${id}`);
}

export async function uploadDoc(kbId: string, file: File) {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${API_BASE}/documents/upload?kb_id=${encodeURIComponent(kbId)}`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
  const data = await res.json();
  return mapKeysToCamel(data) as { id: string; status: string; message: string };
}

export function deleteDoc(id: string) {
  return request<void>(`/documents/${id}`, { method: 'DELETE' });
}

export function updateDocument(id: string, data: { tags?: string[]; category?: string }) {
  return request<DocData>(`/documents/${id}`, {
    method: 'PUT',
    body: JSON.stringify(mapKeysToSnake(data)),
  });
}

export function reprocessDoc(id: string) {
  return request<{ status: string; chunks?: number; error?: string }>(`/documents/${id}/reprocess`, { method: 'POST' });
}

export async function batchUploadDocs(kbId: string, files: File[]) {
  const formData = new FormData();
  files.forEach(f => formData.append('files', f));
  const res = await fetch(`${API_BASE}/documents/batch-upload?kb_id=${encodeURIComponent(kbId)}`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
  const data = await res.json();
  return mapKeysToCamel(data) as { id: string; status: string; message: string }[];
}

// --- Retrieval ---
export interface SearchResultData {
  chunkId: string;
  content: string;
  score: number;
  metadata: Record<string, any>;
}

export interface SearchResponseData {
  results: SearchResultData[];
  query: string;
  searchTimeMs: number;
  totalRecalled: number;
}

export function searchChunks(params: {
  kbId: string;
  query: string;
  topK?: number;
  minScore?: number;
  enableHybrid?: boolean;
  enableRerank?: boolean;
}) {
  return request<SearchResponseData>('/retrieval/search', {
    method: 'POST',
    body: JSON.stringify(mapKeysToSnake(params)),
  });
}

export function fetchSearchHistory(limit?: number) {
  const qs = limit ? `?limit=${limit}` : '';
  return request<{ items: any[]; total: number }>(`/retrieval/history${qs}`);
}

// --- Dashboard ---
export interface DashboardData {
  totalKnowledgeBases: number;
  totalDocuments: number;
  totalVectors: number;
  avgLatencyMs: number;
  services: {
    milvus: string;
    postgres: string;
    redis: string;
    embedding?: string;
    docProcessor?: string;
  };
}

export function fetchDashboard() {
  return request<DashboardData>('/dashboard/stats');
}

export interface QualityMetricsData {
  avgScore7d: number;
  avgLatency7d: number;
  totalSearches7d: number;
  zeroResultRate: number;
  trend: { date: string; avgScore: number; searchCount: number }[];
}

export function fetchQualityMetrics() {
  return request<QualityMetricsData>('/dashboard/quality');
}

export interface TopDocItem {
  docId: string;
  docName: string;
  kbName: string;
  searchCount: number;
  avgScore: number;
}

export function fetchTopDocs() {
  return request<{ items: TopDocItem[] }>('/dashboard/top-docs');
}

// --- Settings ---
export interface SettingsData {
  version: number;
  isActive: boolean;
  settings: Record<string, any>;
  publishedAt?: string | null;
}

export function fetchSettings() {
  return request<SettingsData>('/settings');
}

export function updateSettings(data: Record<string, any>) {
  return request<SettingsData>('/settings', {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export function fetchSettingsHistory() {
  return request<any[]>('/settings/history');
}

// --- Health ---
export function checkHealth() {
  return request<any>('/health');
}

// --- Data Sources ---
export interface DataSource {
  id: number;
  name: string;
  sourceType: string;
  description?: string;
  kbId: number;
  syncMode: string;
  cronExpression?: string;
  autoProcess: boolean;
  enabled: boolean;
  status: 'active' | 'inactive' | 'syncing' | 'error' | 'pending';
  lastSyncAt?: string;
  lastSyncStatus?: string;
  syncMessage?: string;
  itemsSynced: number;
  itemsFailed: number;
  configJson: Record<string, any>;
  createdAt: string;
  updatedAt: string;
}

export interface DataSourcePreset {
  id: string;
  name: string;
  description: string;
  sourceType: string;
  icon: string;
  configTemplate: Record<string, any>;
  useCases: string[];
}

// Legacy snake_case interface for backward compatibility with existing components
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
  status: 'active' | 'inactive' | 'syncing' | 'error' | 'pending';
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

export interface SyncJob {
  id: number;
  dataSourceId: number;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  triggerBy: string;
  itemsSynced: number;
  itemsFailed: number;
  progressPercent: number;
  startedAt?: string;
  completedAt?: string;
  errorMessage?: string;
  createdAt: string;
}

// Legacy snake_case interface for backward compatibility
export interface SyncJobSnake {
  id: number;
  data_source_id: number;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  trigger_by: string;
  items_synced: number;
  items_failed: number;
  progress_percent: number;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
  created_at: string;
}

export function fetchDataSources() {
  return requestRaw<{ items: DataSourceSnake[]; total: number }>('/data-sources');
}

export function fetchDataSourcesPresets() {
  return requestRaw<DataSourcePresetSnake[]>('/data-sources/presets');
}

export function syncDataSource(id: number, fullSync?: boolean) {
  return requestRaw<any>(`/data-sources/${id}/sync${fullSync ? '?full_sync=true' : ''}`, {
    method: 'POST',
  });
}

export function getSyncJobStatus(jobId: number) {
  return requestRaw<SyncJobSnake>(`/data-sources/sync/${jobId}`);
}

export function deleteDataSource(id: number) {
  return requestRaw<void>(`/data-sources/${id}`, { method: 'DELETE' });
}

export function updateDataSource(id: number, data: Partial<DataSourceSnake>) {
  return requestRaw<DataSourceSnake>(`/data-sources/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export function createDataSource(data: Partial<DataSourceSnake>) {
  return requestRaw<DataSourceSnake>('/data-sources', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export function getSyncHistory(id: number) {
  return requestRaw<SyncJobSnake[]>(`/data-sources/${id}/sync-history`);
}

// --- Model Management ---
export interface ModelConfig {
  id: number;
  name: string;
  modelId: string;
  modelType: string;
  adapterType: string;
  provider: string;
  description?: string;
  apiUrl?: string;
  status: 'active' | 'inactive' | 'error' | 'testing';
  isDefault: boolean;
  isEnabled: boolean;
  embeddingDim?: number;
  createdAt: string;
  updatedAt: string;
}

export interface ModelPreset {
  id: string;
  name: string;
  description: string;
  modelType: string;
  adapterType: string;
  provider: string;
  modelId: string;
  defaultConfig: Record<string, any>;
  recommendedFor: string[];
}

// Legacy snake_case interface for backward compatibility
export interface ModelConfigSnake {
  id: number;
  name: string;
  model_id: string;
  model_type: string;
  adapter_type: string;
  provider: string;
  description?: string;
  api_url?: string;
  api_key?: string;
  status: 'active' | 'inactive' | 'error' | 'testing';
  is_default: boolean;
  is_enabled: boolean;
  embedding_dim?: number;
  temperature?: number;
  max_tokens?: number;
  top_p?: number;
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

export function fetchModels() {
  return requestRaw<{ items: ModelConfigSnake[]; total: number }>('/models');
}

export function fetchModelPresets(modelType?: string) {
  const qs = modelType ? `/presets?model_type=${modelType}` : '/presets';
  return requestRaw<ModelPresetSnake[]>(`/models${qs}`);
}

export function testModelConnection(id: number) {
  return requestRaw<any>(`/models/${id}/test`, { method: 'POST' });
}

export function deleteModel(id: number) {
  return requestRaw<void>(`/models/${id}`, { method: 'DELETE' });
}

export function updateModel(id: number, data: Partial<ModelConfigSnake>) {
  return requestRaw<ModelConfigSnake>(`/models/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export function createModel(data: Partial<ModelConfigSnake>) {
  return requestRaw<ModelConfigSnake>('/models', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// --- User Management ---
export interface UserData {
  id: number;
  email: string;
  username: string;
  fullName?: string;
  isActive: boolean;
  tenantId?: string;
  createdAt: string;
  lastLoginAt?: string;
  roles: RoleData[];
}

export interface RoleData {
  id: number;
  name: string;
  description?: string;
  isSystem: boolean;
}

export interface UserListResponse {
  items: UserData[];
  total: number;
  skip: number;
  limit: number;
}

export interface UserCreate {
  email: string;
  username: string;
  password: string;
  fullName?: string;
  tenantId?: string;
  isActive?: boolean;
  roleIds?: number[];
}

export interface UserUpdate {
  email?: string;
  username?: string;
  password?: string;
  fullName?: string;
  isActive?: boolean;
  tenantId?: string;
}

export function fetchUsers(search?: string, role?: string) {
  const params = new URLSearchParams();
  if (search) params.set('search', search);
  if (role) params.set('role', role);
  const qs = params.toString();
  return requestRaw<UserListResponse>(`/users${qs ? `?${qs}` : ''}`);
}

export function fetchUser(id: number) {
  return requestRaw<UserData>(`/users/${id}`);
}

export function createUser(data: UserCreate) {
  return requestRaw<UserData>('/users', {
    method: 'POST',
    body: JSON.stringify(mapKeysToSnake(data)),
  });
}

export function updateUser(id: number, data: UserUpdate) {
  return requestRaw<UserData>(`/users/${id}`, {
    method: 'PUT',
    body: JSON.stringify(mapKeysToSnake(data)),
  });
}

export function deleteUser(id: number) {
  return requestRaw<void>(`/users/${id}`, { method: 'DELETE' });
}

export function assignUserRoles(id: number, roleIds: number[]) {
  return requestRaw<UserData>(`/users/${id}/roles`, {
    method: 'POST',
    body: JSON.stringify({ role_ids: roleIds }),
  });
}

export function fetchUserRoles(id: number) {
  return requestRaw<RoleData[]>(`/users/${id}/roles`);
}

export function fetchRoles() {
  return requestRaw<{ items: RoleData[] }>('/users/roles');
}

export function createRole(name: string, description?: string) {
  return requestRaw<RoleData>(`/users/roles?role_name=${encodeURIComponent(name)}${description ? `&description=${encodeURIComponent(description)}` : ''}`, {
    method: 'POST',
  });
}

// --- Token Usage & Model Management ---

export interface TokenUsageStats {
  totalTokens: number;
  inputTokens: number;
  outputTokens: number;
  totalCost: number;
  requestCount: number;
  periodDays: number;
}

export interface TokenUsageTrendItem {
  date: string;
  totalTokens: number;
  cost: number;
  requests: number;
}

export interface UserQuota {
  id: number;
  userId: number;
  dailyTokenLimit?: number;
  dailyCostLimit?: number;
  monthlyTokenLimit?: number;
  monthlyCostLimit?: number;
  usedDailyTokens: number;
  usedDailyCost: number;
  usedMonthlyTokens: number;
  usedMonthlyCost: number;
  dailyResetAt?: string;
  monthlyResetAt?: string;
  isActive: boolean;
  exceededAction: string;
}

export interface UserQuotaUpdate {
  dailyTokenLimit?: number;
  dailyCostLimit?: number;
  monthlyTokenLimit?: number;
  monthlyCostLimit?: number;
  isActive?: boolean;
  exceededAction?: string;
}

export interface ModelProvider {
  id: number;
  name: string;
  displayName: string;
  providerType: 'api' | 'local';
  category: string;
  apiBase?: string;
  authType?: string;
  pricing?: Record<string, any>;
  capabilities?: string[];
  supportedModels?: string[];
  icon?: string;
  description?: string;
  isEnabled: boolean;
  isDefault: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface DashboardStats {
  totalUsers: number;
  totalTokensToday: number;
  totalTokensMonth: number;
  totalCostToday: number;
  totalCostMonth: number;
  activeModels: number;
  requestsToday: number;
}

export function fetchMyTokenUsage(days?: number, modelType?: string) {
  const params = new URLSearchParams();
  if (days) params.set('days', String(days));
  if (modelType) params.set('model_type', modelType);
  const qs = params.toString();
  return requestRaw<TokenUsageStats>(`/token-usage/my-stats${qs ? `?${qs}` : ''}`);
}

export function fetchMyTokenTrend(days?: number, modelType?: string) {
  const params = new URLSearchParams();
  if (days) params.set('days', String(days));
  if (modelType) params.set('model_type', modelType);
  const qs = params.toString();
  return requestRaw<{ items: TokenUsageTrendItem[] }>(`/token-usage/my-trend${qs ? `?${qs}` : ''}`);
}

export function fetchMyQuota() {
  return requestRaw<UserQuota>('/token-usage/my-quota');
}

export function fetchDashboardStats() {
  return requestRaw<DashboardStats>('/token-usage/admin/stats');
}

export function fetchTopUsers(days?: number, limit?: number) {
  const params = new URLSearchParams();
  if (days) params.set('days', String(days));
  if (limit) params.set('limit', String(limit));
  const qs = params.toString();
  return requestRaw<{ items: any[] }>(`/token-usage/admin/users${qs ? `?${qs}` : ''}`);
}

export function fetchAllQuotas() {
  return requestRaw<{ items: UserQuota[] }>('/token-usage/admin/quotas');
}

export function setUserQuota(userId: number, data: UserQuotaUpdate) {
  return requestRaw<UserQuota>(`/token-usage/admin/quota/${userId}`, {
    method: 'POST',
    body: JSON.stringify(mapKeysToSnake(data)),
  });
}

export function fetchModelProviders() {
  return requestRaw<ModelProvider[]>('/token-usage/admin/providers');
}

export function createModelProvider(data: Partial<ModelProvider>) {
  return requestRaw<ModelProvider>('/token-usage/admin/providers', {
    method: 'POST',
    body: JSON.stringify(mapKeysToSnake(data)),
  });
}

export function deleteRole(id: number) {
  return requestRaw<void>(`/users/roles/${id}`, { method: 'DELETE' });
}
