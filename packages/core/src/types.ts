export interface KnowledgeBase {
  id: string;
  name: string;
  description: string;
  documentCount: number;
  vectorCount: number;
  createdAt: string;
  updatedAt: string;
  permissions: 'read' | 'write' | 'admin';
}

export type DocStatus = 'pending' | 'processing' | 'completed' | 'failed';

export interface Document {
  id: string;
  kbId: string;
  name: string;
  format: string;
  size: number;
  file_size: number;
  uploadedAt: string;
  status: DocStatus;
  errorMessage?: string;
  category?: string | null;
  tags?: string[];
}

export interface SearchResult {
  chunk_id: string;
  content: string;
  score: number;
  metadata: {
    doc_name: string;
    doc_id: string;
    page?: number;
    chapter?: string;
    tags?: string[];
  };
}
