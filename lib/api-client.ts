const API_BASE = '/api/v1';

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
    headers: { 'Content-Type': 'application/json', ...options?.headers },
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
  kb_id: number;
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
  return request<{ items: DataSource[]; total: number }>('/data-sources');
}

export function fetchDataSourcesPresets() {
  return request<DataSourcePreset[]>('/data-sources/presets');
}

export function syncDataSource(id: number, fullSync?: boolean) {
  return request<any>(`/data-sources/${id}/sync${fullSync ? '?full_sync=true' : ''}`, {
    method: 'POST',
  });
}

export function getSyncJobStatus(jobId: number) {
  return request<SyncJob>(`/data-sources/sync/${jobId}`);
}

export function deleteDataSource(id: number) {
  return request<void>(`/data-sources/${id}`, { method: 'DELETE' });
}

export function updateDataSource(id: number, data: Partial<DataSource>) {
  return request<DataSource>(`/data-sources/${id}`, {
    method: 'PUT',
    body: JSON.stringify(mapKeysToSnake(data)),
  });
}

export function createDataSource(data: Partial<DataSource>) {
  return request<DataSource>('/data-sources', {
    method: 'POST',
    body: JSON.stringify(mapKeysToSnake(data)),
  });
}

export function getSyncHistory(id: number) {
  return request<SyncJob[]>(`/data-sources/${id}/sync-history`);
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
  status: 'active' | 'inactive' | 'error' | 'testing';
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

export function fetchModels() {
  return request<{ items: ModelConfig[]; total: number }>('/models');
}

export function fetchModelPresets(modelType?: string) {
  const qs = modelType ? `/presets?model_type=${modelType}` : '/presets';
  return request<ModelPreset[]>(`/models${qs}`);
}

export function testModelConnection(id: number) {
  return request<any>(`/models/${id}/test`, { method: 'POST' });
}

export function deleteModel(id: number) {
  return request<void>(`/models/${id}`, { method: 'DELETE' });
}

export function updateModel(id: number, data: Partial<ModelConfig>) {
  return request<ModelConfig>(`/models/${id}`, {
    method: 'PUT',
    body: JSON.stringify(mapKeysToSnake(data)),
  });
}

export function createModel(data: Partial<ModelConfig>) {
  return request<ModelConfig>('/models', {
    method: 'POST',
    body: JSON.stringify(mapKeysToSnake(data)),
  });
}
