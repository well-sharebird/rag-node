/**
 * Model Gateway API - Quota Management
 * 配额管理 API
 */
import { fetchApi } from '@packages/core/api/core';
import type { UserQuota } from '@packages/model-gateway/api/tokenUsage';

export const fetchAllQuotas = async () => {
  return fetchApi('/api/v1/token-usage/admin/quotas');
};

export const setUserQuota = async (userId: number, data: Partial<UserQuota>) => {
  return fetchApi(`/api/v1/token-usage/admin/quota/${userId}`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
};
