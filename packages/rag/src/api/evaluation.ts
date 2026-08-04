/**
 * RAG API - Evaluation
 * 质量评估 API
 */
import { fetchApi } from '@packages/core/api/core';

export interface GoldenSampleCreate {
  kb_id: string;
  question: string;
  expected_answer: string;
  expected_context_ids?: string[];
  metadata?: Record<string, any>;
}

export interface GoldenSampleResponse {
  id: string;
  kb_id: string;
  question: string;
  expected_answer: string;
  expected_context_ids?: string[];
  metadata?: Record<string, any>;
}

export interface EvaluationRunCreate {
  kb_id: string;
  name?: string;
  sample_ids?: string[];
  metrics?: string[];
}

export interface EvaluationRunResponse {
  id: string;
  kb_id: string;
  name?: string;
  status: string;
  results?: any[];
  created_at: string;
  completed_at?: string;
}

export const createGoldenSample = async (data: GoldenSampleCreate) => {
  return fetchApi<GoldenSampleResponse>('/api/v1/evaluation/golden-samples', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const listGoldenSamples = async (kb_id?: string, limit?: number) => {
  const params = new URLSearchParams();
  if (kb_id) params.set('kb_id', kb_id);
  if (limit) params.set('limit', String(limit));
  const qs = params.toString();
  return fetchApi<GoldenSampleResponse[]>(`/api/v1/evaluation/golden-samples${qs ? `?${qs}` : ''}`);
};

export const deleteGoldenSample = async (sample_id: string) => {
  return fetchApi<void>(`/api/v1/evaluation/golden-samples/${sample_id}`, { method: 'DELETE' });
};

export const createEvaluationRun = async (data: EvaluationRunCreate) => {
  return fetchApi<EvaluationRunResponse>('/api/v1/evaluation/runs', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const getEvaluationRun = async (run_id: string) => {
  return fetchApi<EvaluationRunResponse>(`/api/v1/evaluation/runs/${run_id}`);
};

export const executeEvaluationRun = async (run_id: string) => {
  return fetchApi(`/api/v1/evaluation/runs/${run_id}/execute`, { method: 'POST' });
};

export const getEvaluationSummary = async () => {
  return fetchApi('/api/v1/evaluation/summary');
};
