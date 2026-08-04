/**
 * Model Gateway API - Model Management
 * 模型管理 API
 */
import { fetchApi } from '@packages/core/api/core';

export interface ModelConfigSnake {
  id: number;
  name: string;
  model_id: string;
  model_type: string;
  adapter_type: string;
  provider: string;
  description?: string;
  api_url?: string;
  status: string;
  is_default: boolean;
  is_enabled: boolean;
  embedding_dim?: number;
  created_at: string;
  updated_at: string;
}

export interface ModelPresetSnake {
  id: string;
  name: string;
  description: string;
  model_type: string;
  adapter_type: string;
  provider: string;
  model_id: string;
  default_config: Record<string, any>;
  recommended_for: string[];
}

export const fetchModels = async () => {
  return fetchApi('/api/v1/models');
};

export const fetchModelPresets = async (modelType?: string) => {
  const qs = modelType ? `?model_type=${modelType}` : '';
  return fetchApi(`/api/v1/models/presets${qs}`);
};

export const testModelConnection = async (id: number) => {
  return fetchApi(`/api/v1/models/${id}/test`, { method: 'POST' });
};

export const deleteModel = async (id: number) => {
  return fetchApi(`/api/v1/models/${id}`, { method: 'DELETE' });
};

export const updateModel = async (id: number, data: Partial<ModelConfigSnake>) => {
  return fetchApi(`/api/v1/models/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
};

export const createModel = async (data: Partial<ModelConfigSnake>) => {
  return fetchApi('/api/v1/models', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const getDefaultModel = async (model_type: string) => {
  return fetchApi(`/api/v1/models/default/${model_type}`);
};
