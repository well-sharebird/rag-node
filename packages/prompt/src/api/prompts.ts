/**
 * Prompt Engineering API Client
 * 提示词工程管理 API 客户端
 */

import { api } from '@packages/core/api/core';

// ==================== Types ====================

export interface PromptTemplate {
  id: number;
  name: string;
  description?: string;
  category: 'system' | 'user' | 'instruction';
  owner?: string;
  status: 'active' | 'archived';
  created_at: string;
  updated_at: string;
  current_tags?: Record<string, string>;
}

export interface PromptVersion {
  id: number;
  template_id: number;
  version: string;
  content: string;
  variables_schema: Array<{
    name: string;
    type: string;
    required?: boolean;
    default?: any;
  }>;
  system_role?: string;
  changelog?: string;
  released_by?: string;
  released_at?: string;
  status: 'draft' | 'released' | 'archived';
  latest_eval_score?: number;
  eval_dataset_hash?: string;
  created_at: string;
  updated_at: string;
}

export interface PromptTag {
  id: number;
  template_id: number;
  tag_name: string;
  version_id: number;
  version: string;
  meta_config: Record<string, any>;
  updated_by?: string;
  updated_at: string;
}

export interface TestCase {
  id: number;
  template_id: number;
  input_context: Record<string, any>;
  expected_output?: string;
  expected_behavior?: string;
  tags: string[];
  priority: number;
  is_active: boolean;
  created_by?: string;
  created_at: string;
}

export interface EvalResult {
  case_id: number;
  score: number;
  llm_output: string;
  reasoning: string;
  passed: boolean;
}

export interface EvalReport {
  run_id: number;
  version_id: number;
  baseline_version_id?: number;
  avg_score?: number;
  delta?: number;
  pass_count?: number;
  fail_count?: number;
  total_count?: number;
  passed: boolean;
  detailed_results: EvalResult[];
  run_at: string;
  triggered_by: string;
}

// ==================== Request Types ====================

export interface CreateTemplateRequest {
  name: string;
  description?: string;
  category?: 'system' | 'user' | 'instruction';
  owner?: string;
}

export interface CreateVersionRequest {
  version: string;
  content: string;
  variables_schema?: Array<{
    name: string;
    type: string;
    required?: boolean;
    default?: any;
  }>;
  system_role?: string;
  changelog?: string;
}

export interface SetTagRequest {
  tag_name: string;
  version_id: number;
  meta_config?: Record<string, any>;
}

export interface RunEvalRequest {
  candidate_version_id: number;
  baseline_version_id?: number;
  test_case_ids?: number[];
  judge_model?: string;
  triggered_by?: string;
}

export interface RenderRequest {
  version_id?: number;
  variables: Record<string, any>;
}

// ==================== API Functions ====================

export const promptsApi = {
  // Templates
  listTemplates: async (params?: { status?: string; category?: string; skip?: number; limit?: number }) => {
    const queryParams = new URLSearchParams();
    if (params?.status) queryParams.append('status_filter', params.status);
    if (params?.category) queryParams.append('category', params.category);
    if (params?.skip) queryParams.append('skip', String(params.skip));
    if (params?.limit) queryParams.append('limit', String(params.limit));
    return api.get(`/api/v1/prompts?${queryParams}`);
  },

  getTemplate: async (name: string) => {
    return api.get(`/api/v1/prompts/${name}`);
  },

  createTemplate: async (data: CreateTemplateRequest) => {
    return api.post(`/api/v1/prompts`, JSON.stringify(data));
  },

  updateTemplate: async (name: string, data: Partial<CreateTemplateRequest>) => {
    return api.put(`/api/v1/prompts/${name}`, JSON.stringify(data));
  },

  archiveTemplate: async (name: string) => {
    return api.delete(`/api/v1/prompts/${name}`);
  },

  // Versions
  listVersions: async (name: string, params?: { status?: string; skip?: number; limit?: number }) => {
    const queryParams = new URLSearchParams();
    if (params?.status) queryParams.append('status_filter', params.status);
    if (params?.skip) queryParams.append('skip', String(params.skip));
    if (params?.limit) queryParams.append('limit', String(params.limit));
    return api.get(`/api/v1/prompts/${name}/versions?${queryParams}`);
  },

  getVersion: async (name: string, version: string) => {
    return api.get(`/api/v1/prompts/${name}/versions/${version}`);
  },

  createVersion: async (name: string, data: CreateVersionRequest) => {
    return api.post(`/api/v1/prompts/${name}/versions`, JSON.stringify(data));
  },

  releaseVersion: async (name: string, versionId: number) => {
    return api.post(`/api/v1/prompts/${name}/versions/${versionId}/release`, JSON.stringify({}));
  },

  // Tags
  listTags: async (name: string) => {
    return api.get(`/api/v1/prompts/${name}/tags`);
  },

  setTag: async (name: string, data: SetTagRequest) => {
    return api.post(`/api/v1/prompts/${name}/tags`, JSON.stringify(data));
  },

  deleteTag: async (name: string, tagName: string) => {
    return api.delete(`/api/v1/prompts/${name}/tags/${tagName}`);
  },

  rollback: async (name: string, targetVersionId: number, tagName: string = 'stable') => {
    return api.post(`/api/v1/prompts/${name}/rollback`, JSON.stringify({
      target_version_id: targetVersionId,
      tag_name: tagName,
    }));
  },

  // Test Cases
  listTestCases: async (name: string, params?: { is_active?: boolean; priority?: number }) => {
    const queryParams = new URLSearchParams();
    if (params?.is_active !== undefined) queryParams.append('is_active', String(params.is_active));
    if (params?.priority !== undefined) queryParams.append('priority', String(params.priority));
    return api.get(`/api/v1/prompts/${name}/test-cases?${queryParams}`);
  },

  createTestCase: async (name: string, data: {
    input_context: Record<string, any>;
    expected_output?: string;
    expected_behavior?: string;
    tags?: string[];
    priority?: number;
  }) => {
    return api.post(`/api/v1/prompts/${name}/test-cases`, JSON.stringify(data));
  },

  deleteTestCase: async (caseId: number) => {
    return api.delete(`/api/v1/prompts/test-cases/${caseId}`);
  },

  // Evaluation
  runEvaluation: async (name: string, data: RunEvalRequest) => {
    return api.post(`/api/v1/prompts/${name}/eval`, JSON.stringify(data));
  },

  // Rendering
  render: async (name: string, data: RenderRequest) => {
    return api.post(`/api/v1/prompts/${name}/render`, JSON.stringify(data));
  },

  // Audit Logs
  listAuditLogs: async (name: string, params?: { skip?: number; limit?: number; action?: string }) => {
    const queryParams = new URLSearchParams();
    if (params?.skip) queryParams.append('skip', String(params.skip));
    if (params?.limit) queryParams.append('limit', String(params.limit));
    if (params?.action) queryParams.append('action', params.action);
    return api.get(`/api/v1/prompts/${name}/audit-logs?${queryParams}`);
  },
};
