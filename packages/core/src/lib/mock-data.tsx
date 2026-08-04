import { createContext, useContext, useState, ReactNode } from 'react';
import { KnowledgeBase, Document } from '@/src/types';

interface AppContextType {
  knowledgeBases: KnowledgeBase[];
  addKnowledgeBase: (kb: Omit<KnowledgeBase, 'id' | 'createdAt' | 'updatedAt' | 'documentCount' | 'vectorCount'>) => void;
  deleteKnowledgeBase: (id: string) => void;
  documents: Document[];
  addDocument: (doc: Omit<Document, 'id' | 'uploadedAt' | 'status'>) => void;
  deleteDocument: (id: string) => void;
  currentKbId: string | null;
  setCurrentKbId: (id: string | null) => void;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

const initialKBs: KnowledgeBase[] = [
  {
    id: 'kb_1',
    name: 'Product Manuals',
    description: 'User guides and product specifications',
    documentCount: 12,
    vectorCount: 4500,
    createdAt: new Date(Date.now() - 86400000 * 5).toISOString(),
    updatedAt: new Date(Date.now() - 3600000 * 2).toISOString(),
    permissions: 'admin',
  },
  {
    id: 'kb_2',
    name: 'Internal Wiki',
    description: 'Company policies and internal documentation',
    documentCount: 45,
    vectorCount: 12500,
    createdAt: new Date(Date.now() - 86400000 * 30).toISOString(),
    updatedAt: new Date().toISOString(),
    permissions: 'write',
  },
];

const initialDocs: Document[] = [
  {
    id: 'doc_1',
    kbId: 'kb_1',
    name: 'user_guide_v2.pdf',
    format: 'pdf',
    size: 2500000,
    file_size: 2500000,
    uploadedAt: new Date(Date.now() - 86400000).toISOString(),
    status: 'completed',
  },
  {
    id: 'doc_2',
    kbId: 'kb_1',
    name: 'api_specs.md',
    format: 'md',
    size: 45000,
    file_size: 45000,
    uploadedAt: new Date(Date.now() - 3600000).toISOString(),
    status: 'completed',
  },
  {
    id: 'doc_3',
    kbId: 'kb_1',
    name: 'draft_release_notes.docx',
    format: 'docx',
    size: 150000,
    file_size: 150000,
    uploadedAt: new Date().toISOString(),
    status: 'processing',
  }
];

export function AppProvider({ children }: { children: ReactNode }) {
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>(initialKBs);
  const [documents, setDocuments] = useState<Document[]>(initialDocs);
  const [currentKbId, setCurrentKbId] = useState<string | null>(null);

  const addKnowledgeBase = (kb: Omit<KnowledgeBase, 'id' | 'createdAt' | 'updatedAt' | 'documentCount' | 'vectorCount'>) => {
    const newKb: KnowledgeBase = {
      ...kb,
      id: `kb_${Math.random().toString(36).substr(2, 9)}`,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      documentCount: 0,
      vectorCount: 0,
    };
    setKnowledgeBases([newKb, ...knowledgeBases]);
  };

  const deleteKnowledgeBase = (id: string) => {
    setKnowledgeBases(knowledgeBases.filter(kb => kb.id !== id));
    setDocuments(documents.filter(doc => doc.kbId !== id));
  };

  const addDocument = (doc: Omit<Document, 'id' | 'uploadedAt' | 'status'>) => {
    const newDoc: Document = {
      ...doc,
      id: `doc_${Math.random().toString(36).substr(2, 9)}`,
      uploadedAt: new Date().toISOString(),
      status: 'completed', // Simulate immediate completion for UI
    };
    setDocuments([newDoc, ...documents]);
    
    // Update KB counts
    setKnowledgeBases(kbs => kbs.map(kb => {
      if (kb.id === doc.kbId) {
        return {
          ...kb,
          documentCount: kb.documentCount + 1,
          vectorCount: kb.vectorCount + Math.floor(Math.random() * 50) + 10, // fake vectors
          updatedAt: new Date().toISOString(),
        };
      }
      return kb;
    }));
  };

  const deleteDocument = (id: string) => {
    const docToDelete = documents.find(d => d.id === id);
    if (!docToDelete) return;
    
    setDocuments(documents.filter(doc => doc.id !== id));
    
    // Update KB counts
    setKnowledgeBases(kbs => kbs.map(kb => {
      if (kb.id === docToDelete.kbId) {
        return {
          ...kb,
          documentCount: Math.max(0, kb.documentCount - 1),
          updatedAt: new Date().toISOString(),
        };
      }
      return kb;
    }));
  };

  return (
    <AppContext.Provider value={{
      knowledgeBases,
      addKnowledgeBase,
      deleteKnowledgeBase,
      documents,
      addDocument,
      deleteDocument,
      currentKbId,
      setCurrentKbId
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
