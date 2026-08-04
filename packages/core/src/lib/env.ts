/**
 * 环境变量配置
 * 统一管理系统环境变量，支持直接连接后端 8000 端口
 */

// 后端 API 基础地址
// 优先级：VITE_API_BASE_URL 环境变量 > 默认值 http://localhost:8000
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// 获取完整的 API URL
export function getApiUrl(endpoint: string): string {
  // 确保 endpoint 以 / 开头
  const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  // 如果 API_BASE_URL 为空（某些构建场景），使用相对路径
  if (!API_BASE_URL) {
    return cleanEndpoint;
  }
  return `${API_BASE_URL.replace(/\/$/, '')}${cleanEndpoint}`;
}

// 便捷 fetch 封装，支持流式请求
export async function fetchWithBaseUrl<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = getApiUrl(endpoint);

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

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get('content-type');
  if (!contentType || !contentType.includes('application/json')) {
    const text = await response.text();
    console.error('Expected JSON but received:', text.substring(0, 200));
    throw new Error(`服务器返回了非 JSON 响应 (HTTP ${response.status})`);
  }

  return response.json();
}
