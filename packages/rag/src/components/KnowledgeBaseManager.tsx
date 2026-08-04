import { useState, useEffect, useRef } from 'react';
import { useAppContext } from '@/lib/app-context';
import { toast } from 'sonner';
import { Button } from '@/src/components/enterprise/Button';
import { Input } from '@/src/components/enterprise/Input';
import { Card, CardHeader, CardBody, CardTitle, CardDescription } from '@/src/components/enterprise/Card';
import { Badge } from '@/src/components/enterprise/Badge';
import { Modal } from '@/src/components/enterprise/Modal';
import { Switch } from '@/src/components/enterprise/Switch';
import { Table, TableBody, TableCell, TableHeader, TableRow } from '@/src/components/enterprise/Table';
import { Select } from '@/src/components/enterprise/Select';
import {
  Database, FileText, Plus, Search, UploadCloud, MoreVertical,
  Trash2, Eye, RefreshCw, Loader2, X, FolderOpen,
  TrendingUp, Calendar, Shield, ChevronLeft, Settings, CheckCircle2
} from 'lucide-react';
import { useI18n } from '@/src/lib/i18n';
import { fetchDocs, deleteDoc, uploadDoc, fetchApi } from '@/lib/api-client';
import { cn } from '@/lib/utils';

const STAGE_LABELS: Record<string, string> = {
  pending: '等待处理',
  parsing: '解析文档',
  cleaning: '文本清洗',
  desensitization: '数据脱敏',
  chunking: '分块处理',
  embedding: '向量化',
  validation: '质量验证',
  indexing: '索引构建',
  completed: '处理完成',
  failed: '处理失败',
  processing: '处理中',
};

// 处理阶段顺序
const STAGE_ORDER = ['pending', 'parsing', 'cleaning', 'desensitization', 'chunking', 'embedding', 'validation', 'indexing', 'completed'];

function getStageLabel(stage: string): string {
  return STAGE_LABELS[stage] || stage;
}

// 获取文档已完成的阶段
function getCompletedStages(currentStage: string | null): string[] {
  if (!currentStage || currentStage === 'pending') return [];
  if (currentStage === 'completed') return Object.keys(STAGE_LABELS).filter(k => k !== 'pending' && k !== 'processing' && k !== 'failed');

  const currentIndex = STAGE_ORDER.indexOf(currentStage);
  if (currentIndex <= 0) return [];
  return STAGE_ORDER.slice(0, currentIndex);
}

interface KBDetail {
  id: string;
  name: string;
  description: string;
  documentCount: number;
  vectorCount: number;
  permissions: string;
  createdAt: string;
  updatedAt: string;
}

export function KnowledgeBaseManager() {
  const { knowledgeBases, addKnowledgeBase, deleteKnowledgeBase, refresh } = useAppContext();
  const { t, language } = useI18n();

  // 组件挂载时刷新数据，确保点击左侧菜单时能正确加载
  useEffect(() => {
    refresh();
  }, []);

  const [selectedKb, setSelectedKb] = useState<KBDetail | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [docSearchTerm, setDocSearchTerm] = useState('');
  const [filterCategory, setFilterCategory] = useState('all');
  const [categories, setCategories] = useState<string[]>([]);

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newKbName, setNewKbName] = useState('');
  const [newKbDesc, setNewKbDesc] = useState('');

  const [isEditOpen, setIsEditOpen] = useState(false);
  const [editingKb, setEditingKb] = useState<any | null>(null);
  const [editLoading, setEditLoading] = useState(false);
  const [editName, setEditName] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editTopK, setEditTopK] = useState<number | undefined>(undefined);
  const [editMinScore, setEditMinScore] = useState<number | undefined>(undefined);
  const [editEnableRerank, setEditEnableRerank] = useState<boolean>(false);

  const [kbDocuments, setKbDocuments] = useState<any[]>([]);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [previewDoc, setPreviewDoc] = useState<any>(null);
  const [recentlyUploadedIds, setRecentlyUploadedIds] = useState<string[]>([]);
  const [processingDocIds, setProcessingDocIds] = useState<Set<string>>(new Set());
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const previewPollingRef = useRef<NodeJS.Timeout | null>(null);

  const filteredKbs = knowledgeBases.filter(kb =>
    kb.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    kb.description.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const filteredDocs = kbDocuments.filter(doc => {
    const matchesSearch = doc.name.toLowerCase().includes(docSearchTerm.toLowerCase());
    const matchesCat = filterCategory === 'all' || (doc.category || '') === filterCategory;
    return matchesSearch && matchesCat;
  });

  const handleSelectKb = (kb: any) => {
    setSelectedKb({
      id: kb.id,
      name: kb.name,
      description: kb.description,
      documentCount: kb.documentCount,
      vectorCount: kb.vectorCount,
      permissions: kb.permissions,
      createdAt: kb.createdAt,
      updatedAt: kb.updatedAt,
    });
    loadDocuments(kb.id);
  };

  const loadDocuments = async (kbId: string) => {
    setLoadingDocs(true);
    try {
      const data = await fetchDocs(kbId);
      setKbDocuments(data.items || []);
      setCategories(data.categories || []);
    } catch (err) {
      toast.error('加载文档失败');
    } finally {
      setLoadingDocs(false);
    }
  };

  const handleCreateKb = async () => {
    if (!newKbName.trim()) {
      toast.error('请输入知识库名称');
      return;
    }
    try {
      const res = await fetchApi('/api/v1/knowledge-bases', {
        method: 'POST',
        body: JSON.stringify({
          name: newKbName,
          description: newKbDesc,
          permissions: 'write',
        }),
      });
      // 直接刷新列表，而不是调用 addKnowledgeBase（它会再次调用 API）
      await refresh();
      setIsCreateOpen(false);
      setNewKbName('');
      setNewKbDesc('');
      toast.success('知识库创建成功');
    } catch (err: any) {
      toast.error(err.message || '创建失败');
    }
  };

  const handleDeleteKb = async (kbId: string) => {
    if (!window.confirm('确定要删除此知识库吗？')) return;
    try {
      await deleteKnowledgeBase(kbId);
      setSelectedKb(null);
      toast.success('知识库已删除');
    } catch (err: any) {
      toast.error(err.message || '删除失败');
    }
  };

  const handleEditKb = async () => {
    if (!editingKb) return;
    setEditLoading(true);
    try {
      await fetchApi(`/api/v1/knowledge-bases/${editingKb.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          name: editName,
          description: editDescription,
          top_k: editTopK,
          min_score: editMinScore,
          enable_rerank: editEnableRerank,
        }),
      });
      refresh();
      setIsEditOpen(false);
      toast.success('知识库已更新');
    } catch (err: any) {
      toast.error(err.message || '更新失败');
    } finally {
      setEditLoading(false);
    }
  };

  const openEditDialog = async (kb: any) => {
    setEditingKb(kb);
    setEditName(kb.name);
    setEditDescription(kb.description || '');
    setEditTopK(kb.top_k);
    setEditMinScore(kb.min_score);
    setEditEnableRerank(kb.enable_rerank ?? false);
    setIsEditOpen(true);
  };

  const handleUploadFiles = async () => {
    if (!selectedKb || uploadFiles.length === 0) return;
    setUploading(true);
    const docIds: string[] = [];
    try {
      for (const file of uploadFiles) {
        const result = await uploadDoc(selectedKb.id, file);
        if (result.id) {
          docIds.push(result.id);
        }
      }
      // 上传成功后关闭弹窗，记录新上传的文档 ID
      setRecentlyUploadedIds(docIds);
      setProcessingDocIds(new Set(docIds));
      setIsUploadOpen(false);
      setUploadFiles([]);
      toast.success('文档上传成功，正在后台处理');
      // 先将新文档添加到列表（显示处理中状态）
      const newDocs = docIds.map(id => ({
        id,
        name: uploadFiles.find(f => true)?.name || '上传中...',
        status: 'pending',
        progress: 0,
        current_stage: 'pending',
        uploaded_at: new Date().toISOString(),
      }));
      setKbDocuments(prev => [...newDocs, ...prev]);
      // 启动轮询，只更新处理中的文档进度
      startPolling(selectedKb.id);
    } catch (err: any) {
      toast.error(err.message || '上传失败');
    } finally {
      setUploading(false);
    }
  };

  const startPolling = (kbId: string) => {
    // 清除之前的轮询
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
    }
    // 每 2 秒轮询一次处理中的文档
    pollingIntervalRef.current = setInterval(() => {
      updateProcessingDocs(kbId);
    }, 2000);
  };

  const stopPolling = () => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
  };

  // 只更新处理中的文档进度，不刷新整个列表
  const updateProcessingDocs = async (kbId: string) => {
    const processingIds = Array.from(processingDocIds);
    if (processingIds.length === 0) {
      stopPolling();
      return;
    }

    try {
      // 并行获取所有处理中文档的进度
      const progressPromises = processingIds.map(async (docId) => {
        try {
          const data = await fetchApi(`/api/v1/documents/${docId}/progress`);
          return { docId, progress: data };
        } catch {
          return { docId, progress: null };
        }
      });

      const results = await Promise.all(progressPromises);
      const completedIds: string[] = [];

      // 更新文档状态
      setKbDocuments(prev => prev.map(doc => {
        const result = results.find(r => r.docId === doc.id);
        if (!result || !result.progress) return doc;

        // 如果处理完成或失败，标记为已完成
        if (result.progress.status === 'completed' || result.progress.status === 'failed') {
          completedIds.push(doc.id);
        }

        return {
          ...doc,
          status: result.progress.status,
          progress: result.progress.progress,
          current_stage: result.progress.current_stage,
          chunk_count: result.progress.chunk_count,
          error_message: result.progress.error_message,
          processed_at: result.progress.processed_at,
        };
      }));

      // 移除已完成的文档 ID
      if (completedIds.length > 0) {
        setProcessingDocIds(prev => {
          const next = new Set(prev);
          completedIds.forEach(id => next.delete(id));
          return next;
        });
      }

      // 如果所有文档都处理完成，停止轮询
      const remaining = processingIds.filter(id => !completedIds.includes(id));
      if (remaining.length === 0) {
        stopPolling();
        setRecentlyUploadedIds([]);
        // 刷新一次列表以更新向量计数等
        loadDocuments(kbId);
        toast.success('所有文档处理完成');
      }
    } catch (err) {
      console.error('Failed to update progress:', err);
    }
  };

  // 当有正在处理的文档时继续轮询，全部完成后停止
  useEffect(() => {
    if (processingDocIds.size === 0 && recentlyUploadedIds.length > 0) {
      setRecentlyUploadedIds([]);
    }
  }, [processingDocIds]);

  // 组件卸载时清除轮询
  useEffect(() => {
    return () => {
      stopPolling();
      if (previewPollingRef.current) {
        clearInterval(previewPollingRef.current);
      }
    };
  }, []);

  // 详情弹窗实时刷新进度
  useEffect(() => {
    if (previewPollingRef.current) {
      clearInterval(previewPollingRef.current);
      previewPollingRef.current = null;
    }

    if (previewDoc && (previewDoc.status === 'processing' || previewDoc.status === 'pending')) {
      // 立即获取一次进度
      fetchDocProgress(previewDoc.id);
      // 每 2 秒轮询一次
      previewPollingRef.current = setInterval(() => {
        fetchDocProgress(previewDoc.id);
      }, 2000);
    }

    return () => {
      if (previewPollingRef.current) {
        clearInterval(previewPollingRef.current);
        previewPollingRef.current = null;
      }
    };
  }, [previewDoc?.id, previewDoc?.status]);

  const fetchDocProgress = async (docId: string) => {
    try {
      const data = await fetchApi(`/api/v1/documents/${docId}/progress`);
      setPreviewDoc(prev => prev ? { ...prev, ...data } : null);
      // 同时更新列表中的文档状态
      setKbDocuments(prev => prev.map(doc =>
        doc.id === docId ? { ...doc, ...data } : doc
      ));
    } catch (err) {
      console.error('Failed to fetch doc progress:', err);
    }
  };

  const handleDeleteDoc = async (docId: string) => {
    if (!selectedKb || !window.confirm('确定要删除此文档吗？')) return;
    try {
      await deleteDoc(docId);
      toast.success('文档已删除');
      loadDocuments(selectedKb.id);
    } catch (err: any) {
      toast.error(err.message || '删除失败');
    }
  };

  const openFilePicker = () => {
    fileInputRef.current?.click();
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setUploadFiles(Array.from(e.target.files));
    }
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-white">
      {/* Header - Bird 风格 */}
      <header className="h-[60px] px-6 bg-white flex items-center justify-between shrink-0 border-b border-[var(--sidebar-border)]">
        <div className="flex items-baseline gap-3">
          <h1 className="text-[18px] font-semibold text-[var(--text-primary)]">{t('kb.title')}</h1>
          <span className="text-[13px] text-[var(--text-tertiary)]">{t('kb.desc')}</span>
        </div>
        <Button variant="primary" size="md" onClick={() => setIsCreateOpen(true)}>
          <Plus className="w-4 h-4 mr-2" />
          新建知识库
        </Button>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar - KB List */}
        <div className="w-80 border-r border-[var(--gray-200)] bg-[var(--card-bg)] flex flex-col">
          {/* Search */}
          <div className="p-4 border-b border-[var(--gray-200)]">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text-tertiary)]" />
              <Input
                placeholder={t('kb.search')}
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10"
              />
            </div>
          </div>

          {/* KB List */}
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {filteredKbs.length === 0 ? (
              <div className="text-center py-10">
                <Database className="w-12 h-12 text-[var(--text-tertiary)] mx-auto mb-3" />
                <p className="text-[13px] text-[var(--text-tertiary)]">{t('kb.empty.title')}</p>
              </div>
            ) : (
              filteredKbs.map((kb) => (
                <div
                  key={kb.id}
                  className={cn(
                    "p-3 rounded-xl cursor-pointer transition-colors border",
                    selectedKb?.id === kb.id
                      ? "bg-[var(--accent-light)] border-[var(--primary-light)]"
                      : "bg-[var(--card-bg)] border-[var(--card-border)] hover:bg-[var(--gray-50)]"
                  )}
                  onClick={() => handleSelectKb(kb)}
                >
                  <div className="flex items-start justify-between mb-2">
                    <h3 className="text-[14px] font-medium text-[var(--text-primary)] truncate flex-1">
                      {kb.name}
                    </h3>
                    <Badge variant={kb.documentCount > 0 ? 'success' : 'neutral'}>
                      {kb.documentCount} {t('kb.docs')}
                    </Badge>
                  </div>
                  <p className="text-[12px] text-[var(--text-tertiary)] line-clamp-2 mb-2">
                    {kb.description || t('kb.noDescription')}
                  </p>
                  <div className="flex items-center gap-3 text-[11px] text-[var(--text-tertiary)]">
                    <span className="flex items-center gap-1">
                      <TrendingUp className="w-3 h-3" />
                      {(kb.vectorCount ?? 0).toLocaleString()}
                    </span>
                    <span className="flex items-center gap-1">
                      <Calendar className="w-3 h-3" />
                      {kb.updatedAt ? new Date(kb.updatedAt).toLocaleDateString() : '-'}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Main Content - Document View */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {selectedKb ? (
            <>
              {/* Toolbar */}
              <div className="h-[60px] px-6 border-b border-[var(--gray-200)] bg-[var(--card-bg)] flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setSelectedKb(null)}
                    className="mr-2"
                  >
                    <ChevronLeft className="w-4 h-4 mr-1" />
                    返回
                  </Button>
                  <h2 className="text-[16px] font-semibold text-[var(--text-primary)]">
                    {selectedKb.name}
                  </h2>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => openEditDialog(knowledgeBases.find(k => k.id === selectedKb.id))}
                  >
                    <Settings className="w-4 h-4" />
                  </Button>
                </div>
                <div className="flex items-center gap-2">
                  <Button variant="secondary" size="sm" onClick={() => setIsUploadOpen(true)}>
                    <UploadCloud className="w-4 h-4 mr-2" />
                    上传文档
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => handleDeleteKb(selectedKb.id)}
                  >
                    <Trash2 className="w-4 h-4 mr-2" />
                    删除知识库
                  </Button>
                </div>
              </div>

              {/* Document Table */}
              <div className="flex-1 overflow-y-auto p-6">
                {loadingDocs ? (
                  <div className="flex items-center justify-center py-20">
                    <Loader2 className="w-8 h-8 animate-spin text-[var(--primary)]" />
                  </div>
                ) : filteredDocs.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-20">
                    <FileText className="w-16 h-16 text-[var(--text-tertiary)] mb-4" />
                    <p className="text-[14px] text-[var(--text-tertiary)]">暂无文档</p>
                    <Button
                      variant="primary"
                      size="sm"
                      className="mt-4"
                      onClick={() => setIsUploadOpen(true)}
                    >
                      <Plus className="w-4 h-4 mr-2" />
                      上传第一个文档
                    </Button>
                  </div>
                ) : (
                  <>
                    {/* Document Filters */}
                    <div className="flex items-center gap-3 mb-4">
                      <div className="relative flex-1 max-w-sm">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text-tertiary)]" />
                        <Input
                          placeholder="搜索文档..."
                          value={docSearchTerm}
                          onChange={(e) => setDocSearchTerm(e.target.value)}
                          className="pl-10"
                        />
                      </div>
                      {categories.length > 0 && (
                        <Select
                          value={filterCategory}
                          onChange={(e) => setFilterCategory(e.target.value)}
                          className="w-[180px]"
                        >
                          <option value="all">全部分类</option>
                          {categories.map((cat) => (
                            <option key={cat} value={cat}>{cat}</option>
                          ))}
                        </Select>
                      )}
                    </div>

                    {/* Document Table */}
                    <Table hover>
                      <TableHeader>
                        <TableRow>
                          <TableCell variant="header" className="text-[12px] font-medium text-[var(--text-tertiary)]">
                            文档名称
                          </TableCell>
                          <TableCell variant="header" className="text-[12px] font-medium text-[var(--text-tertiary)]">
                            分类
                          </TableCell>
                          <TableCell variant="header" className="text-[12px] font-medium text-[var(--text-tertiary)]">
                            大小
                          </TableCell>
                          <TableCell variant="header" className="text-[12px] font-medium text-[var(--text-tertiary)]">
                            上传日期
                          </TableCell>
                          <TableCell variant="header" className="text-[12px] font-medium text-[var(--text-tertiary)]">
                            状态
                          </TableCell>
                          <TableCell variant="header" className="text-[12px] font-medium text-[var(--text-tertiary)] text-right">
                            操作
                          </TableCell>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {filteredDocs.map((doc) => (
                          <TableRow key={doc.id}>
                            <TableCell>
                              <div className="flex items-center gap-2">
                                <FileText className="w-4 h-4 text-[var(--text-tertiary)]" />
                                <span className="text-[14px] text-[var(--text-primary)] truncate max-w-[250px]">
                                  {doc.name}
                                </span>
                              </div>
                            </TableCell>
                            <TableCell className="text-[14px] text-[var(--text-secondary)]">
                              {doc.category || '-'}
                            </TableCell>
                            <TableCell className="text-[14px] text-[var(--text-secondary)]">
                              {(doc.file_size / 1024).toFixed(1)} KB
                            </TableCell>
                            <TableCell className="text-[14px] text-[var(--text-secondary)]">
                              {doc.uploaded_at ? new Date(doc.uploaded_at).toLocaleDateString() : '-'}
                            </TableCell>
                            <TableCell className="min-w-[150px]">
                              {doc.status === 'processing' || doc.status === 'pending' ? (
                                <div className="space-y-1">
                                  <div className="flex items-center gap-2">
                                    <Loader2 className="w-3 h-3 animate-spin text-[var(--primary)]" />
                                    <span className="text-[12px] text-[var(--text-secondary)]">
                                      {doc.current_stage ? getStageLabel(doc.current_stage) : '处理中'}
                                    </span>
                                  </div>
                                  <div className="h-1.5 bg-[var(--gray-200)] rounded-full overflow-hidden">
                                    <div
                                      className="h-full bg-[var(--primary)] transition-all duration-300"
                                      style={{ width: `${doc.progress || 0}%` }}
                                    />
                                  </div>
                                  <span className="text-[11px] text-[var(--text-tertiary)]">{doc.progress || 0}%</span>
                                </div>
                              ) : doc.status === 'completed' ? (
                                <Badge variant="success">已完成</Badge>
                              ) : doc.status === 'failed' ? (
                                <div className="text-[12px] text-red-600" title={doc.error_message}>
                                  失败
                                </div>
                              ) : (
                                <Badge variant="neutral">待处理</Badge>
                              )}
                            </TableCell>
                            <TableCell className="text-right">
                              <div className="flex items-center justify-end gap-1">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => setPreviewDoc(doc)}
                                >
                                  <Eye className="w-4 h-4" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="text-[var(--error)] hover:bg-[var(--error-bg)]"
                                  onClick={() => handleDeleteDoc(doc.id)}
                                >
                                  <Trash2 className="w-4 h-4" />
                                </Button>
                              </div>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </>
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <Database className="w-16 h-16 text-[var(--text-tertiary)] mx-auto mb-4" />
                <h3 className="text-[16px] font-medium text-[var(--text-primary)] mb-2">
                  选择一个知识库
                </h3>
                <p className="text-[14px] text-[var(--text-tertiary)]">
                  从左侧列表选择一个知识库查看文档，或创建新的知识库
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Create KB Modal */}
      <Modal
        open={isCreateOpen}
        onOpenChange={setIsCreateOpen}
        title="新建知识库"
        description="定义一个新的隔离空间，用于文档存储和向量检索"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsCreateOpen(false)}>取消</Button>
            <Button variant="primary" onClick={handleCreateKb}>创建</Button>
          </>
        }
      >
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <label className="text-[14px] font-medium text-[var(--text-secondary)]">
              名称 <span className="text-[var(--error)]">*</span>
            </label>
            <Input
              placeholder="例如：工程文档"
              value={newKbName}
              onChange={(e) => setNewKbName(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <label className="text-[14px] font-medium text-[var(--text-secondary)]">
              描述
            </label>
            <Input
              placeholder="可选描述"
              value={newKbDesc}
              onChange={(e) => setNewKbDesc(e.target.value)}
            />
          </div>
        </div>
      </Modal>

      {/* Edit KB Modal */}
      <Modal
        open={isEditOpen}
        onOpenChange={setIsEditOpen}
        title="编辑知识库"
        description="修改知识库配置和参数"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsEditOpen(false)} disabled={editLoading}>取消</Button>
            <Button variant="primary" onClick={handleEditKb} disabled={editLoading}>
              {editLoading ? '保存中...' : '保存'}
            </Button>
          </>
        }
      >
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <label className="text-[14px] font-medium text-[var(--text-secondary)]">
              名称
            </label>
            <Input
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <label className="text-[14px] font-medium text-[var(--text-secondary)]">
              描述
            </label>
            <Input
              value={editDescription}
              onChange={(e) => setEditDescription(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <label className="text-[14px] font-medium text-[var(--text-secondary)]">
              Top-K
            </label>
            <Input
              type="number"
              value={editTopK ?? ''}
              onChange={(e) => setEditTopK(parseInt(e.target.value) || undefined)}
              placeholder="默认检索数量"
            />
          </div>
          <div className="space-y-2">
            <label className="text-[14px] font-medium text-[var(--text-secondary)]">
              最低相似度分数
            </label>
            <Input
              type="number"
              step="0.01"
              value={editMinScore ?? ''}
              onChange={(e) => setEditMinScore(parseFloat(e.target.value) || undefined)}
              placeholder="0-1 之间，0 表示不过滤"
            />
          </div>
          <div className="flex items-center gap-2">
            <Switch
              checked={editEnableRerank}
              onCheckedChange={setEditEnableRerank}
            />
            <label className="text-[14px] text-[var(--text-secondary)]">
              启用重排序
            </label>
          </div>
        </div>
      </Modal>

      {/* Upload Modal */}
      <Modal
        open={isUploadOpen}
        onOpenChange={setIsUploadOpen}
        title="上传文档"
        description="支持 PDF, DOCX, XLSX, PPTX, TXT, MD, HTML, 图片 (单文件最大 50MB)"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsUploadOpen(false)}>取消</Button>
            <Button
              variant="primary"
              onClick={handleUploadFiles}
              disabled={uploadFiles.length === 0 || uploading}
            >
              {uploading ? '上传中...' : '上传'}
            </Button>
          </>
        }
      >
        <div className="space-y-4 py-4">
          <div
            className="border-2 border-dashed border-[var(--gray-300)] rounded-xl p-8 text-center cursor-pointer hover:border-[var(--accent)] transition-colors"
            onClick={openFilePicker}
          >
            <UploadCloud className="w-12 h-12 text-[var(--accent)] mx-auto mb-3" />
            <p className="text-[14px] text-[var(--text-secondary)] mb-1">
              点击选择文件或拖放文件到此处
            </p>
            <p className="text-[12px] text-[var(--text-tertiary)]">
              已选择 {uploadFiles.length} 个文件
            </p>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            onChange={handleFileSelect}
            className="hidden"
          />
          {uploadFiles.length > 0 && (
            <div className="max-h-32 overflow-y-auto space-y-2">
              {uploadFiles.map((file, i) => (
                <div key={i} className="flex items-center justify-between p-2 bg-[var(--gray-50)] rounded-lg">
                  <div className="flex items-center gap-2">
                    <FileText className="w-4 h-4 text-[var(--text-tertiary)]" />
                    <span className="text-[13px] text-[var(--text-primary)] truncate max-w-[200px]">
                      {file.name}
                    </span>
                  </div>
                  <span className="text-[12px] text-[var(--text-tertiary)]">
                    {(file.size / 1024).toFixed(1)} KB
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </Modal>

      {/* Preview Modal */}
      {previewDoc && (
        <Modal
          open={!!previewDoc}
          onOpenChange={() => setPreviewDoc(null)}
          title={previewDoc.name}
          description="文档详情"
          width="650px"
          footer={
            <Button variant="secondary" onClick={() => setPreviewDoc(null)}>关闭</Button>
          }
        >
          <div className="space-y-4 py-4">
            {/* 基本信息 */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-[12px] text-[var(--text-tertiary)]">文档 ID</label>
                <p className="text-[13px] text-[var(--text-primary)] font-mono truncate">{previewDoc.id}</p>
              </div>
              <div>
                <label className="text-[12px] text-[var(--text-tertiary)]">知识库</label>
                <p className="text-[14px] text-[var(--text-primary)]">{previewDoc.kb_name || '-'}</p>
              </div>
              <div>
                <label className="text-[12px] text-[var(--text-tertiary)]">分类</label>
                <p className="text-[14px] text-[var(--text-primary)]">{previewDoc.category || '-'}</p>
              </div>
              <div>
                <label className="text-[12px] text-[var(--text-tertiary)]">大小</label>
                <p className="text-[14px] text-[var(--text-primary)]">
                  {(previewDoc.file_size / 1024).toFixed(1)} KB
                </p>
              </div>
              <div>
                <label className="text-[12px] text-[var(--text-tertiary)]">状态</label>
                <p className="text-[14px] text-[var(--text-primary)]">
                  <Badge variant={previewDoc.status === 'completed' ? 'success' : previewDoc.status === 'failed' ? 'danger' : 'warning'}>
                    {previewDoc.status === 'completed' ? '已完成' : previewDoc.status === 'failed' ? '失败' : '处理中'}
                  </Badge>
                </p>
              </div>
              <div>
                <label className="text-[12px] text-[var(--text-tertiary)]">上传日期</label>
                <p className="text-[14px] text-[var(--text-primary)]">
                  {previewDoc.uploaded_at ? new Date(previewDoc.uploaded_at).toLocaleString() : '-'}
                </p>
              </div>
            </div>

            {/* 处理进度节点 */}
            {(previewDoc.status === 'completed' || previewDoc.status === 'processing' || previewDoc.status === 'pending') && (
              <div className="border-t border-[var(--gray-200)] pt-4">
                <label className="text-[12px] text-[var(--text-tertiary)] mb-3 block">处理进度</label>
                <div className="flex items-center gap-2 mb-2">
                  {['parsing', 'cleaning', 'chunking', 'embedding', 'indexing'].map((stage) => {
                    const completedStages = getCompletedStages(previewDoc.current_stage || previewDoc.status);
                    const isCompleted = completedStages.includes(stage) || previewDoc.status === 'completed';
                    const isCurrent = previewDoc.current_stage === stage;
                    return (
                      <div key={stage} className="flex flex-col items-center gap-1">
                        <div
                          className={cn(
                            "w-8 h-8 rounded-full flex items-center justify-center text-[10px] font-bold transition-all",
                            isCompleted && "bg-green-500 text-white",
                            isCurrent && "bg-[var(--primary)] text-white animate-pulse",
                            !isCompleted && !isCurrent && "bg-[var(--gray-200)] text-[var(--text-tertiary)]"
                          )}
                        >
                          {isCompleted ? '✓' : isCurrent ? '⋯' : stage.charAt(0).toUpperCase()}
                        </div>
                        <span className="text-[10px] text-[var(--text-tertiary)]">{getStageLabel(stage)}</span>
                      </div>
                    );
                  })}
                </div>
                {previewDoc.status === 'processing' && (
                  <div className="mt-3">
                    <div className="h-2 bg-[var(--gray-200)] rounded-full overflow-hidden">
                      <div
                        className="h-full bg-[var(--primary)] transition-all duration-300"
                        style={{ width: `${previewDoc.progress || 0}%` }}
                      />
                    </div>
                    <span className="text-[11px] text-[var(--text-tertiary)]">{previewDoc.progress || 0}%</span>
                  </div>
                )}
              </div>
            )}

            {/* 分块信息 */}
            {previewDoc.status === 'completed' && previewDoc.chunk_count && (
              <div className="border-t border-[var(--gray-200)] pt-4">
                <label className="text-[12px] text-[var(--text-tertiary)] mb-2 block">向量化信息</label>
                <div className="flex items-center gap-6">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-lg bg-green-100 flex items-center justify-center">
                      <FileText className="w-4 h-4 text-green-600" />
                    </div>
                    <div>
                      <div className="text-[11px] text-[var(--text-tertiary)]">分块数量</div>
                      <div className="text-[16px] font-semibold text-green-600">{previewDoc.chunk_count}</div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* 错误信息 */}
            {previewDoc.status === 'failed' && previewDoc.error_message && (
              <div className="border-t border-red-200 pt-4">
                <label className="text-[12px] text-red-600 mb-2 block">错误信息</label>
                <div className="p-3 bg-red-50 rounded-lg border border-red-200">
                  <p className="text-[13px] text-red-700">{previewDoc.error_message}</p>
                </div>
              </div>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}
