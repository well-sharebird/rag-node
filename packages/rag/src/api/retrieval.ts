/**
 * RAG API - Retrieval
 * 检索相关 API
 */
import { fetchApi } from '@packages/core/api/core';

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
