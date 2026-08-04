/**
 * Core API - Authentication
 * 认证相关 API
 */
import { fetchApi } from '@packages/core/api/core';
import type { UserData, RoleData } from '@packages/core/api/core-users';

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

export const getUserMenus = async () => {
  return fetchApi<MenuTreeResponse>('/api/v1/auth/me/menus');
};

export const getUserPermissions = async () => {
  return fetchApi<UserPermissionsResponse>('/api/v1/auth/me/permissions');
};

export const getUserDepartments = async () => {
  return fetchApi<UserDepartmentsResponse>('/api/v1/auth/me/departments');
};

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
