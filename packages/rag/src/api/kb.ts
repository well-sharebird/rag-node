/**
 * RAG API - Knowledge Base Management
 * 知识库管理 API
 */
import { fetchApi } from '@packages/core/api/core';

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
