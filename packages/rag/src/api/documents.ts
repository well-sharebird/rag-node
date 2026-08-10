/**
 * RAG API - Document Management
 * 文档管理 API
 */
import { fetchApi } from '@packages/core/api/core';

export interface DocData {
  id: string;
  kbId: string;
  kb_id: string;
  name: string;
  format: string;
  size: number;
  file_size: number;
  status: string;
  uploadedAt: string;
  uploaded_at: string;
  chunk_count?: number;
  category?: string;
  tags?: string[];
  errorMessage?: string | null;
  error_message?: string | null;
  // 智能标签元数据
  content_types?: string[];
  progress?: number;
  current_stage?: string;
}

export const fetchDocs = async (kbId: string) => {
  return fetchApi<{ items: DocData[]; categories?: string[] }>(`/api/v1/documents?kb_id=${kbId}`);
};

export const deleteDoc = async (docId: string) => {
  return fetchApi(`/api/v1/documents/${docId}`, { method: 'DELETE' });
};

export const uploadDoc = async (kbId: string, file: File) => {
  const formData = new FormData();
  formData.append('file', file);
  return fetchApi(`/api/v1/documents/upload?kb_id=${encodeURIComponent(kbId)}`, {
    method: 'POST',
    body: formData,
  });
};

export const fetchDocumentCategories = async (kbId: string) => {
  return fetchApi(`/api/v1/documents/categories?kb_id=${encodeURIComponent(kbId)}`);
};

// Batch upload
export const batchUploadDocs = async (kbId: string, files: File[]) => {
  const formData = new FormData();
  files.forEach(f => formData.append('files', f));
  return fetchApi(`/api/v1/documents/batch-upload?kb_id=${encodeURIComponent(kbId)}`, {
    method: 'POST',
    body: formData,
  });
};

export const fetchDoc = async (id: string) => {
  return fetchApi(`/api/v1/documents/${id}`);
};

export const updateDocument = async (id: string, data: { tags?: string[]; category?: string }) => {
  return fetchApi(`/api/v1/documents/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
};

export const reprocessDocument = async (id: string, force: boolean = false) => {
  return fetchApi(`/api/v1/documents/${id}/reprocess${force ? '?force=true' : ''}`, {
    method: 'POST',
  });
};

export const batchReprocessDocuments = async (kb_id: string, failed_only: boolean = true, doc_ids?: string[]) => {
  const params = new URLSearchParams();
  params.append('kb_id', kb_id);
  params.append('failed_only', String(failed_only));
  if (doc_ids && doc_ids.length > 0) {
    for (const id of doc_ids) {
      params.append('doc_ids', id);
    }
  }
  return fetchApi(`/api/v1/documents/batch-reprocess?${params.toString()}`, {
    method: 'POST',
  });
};

// ============================================================
// Documents - Advanced Operations
// ============================================================

export interface ChunkPreviewRequest {
  file_content: string;
  chunk_size?: number;
  chunk_overlap?: number;
}

export interface ChunkPreviewResponse {
  chunks: string[];
  total_chunks: number;
}

export const previewChunks = async (data: ChunkPreviewRequest) => {
  return fetchApi<ChunkPreviewResponse>('/api/v1/documents/preview-chunks', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const listFailedDocuments = async (kb_id?: string) => {
  const qs = kb_id ? `?kb_id=${kb_id}` : '';
  return fetchApi<{ items: DocData[]; total: number }>(`/api/v1/documents/failed${qs}`);
};

export const getDocumentVersions = async (doc_id: string) => {
  return fetchApi(`/api/v1/documents/${doc_id}/versions`);
};

// ============================================================
// Documents - Pipeline Tracing
// ============================================================

export interface PipelineStage {
  stage: string;
  label: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  duration_ms: number | null;
  input_summary: {
    preview: string;
    count?: number | null;
    size?: number | null;
  } | null;
  output_summary: {
    preview: string;
    count?: number | null;
    size?: number | null;
  } | null;
  error: {
    message: string;
    details: Record<string, unknown>;
  } | null;
  span_id: string;
}

export interface PipelineResponse {
  document_id: string;
  stages: PipelineStage[];
  total_duration_ms: number;
  status: string;
}

export const getDocumentPipeline = async (doc_id: string) => {
  return fetchApi<PipelineResponse>(`/api/v1/documents/${doc_id}/pipeline`);
};

export const getStageData = async (doc_id: string, stage: string) => {
  return fetchApi(`/api/v1/documents/${doc_id}/stages/${stage}/data`);
};
