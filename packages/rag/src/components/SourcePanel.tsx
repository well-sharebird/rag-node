import { useState, useEffect } from 'react';
import { X, BookOpen, FileText, ChevronRight, ChevronDown, ExternalLink, Copy } from 'lucide-react';

interface Citation {
  index: number;
  doc_name: string;
  doc_id?: string;
  chunk_id?: string;
  page?: number;
  content?: string;
  score?: number;
}

interface SourcePanelProps {
  isOpen: boolean;
  onClose: () => void;
  citations: Citation[];
  selectedCitation: Citation | null;
  onSelectCitation: (citation: Citation) => void;
}

export function SourcePanel({
  isOpen,
  onClose,
  citations,
  selectedCitation,
  onSelectCitation,
}: SourcePanelProps) {
  const [expandedDocs, setExpandedDocs] = useState<Set<string>>(new Set());
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Group citations by document
  const citationsByDoc = citations.reduce((acc, citation) => {
    const docName = citation.doc_name || 'Unknown';
    if (!acc[docName]) {
      acc[docName] = [];
    }
    acc[docName].push(citation);
    return acc;
  }, {} as Record<string, Citation[]>);

  const toggleDoc = (docName: string) => {
    setExpandedDocs(prev => {
      const next = new Set(prev);
      if (next.has(docName)) {
        next.delete(docName);
      } else {
        next.add(docName);
      }
      return next;
    });
  };

  const handleCopyContent = async (citation: Citation, e: React.MouseEvent) => {
    e.stopPropagation();
    if (citation.content) {
      await navigator.clipboard.writeText(citation.content);
      setCopiedId(citation.chunk_id || `${citation.index}`);
      setTimeout(() => setCopiedId(null), 2000);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed right-0 top-0 h-full w-[400px] bg-white shadow-2xl border-l border-gray-200 z-50 overflow-hidden flex flex-col"
      style={{ animation: 'slideIn 0.3s ease-out' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
        <div className="flex items-center gap-2">
          <BookOpen className="w-4 h-4 text-indigo-600" />
          <h3 className="text-sm font-medium text-gray-900">引用来源</h3>
          <span className="text-xs text-gray-500">({citations.length} 个)</span>
        </div>
        <button
          onClick={onClose}
          className="p-1 hover:bg-gray-100 rounded transition-colors"
        >
          <X className="w-4 h-4 text-gray-500" />
        </button>
      </div>

      {/* Citation List */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {citations.length === 0 ? (
          <div className="text-center py-8 text-gray-500 text-sm">
            <FileText className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p>暂无引用来源</p>
          </div>
        ) : (
          Object.entries(citationsByDoc).map(([docName, docCitations]) => {
            const isExpanded = expandedDocs.has(docName);
            const isSelected = selectedCitation && docCitations.some(c => c.chunk_id === selectedCitation.chunk_id);

            return (
              <div key={docName} className="border border-gray-200 rounded-lg overflow-hidden">
                {/* Document Header */}
                <button
                  onClick={() => toggleDoc(docName)}
                  className={`w-full px-3 py-2 flex items-center justify-between text-left hover:bg-gray-50 transition-colors ${
                    isSelected ? 'bg-indigo-50' : ''
                  }`}
                >
                  <div className="flex items-center gap-2">
                    {isExpanded ? (
                      <ChevronDown className="w-4 h-4 text-gray-400" />
                    ) : (
                      <ChevronRight className="w-4 h-4 text-gray-400" />
                    )}
                    <FileText className="w-4 h-4 text-gray-400" />
                    <span className="text-sm font-medium text-gray-700 truncate max-w-[250px]">
                      {docName}
                    </span>
                  </div>
                  <span className="text-xs text-gray-500">{docCitations.length} 处引用</span>
                </button>

                {/* Citation Chunks */}
                {isExpanded && (
                  <div className="border-t border-gray-200">
                    {docCitations.map((citation) => (
                      <div
                        key={citation.chunk_id || citation.index}
                        onClick={() => onSelectCitation(citation)}
                        className={`px-3 py-2.5 cursor-pointer hover:bg-gray-50 transition-colors border-b border-gray-100 last:border-b-0 ${
                          selectedCitation?.chunk_id === citation.chunk_id
                            ? 'bg-indigo-50 border-l-2 border-l-indigo-600'
                            : 'border-l-2 border-l-transparent'
                        }`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-1">
                              <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-indigo-100 text-indigo-700 text-xs font-medium">
                                {citation.index}
                              </span>
                              {citation.page && (
                                <span className="text-xs text-gray-500">第 {citation.page} 页</span>
                              )}
                              {citation.score && (
                                <span className="text-xs text-gray-400">
                                  相似度 {(citation.score * 100).toFixed(0)}%
                                </span>
                              )}
                            </div>
                            {citation.content && (
                              <p className="text-xs text-gray-600 line-clamp-3 leading-relaxed">
                                {citation.content}
                              </p>
                            )}
                          </div>
                          <button
                            onClick={(e) => handleCopyContent(citation, e)}
                            className="p-1 hover:bg-gray-200 rounded transition-colors shrink-0"
                            title="复制内容"
                          >
                            <Copy className="w-3.5 h-3.5 text-gray-400" />
                          </button>
                        </div>
                        {copiedId === (citation.chunk_id || `${citation.index}`) && (
                          <span className="text-xs text-green-600 mt-1 block">已复制</span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Footer */}
      {selectedCitation && (
        <div className="border-t border-gray-200 p-4 bg-gray-50">
          <div className="text-xs text-gray-500 mb-2">已选择引用</div>
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-gray-900 truncate">
              [{selectedCitation.index}] {selectedCitation.doc_name}
            </span>
            <button
              className="text-xs text-indigo-600 hover:text-indigo-700 flex items-center gap-1"
              onClick={() => {
                // TODO: Navigate to document view
                console.log('Navigate to document:', selectedCitation.doc_id);
              }}
            >
              <ExternalLink className="w-3 h-3" />
              查看原文
            </button>
          </div>
        </div>
      )}

      <style>{`
        @keyframes slideIn {
          from {
            transform: translateX(100%);
            opacity: 0;
          }
          to {
            transform: translateX(0);
            opacity: 1;
          }
        }
      `}</style>
    </div>
  );
}
