/**
 * API Client Utilities
 * 基础 API 客户端工具
 */

const API_BASE_URL = '';

// 通用 fetch 封装
async function fetchApi<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;

  const defaultHeaders: HeadersInit = {
    'Content-Type': 'application/json',
  };

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

// 导出通用 fetch 供其他模块使用
export { fetchApi };
