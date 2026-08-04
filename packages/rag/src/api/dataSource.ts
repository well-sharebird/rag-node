/**
 * RAG API - Data Source Management
 * 数据源管理 API
 */
import { fetchApi } from '@packages/core/api/core';

export interface DataSourceSnake {
  id: number;
  name: string;
  source_type: string;
  description?: string;
  kb_id: number | string;
  sync_mode: string;
  cron_expression?: string;
  auto_process: boolean;
  enabled: boolean;
  status: string;
  last_sync_at?: string;
  last_sync_status?: string;
  sync_message?: string;
  items_synced: number;
  items_failed: number;
  config_json: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface DataSourcePresetSnake {
  id: string;
  name: string;
  description: string;
  source_type: string;
  icon: string;
  config_template: Record<string, any>;
  use_cases: string[];
}

export interface SyncJobSnake {
  id: number;
  data_source_id: number;
  status: string;
  trigger_by: string;
  items_synced: number;
  items_failed: number;
  progress_percent: number;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
  created_at: string;
}

export const fetchDataSources = async () => {
  return fetchApi('/api/v1/data-sources');
};

export const fetchDataSourcesPresets = async () => {
  return fetchApi('/api/v1/data-sources/presets');
};

export const syncDataSource = async (id: number, fullSync?: boolean) => {
  const qs = fullSync ? '?full_sync=true' : '';
  return fetchApi(`/api/v1/data-sources/${id}/sync${qs}`, { method: 'POST' });
};

export const getSyncJobStatus = async (jobId: number) => {
  return fetchApi(`/api/v1/data-sources/sync/${jobId}`);
};

export const deleteDataSource = async (id: number) => {
  return fetchApi(`/api/v1/data-sources/${id}`, { method: 'DELETE' });
};

export const updateDataSource = async (id: number, data: Partial<DataSourceSnake>) => {
  return fetchApi(`/api/v1/data-sources/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
};

export const createDataSource = async (data: Partial<DataSourceSnake>) => {
  return fetchApi('/api/v1/data-sources', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const getSyncHistory = async (id: number) => {
  return fetchApi(`/api/v1/data-sources/${id}/sync-history`);
};
