/**
 * Core API Client - Base Infrastructure
 * 基础 API 客户端封装
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

// ============================================================
// Dashboard
// ============================================================

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

// ============================================================
// Settings
// ============================================================

export const fetchSettings = async () => {
  return fetchApi('/api/v1/settings');
};

export const updateSettings = async (data: Record<string, any>) => {
  return fetchApi('/api/v1/settings', {
    method: 'PUT',
    body: JSON.stringify(data),
  });
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

export const getMetricsJson = async () => {
  return fetchApi('/api/v1/metrics/json');
};

export const getMetricsErrors = async () => {
  return fetchApi('/api/v1/metrics/errors');
};
