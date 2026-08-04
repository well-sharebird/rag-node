/**
 * Agent API - Feedback Management
 * 反馈管理 API
 */
import { fetchApi } from '@packages/core/api/core';

export interface FeedbackCreate {
  session_id: string;
  message_id: string;
  feedback_type: 'thumbs_up' | 'thumbs_down';
  reason_category?: string;
  reason_text?: string;
  comment?: string;
  query?: string;
  response?: string;
  referenced_docs?: string[];
}

export interface FeedbackResponse {
  id: number;
  session_id: string;
  message_id: string;
  feedback_type: string;
  rating?: number;
  reason_category?: string;
  reason_text?: string;
  comment?: string;
  query?: string;
  response?: string;
  referenced_docs?: string[];
  user_id?: number;
  kb_id?: string;
  created_at: string;
  is_positive: boolean;
}

export interface FeedbackStats {
  total: number;
  positive: number;
  negative: number;
  positive_rate: number;
}

export interface FeedbackListResponse {
  items: FeedbackResponse[];
  total: number;
}

export const submitFeedback = async (data: FeedbackCreate) => {
  return fetchApi<FeedbackResponse>('/api/v1/feedback', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const getFeedbackStats = async (params?: { kb_id?: string; start_date?: string; end_date?: string }) => {
  const qs = new URLSearchParams(params as Record<string, string>).toString();
  return fetchApi<FeedbackStats>(`/api/v1/feedback/stats${qs ? `?${qs}` : ''}`);
};

export const getFeedbackList = async (params?: { limit?: number; offset?: number }) => {
  const qs = new URLSearchParams(params as Record<string, string>).toString();
  return fetchApi<FeedbackListResponse>(`/api/v1/feedback${qs ? `?${qs}` : ''}`);
};

export const deleteFeedback = async (feedback_id: number) => {
  return fetchApi<void>(`/api/v1/feedback/${feedback_id}`, { method: 'DELETE' });
};

export const processFeedback = async (feedback_id: number) => {
  return fetchApi(`/api/v1/feedback/${feedback_id}/process`, { method: 'POST' });
};
