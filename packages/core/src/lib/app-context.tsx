import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import * as api from '@/lib/api-client';

// Keep the same types as the mock provider for source compatibility
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

interface AppContextType {
  knowledgeBases: KnowledgeBase[];
  addKnowledgeBase: (kb: Omit<KnowledgeBase, 'id' | 'createdAt' | 'updatedAt' | 'documentCount' | 'vectorCount'>) => Promise<void>;
  deleteKnowledgeBase: (id: string) => Promise<void>;
  documents: Document[];
  addDocument: (doc: Omit<Document, 'id' | 'uploadedAt' | 'status'>) => Promise<void>;
  deleteDocument: (id: string) => Promise<void>;
  currentKbId: string | null;
  setCurrentKbId: (id: string | null) => void;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

function apiKBToLocal(kb: api.KBData): KnowledgeBase {
  return {
    id: kb.id,
    name: kb.name,
    description: kb.description,
    documentCount: kb.documentCount || kb.document_count || 0,
    vectorCount: kb.vectorCount || kb.vector_count || 0,
    createdAt: kb.createdAt || kb.created_at,
    updatedAt: kb.updatedAt || kb.updated_at,
    permissions: kb.permissions as KnowledgeBase['permissions'],
  };
}

function apiDocToLocal(doc: api.DocData): Document {
  return {
    id: doc.id,
    kbId: doc.kbId,
    name: doc.name,
    format: doc.format,
    size: doc.size || 0,
    file_size: doc.size || 0,
    uploadedAt: doc.uploadedAt,
    status: doc.status as DocStatus,
    errorMessage: doc.errorMessage || undefined,
    category: doc.category || null,
    tags: doc.tags || [],
  };
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [currentKbId, setCurrentKbId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [initialized, setInitialized] = useState(false);

  const loadAll = useCallback(async () => {
    try {
      setError(null);
      const kbRes = await api.fetchKBs();
      setKnowledgeBases(kbRes.items.map(apiKBToLocal));
      // Load docs for first KB if available
      if (kbRes.items.length > 0) {
        const docRes = await api.fetchDocs(kbRes.items[0].id);
        setDocuments(docRes.items.map(apiDocToLocal));
      }
    } catch (e: any) {
      setError(e.message || 'Failed to load data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!initialized) {
      setInitialized(true);
      loadAll();
    }
  }, [initialized, loadAll]);

  const addKnowledgeBase = useCallback(async (kb: Omit<KnowledgeBase, 'id' | 'createdAt' | 'updatedAt' | 'documentCount' | 'vectorCount'>) => {
    const created = await api.createKB({
      name: kb.name,
      description: kb.description,
      permissions: kb.permissions,
    });
    setKnowledgeBases(prev => [apiKBToLocal(created), ...prev]);
  }, []);

  const deleteKnowledgeBase = useCallback(async (id: string) => {
    await api.deleteKB(id);
    setKnowledgeBases(prev => prev.filter(kb => kb.id !== id));
    setDocuments(prev => prev.filter(doc => doc.kbId !== id));
  }, []);

  const addDocument = useCallback(async (doc: Omit<Document, 'id' | 'uploadedAt' | 'status'>) => {
    // uploadDoc needs a File object, but our context interface doesn't provide one
    // for the programmatic API. The DocumentsView handles file uploads directly.
    // This is kept for interface compatibility but delegates to the view.
    await loadAll();
  }, [loadAll]);

  const deleteDocument = useCallback(async (id: string) => {
    await api.deleteDoc(id);
    setDocuments(prev => prev.filter(doc => doc.id !== id));
    // Refresh KBs to update counts
    const kbRes = await api.fetchKBs();
    setKnowledgeBases(kbRes.items.map(apiKBToLocal));
  }, []);

  return (
    <AppContext.Provider value={{
      knowledgeBases,
      addKnowledgeBase,
      deleteKnowledgeBase,
      documents,
      addDocument,
      deleteDocument,
      currentKbId,
      setCurrentKbId,
      loading,
      error,
      refresh: loadAll,
    }}>
      {children}
    </AppContext.Provider>
  );
}

export function useAppContext() {
  const context = useContext(AppContext);
  if (context === undefined) {
    throw new Error('useAppContext must be used within an AppProvider');
  }
  return context;
}
