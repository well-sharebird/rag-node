/**
 * Agent API - Skill Management
 * 技能仓库管理 API
 */
import { fetchApi } from '@packages/core/api/core';

export interface SkillResponse {
  id: number;
  name: string;
  description?: string;
  category?: string;
  owner?: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface SkillListResponse {
  items: SkillResponse[];
  total: number;
}

export interface VersionResponse {
  id: number;
  skill_name: string;
  version: string;
  content: string;
  is_released: boolean;
  released_at?: string;
  created_at: string;
}

export interface VersionListResponse {
  skill_name: string;
  items: VersionResponse[];
  total: number;
}

export const listSkills = async (params?: { search?: string; category?: string; limit?: number; offset?: number }) => {
  const qs = new URLSearchParams(params as Record<string, string>).toString();
  return fetchApi<SkillListResponse>(`/api/v1/skills${qs ? `?${qs}` : ''}`);
};

export const getSkill = async (skill_name: string) => {
  return fetchApi(`/api/v1/skills/${encodeURIComponent(skill_name)}`);
};

export const createSkill = async (data: { name: string; description?: string; category?: string; owner?: string }) => {
  return fetchApi<SkillResponse>('/api/v1/skills', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const listSkillVersions = async (skill_name: string) => {
  return fetchApi<VersionListResponse>(`/api/v1/skills/${encodeURIComponent(skill_name)}/versions`);
};

export const getSkillVersion = async (skill_name: string, version: string) => {
  return fetchApi(`/api/v1/skills/${encodeURIComponent(skill_name)}/versions/${version}`);
};

export const getSkillTags = async (skill_name: string) => {
  return fetchApi(`/api/v1/skills/${encodeURIComponent(skill_name)}/tags`);
};

export const addSkillTag = async (skill_name: string, tag: string) => {
  return fetchApi(`/api/v1/skills/${encodeURIComponent(skill_name)}/tags`, {
    method: 'POST',
    body: JSON.stringify({ tag }),
  });
};

export const publishSkill = async (data: { skill_name: string; version?: string }) => {
  return fetchApi('/api/v1/skills/publish', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const acquireSkillLock = async (skill_name: string, user_id: number) => {
  return fetchApi(`/api/v1/skills/${encodeURIComponent(skill_name)}/locks`, {
    method: 'POST',
    body: JSON.stringify({ user_id }),
  });
};

export const releaseSkillLock = async (skill_name: string, user_id: number) => {
  return fetchApi(`/api/v1/skills/${encodeURIComponent(skill_name)}/locks/${user_id}`, { method: 'DELETE' });
};

export const getSkillDependencies = async (skill_name: string) => {
  return fetchApi(`/api/v1/skills/${encodeURIComponent(skill_name)}/deps`);
};

export const downloadSkill = async (skill_name: string) => {
  return fetchApi(`/api/v1/skills/${encodeURIComponent(skill_name)}/download`);
};
