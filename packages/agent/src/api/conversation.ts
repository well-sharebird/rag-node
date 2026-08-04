/**
 * Agent API - Conversation Management
 * 会话管理 API
 */
import { fetchApi } from '@packages/core/api/core';

// ============================================================
// Chat Completions
// ============================================================

export interface ChatCompletionRequest {
  query: string;
  kb_ids: string[];
  session_id?: string;
  stream?: boolean;
  top_k?: number;
  min_score?: number;
  enable_rerank?: boolean;
  enable_expansion?: boolean;
  enable_hybrid?: boolean;
}

export interface ChatCompletionResponse {
  answer: string;
  reasoning?: string;
  citations: Array<{ index: number; doc_name: string; chunk_id: string }>;
  hallu_score?: number;
  chunks_used?: number;
}

export const chatCompletions = async (data: ChatCompletionRequest) => {
  return fetchApi<ChatCompletionResponse>('/api/v1/chat/completions', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

// ============================================================
// Conversations
// ============================================================

export interface ConversationResponse {
  id: string;
  user_id?: string;
  title: string;
  kb_ids?: string[];
  is_active: boolean;
  is_archived: boolean;
  message_count: number;
  last_message_at?: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationListResponse {
  items: ConversationResponse[];
  total: number;
}

export interface ConversationCreate {
  title?: string;
  kb_ids?: string[];
}

export interface ConversationUpdate {
  title?: string;
  kb_ids?: string[];
  is_active?: boolean;
  is_archived?: boolean;
}

export const createConversation = async (data: ConversationCreate, user_id?: string) => {
  const qs = user_id ? `?user_id=${user_id}` : '';
  return fetchApi<ConversationResponse>('/api/v1/conversations' + qs, {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const listConversations = async (params?: { user_id?: string; limit?: number; offset?: number; include_archived?: boolean }) => {
  const qs = new URLSearchParams(params as Record<string, string>).toString();
  return fetchApi<ConversationListResponse>(`/api/v1/conversations${qs ? `?${qs}` : ''}`);
};

export const updateConversation = async (conv_id: string, data: ConversationUpdate) => {
  return fetchApi<ConversationResponse>(`/api/v1/conversations/${conv_id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
};

export const deleteConversation = async (conv_id: string) => {
  return fetchApi<void>(`/api/v1/conversations/${conv_id}`, { method: 'DELETE' });
};

export const searchConversations = async (query: string) => {
  return fetchApi(`/api/v1/conversations/search/${encodeURIComponent(query)}`);
};

export const getConversation = async (conv_id: string) => {
  return fetchApi(`/api/v1/conversations/${conv_id}`);
};

export const addMessageToConversation = async (
  conv_id: string,
  data: { role: string; content: string; sources?: any[]; model_used?: string; latency_ms?: number }
) => {
  return fetchApi(`/api/v1/conversations/${conv_id}/messages`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
};
