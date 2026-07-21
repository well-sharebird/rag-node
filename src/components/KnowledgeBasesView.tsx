import { useState, useEffect } from 'react';
import { useAppContext } from '@/lib/app-context';
import { toast } from 'sonner';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Plus, Search, Database, FileText, Clock, MoreVertical, Trash2, Settings, ChevronLeft, Upload, Eye, Download, RefreshCw, Loader2 } from 'lucide-react';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { useI18n } from '@/src/lib/i18n';
import { fetchDocs, deleteDoc, DocData as DocType } from '@/lib/api-client';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Switch } from '@/components/ui/switch';
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

export function KnowledgeBasesView() {
  const { knowledgeBases, addKnowledgeBase, deleteKnowledgeBase, setCurrentKbId } = useAppContext();
  const { t } = useI18n();
  const [searchTerm, setSearchTerm] = useState('');
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [viewingKb, setViewingKb] = useState<KBDetail | null>(null);
  const [kbDocuments, setKbDocuments] = useState<DocType[]>([]);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [docSearchTerm, setDocSearchTerm] = useState('');
  const [selectedDoc, setSelectedDoc] = useState<DocType | null>(null);
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);

  const [newKbName, setNewKbName] = useState('');
  const [newKbDesc, setNewKbDesc] = useState('');
  const [newKbPerms, setNewKbPerms] = useState<'read'|'write'|'admin'>('write');

  const filteredKbs = knowledgeBases.filter(kb =>
    kb.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    kb.description.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleKbClick = (kb: typeof knowledgeBases[0]) => {
    setViewingKb({
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
    } catch (e: any) {
      console.error('Failed to load documents:', e);
      toast.error('加载文档列表失败');
    } finally {
      setLoadingDocs(false);
    }
  };

  const handleDeleteDoc = async (docId: string) => {
    if (!window.confirm('确定要删除此文档吗？')) return;
    try {
      await deleteDoc(docId);
      toast.success('文档已删除');
      if (viewingKb) loadDocuments(viewingKb.id);
    } catch (e: any) {
      toast.error(`删除失败：${e.message}`);
    }
  };

  const handlePreviewDoc = (doc: DocType) => {
    setSelectedDoc(doc);
    setIsPreviewOpen(true);
  };

  const filteredDocs = kbDocuments.filter(doc =>
    doc.name.toLowerCase().includes(docSearchTerm.toLowerCase())
  );

  const handleCreate = () => {
    if (!newKbName) return;
    addKnowledgeBase({
      name: newKbName,
      description: newKbDesc,
      permissions: newKbPerms
    });
    setIsCreateOpen(false);
    setNewKbName('');
    setNewKbDesc('');
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden relative">
      <header className="h-[52px] px-5 bg-white flex items-center justify-between shrink-0" style={{ borderBottom: '0.5px solid #e2e1dd' }}>
        <div className="flex items-center gap-3">
          {viewingKb && (
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 -ml-2"
              onClick={() => setViewingKb(null)}
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
          )}
          <div className="flex items-baseline gap-3">
            <h1 className="text-[15px] font-medium text-[#1a1a1a]">
              {viewingKb ? viewingKb.name : t('kb.title')}
            </h1>
            {!viewingKb && (
              <span className="text-[11px] text-[#9b9b9b] hidden sm:inline">{t('kb.desc')}</span>
            )}
          </div>
        </div>

        {!viewingKb ? (
          <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
            <DialogTrigger render={
              <Button className="bg-slate-900 text-white px-5 py-2.5 rounded-xl text-sm font-medium hover:bg-slate-800 shadow-sm gap-2 transition-all">
                <Plus className="w-4 h-4" />
                {t('kb.new')}
              </Button>
            } />
            <DialogContent className="rounded-2xl sm:max-w-[425px]">
              <DialogHeader>
                <DialogTitle className="text-xl font-bold">{t('kb.create.title')}</DialogTitle>
                <DialogDescription>{t('kb.create.desc')}</DialogDescription>
              </DialogHeader>
              <div className="space-y-5 py-4">
                <div className="space-y-2">
                  <Label htmlFor="name" className="font-semibold text-slate-700">{t('kb.create.name')}</Label>
                  <Input id="name" className="rounded-xl bg-slate-50 border-slate-200 focus-visible:ring-slate-400 h-10" placeholder={t('kb.create.namePlaceholder')} value={newKbName} onChange={(e) => setNewKbName(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="desc" className="font-semibold text-slate-700">{t('kb.create.description')}</Label>
                  <Input id="desc" className="rounded-xl bg-slate-50 border-slate-200 focus-visible:ring-slate-400 h-10" placeholder={t('kb.create.descPlaceholder')} value={newKbDesc} onChange={(e) => setNewKbDesc(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="perms" className="font-semibold text-slate-700">{t('kb.create.access')}</Label>
                  <Select value={newKbPerms} onValueChange={(val: any) => setNewKbPerms(val)}>
                    <SelectTrigger className="rounded-xl bg-slate-50 border-slate-200 focus-visible:ring-slate-400 h-10">
                      <SelectValue placeholder={t('kb.create.selectPerms')} />
                    </SelectTrigger>
                    <SelectContent className="rounded-xl">
                      <SelectItem value="read">{t('kb.create.readOnly')}</SelectItem>
                      <SelectItem value="write">{t('kb.create.readWrite')}</SelectItem>
                      <SelectItem value="admin">{t('kb.create.admin')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <DialogFooter>
                <Button variant="ghost" className="rounded-xl" onClick={() => setIsCreateOpen(false)}>{t('kb.cancel')}</Button>
                <Button onClick={handleCreate} disabled={!newKbName} className="bg-[#534ab7] hover:bg-[#4438a0] rounded-xl">{t('kb.create')}</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        ) : (
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" className="rounded-xl" onClick={() => loadDocuments(viewingKb.id)}>
              <RefreshCw className={`w-4 h-4 mr-1 ${loadingDocs ? 'animate-spin' : ''}`} /> 刷新
            </Button>
          </div>
        )}
      </header>

      <div className="flex-1 overflow-y-auto p-8 lg:p-10 bg-[#f7f7f5]">
        {!viewingKb ? (
          <>
            <div className="flex items-center gap-4 mb-8">
              <div className="relative flex-1 max-w-md">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4.5 h-4.5 text-slate-400" />
                <Input
                  placeholder={t('kb.search')}
                  className="pl-11 bg-white border-slate-200/60 shadow-sm rounded-xl font-medium text-slate-700 h-12 focus-visible:ring-slate-300 transition-all"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {filteredKbs.map((kb) => (
                <Card
                  key={kb.id}
                  className="bg-white border-slate-200/60 shadow-sm rounded-2xl hover:shadow-xl hover:shadow-slate-200/40 hover:-translate-y-1 transition-all duration-300 group relative overflow-hidden flex flex-col cursor-pointer"
                  onClick={() => handleKbClick(kb)}
                >
                  <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-blue-500 to-indigo-500 opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
                  <CardHeader className="pb-4 pt-6 flex flex-row items-start justify-between space-y-0 relative z-10">
                    <div className="flex gap-4">
                      <div className="w-12 h-12 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center shrink-0">
                        <Database className="w-6 h-6" />
                      </div>
                      <div>
                        <CardTitle className="text-lg font-bold tracking-tight text-slate-900 mt-0.5">{kb.name}</CardTitle>
                        <div className="text-sm text-slate-500 mt-1 line-clamp-2 leading-relaxed">{kb.description || t('kb.noDescription')}</div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <DropdownMenu>
                        <DropdownMenuTrigger render={
                          <Button variant="ghost" size="icon" className="h-8 w-8 -mt-1 -mr-2 opacity-0 group-hover:opacity-100 transition-opacity rounded-lg hover:bg-slate-100" onClick={(e) => e.stopPropagation()}>
                            <MoreVertical className="w-4 h-4 text-slate-500" />
                          </Button>
                        } />
                        <DropdownMenuContent align="end" className="rounded-xl">
                          <DropdownMenuItem className="rounded-lg cursor-pointer" onClick={(e) => { e.stopPropagation(); handleKbClick(kb); }}>
                            <Eye className="w-4 h-4 mr-2" /> 查看详情
                          </DropdownMenuItem>
                          <DropdownMenuItem className="text-red-600 rounded-lg cursor-pointer" onClick={(e) => { e.stopPropagation(); deleteKnowledgeBase(kb.id); }}>
                            <Trash2 className="w-4 h-4 mr-2" /> {t('kb.delete')}
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  </CardHeader>
                  <CardContent className="pt-2 pb-6 mt-auto">
                    <div className="grid grid-cols-3 gap-4 border-t border-slate-100/80 pt-5">
                      <div className="text-center border-r border-slate-100">
                        <p className="text-[11px] text-slate-400 mb-1 font-semibold uppercase tracking-wider">{t('kb.docs')}</p>
                        <p className="font-bold text-slate-800">{kb.documentCount}</p>
                      </div>
                      <div className="text-center border-r border-slate-100">
                        <p className="text-[11px] text-slate-400 mb-1 font-semibold uppercase tracking-wider">{t('kb.vectors')}</p>
                        <p className="font-bold text-slate-800">{kb.vectorCount.toLocaleString()}</p>
                      </div>
                      <div className="text-center">
                        <p className="text-[11px] text-slate-400 mb-1 font-semibold uppercase tracking-wider">{t('kb.perms')}</p>
                        <p className="font-bold text-slate-800 uppercase text-[11px] mt-1.5 tracking-wider">{kb.permissions}</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>

            {filteredKbs.length === 0 && (
              <div className="text-center py-24 bg-white/50 backdrop-blur-sm rounded-3xl border border-slate-200/60 shadow-sm mt-8">
                <div className="w-20 h-20 rounded-2xl bg-white shadow-sm border border-slate-100 flex items-center justify-center mx-auto mb-6">
                  <Database className="w-10 h-10 text-slate-300" />
                </div>
                <h3 className="text-xl font-bold text-slate-900 mb-2 tracking-tight">{t('kb.empty.title')}</h3>
                <p className="text-slate-500 text-sm max-w-sm mx-auto">{t('kb.empty.desc')}</p>
              </div>
            )}
          </>
        ) : (
          // KB Detail View with Document List
          <div className="space-y-6">
            {/* KB Info Card */}
            <Card className="bg-white border-slate-200/60 shadow-sm rounded-2xl">
              <CardContent className="p-6">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-4">
                    <div className="w-14 h-14 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center">
                      <Database className="w-7 h-7" />
                    </div>
                    <div>
                      <h2 className="text-xl font-bold text-slate-900">{viewingKb.name}</h2>
                      <p className="text-sm text-slate-500 mt-1">{viewingKb.description || t('kb.noDescription')}</p>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" className="rounded-xl" onClick={() => { setCurrentKbId(viewingKb.id); setViewingKb(null); }}>
                      设为当前知识库
                    </Button>
                    <Button variant="outline" size="sm" className="rounded-xl text-red-600 border-red-200 hover:bg-red-50" onClick={async () => { if (await window.confirm('确定要删除此知识库吗？')) { deleteKnowledgeBase(viewingKb.id); toast.success('知识库已删除'); setViewingKb(null); }}}>
                      <Trash2 className="w-4 h-4 mr-1" /> 删除
                    </Button>
                  </div>
                </div>
                <div className="grid grid-cols-4 gap-4 mt-6">
                  <div className="text-center p-4 bg-slate-50 rounded-xl">
                    <p className="text-xs text-slate-400 uppercase tracking-wider font-semibold">{t('kb.docs')}</p>
                    <p className="text-2xl font-bold text-slate-900 mt-1">{viewingKb.documentCount}</p>
                  </div>
                  <div className="text-center p-4 bg-slate-50 rounded-xl">
                    <p className="text-xs text-slate-400 uppercase tracking-wider font-semibold">{t('kb.vectors')}</p>
                    <p className="text-2xl font-bold text-slate-900 mt-1">{viewingKb.vectorCount.toLocaleString()}</p>
                  </div>
                  <div className="text-center p-4 bg-slate-50 rounded-xl">
                    <p className="text-xs text-slate-400 uppercase tracking-wider font-semibold">{t('kb.perms')}</p>
                    <Badge className="mt-2 text-xs rounded-lg">{viewingKb.permissions}</Badge>
                  </div>
                  <div className="text-center p-4 bg-slate-50 rounded-xl">
                    <p className="text-xs text-slate-400 uppercase tracking-wider font-semibold">创建时间</p>
                    <p className="text-sm font-medium text-slate-700 mt-2">{new Date(viewingKb.createdAt).toLocaleDateString('zh-CN')}</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Document List */}
            <Card className="bg-white border-slate-200/60 shadow-sm rounded-2xl">
              <CardHeader className="pb-4 border-b border-slate-100">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <FileText className="w-5 h-5 text-slate-400" />
                    <CardTitle className="text-lg font-bold">文档列表</CardTitle>
                    <Badge variant="secondary" className="rounded-lg">{filteredDocs.length}</Badge>
                  </div>
                  <div className="relative w-64">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                    <Input
                      placeholder="搜索文档..."
                      className="pl-9 h-9 rounded-xl bg-slate-50 border-slate-200 text-sm"
                      value={docSearchTerm}
                      onChange={(e) => setDocSearchTerm(e.target.value)}
                    />
                  </div>
                </div>
              </CardHeader>
              <CardContent className="p-0">
                {loadingDocs ? (
                  <div className="flex items-center justify-center py-12">
                    <Loader2 className="w-6 h-6 animate-spin text-[#534ab7]" />
                  </div>
                ) : filteredDocs.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-12 text-center">
                    <FileText className="w-12 h-12 text-slate-300 mb-3" />
                    <p className="text-sm font-medium text-slate-700">暂无文档</p>
                    <p className="text-xs text-slate-500 mt-1">上传文档到此知识库开始使用</p>
                  </div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow className="border-slate-100">
                        <TableHead className="font-semibold text-slate-600">文档名称</TableHead>
                        <TableHead className="font-semibold text-slate-600">状态</TableHead>
                        <TableHead className="font-semibold text-slate-600">分块数</TableHead>
                        <TableHead className="font-semibold text-slate-600">上传时间</TableHead>
                        <TableHead className="font-semibold text-slate-600 text-right">操作</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filteredDocs.map((doc) => (
                        <TableRow key={doc.id} className="border-slate-100 hover:bg-slate-50/50">
                          <TableCell className="font-medium">
                            <div className="flex items-center gap-2">
                              <FileText className="w-4 h-4 text-slate-400" />
                              <span className="truncate max-w-xs">{doc.name}</span>
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
                          <TableCell className="text-slate-600">{doc.size || '-'}</TableCell>
                          <TableCell className="text-slate-600 text-sm">{new Date(doc.uploadedAt).toLocaleDateString('zh-CN')}</TableCell>
                          <TableCell className="text-right">
                            <div className="flex items-center justify-end gap-1">
                              <Button variant="ghost" size="sm" className="h-8" onClick={() => handlePreviewDoc(doc)}>
                                <Eye className="w-4 h-4" />
                              </Button>
                              <Button variant="ghost" size="sm" className="h-8 text-red-600 hover:bg-red-50" onClick={() => handleDeleteDoc(doc.id)}>
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

        {/* Document Preview Dialog */}
        <Dialog open={isPreviewOpen} onOpenChange={setIsPreviewOpen}>
          <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto rounded-2xl">
            <DialogHeader>
              <DialogTitle className="text-xl font-bold flex items-center gap-2">
                <FileText className="w-5 h-5" />
                文档详情
              </DialogTitle>
            </DialogHeader>
            {selectedDoc && (
              <div className="space-y-4 py-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <Label className="text-xs text-slate-500">文档名称</Label>
                    <p className="text-sm font-medium">{selectedDoc.name}</p>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs text-slate-500">文件格式</Label>
                    <p className="text-sm font-medium uppercase">{selectedDoc.format}</p>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs text-slate-500">文件大小</Label>
                    <p className="text-sm font-medium">{(selectedDoc.size / 1024).toFixed(2)} KB</p>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs text-slate-500">文件大小</Label>
                    <p className="text-sm font-medium">{selectedDoc.size} bytes</p>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs text-slate-500">状态</Label>
                    <Badge className={cn(
                      "text-xs rounded-lg",
                      selectedDoc.status === 'completed' ? 'bg-green-50 text-green-600' :
                      selectedDoc.status === 'failed' ? 'bg-red-50 text-red-600' :
                      'bg-slate-100 text-slate-500'
                    )}>
                      {selectedDoc.status}
                    </Badge>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs text-slate-500">上传时间</Label>
                    <p className="text-sm font-medium">{new Date(selectedDoc.uploadedAt).toLocaleString('zh-CN')}</p>
                  </div>
                </div>
                {selectedDoc.errorMessage && (
                  <div className="space-y-1">
                    <Label className="text-xs text-slate-500">错误信息</Label>
                    <p className="text-sm text-red-600 bg-red-50 p-3 rounded-lg">{selectedDoc.errorMessage}</p>
                  </div>
                )}
                <div className="space-y-1">
                  <Label className="text-xs text-slate-500">分类</Label>
                  <p className="text-sm">{selectedDoc.category || '-'}</p>
                </div>
                {selectedDoc.tags && selectedDoc.tags.length > 0 && (
                  <div className="space-y-1">
                    <Label className="text-xs text-slate-500">标签</Label>
                    <div className="flex flex-wrap gap-2">
                      {selectedDoc.tags.map((tag: string, i: number) => (
                        <Badge key={i} variant="secondary" className="rounded-lg">{tag}</Badge>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
            <DialogFooter>
              <Button variant="outline" className="rounded-xl" onClick={() => setIsPreviewOpen(false)}>关闭</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
}
