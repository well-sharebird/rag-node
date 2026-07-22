import { useState, useEffect, useRef } from 'react';
import { useAppContext } from '@/lib/app-context';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  Database, FileText, Plus, Search, UploadCloud, MoreVertical,
  Trash2, Eye, RefreshCw, Loader2, X, FolderOpen,
  TrendingUp, Calendar, Shield, ChevronLeft
} from 'lucide-react';
import { useI18n } from '@/src/lib/i18n';
import { fetchDocs, deleteDoc, uploadDoc, fetchDocumentCategories } from '@/lib/api-client';
import { cn } from '@/lib/utils';

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

  // Selected KB
  const [selectedKb, setSelectedKb] = useState<KBDetail | null>(null);

  // Search & filter
  const [searchTerm, setSearchTerm] = useState('');
  const [docSearchTerm, setDocSearchTerm] = useState('');
  const [filterCategory, setFilterCategory] = useState('all');
  const [categories, setCategories] = useState<string[]>([]);

  // KB management
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newKbName, setNewKbName] = useState('');
  const [newKbDesc, setNewKbDesc] = useState('');

  // Document management
  const [kbDocuments, setKbDocuments] = useState<any[]>([]);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [previewDoc, setPreviewDoc] = useState<any>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Filtered KBs
  const filteredKbs = knowledgeBases.filter(kb =>
    kb.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    kb.description.toLowerCase().includes(searchTerm.toLowerCase())
  );

  // Filtered documents
  const filteredDocs = kbDocuments.filter(doc => {
    const matchesSearch = doc.name.toLowerCase().includes(docSearchTerm.toLowerCase());
    const matchesCat = filterCategory === 'all' || (doc.category || '') === filterCategory;
    return matchesSearch && matchesCat;
  });

  // Load categories when viewing a KB
  useEffect(() => {
    if (selectedKb) {
      fetchDocumentCategories(selectedKb.id)
        .then(d => setCategories(d.categories || []))
        .catch(() => {});
    }
  }, [selectedKb]);

  // Handle KB selection - expand to show documents
  const handleSelectKb = (kb: typeof knowledgeBases[0]) => {
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

  // Load documents for a KB
  const loadDocuments = async (kbId: string) => {
    setLoadingDocs(true);
    try {
      const data = await fetchDocs(kbId);
      setKbDocuments(data.items || []);
    } catch (e: any) {
      toast.error('加载文档列表失败');
    } finally {
      setLoadingDocs(false);
    }
  };

  // Upload files
  const handleUpload = async () => {
    if (!selectedKb || uploadFiles.length === 0) return;
    setUploading(true);
    try {
      for (const file of uploadFiles) {
        await uploadDoc(selectedKb.id, file);
      }
      toast.success(`已上传 ${uploadFiles.length} 个文件`);
      setUploadFiles([]);
      setIsUploadOpen(false);
      loadDocuments(selectedKb.id);
      refresh();
    } catch (e: any) {
      toast.error(`上传失败：${e.message}`);
    } finally {
      setUploading(false);
    }
  };

  // Delete document
  const handleDeleteDoc = async (docId: string) => {
    if (!window.confirm('确定要删除此文档吗？')) return;
    try {
      await deleteDoc(docId);
      toast.success('文档已删除');
      if (selectedKb) loadDocuments(selectedKb.id);
      refresh();
    } catch (e: any) {
      toast.error(`删除失败：${e.message}`);
    }
  };

  // Create KB - 简化创建流程
  const handleCreateKb = () => {
    if (!newKbName.trim()) return;
    addKnowledgeBase({
      name: newKbName.trim(),
      description: newKbDesc.trim() || undefined,
      permissions: 'write' // 默认写入权限
    });
    setIsCreateOpen(false);
    setNewKbName('');
    setNewKbDesc('');
    toast.success(language === 'zh' ? `"${newKbName.trim()}" 已创建` : `"${newKbName.trim()}" created`);
    refresh();
  };

  // Delete KB
  const handleDeleteKb = async (kbId: string) => {
    if (!window.confirm('确定要删除此知识库吗？')) return;
    deleteKnowledgeBase(kbId);
    toast.success('知识库已删除');
    setSelectedKb(null);
    setActiveTab('list');
    refresh();
  };

  // Clear selection - collapse the KB
  const handleClearSelection = () => {
    setSelectedKb(null);
    setKbDocuments([]);
  };

  // Format file size
  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-[#f7f7f7]">
      {/* Header */}
      <header className="h-[60px] px-6 bg-white flex items-center justify-between shrink-0 border-b border-[#e5e5e5]">
        <div className="flex items-center gap-4 flex-1">
          {selectedKb && (
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 -ml-2"
              onClick={handleClearSelection}
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
          )}
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-50 to-indigo-50 flex items-center justify-center">
            <Database className="w-5 h-5 text-blue-600" />
          </div>
          <div>
            <h1 className="text-[18px] font-semibold text-[#1a1a1a]">
              {selectedKb ? selectedKb.name : (language === 'zh' ? '知识库' : 'Knowledge Base')}
            </h1>
            <p className="text-[13px] text-[#999999] mt-0.5">
              {selectedKb?.description || (language === 'zh' ? '管理和配置您的向量存储和文档集合' : 'Manage your vector storage and document collections')}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {selectedKb && (
            <>
              <Button
                variant="outline"
                onClick={() => loadDocuments(selectedKb.id)}
                className="rounded-xl"
              >
                <RefreshCw className={cn("w-4 h-4 mr-1", loadingDocs ? 'animate-spin' : '')} />
                {language === 'zh' ? '刷新' : 'Refresh'}
              </Button>
              <Button
                onClick={() => setIsUploadOpen(true)}
                className="bg-[#1a1a1a] text-white hover:bg-[#333] rounded-xl shadow-sm"
              >
                <UploadCloud className="w-4 h-4 mr-2" />
                {language === 'zh' ? '上传文档' : 'Upload Document'}
              </Button>
            </>
          )}
          {!selectedKb && (
            <Button
              onClick={() => setIsCreateOpen(true)}
              className="bg-[#1a1a1a] text-white hover:bg-[#333] rounded-xl shadow-sm"
            >
              <Plus className="w-4 h-4 mr-2" />
              {language === 'zh' ? '新建知识库' : 'New Knowledge Base'}
            </Button>
          )}
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {!selectedKb ? (
          /* 知识库列表视图 */
          <div className="space-y-6">
            {/* Search Bar */}
            <div className="flex items-center gap-4">
              <div className="relative flex-1 max-w-md">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-[#999]" />
                <Input
                  placeholder={language === 'zh' ? '搜索知识库...' : 'Search knowledge bases...'}
                  className="pl-10 h-11 rounded-xl bg-white border-[#e5e5e5]"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
              </div>
              <Badge variant="secondary" className="h-8 px-3 text-sm">
                {filteredKbs.length} {language === 'zh' ? '个知识库' : 'KBs'}
              </Badge>
            </div>

            {/* KB Cards */}
            {filteredKbs.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-20 bg-white rounded-2xl border border-[#e5e5e5]">
                <div className="w-20 h-20 rounded-2xl bg-[#f5f5f5] flex items-center justify-center mb-6">
                  <Database className="w-10 h-10 text-[#ccc]" />
                </div>
                <h3 className="text-lg font-semibold text-[#1a1a1a] mb-2">
                  {language === 'zh' ? '暂无知识库' : 'No knowledge bases'}
                </h3>
                <p className="text-[#999] text-sm mb-6">
                  {language === 'zh' ? '创建第一个知识库开始使用' : 'Create your first knowledge base to get started'}
                </p>
                <Button
                  onClick={() => setIsCreateOpen(true)}
                  className="bg-[#1a1a1a] text-white hover:bg-[#333] rounded-xl"
                >
                  <Plus className="w-4 h-4 mr-2" />
                  {language === 'zh' ? '创建知识库' : 'Create Knowledge Base'}
                </Button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {filteredKbs.map((kb) => (
                  <Card
                    key={kb.id}
                    className="bg-white border-[#e5e5e5] rounded-2xl hover:shadow-lg hover:-translate-y-1 transition-all cursor-pointer group"
                    onClick={() => handleSelectKb(kb)}
                  >
                    <CardHeader className="pb-4">
                      <div className="flex items-start justify-between">
                        <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-50 to-indigo-50 flex items-center justify-center">
                          <Database className="w-6 h-6 text-blue-600" />
                        </div>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <MoreVertical className="w-4 h-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end" className="rounded-xl">
                            <DropdownMenuItem onClick={(e) => { e.stopPropagation(); handleDeleteKb(kb.id); }}>
                              <Trash2 className="w-4 h-4 mr-2 text-red-600" />
                              {language === 'zh' ? '删除' : 'Delete'}
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                      <CardTitle className="text-lg font-semibold mt-4">{kb.name}</CardTitle>
                      <CardDescription className="text-sm text-[#999] line-clamp-2 mt-2">
                        {kb.description || (language === 'zh' ? '暂无描述' : 'No description')}
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="grid grid-cols-3 gap-3 pt-4 border-t border-[#e5e5e5]">
                        <div className="text-center">
                          <div className="text-2xl font-bold text-[#1a1a1a]">{kb.documentCount}</div>
                          <div className="text-[11px] text-[#999] uppercase tracking-wide mt-1">
                            {language === 'zh' ? '文档' : 'Docs'}
                          </div>
                        </div>
                        <div className="text-center border-l border-[#e5e5e5]">
                          <div className="text-2xl font-bold text-[#1a1a1a]">{(kb.vectorCount / 1000).toFixed(1)}k</div>
                          <div className="text-[11px] text-[#999] uppercase tracking-wide mt-1">
                            {language === 'zh' ? '向量' : 'Vectors'}
                          </div>
                        </div>
                        <div className="text-center border-l border-[#e5e5e5]">
                          <Badge className="mt-1.5 text-[10px] rounded-lg" variant="secondary">
                            {kb.permissions}
                          </Badge>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </div>
        ) : (
          /* 知识库详情 + 文档列表 */
          <div className="space-y-6">
            {/* 统计卡片 */}
            <div className="grid grid-cols-4 gap-4">
              <Card className="bg-white border-[#e5e5e5] rounded-2xl">
                <CardContent className="p-5">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center">
                      <FileText className="w-5 h-5 text-blue-600" />
                    </div>
                    <div>
                      <div className="text-2xl font-bold text-[#1a1a1a]">{selectedKb?.documentCount}</div>
                      <div className="text-[12px] text-[#999]">{language === 'zh' ? '文档总数' : 'Total Documents'}</div>
                    </div>
                  </div>
                </CardContent>
              </Card>
              <Card className="bg-white border-[#e5e5e5] rounded-2xl">
                <CardContent className="p-5">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-indigo-50 flex items-center justify-center">
                      <TrendingUp className="w-5 h-5 text-indigo-600" />
                    </div>
                    <div>
                      <div className="text-2xl font-bold text-[#1a1a1a]">{(selectedKb?.vectorCount / 1000).toFixed(1)}k</div>
                      <div className="text-[12px] text-[#999]">{language === 'zh' ? '向量总数' : 'Total Vectors'}</div>
                    </div>
                  </div>
                </CardContent>
              </Card>
              <Card className="bg-white border-[#e5e5e5] rounded-2xl">
                <CardContent className="p-5">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-purple-50 flex items-center justify-center">
                      <Shield className="w-5 h-5 text-purple-600" />
                    </div>
                    <div>
                      <div className="text-lg font-bold text-[#1a1a1a] uppercase">{selectedKb?.permissions}</div>
                      <div className="text-[12px] text-[#999]">{language === 'zh' ? '权限级别' : 'Permission Level'}</div>
                    </div>
                  </div>
                </CardContent>
              </Card>
              <Card className="bg-white border-[#e5e5e5] rounded-2xl">
                <CardContent className="p-5">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-green-50 flex items-center justify-center">
                      <Calendar className="w-5 h-5 text-green-600" />
                    </div>
                    <div>
                      <div className="text-sm font-medium text-[#1a1a1a]">
                        {new Date(selectedKb?.createdAt).toLocaleDateString('zh-CN')}
                      </div>
                      <div className="text-[12px] text-[#999]">{language === 'zh' ? '创建时间' : 'Created At'}</div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* 文档列表 */}
            <Card className="bg-white border-[#e5e5e5] rounded-2xl">
              <CardHeader className="pb-4 border-b border-[#e5e5e5]">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <FolderOpen className="w-5 h-5 text-[#999]" />
                    <CardTitle className="text-base font-semibold">
                      {language === 'zh' ? '文档列表' : 'Documents'}
                    </CardTitle>
                    <Badge variant="secondary" className="h-6 text-xs">
                      {filteredDocs.length}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-3">
                    {/* Category Filter */}
                    <Select value={filterCategory} onValueChange={setFilterCategory}>
                      <SelectTrigger className="w-[150px] h-9 rounded-lg">
                        <SelectValue placeholder={language === 'zh' ? '全部分类' : 'All Categories'} />
                      </SelectTrigger>
                      <SelectContent className="rounded-xl">
                        <SelectItem value="all">{language === 'zh' ? '全部分类' : 'All Categories'}</SelectItem>
                        <SelectItem value="">{language === 'zh' ? '未分类' : 'Uncategorized'}</SelectItem>
                        {categories.filter(c => c).map(c => (
                          <SelectItem key={c} value={c}>{c}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {/* Document Search */}
                    <div className="relative">
                      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#999]" />
                      <Input
                        placeholder={language === 'zh' ? '搜索文档...' : 'Search documents...'}
                        className="pl-9 h-9 w-64 rounded-lg bg-[#f9f9f9] border-transparent"
                        value={docSearchTerm}
                        onChange={(e) => setDocSearchTerm(e.target.value)}
                      />
                    </div>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="p-0">
                {loadingDocs ? (
                  <div className="flex items-center justify-center py-12">
                    <Loader2 className="w-6 h-6 animate-spin text-[#1a1a1a]" />
                  </div>
                ) : filteredDocs.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-12">
                    <FileText className="w-12 h-12 text-[#ccc] mb-4" />
                    <p className="text-sm font-medium text-[#1a1a1a]">
                      {language === 'zh' ? '暂无文档' : 'No documents'}
                    </p>
                    <p className="text-xs text-[#999] mt-1">
                      {language === 'zh' ? '上传文档到此知识库' : 'Upload documents to this knowledge base'}
                    </p>
                    <Button
                      onClick={() => setIsUploadOpen(true)}
                      className="mt-4 bg-[#1a1a1a] text-white hover:bg-[#333] rounded-xl"
                    >
                      <UploadCloud className="w-4 h-4 mr-2" />
                      {language === 'zh' ? '上传文档' : 'Upload Document'}
                    </Button>
                  </div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow className="border-[#e5e5e5]">
                        <TableHead className="font-medium text-[#666]">
                          {language === 'zh' ? '文档名称' : 'Document Name'}
                        </TableHead>
                        <TableHead className="font-medium text-[#666]">
                          {language === 'zh' ? '状态' : 'Status'}
                        </TableHead>
                        <TableHead className="font-medium text-[#666]">
                          {language === 'zh' ? '大小' : 'Size'}
                        </TableHead>
                        <TableHead className="font-medium text-[#666]">
                          {language === 'zh' ? '上传时间' : 'Uploaded'}
                        </TableHead>
                        <TableHead className="font-medium text-[#666] text-right">
                          {language === 'zh' ? '操作' : 'Actions'}
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filteredDocs.map((doc) => (
                        <TableRow key={doc.id} className="border-[#f0f0f0] hover:bg-[#fafafa]">
                          <TableCell className="font-medium">
                            <div className="flex items-center gap-2">
                              <div className="w-8 h-8 rounded-lg bg-[#f5f5f5] flex items-center justify-center">
                                <FileText className="w-4 h-4 text-[#999]" />
                              </div>
                              <div>
                                <div className="text-sm font-medium text-[#1a1a1a] truncate max-w-[300px]">
                                  {doc.name}
                                </div>
                                <div className="text-xs text-[#999] mt-0.5">
                                  {doc.format.toUpperCase()} · {doc.chunk_count || 0} chunks
                                </div>
                              </div>
                            </div>
                          </TableCell>
                          <TableCell>
                            <Badge
                              className={cn(
                                "text-xs rounded-lg",
                                doc.status === 'completed' ? 'bg-green-50 text-green-600' :
                                doc.status === 'failed' ? 'bg-red-50 text-red-600' :
                                doc.status === 'processing' ? 'bg-blue-50 text-blue-600' :
                                'bg-slate-100 text-slate-500'
                              )}
                            >
                              {doc.status === 'completed' ? (language === 'zh' ? '已完成' : 'Completed') :
                               doc.status === 'failed' ? (language === 'zh' ? '失败' : 'Failed') :
                               doc.status === 'processing' ? (language === 'zh' ? '处理中' : 'Processing') : doc.status}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-sm text-[#666]">
                            {formatBytes(doc.file_size)}
                          </TableCell>
                          <TableCell className="text-sm text-[#999]">
                            {new Date(doc.uploadedAt).toLocaleDateString(language === 'zh' ? 'zh-CN' : 'en-US')}
                          </TableCell>
                          <TableCell className="text-right">
                            <div className="flex items-center justify-end gap-1">
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-8"
                                onClick={() => setPreviewDoc(doc)}
                              >
                                <Eye className="w-4 h-4" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-8 text-red-600 hover:bg-red-50"
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
                )}
              </CardContent>
            </Card>
          </div>
        )}
      </div>

      {/* Create KB Dialog - 简化表单 */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent className="rounded-2xl sm:max-w-[400px]">
          <DialogHeader>
            <DialogTitle className="text-xl font-bold flex items-center gap-2">
              <Database className="w-5 h-5" />
              {language === 'zh' ? '创建知识库' : 'Create Knowledge Base'}
            </DialogTitle>
            <DialogDescription>
              {language === 'zh'
                ? '只需输入名称即可创建，其他设置可后续配置'
                : 'Just enter a name to create, other settings can be configured later'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="name" className="font-semibold text-[#1a1a1a]">
                {language === 'zh' ? '名称' : 'Name'} *
              </Label>
              <Input
                id="name"
                className="rounded-xl bg-[#f9f9f9] border-[#e5e5e5] h-11"
                placeholder={language === 'zh' ? '例如：产品文档、团队知识库' : 'e.g., Product Docs, Team KB'}
                value={newKbName}
                onChange={(e) => setNewKbName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && newKbName.trim()) {
                    handleCreateKb();
                  }
                }}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="desc" className="font-semibold text-[#1a1a1a]">
                {language === 'zh' ? '描述（可选）' : 'Description (Optional)'}
              </Label>
              <Input
                id="desc"
                className="rounded-xl bg-[#f9f9f9] border-[#e5e5e5] h-11"
                placeholder={language === 'zh' ? '简要描述用途...' : 'Brief description...'}
                value={newKbDesc}
                onChange={(e) => setNewKbDesc(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" className="rounded-xl" onClick={() => setIsCreateOpen(false)}>
              {language === 'zh' ? '取消' : 'Cancel'}
            </Button>
            <Button
              onClick={handleCreateKb}
              disabled={!newKbName.trim()}
              className="bg-[#1a1a1a] hover:bg-[#333] rounded-xl"
            >
              {language === 'zh' ? '立即创建' : 'Create Now'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Upload Dialog - 优化拖拽体验 */}
      <Dialog open={isUploadOpen} onOpenChange={setIsUploadOpen}>
        <DialogContent className="max-w-2xl rounded-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl font-bold flex items-center gap-2">
              <UploadCloud className="w-5 h-5 text-blue-600" />
              {language === 'zh' ? '上传文档到' : 'Upload to'} "{selectedKb?.name}"
            </DialogTitle>
            <DialogDescription>
              {language === 'zh'
                ? '支持 PDF, DOCX, XLSX, PPTX, TXT, MD, HTML, 图片 (单个文件最大 50MB)'
                : 'Supports PDF, DOCX, XLSX, PPTX, TXT, MD, HTML, Images (Max 50MB per file)'}
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <div
              className="border-2 border-dashed border-[#e5e5e5] rounded-xl p-10 text-center hover:border-blue-400 hover:bg-blue-50/30 transition-all cursor-pointer"
              onDragOver={(e) => { e.preventDefault(); }}
              onDrop={(e) => {
                e.preventDefault();
                const files = Array.from(e.dataTransfer.files).filter(f => f.size <= 50 * 1024 * 1024);
                if (files.length < e.dataTransfer.files.length) {
                  toast.warning(language === 'zh' ? '有文件超过 50MB，已自动过滤' : 'Some files exceed 50MB and were filtered');
                }
                setUploadFiles(prev => [...prev, ...files]);
              }}
              onClick={() => fileInputRef.current?.click()}
            >
              <div className="w-14 h-14 rounded-2xl bg-blue-50 flex items-center justify-center mx-auto mb-4">
                <UploadCloud className="w-7 h-7 text-blue-600" />
              </div>
              <p className="text-sm font-semibold text-[#1a1a1a] mb-1">
                {language === 'zh' ? '拖拽文件到此处，或点击选择' : 'Drag & drop files here, or click to select'}
              </p>
              <p className="text-xs text-[#999]">
                {language === 'zh' ? '单次可选择多个文件，每个文件最大 50MB' : 'Select multiple files at once, max 50MB each'}
              </p>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              accept=".pdf,.docx,.xlsx,.pptx,.txt,.md,.html,.htm,.jpg,.jpeg,.png,.tiff,.tif,.bmp"
              onChange={(e) => setUploadFiles(prev => [...prev, ...Array.from(e.target.files || [])])}
            />

            {/* 文件列表 */}
            {uploadFiles.length > 0 && (
              <div className="mt-5 space-y-2 max-h-56 overflow-y-auto">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-medium text-[#666]">
                    {uploadFiles.length} {language === 'zh' ? '个文件待上传' : 'file(s) to upload'}
                  </span>
                  <Button
                    variant="ghost"
                    size="xs"
                    className="h-6 text-xs text-red-600 hover:bg-red-50"
                    onClick={() => setUploadFiles([])}
                  >
                    <X className="w-3 h-3 mr-1" />
                    {language === 'zh' ? '清空全部' : 'Clear All'}
                  </Button>
                </div>
                {uploadFiles.map((file, i) => (
                  <div key={i} className="flex items-center gap-3 p-3 bg-[#f9f9f9] rounded-xl border border-[#e5e5e5]">
                    <div className="w-9 h-9 rounded-lg bg-white flex items-center justify-center shrink-0">
                      <FileText className="w-4 h-4 text-blue-600" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-[#1a1a1a] truncate">{file.name}</p>
                      <p className="text-xs text-[#999]">{formatBytes(file.size)}</p>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 shrink-0 hover:bg-white"
                      onClick={(e) => {
                        e.stopPropagation();
                        setUploadFiles(uploadFiles.filter((_, idx) => idx !== i));
                      }}
                    >
                      <X className="w-4 h-4 text-[#999]" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              className="rounded-xl"
              onClick={() => { setUploadFiles([]); setIsUploadOpen(false); }}
            >
              {language === 'zh' ? '取消' : 'Cancel'}
            </Button>
            <Button
              className="bg-[#1a1a1a] text-white hover:bg-[#333] rounded-xl"
              onClick={handleUpload}
              disabled={uploadFiles.length === 0 || uploading}
            >
              {uploading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  {language === 'zh' ? '上传中...' : 'Uploading...'}
                </>
              ) : (
                <>
                  <UploadCloud className="w-4 h-4 mr-2" />
                  {language === 'zh' ? `上传 ${uploadFiles.length} 个文件` : `Upload ${uploadFiles.length} File(s)`}
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Document Preview Dialog */}
      <Dialog open={!!previewDoc} onOpenChange={() => setPreviewDoc(null)}>
        <DialogContent className="max-w-3xl rounded-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl font-bold flex items-center gap-2">
              <FileText className="w-5 h-5" />
              文档详情
            </DialogTitle>
          </DialogHeader>
          {previewDoc && (
            <div className="space-y-4 py-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label className="text-xs text-[#999]">文档名称</Label>
                  <p className="text-sm font-medium mt-1">{previewDoc.name}</p>
                </div>
                <div>
                  <Label className="text-xs text-[#999]">格式</Label>
                  <p className="text-sm font-medium mt-1 uppercase">{previewDoc.format}</p>
                </div>
                <div>
                  <Label className="text-xs text-[#999]">大小</Label>
                  <p className="text-sm font-medium mt-1">{formatBytes(previewDoc.file_size)}</p>
                </div>
                <div>
                  <Label className="text-xs text-[#999]">状态</Label>
                  <Badge className="mt-1.5" variant="secondary">{previewDoc.status}</Badge>
                </div>
                <div>
                  <Label className="text-xs text-[#999]">分块数</Label>
                  <p className="text-sm font-medium mt-1">{previewDoc.chunk_count || 0}</p>
                </div>
                <div>
                  <Label className="text-xs text-[#999]">上传时间</Label>
                  <p className="text-sm font-medium mt-1">
                    {new Date(previewDoc.uploadedAt).toLocaleString('zh-CN')}
                  </p>
                </div>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" className="rounded-xl" onClick={() => setPreviewDoc(null)}>
              关闭
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
