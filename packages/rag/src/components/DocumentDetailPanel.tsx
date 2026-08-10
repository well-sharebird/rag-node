/**
 * 文档详情侧边栏组件
 * 展示文档基本信息、处理统计、处理流水线入口
 */
import { useState, useEffect, useRef } from 'react';
import {
  FileText, Database, Clock, CheckCircle, AlertCircle,
  X, ExternalLink, ChevronRight, Tag, FolderTree, RefreshCw,
  Edit2, Save, Plus, Eye
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { Badge } from '@/components/enterprise';

export interface DocumentDetail {
  id: string;
  kb_id: string;
  kb_name?: string;
  name: string;
  format: string;
  file_size: number;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  error_message?: string | null;
  uploaded_at: string;
  processed_at?: string | null;
  chunk_count?: number;
  category?: string;
  tags?: string[];
  content_types?: string[];  // 内容类型：text, table, image
  progress?: number;
  current_stage?: string;
  version?: number;
  previous_version_id?: string | null;
  preview_text?: string | null;
}

export interface DocumentDetailPanelProps {
  docId: string | null;
  onClose: () => void;
  onViewPipeline?: (docId: string) => void;
}

function formatBytes(bytes: number) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function formatTime(dateStr: string) {
  if (!dateStr) return '-';
  const date = new Date(dateStr);
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function DocumentDetailPanel({ docId, onClose, onViewPipeline }: DocumentDetailPanelProps) {
  const [loading, setLoading] = useState(false);
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [editingTags, setEditingTags] = useState(false);
  const [newTag, setNewTag] = useState('');
  const [localTags, setLocalTags] = useState<string[]>([]);
  const [savingTags, setSavingTags] = useState(false);
  const tagInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (docId) {
      loadDocument(docId);
    }
  }, [docId]);

  useEffect(() => {
    if (doc?.tags) {
      setLocalTags(doc.tags);
    }
  }, [doc?.tags]);

  useEffect(() => {
    if (editingTags && tagInputRef.current) {
      tagInputRef.current.focus();
    }
  }, [editingTags]);

  const loadDocument = async (id: string) => {
    setLoading(true);
    try {
      const response = await fetch(`/api/v1/documents/${id}`);
      if (response.ok) {
        const data = await response.json();
        setDoc(data);
        setLocalTags(data.tags || []);
      }
    } catch (error) {
      console.error('Failed to load document:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAddTag = () => {
    const tag = newTag.trim();
    if (tag && !localTags.includes(tag)) {
      setLocalTags([...localTags, tag]);
      setNewTag('');
    }
  };

  const handleRemoveTag = (tagToRemove: string) => {
    setLocalTags(localTags.filter(t => t !== tagToRemove));
  };

  const handleSaveTags = async () => {
    setSavingTags(true);
    try {
      const response = await fetch(`/api/v1/documents/${docId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tags: localTags }),
      });
      if (response.ok) {
        toast.success('标签已保存');
        setEditingTags(false);
        loadDocument(docId);
      } else {
        toast.error('保存失败');
      }
    } catch (error) {
      console.error('Failed to save tags:', error);
      toast.error('保存失败');
    } finally {
      setSavingTags(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleAddTag();
    }
  };

  const getStatusInfo = () => {
    if (!doc) return { icon: null, text: '', color: '' };
    switch (doc.status) {
      case 'completed':
        return { icon: CheckCircle, text: '处理完成', color: 'text-emerald-600' };
      case 'failed':
        return { icon: AlertCircle, text: '处理失败', color: 'text-red-600' };
      case 'processing':
        return { icon: RefreshCw, text: '处理中', color: 'text-blue-600' };
      default:
        return { icon: Clock, text: '等待中', color: 'text-gray-500' };
    }
  };

  const statusInfo = getStatusInfo();
  const StatusIcon = statusInfo.icon || FileText;

  if (!docId) return null;

  return (
    <div className="w-[480px] h-full bg-white border-l border-gray-200 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="h-[60px] px-5 border-b border-gray-200 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center">
            <FileText className="w-5 h-5 text-blue-600" />
          </div>
          <div className="min-w-0">
            <h2 className="text-sm font-medium text-gray-900 truncate">{doc?.name || '加载中...'}</h2>
            <div className="flex items-center gap-2 text-xs text-gray-500">
              {statusInfo.icon && <StatusIcon className={cn("w-3 h-3", statusInfo.color)} />}
              <span className={statusInfo.color}>{statusInfo.text}</span>
            </div>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
        >
          <X className="w-4 h-4 text-gray-500" />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <RefreshCw className="w-6 h-6 animate-spin text-blue-600" />
          </div>
        ) : !doc ? (
          <div className="flex items-center justify-center py-12">
            <p className="text-sm text-gray-500">文档加载失败</p>
          </div>
        ) : (
          <div className="p-5 space-y-6">
            {/* 基本信息 */}
            <section>
              <h3 className="text-xs font-medium text-gray-500 uppercase mb-3">基本信息</h3>
              <div className="space-y-3">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-500">知识库</span>
                  <span className="text-gray-900">{doc.kb_name || doc.kb_id}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-500">格式</span>
                  <span className="text-gray-900 uppercase">{doc.format}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-500">大小</span>
                  <span className="text-gray-900">{formatBytes(doc.file_size)}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-500">上传时间</span>
                  <span className="text-gray-900">{formatTime(doc.uploaded_at)}</span>
                </div>
                {doc.processed_at && (
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-gray-500">处理完成</span>
                    <span className="text-gray-900">{formatTime(doc.processed_at)}</span>
                  </div>
                )}
              </div>
            </section>

            {/* 分类和标签 */}
            <section>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-xs font-medium text-gray-500 uppercase">分类和标签</h3>
                {!editingTags && (
                  <button
                    onClick={() => setEditingTags(true)}
                    className="p-1 hover:bg-gray-100 rounded transition-colors"
                    title="编辑标签"
                  >
                    <Edit2 className="w-3 h-3 text-gray-500" />
                  </button>
                )}
              </div>
              <div className="space-y-3">
                {doc.category && (
                  <div className="flex items-center gap-2">
                    <FolderTree className="w-4 h-4 text-gray-400" />
                    <span className="text-sm text-gray-700">{doc.category}</span>
                  </div>
                )}

                {/* 标签编辑模式 */}
                {editingTags ? (
                  <div className="space-y-2">
                    <div className="flex gap-2">
                      <input
                        ref={tagInputRef}
                        type="text"
                        value={newTag}
                        onChange={(e) => setNewTag(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="输入标签后按回车添加"
                        className="flex-1 px-3 py-1.5 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                      <button
                        onClick={handleAddTag}
                        className="px-3 py-1.5 bg-blue-50 text-blue-600 text-sm font-medium rounded hover:bg-blue-100 transition-colors flex items-center gap-1"
                      >
                        <Plus className="w-3 h-3" />
                        添加
                      </button>
                    </div>
                    {localTags.length > 0 && (
                      <div className="flex flex-wrap gap-2">
                        {localTags.map((tag, idx) => (
                          <span
                            key={idx}
                            className="inline-flex items-center gap-1 px-2 py-1 bg-gray-100 text-gray-600 text-xs rounded group"
                          >
                            <Tag className="w-3 h-3" />
                            {tag}
                            <button
                              onClick={() => handleRemoveTag(tag)}
                              className="ml-1 hover:text-red-500 transition-colors"
                            >
                              <X className="w-3 h-3" />
                            </button>
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="flex gap-2 pt-2">
                      <button
                        onClick={handleSaveTags}
                        disabled={savingTags}
                        className="px-3 py-1.5 bg-blue-600 text-white text-sm font-medium rounded hover:bg-blue-700 transition-colors flex items-center gap-1 disabled:opacity-50"
                      >
                        <Save className="w-3 h-3" />
                        {savingTags ? '保存中...' : '保存'}
                      </button>
                      <button
                        onClick={() => {
                          setEditingTags(false);
                          setLocalTags(doc.tags || []);
                          setNewTag('');
                        }}
                        className="px-3 py-1.5 bg-gray-100 text-gray-600 text-sm font-medium rounded hover:bg-gray-200 transition-colors"
                      >
                        取消
                      </button>
                    </div>
                  </div>
                ) : (
                  /* 标签展示模式 */
                  localTags.length > 0 ? (
                    <div className="flex flex-wrap gap-2">
                      {localTags.map((tag, idx) => (
                        <span
                          key={idx}
                          className="inline-flex items-center gap-1 px-2 py-1 bg-gray-100 text-gray-600 text-xs rounded"
                        >
                          <Tag className="w-3 h-3" />
                          {tag}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-gray-400">暂无标签，点击编辑添加</p>
                  )
                )}
              </div>
            </section>

            {/* 内容类型 */}
            {doc.content_types && doc.content_types.length > 0 && (
              <section>
                <h3 className="text-xs font-medium text-gray-500 uppercase mb-3">内容类型</h3>
                <div className="flex flex-wrap gap-2">
                  {doc.content_types.map((ct: string, idx: number) => (
                    <Badge
                      key={idx}
                      variant="secondary"
                      className="bg-indigo-50 text-indigo-700 border border-indigo-200"
                    >
                      {ct === 'text' && <FileText className="w-3 h-3 mr-1" />}
                      {ct === 'table' && <Database className="w-3 h-3 mr-1" />}
                      {ct === 'image' && <Eye className="w-3 h-3 mr-1" />}
                      {ct}
                    </Badge>
                  ))}
                </div>
              </section>
            )}

            {/* 处理统计 */}
            {doc.chunk_count !== undefined && doc.chunk_count !== null && (
              <section>
                <h3 className="text-xs font-medium text-gray-500 uppercase mb-3">处理统计</h3>
                <div className="bg-blue-50 rounded-lg p-4">
                  <div className="flex items-center gap-3">
                    <Database className="w-8 h-8 text-blue-600" />
                    <div>
                      <div className="text-2xl font-bold text-blue-900">{doc.chunk_count}</div>
                      <div className="text-xs text-blue-600">文本块 / 向量</div>
                    </div>
                  </div>
                </div>
              </section>
            )}

            {/* 错误信息 */}
            {doc.status === 'failed' && doc.error_message && (
              <section>
                <h3 className="text-xs font-medium text-gray-500 uppercase mb-3">错误信息</h3>
                <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                  <div className="flex items-start gap-2">
                    <AlertCircle className="w-5 h-5 text-red-600 shrink-0" />
                    <div className="text-sm text-red-700 break-all">{doc.error_message}</div>
                  </div>
                </div>
              </section>
            )}

            {/* 处理流水线入口 */}
            {onViewPipeline && (
              <section>
                <h3 className="text-xs font-medium text-gray-500 uppercase mb-3">处理流程</h3>
                <button
                  onClick={() => onViewPipeline(doc.id)}
                  className="w-full flex items-center justify-between px-4 py-3 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors group"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
                      <RefreshCw className="w-5 h-5 text-blue-600" />
                    </div>
                    <div className="text-left">
                      <div className="text-sm font-medium text-gray-900">查看处理流水线</div>
                      <div className="text-xs text-gray-500">查看各阶段输入输出数据</div>
                    </div>
                  </div>
                  <ChevronRight className="w-5 h-5 text-gray-400 group-hover:translate-x-1 transition-transform" />
                </button>
              </section>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
