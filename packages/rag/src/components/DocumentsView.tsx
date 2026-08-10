import { useState, useEffect, useRef } from 'react';
import { useAppContext } from '@/lib/app-context';
import { uploadDoc, fetchDoc, updateDocument, fetchDocumentCategories, reprocessDocument, batchReprocessDocuments, getDocumentPipeline } from '@/lib/api-client';
import { Button, Card, CardHeader, CardBody, CardTitle, Badge, Input, Modal } from '@/src/components/enterprise';
import { Select } from '@/src/components/enterprise/Select';
import { Table, TableHeader, TableBody, TableRow, TableCell } from '@/src/components/enterprise/Table';
import { UploadCloud, Search, Trash2, RefreshCw, FileText, Database, Link as LinkIcon, AlertCircle, Tag, X, Eye, FolderTree, Activity } from 'lucide-react';
import { useI18n } from '@/src/lib/i18n';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { DocumentPipelineTracing } from '@packages/rag/components/DocumentPipelineTracing';

function formatBytes(bytes: number) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

export function DocumentsView() {
  const { documents, knowledgeBases, deleteDocument, refresh } = useAppContext();
  const { t } = useI18n();
  const [searchTerm, setSearchTerm] = useState('');
  const [filterKb, setFilterKb] = useState<string>('all');
  const [filterCategory, setFilterCategory] = useState<string>('all');
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [categories, setCategories] = useState<string[]>([]);
  const [previewDoc, setPreviewDoc] = useState<any>(null);
  const [editingTags, setEditingTags] = useState<string | null>(null);
  const [tagInput, setTagInput] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [reprocessing, setReprocessing] = useState<string | null>(null);
  const [selectedFailedDocs, setSelectedFailedDocs] = useState<string[]>([]);
  const [viewingPipeline, setViewingPipeline] = useState<string | null>(null);

  useEffect(() => {
    const kbParam = filterKb !== 'all' ? filterKb : undefined;
    fetchDocumentCategories(kbParam)
      .then((d: any) => {
        setCategories(d.categories || []);
      })
      .catch(() => {});
  }, [filterKb, documents.length]);

  const filteredDocs = documents.filter(doc => {
    const matchesSearch = doc.name.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesKb = filterKb === 'all' || doc.kbId === filterKb;
    const matchesCat = filterCategory === 'all' || (doc.category || '') === filterCategory;
    const matchesStatus = filterStatus === 'all' || doc.status === filterStatus;
    return matchesSearch && matchesKb && matchesCat && matchesStatus;
  });

  const handleFileUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const targetKbId = filterKb !== 'all' ? filterKb : (knowledgeBases.length > 0 ? knowledgeBases[0].id : null);
    if (!targetKbId) { toast.error(t('doc.alert.noKb')); return; }
    setUploading(true);
    try {
      for (const file of Array.from(files)) { await uploadDoc(targetKbId, file); }
      await refresh();
      toast.success(t('doc.upload'));
    } catch (e: any) { toast.error(e.message || 'Upload failed'); }
    finally { setUploading(false); if (fileInputRef.current) fileInputRef.current.value = ''; }
  };

  const handleShowPreview = async (docId: string) => {
    try {
      const data = await fetchDoc(docId);
      setPreviewDoc(data);
    } catch { setPreviewDoc(null); }
  };

  const handleViewPipeline = async (docId: string) => {
    try {
      const pipeline = await getDocumentPipeline(docId);
      if (!pipeline || !pipeline.stages || pipeline.stages.length === 0) {
        toast.info('该文档暂无处理流程数据');
        return;
      }
      setViewingPipeline(docId);
    } catch (e: any) {
      toast.error(e.message || '加载流水线失败');
    }
  };

  const handleSaveTags = async (docId: string) => {
    const tags = tagInput.split(',').map(s => s.trim()).filter(Boolean);
    try {
      await updateDocument(docId, { tags });
      setTagInput('');
      setEditingTags(null);
      await refresh();
      toast.success('Tags saved');
    } catch (e: any) { toast.error('Failed to save tags'); }
  };

  const handleSetCategory = async (docId: string, category: string) => {
    try {
      await updateDocument(docId, { category });
      await refresh();
      toast.success('Category updated');
    } catch (e: any) { toast.error('Failed to set category'); }
  };

  const handleReprocess = async (docId: string) => {
    setReprocessing(docId);
    try {
      await reprocessDocument(docId, true);
      await refresh();
      toast.success('文档重新解析成功');
    } catch (e: any) {
      toast.error(e.message || '重新解析失败');
    } finally {
      setReprocessing(null);
    }
  };

  const handleBatchReprocess = async () => {
    if (selectedFailedDocs.length === 0) {
      toast.error('请选择要重新解析的文档');
      return;
    }
    const targetKbId = filterKb !== 'all' ? filterKb : (knowledgeBases.length > 0 ? knowledgeBases[0].id : null);
    if (!targetKbId) {
      toast.error('请选择知识库');
      return;
    }
    setReprocessing('batch');
    try {
      await batchReprocessDocuments(targetKbId, false, selectedFailedDocs);
      await refresh();
      setSelectedFailedDocs([]);
      toast.success(`成功重新解析 ${selectedFailedDocs.length} 个文档`);
    } catch (e: any) {
      toast.error(e.message || '批量重新解析失败');
    } finally {
      setReprocessing(null);
    }
  };

  const toggleSelectFailedDoc = (docId: string) => {
    setSelectedFailedDocs(prev =>
      prev.includes(docId) ? prev.filter(id => id !== docId) : [...prev, docId]
    );
  };

  const getStatusBadge = (status: string) => {
    const variants: Record<string, 'success' | 'primary' | 'neutral' | 'error'> = {
      completed: 'success',
      processing: 'primary',
      pending: 'neutral',
      failed: 'error',
    };
    const labels: Record<string, string> = {
      completed: t('doc.status.completed'),
      processing: t('doc.status.processing'),
      pending: t('doc.status.pending'),
      failed: t('doc.status.failed'),
    };
    return <Badge variant={variants[status] || 'neutral'} size="sm">{labels[status] || status}</Badge>;
  };

  const getKbName = (kbId: string) => {
    const kb = knowledgeBases.find(k => k.id === kbId);
    return kb?.name || kbId;
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    handleFileUpload(e.dataTransfer.files);
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-white">
      {/* Header */}
      <header className="h-[60px] px-6 bg-white flex items-center justify-between shrink-0 border-b border-[var(--gray-200)]">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-[var(--accent-light)] flex items-center justify-center">
            <FileText className="w-5 h-5 text-[var(--accent)]" />
          </div>
          <div>
            <h1 className="text-[18px] font-semibold text-[var(--text-primary)]">{t('doc.title')}</h1>
            <p className="text-[12px] text-[var(--text-secondary)]">{t('doc.desc')}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.doc,.docx,.txt,.md"
            className="hidden"
            onChange={(e) => handleFileUpload(e.target.files)}
          />
          <Button
            variant="secondary"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            icon={<UploadCloud className="w-4 h-4" />}
          >
            {uploading ? t('doc.uploading') : t('doc.uploadBtn')}
          </Button>
          {selectedFailedDocs.length > 0 && (
            <Button
              variant="primary"
              onClick={handleBatchReprocess}
              disabled={reprocessing === 'batch'}
              icon={<RefreshCw className={cn("w-4 h-4", reprocessing === 'batch' && "animate-spin")} />}
            >
              批量重新解析 ({selectedFailedDocs.length})
            </Button>
          )}
          <Button
            onClick={() => refresh()}
            icon={<RefreshCw className="w-4 h-4" />}
          >
            {t('doc.refresh')}
          </Button>
        </div>
      </header>

      {/* Filters */}
      <div className="px-6 py-4 bg-white border-b border-[var(--gray-200)]">
        <div className="flex gap-3">
          <div className="flex-1 relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)]" />
            <Input
              placeholder={t('doc.search')}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10"
            />
          </div>
          <select
            value={filterKb}
            onChange={(e) => setFilterKb(e.target.value)}
            className="enterprise-select w-[180px]"
          >
            <option value="all">{t('doc.allKb')}</option>
            {knowledgeBases.map(kb => (
              <option key={kb.id} value={kb.id}>{kb.name}</option>
            ))}
          </select>
          <select
            value={filterCategory}
            onChange={(e) => setFilterCategory(e.target.value)}
            className="enterprise-select w-[150px]"
          >
            <option value="all">{t('doc.allCategories')}</option>
            {categories.map(cat => (
              <option key={cat} value={cat}>{cat}</option>
            ))}
          </select>
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="enterprise-select w-[130px]"
          >
            <option value="all">{t('doc.allStatus')}</option>
            <option value="completed">{t('doc.status.completed')}</option>
            <option value="processing">{t('doc.status.processing')}</option>
            <option value="pending">{t('doc.status.pending')}</option>
            <option value="failed">{t('doc.status.failed')}</option>
          </select>
        </div>
      </div>

      {/* Drop Zone */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={cn(
          "mx-6 mt-4 border-2 border-dashed rounded-xl p-6 text-center transition-colors",
          isDragging ? "border-[var(--accent)] bg-[var(--accent-light)]" : "border-[var(--gray-200)] bg-white hover:border-[#a78bfa]"
        )}
      >
        <UploadCloud className="w-8 h-8 mx-auto mb-2 text-[var(--text-tertiary)]" />
        <p className="text-[13px] text-[var(--text-secondary)]">
          {t('doc.dragDrop')} <span className="text-[var(--accent)]">{t('doc.orClickToUpload')}</span>
        </p>
      </div>

      {/* Documents Table */}
      <div className="flex-1 overflow-y-auto p-6">
        <Card>
          <CardBody className="p-0">
            {filteredDocs.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-[var(--text-tertiary)]">
                <FileText className="w-12 h-12 mb-4" />
                <p className="text-[14px]">{t('doc.noDocs')}</p>
              </div>
            ) : (
              <Table hover>
                <TableHeader>
                  <TableRow>
                    <TableCell className="font-medium">{t('doc.col.name')}</TableCell>
                    <TableCell className="font-medium">{t('doc.col.kb')}</TableCell>
                    <TableCell className="font-medium">{t('doc.col.category')}</TableCell>
                    <TableCell className="font-medium">{t('doc.col.tags')}</TableCell>
                    <TableCell className="font-medium">{t('doc.col.size')}</TableCell>
                    <TableCell className="font-medium">{t('doc.col.status')}</TableCell>
                    <TableCell className="font-medium text-right">{t('doc.col.actions')}</TableCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredDocs.map(doc => (
                    <TableRow key={doc.id} className={doc.status === 'failed' ? 'bg-red-50' : ''}>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          {doc.status === 'failed' && (
                            <input
                              type="checkbox"
                              checked={selectedFailedDocs.includes(doc.id)}
                              onChange={() => toggleSelectFailedDoc(doc.id)}
                              className="w-4 h-4 rounded border-gray-300 text-[var(--accent)] focus:ring-[var(--accent)]"
                              onClick={(e) => e.stopPropagation()}
                            />
                          )}
                          <FileText className="w-4 h-4 text-[var(--text-tertiary)]" />
                          <span className="font-medium text-[var(--text-primary)]">{doc.name}</span>
                        </div>
                      </TableCell>
                      <TableCell className="text-[var(--text-secondary)]">{getKbName(doc.kbId)}</TableCell>
                      <TableCell>
                        <select
                          value={doc.category || ''}
                          onChange={(e) => handleSetCategory(doc.id, e.target.value)}
                          className="enterprise-select w-[120px]"
                        >
                          <option value="">{t('doc.uncategorized')}</option>
                          {categories.map(cat => (
                            <option key={cat} value={cat}>{cat}</option>
                          ))}
                        </select>
                      </TableCell>
                      <TableCell>
                        {editingTags === doc.id ? (
                          <div className="flex items-center gap-1">
                            <Input
                              value={tagInput}
                              onChange={(e) => setTagInput(e.target.value)}
                              className="w-[120px]"
                              placeholder="tag1, tag2"
                            />
                            <Button size="sm" onClick={() => handleSaveTags(doc.id)}>
                              <Tag className="w-3 h-3" />
                            </Button>
                            <Button size="sm" variant="secondary" onClick={() => setEditingTags(null)}>
                              <X className="w-3 h-3" />
                            </Button>
                          </div>
                        ) : (
                          <div className="flex flex-wrap items-center gap-1.5 max-w-[280px]">
                            {doc.tags && doc.tags.length > 0 ? (
                              <>
                                {doc.tags.slice(0, 5).map((tag: string, i: number) => (
                                  <Badge
                                    key={i}
                                    variant="secondary"
                                    size="sm"
                                    className="bg-purple-50 text-purple-700 border-purple-200"
                                  >
                                    <Tag className="w-2.5 h-2.5 mr-1" />
                                    {tag}
                                  </Badge>
                                ))}
                                {doc.tags.length > 5 && (
                                  <Badge variant="secondary" size="sm" className="bg-gray-100">
                                    +{doc.tags.length - 5}
                                  </Badge>
                                )}
                              </>
                            ) : (
                              <span className="text-xs text-gray-400">暂无标签</span>
                            )}
                            <button
                              onClick={() => {
                                setEditingTags(doc.id);
                                setTagInput(doc.tags?.join(', ') || '');
                              }}
                              className="ml-1 p-1 text-gray-400 hover:text-[var(--accent)] transition-colors"
                              title="编辑标签"
                            >
                              <Tag className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        )}
                      </TableCell>
                      <TableCell className="text-[var(--text-secondary)]">{formatBytes(doc.size)}</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          {getStatusBadge(doc.status)}
                          {doc.errorMessage && (
                            <div className="group relative">
                              <AlertCircle className="w-4 h-4 text-red-500 cursor-help" />
                              <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 text-white text-xs rounded-lg whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity z-10">
                                {doc.errorMessage}
                              </div>
                            </div>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-1">
                          {doc.status === 'failed' && (
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={() => handleReprocess(doc.id)}
                              disabled={reprocessing === doc.id}
                              icon={<RefreshCw className={cn("w-3.5 h-3.5", reprocessing === doc.id && "animate-spin")} />}
                            >
                              重新解析
                            </Button>
                          )}
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleShowPreview(doc.id)}
                            title="查看详情"
                            className="hover:bg-gray-100"
                          >
                            <Eye className="w-3.5 h-3.5" />
                          </Button>
                          <button
                            onClick={() => handleViewPipeline(doc.id)}
                            title="查看处理流水线"
                            className="inline-flex items-center gap-1 px-2 py-1 bg-purple-100 hover:bg-purple-200 text-purple-700 rounded text-xs font-medium transition-colors"
                          >
                            <Activity className="w-4 h-4" />
                            <span>流水线</span>
                          </button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={async () => {
                              try {
                                const docData = await fetchDoc(doc.id);
                                const downloadUrl = `/api/v1/documents/${doc.id}/download`;
                                window.open(downloadUrl, '_blank');
                              } catch (e) {
                                toast.error('下载失败');
                              }
                            }}
                            icon={<LinkIcon className="w-3.5 h-3.5" />}
                          />
                          <Button
                            variant="danger"
                            size="sm"
                            onClick={() => deleteDocument(doc.id)}
                            icon={<Trash2 className="w-3.5 h-3.5" />}
                          />
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardBody>
        </Card>
      </div>

      {/* Preview Modal */}
      <Modal
        open={!!previewDoc}
        onOpenChange={() => setPreviewDoc(null)}
        title={previewDoc?.name}
        className="max-w-3xl"
      >
        <div className="space-y-4 py-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <span className="text-[12px] text-[var(--text-secondary)]">知识库</span>
              <p className="text-[14px] font-medium">{getKbName(previewDoc.kbId)}</p>
            </div>
            <div>
              <span className="text-[12px] text-[var(--text-secondary)]">大小</span>
              <p className="text-[14px] font-medium">{formatBytes(previewDoc.size)}</p>
            </div>
            <div>
              <span className="text-[12px] text-[var(--text-secondary)]">状态</span>
              <p className="text-[14px] font-medium">{getStatusBadge(previewDoc.status)}</p>
            </div>
            <div>
              <span className="text-[12px] text-[var(--text-secondary)]">上传时间</span>
              <p className="text-[14px] font-medium">
                {previewDoc.createdAt ? new Date(previewDoc.createdAt).toLocaleString('zh-CN') : '-'}
              </p>
            </div>
          </div>
          {previewDoc.content && (
            <div className="border-t border-[var(--gray-200)] pt-4">
              <span className="text-[12px] text-[var(--text-secondary)]">内容预览</span>
              <div className="mt-2 p-4 bg-[var(--bg-primary)] rounded-xl text-[13px] text-[var(--text-secondary)] max-h-[300px] overflow-y-auto">
                {previewDoc.content.slice(0, 2000)}
              </div>
            </div>
          )}
        </div>
      </Modal>

      {/* Pipeline Modal */}
      <Modal
        open={!!viewingPipeline}
        onOpenChange={() => setViewingPipeline(null)}
        title="文档处理流水线"
        className="max-w-6xl h-[85vh]"
      >
        {viewingPipeline && (
          <div className="h-[70vh]">
            <DocumentPipelineTracing
              docId={viewingPipeline}
              onClose={() => setViewingPipeline(null)}
            />
          </div>
        )}
      </Modal>
    </div>
  );
}
