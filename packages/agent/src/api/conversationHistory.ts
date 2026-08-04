/**
 * Agent API - Conversation History
 * 会话历史与归档 API
 */
import { fetchApi } from '@packages/core/api/core';

export interface ConversationHistoryItem {
  thread_id: string;
  agent_id: string | null;
  agent_name: string | null;
  message_count: number;
  last_message_at: string;
  source: 'hot' | 'archive';
  archive_tier?: 'warm' | 'cold';
  summary?: string;
}

export interface ConversationHistoryResponse {
  items: ConversationHistoryItem[];
  total: number;
}

export interface ChatMessageDetail {
  role: string;
  content: string;
  timestamp?: string;
  [key: string]: unknown;
}

export const fetchConversationHistory = async (params?: {
  limit?: number;
  offset?: number;
  agent_id?: string;
}) => {
  const qs = new URLSearchParams();
  if (params?.limit) qs.append('limit', String(params.limit));
  if (params?.offset) qs.append('offset', String(params.offset));
  if (params?.agent_id) qs.append('agent_id', params.agent_id);
  const query = qs.toString();
  return fetchApi<ConversationHistoryResponse>(`/api/v1/conversation-history${query ? `?${query}` : ''}`);
};

export const fetchThreadMessages = async (threadId: string) => {
  return fetchApi<{ messages: ChatMessageDetail[]; source: string; archive_tier?: string }>(
    `/api/v1/conversation-history/${threadId}/messages`
  );
};

export const restoreArchive = async (archiveId: string) => {
  return fetchApi<{ message: string; thread_id: string }>(
    `/api/v1/conversation-history/archive/${archiveId}/restore`,
    { method: 'POST' }
  );
};

export const fetchArchiveDetail = async (archiveId: string) => {
  return fetchApi<{
    id: string;
    thread_id: string;
    agent_id: string;
    agent_name: string;
    archive_tier: string;
    message_count: number;
    archive_size_bytes: number;
    date_range_start: string;
    date_range_end: string;
    summary: string;
    last_message_at: string;
    archived_at: string;
    is_restored: boolean;
  }>(`/api/v1/conversation-history/archive/${archiveId}`);
};

export const deleteArchive = async (archiveId: string) => {
  return fetchApi<{ message: string }>(
    `/api/v1/conversation-history/archive/${archiveId}`,
    { method: 'DELETE' }
  );
};

export const runArchiveJob = async () => {
  return fetchApi<{ message: string; result: Record<string, number> }>(
    '/api/v1/conversation-history/archive/run',
    { method: 'POST' }
  );
};

// 会话历史统计
export const getConversationHistoryStats = async (agent_id?: string) => {
  const qs = agent_id ? `?agent_id=${encodeURIComponent(agent_id)}` : '';
  return fetchApi<{
    last_7d: number;
    last_30d: number;
    months: Record<string, number>;
  }>(`/api/v1/conversation-history/stats${qs}`);
};
