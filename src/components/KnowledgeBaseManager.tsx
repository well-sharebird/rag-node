import { useState, useEffect, useRef } from 'react';
import { useAppContext } from '@/lib/app-context';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { 
  Database, FileText, Plus, Search, UploadCloud, MoreVertical, 
  Trash2, Eye, RefreshCw, Loader2, X, ChevronLeft, FolderOpen,
  TrendingUp, Calendar, Shield
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
  const { t } = useI18n();
  
  // View mode: 'list' (all KBs) or 'detail' (single KB with docs)
  const [activeTab, setActiveTab] = useState<'list' | 'detail'>('list');
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
  const [newKbPerms, setNewKbPerms] = useState<'read'|'write'|'admin'>('write');
  
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

  // Handle KB selection
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
    setActiveTab('detail');
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

  // Create KB
  const handleCreateKb = () => {
    if (!newKbName) return;
    addKnowledgeBase({
      name: newKbName,
      description: newKbDesc,
      permissions: newKbPerms
    });
    setIsCreateOpen(false);
    setNewKbName('');
    setNewKbDesc('');
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

  // Back to list
  const handleBackToList = () => {
    setSelectedKb(null);
    setActiveTab('list');
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
        <div className="flex items-center gap-4">
          {activeTab === 'detail' && (
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 -ml-2"
              onClick={handleBackToList}
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
          )}
          <div>
            <h1 className="text-[18px] font-semibold text-[#1a1a1a]">
              {activeTab === 'detail' ? selectedKb?.name : '知识库管理'}
            </h1>
            <p className="text-[13px] text-[#999999] mt-0.5">
              {activeTab === 'detail' ? selectedKb?.description : '管理和配置您的向量存储和文档集合'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {activeTab === 'list' ? (
            <Button
              onClick={() => setIsCreateOpen(true)}
              className="bg-[#1a1a1a] text-white hover:bg-[#333] rounded-xl shadow-sm"
            >
              <Plus className="w-4 h-4 mr-2" />
              新建知识库
            </Button>
          ) : (
            <>
              <Button
                variant="outline"
                onClick={() => loadDocuments(selectedKb!.id)}
                className="rounded-xl"
              >
                <RefreshCw className={cn("w-4 h-4 mr-1", loadingDocs ? 'animate-spin' : '')} />
                刷新
              </Button>
              <Button
                onClick={() => setIsUploadOpen(true)}
                className="bg-[#1a1a1a] text-white hover:bg-[#333] rounded-xl shadow-sm"
              >
                <UploadCloud className="w-4 h-4 mr-2" />
                上传文档
              </Button>
            </>
          )}
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {activeTab === 'list' ? (
          // KB List View
          <div className="space-y-6">
            {/* Search Bar */}
            <div className="flex items-center gap-4">
              <div className="relative flex-1 max-w-md">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-[#999]" />
                <Input
                  placeholder="搜索知识库..."
                  className="pl-10 h-11 rounded-xl bg-white border-[#e5e5e5]"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
              </div>
              <Badge variant="secondary" className="h-8 px-3 text-sm">
                {filteredKbs.length} 个知识库
              </Badge>
            </div>

            {/* KB Cards */}
            {filteredKbs.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-20 bg-white rounded-2xl border border-[#e5e5e5]">
                <div className="w-20 h-20 rounded-2xl bg-[#f5f5f5] flex items-center justify-center mb-6">
                  <Database className="w-10 h-10 text-[#ccc]" />
                </div>
                <h3 className="text-lg font-semibold text-[#1a1a1a] mb-2">暂无知识库</h3>
                <p className="text-[#999] text-sm mb-6">创建第一个知识库开始使用</p>
                <Button
                  onClick={() => setIsCreateOpen(true)}
                  className="bg-[#1a1a1a] text-white hover:bg-[#333] rounded-xl"
                >
                  <Plus className="w-4 h-4 mr-2" />
                  创建知识库
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
                              删除
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                      <CardTitle className="text-lg font-semibold mt-4">{kb.name}</CardTitle>
                      <CardDescription className="text-sm text-[#999] line-clamp-2 mt-2">
                        {kb.description || '暂无描述'}
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="grid grid-cols-3 gap-3 pt-4 border-t border-[#e5e5e5]">
                        <div className="text-center">
                          <div className="text-2xl font-bold text-[#1a1a1a]">{kb.documentCount}</div>
                          <div className="text-[11px] text-[#999] uppercase tracking-wide mt-1">文档</div>
                        </div>
                        <div className="text-center border-l border-[#e5e5e5]">
                          <div className="text-2xl font-bold text-[#1a1a1a]">{(kb.vectorCount / 1000).toFixed(1)}k</div>
                          <div className="text-[11px] text-[#999] uppercase tracking-wide mt-1">向量</div>
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
          // KB Detail View with Documents
          <div className="space-y-6">
            {/* KB Info Cards */}
            <div className="grid grid-cols-4 gap-4">
              <Card className="bg-white border-[#e5e5e5] rounded-2xl">
                <CardContent className="p-5">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center">
                      <FileText className="w-5 h-5 text-blue-600" />
                    </div>
                    <div>
                      <div className="text-2xl font-bold text-[#1a1a1a]">{selectedKb?.documentCount}</div>
                      <div className="text-[12px] text-[#999]">文档总数</div>
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
                      <div className="text-[12px] text-[#999]">向量总数</div>
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
                      <div className="text-[12px] text-[#999]">权限级别</div>
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
                      <div className="text-[12px] text-[#999]">创建时间</div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Document Table */}
            <Card className="bg-white border-[#e5e5e5] rounded-2xl">
              <CardHeader className="pb-4 border-b border-[#e5e5e5]">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <FolderOpen className="w-5 h-5 text-[#999]" />
                    <CardTitle className="text-base font-semibold">文档列表</CardTitle>
                    <Badge variant="secondary" className="h-6 text-xs">
                      {filteredDocs.length}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-3">
                    {/* Category Filter */}
                    <Select value={filterCategory} onValueChange={setFilterCategory}>
                      <SelectTrigger className="w-[180px] h-9 rounded-lg">
                        <SelectValue placeholder="全部分类" />
                      </SelectTrigger>
                      <SelectContent className="rounded-xl">
                        <SelectItem value="all">全部分类</SelectItem>
                        <SelectItem value="">未分类</SelectItem>
                        {categories.filter(c => c).map(c => (
                          <SelectItem key={c} value={c}>{c}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {/* Document Search */}
                    <div className="relative">
                      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#999]" />
                      <Input
                        placeholder="搜索文档..."
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
                    <p className="text-sm font-medium text-[#1a1a1a]">暂无文档</p>
                    <p className="text-xs text-[#999] mt-1">上传文档到此知识库</p>
                    <Button
                      onClick={() => setIsUploadOpen(true)}
                      className="mt-4 bg-[#1a1a1a] text-white hover:bg-[#333] rounded-xl"
                    >
                      <UploadCloud className="w-4 h-4 mr-2" />
                      上传文档
                    </Button>
                  </div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow className="border-[#e5e5e5]">
                        <TableHead className="font-medium text-[#666]">文档名称</TableHead>
                        <TableHead className="font-medium text-[#666]">状态</TableHead>
                        <TableHead className="font-medium text-[#666]">大小</TableHead>
                        <TableHead className="font-medium text-[#666]">上传时间</TableHead>
                        <TableHead className="font-medium text-[#666] text-right">操作</TableHead>
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
                              {doc.status === 'completed' ? '已完成' :
                               doc.status === 'failed' ? '失败' :
                               doc.status === 'processing' ? '处理中' : doc.status}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-sm text-[#666]">
                            {formatBytes(doc.file_size)}
                          </TableCell>
                          <TableCell className="text-sm text-[#999]">
                            {new Date(doc.uploadedAt).toLocaleDateString('zh-CN')}
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

      {/* Create KB Dialog */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent className="rounded-2xl sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle className="text-xl font-bold">创建知识库</DialogTitle>
            <DialogDescription>
              定义一个新的隔离空间，用于文档存储和向量检索
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="name" className="font-semibold text-[#1a1a1a]">名称</Label>
              <Input
                id="name"
                className="rounded-xl bg-[#f9f9f9] border-[#e5e5e5] h-10"
                placeholder="例如：工程文档"
                value={newKbName}
                onChange={(e) => setNewKbName(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="desc" className="font-semibold text-[#1a1a1a]">描述</Label>
              <Input
                id="desc"
                className="rounded-xl bg-[#f9f9f9] border-[#e5e5e5] h-10"
                placeholder="可选描述"
                value={newKbDesc}
                onChange={(e) => setNewKbDesc(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="perms" className="font-semibold text-[#1a1a1a]">访问权限</Label>
              <Select value={newKbPerms} onValueChange={(val: any) => setNewKbPerms(val)}>
                <SelectTrigger className="rounded-xl bg-[#f9f9f9] border-[#e5e5e5] h-10">
                  <SelectValue placeholder="选择权限" />
                </SelectTrigger>
                <SelectContent className="rounded-xl">
                  <SelectItem value="read">只读（仅限检索）</SelectItem>
                  <SelectItem value="write">读/写（允许上传）</SelectItem>
                  <SelectItem value="admin">管理员（完全控制）</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" className="rounded-xl" onClick={() => setIsCreateOpen(false)}>
              取消
            </Button>
            <Button
              onClick={handleCreateKb}
              disabled={!newKbName}
              className="bg-[#1a1a1a] hover:bg-[#333] rounded-xl"
            >
              创建
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Upload Dialog */}
      <Dialog open={isUploadOpen} onOpenChange={setIsUploadOpen}>
        <DialogContent className="max-w-2xl rounded-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl font-bold flex items-center gap-2">
              <UploadCloud className="w-5 h-5" />
              上传文档到 "{selectedKb?.name}"
            </DialogTitle>
            <DialogDescription>
              支持 PDF, DOCX, XLSX, PPTX, TXT, MD, HTML, 图片 (Max 50MB)
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <div
              className="border-2 border-dashed border-[#e5e5e5] rounded-xl p-8 text-center hover:border-[#1a1a1a] transition-colors"
              onDragOver={(e) => { e.preventDefault(); }}
              onDrop={(e) => {
                e.preventDefault();
                setUploadFiles(Array.from(e.dataTransfer.files));
              }}
            >
              <UploadCloud className="w-10 h-10 text-[#ccc] mx-auto mb-3" />
              <p className="text-sm font-medium text-[#1a1a1a] mb-1">拖拽文件到此处，或点击选择</p>
              <p className="text-xs text-[#999] mb-4">单个文件最大 50MB</p>
              <Button
                variant="outline"
                className="rounded-xl"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
              >
                选择文件
              </Button>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                accept=".pdf,.docx,.xlsx,.pptx,.txt,.md,.html,.htm,.jpg,.jpeg,.png,.tiff,.tif,.bmp"
                onChange={(e) => setUploadFiles(Array.from(e.target.files || []))}
              />
            </div>
            {uploadFiles.length > 0 && (
              <div className="mt-4 space-y-2 max-h-48 overflow-y-auto">
                {uploadFiles.map((file, i) => (
                  <div key={i} className="flex items-center justify-between p-3 bg-[#f9f9f9] rounded-lg border border-[#e5e5e5]">
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                      <FileText className="w-4 h-4 text-[#999] shrink-0" />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-[#1a1a1a] truncate">{file.name}</p>
                        <p className="text-xs text-[#999]">{formatBytes(file.size)}</p>
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() => setUploadFiles(uploadFiles.filter((_, idx) => idx !== i))}
                    >
                      <X className="w-4 h-4" />
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
              取消
            </Button>
            <Button
              className="bg-[#1a1a1a] text-white hover:bg-[#333] rounded-xl"
              onClick={handleUpload}
              disabled={uploadFiles.length === 0 || uploading}
            >
              {uploading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  上传中...
                </>
              ) : (
                <>
                  <UploadCloud className="w-4 h-4 mr-2" />
                  上传 {uploadFiles.length} 个文件
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
