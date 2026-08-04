/**
 * Model Gateway API - Token Usage
 * Token 使用统计 API
 */
import { fetchApi } from '@packages/core/api/core';

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
