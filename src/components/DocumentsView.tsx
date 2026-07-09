import { useState, useEffect, useRef } from 'react';
import { useAppContext } from '@/lib/app-context';
import { uploadDoc, fetchDoc, updateDocument, fetchDocumentCategories } from '@/lib/api-client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { UploadCloud, Search, Trash2, RefreshCw, FileText, Database, Link as LinkIcon, AlertCircle, Tag, X, Eye, FolderTree } from 'lucide-react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useI18n } from '@/src/lib/i18n';
import { toast } from 'sonner';

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
  const [categories, setCategories] = useState<string[]>([]);
  const [previewDoc, setPreviewDoc] = useState<any>(null);
  const [editingTags, setEditingTags] = useState<string | null>(null);
  const [tagInput, setTagInput] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    // Load categories from API
    const kbParam = filterKb !== 'all' ? filterKb : undefined;
    fetchDocumentCategories(kbParam)
      .then(d => {
        setCategories(d.categories || []);
      })
      .catch(() => {});
  }, [filterKb, documents.length]);

  const filteredDocs = documents.filter(doc => {
    const matchesSearch = doc.name.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesKb = filterKb === 'all' || doc.kbId === filterKb;
    const matchesCat = filterCategory === 'all' || (doc.category || '') === filterCategory;
    return matchesSearch && matchesKb && matchesCat;
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

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed': return <Badge className="bg-emerald-50 text-emerald-700 border-0 text-[10px]">{t('doc.status.completed')}</Badge>;
      case 'processing': return <Badge className="bg-blue-50 text-blue-700 border-0 text-[10px]">{t('doc.status.processing')}</Badge>;
      case 'pending': return <Badge className="bg-slate-100 text-slate-700 border-0 text-[10px]">{t('doc.status.pending')}</Badge>;
      case 'failed': return <Badge className="bg-red-50 text-red-700 border-0 text-[10px]">{t('doc.status.failed')}</Badge>;
      default: return null;
    }
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden relative">
      <header className="h-20 px-8 bg-white/80 backdrop-blur-md border-b border-slate-200/60 flex items-center justify-between sticky top-0 z-10 shrink-0">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">{t('doc.title')}</h1>
          <p className="text-sm text-slate-500">{t('doc.desc')}</p>
        </div>
        <div className="flex gap-3">
          <Button variant="outline" className="gap-2 bg-white rounded-xl h-auto py-2.5 shadow-sm border-slate-200 hover:bg-slate-50">
            <LinkIcon className="w-4 h-4" />{t('doc.importUrl')}
          </Button>
          <Button className="bg-[#1677ff] hover:bg-[#0958d9] text-white gap-2 rounded-xl h-auto py-2.5 shadow-sm" onClick={() => fileInputRef.current?.click()} disabled={uploading}>
            <UploadCloud className="w-4 h-4" />{uploading ? t('doc.status.processing') : t('doc.upload')}
          </Button>
          <input type="file" multiple className="hidden" ref={fileInputRef} onChange={(e) => handleFileUpload(e.target.files)} />
        </div>
      </header>

      <div className="flex-1 overflow-y-auto p-8 lg:p-10">
        {/* Dropzone */}
        <div className={`mb-8 border-2 border-dashed rounded-3xl p-10 flex flex-col items-center justify-center transition-all ${isDragging ? 'border-blue-500 bg-blue-50/50' : 'border-slate-200 bg-white hover:bg-slate-50/50'}`}
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={(e) => { e.preventDefault(); setIsDragging(false); handleFileUpload(e.dataTransfer.files); }}>
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-50 to-indigo-50 border border-blue-100 flex items-center justify-center mb-5">
            <UploadCloud className="w-7 h-7 text-blue-600" />
          </div>
          <h3 className="text-lg font-bold text-slate-900 mb-1">{t('doc.dragDrop')}</h3>
          <p className="text-slate-500 text-sm mb-5">{t('doc.supports')}</p>
          <Button variant="outline" onClick={() => fileInputRef.current?.click()} className="rounded-xl bg-white shadow-sm">{t('doc.browse')}</Button>
        </div>

        {/* Filters Bar */}
        <div className="flex items-center gap-3 mb-6 flex-wrap">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4.5 h-4.5 text-slate-400" />
            <Input placeholder={t('doc.search')} className="pl-11 bg-white border-slate-200/60 shadow-sm p-4 rounded-xl h-12" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} />
          </div>
          <Select value={filterKb} onValueChange={(v) => { setFilterKb(v); setFilterCategory('all'); }}>
            <SelectTrigger className="w-[220px] bg-white border border-slate-200/60 shadow-sm rounded-xl h-12"><SelectValue placeholder={t('doc.allKb')} /></SelectTrigger>
            <SelectContent className="rounded-xl">
              <SelectItem value="all">{t('doc.allKb')}</SelectItem>
              {knowledgeBases.map(kb => (<SelectItem key={kb.id} value={kb.id}>{kb.name}</SelectItem>))}
            </SelectContent>
          </Select>
          <Select value={filterCategory} onValueChange={(v) => setFilterCategory(v)}>
            <SelectTrigger className="w-[200px] bg-white border border-slate-200/60 shadow-sm rounded-xl h-12">
              <FolderTree className="w-4 h-4 mr-2 text-slate-400" /><SelectValue placeholder={t('doc.allKb')} />
            </SelectTrigger>
            <SelectContent className="rounded-xl">
              <SelectItem value="all">{t('doc.allKb')}</SelectItem>
              <SelectItem value="">{t('doc.uncategorized')}</SelectItem>
              {categories.filter(c => c).map(c => (<SelectItem key={c} value={c}>{c}</SelectItem>))}
            </SelectContent>
          </Select>
        </div>

        {/* Document Table */}
        <div className="bg-white border border-slate-200/60 shadow-sm rounded-2xl overflow-hidden">
          <div className="overflow-auto">
            <Table>
              <TableHeader className="bg-slate-50/50 sticky top-0 z-10 border-b border-slate-200/60">
                <TableRow className="hover:bg-transparent">
                  <TableHead className="w-[350px] text-[11px] uppercase tracking-wider text-slate-500 font-semibold h-12">{t('doc.col.doc')}</TableHead>
                  <TableHead className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold">分类</TableHead>
                  <TableHead className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold">标签</TableHead>
                  <TableHead className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold">{t('doc.col.size')}</TableHead>
                  <TableHead className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold">{t('doc.col.status')}</TableHead>
                  <TableHead className="text-right text-[11px] uppercase tracking-wider text-slate-500 font-semibold">{t('doc.col.actions')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredDocs.length === 0 ? (
                  <TableRow><TableCell colSpan={6} className="h-32 text-center text-slate-500"><FileText className="w-8 h-8 text-slate-300 mb-3 mx-auto" /><p>{t('doc.empty')}</p></TableCell></TableRow>
                ) : (
                  filteredDocs.map((doc) => {
                    const kb = knowledgeBases.find(k => k.id === doc.kbId);
                    const docTags = doc.tags || [];
                    return (
                      <TableRow key={doc.id} className="group hover:bg-slate-50/50 transition-colors">
                        <TableCell className="font-medium border-b border-slate-100 py-3">
                          <div className="flex items-center gap-3">
                            <div className="w-9 h-9 rounded-lg bg-slate-50 border border-slate-200/60 flex items-center justify-center text-slate-500 shrink-0">
                              <FileText className="w-4.5 h-4.5" />
                            </div>
                            <div className="min-w-0">
                              <div className="text-slate-900 font-medium truncate max-w-[220px]">{doc.name}</div>
                              <div className="text-[10px] text-slate-400">{doc.format} · {formatBytes(doc.file_size)}</div>
                            </div>
                          </div>
                        </TableCell>
                        <TableCell className="border-b border-slate-100 py-3">
                          <Select value={doc.category || ''} onValueChange={(v) => handleSetCategory(doc.id, v)}>
                            <SelectTrigger className="h-7 text-xs border-0 bg-slate-50 rounded-lg px-2 w-[140px]">
                              <SelectValue placeholder="选择分类" />
                            </SelectTrigger>
                            <SelectContent className="rounded-xl">
                              <SelectItem value="">未分类</SelectItem>
                              {categories.filter(c => c).map(c => (<SelectItem key={c} value={c}>{c}</SelectItem>))}
                            </SelectContent>
                          </Select>
                        </TableCell>
                        <TableCell className="border-b border-slate-100 py-3">
                          <div className="flex items-center gap-1 flex-wrap max-w-[180px]">
                            {docTags.slice(0, 3).map(tag => (
                              <Badge key={tag} variant="secondary" className="text-[10px] rounded-md px-1.5 py-0">{tag}</Badge>
                            ))}
                            {docTags.length > 3 && <span className="text-[10px] text-slate-400">+{docTags.length - 3}</span>}
                            {editingTags === doc.id ? (
                              <div className="flex items-center gap-1 mt-1 w-full">
                                <Input value={tagInput} onChange={(e) => setTagInput(e.target.value)} placeholder="标签,逗号分隔" className="h-7 text-xs rounded-lg" autoFocus onKeyDown={(e) => e.key === 'Enter' && handleSaveTags(doc.id)} />
                                <Button size="sm" className="h-7 text-xs rounded-lg px-2" onClick={() => handleSaveTags(doc.id)}>保存</Button>
                                <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setEditingTags(null)}><X className="w-3 h-3" /></Button>
                              </div>
                            ) : (
                              <Button variant="ghost" size="sm" className="h-6 w-6 p-0 opacity-0 group-hover:opacity-100" onClick={() => { setEditingTags(doc.id); setTagInput((doc.tags || []).join(', ')); }}>
                                <Tag className="w-3 h-3" />
                              </Button>
                            )}
                          </div>
                        </TableCell>
                        <TableCell className="text-sm text-slate-500 border-b border-slate-100 py-3">{formatBytes(doc.file_size)}</TableCell>
                        <TableCell className="border-b border-slate-100 py-3">{getStatusBadge(doc.status)}</TableCell>
                        <TableCell className="text-right border-b border-slate-100 py-3">
                          <div className="flex items-center justify-end gap-1">
                            <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg" onClick={() => handleShowPreview(doc.id)}><Eye className="w-4 h-4 text-slate-400" /></Button>
                            <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg" onClick={() => deleteDocument(doc.id)}><Trash2 className="w-4 h-4 text-red-400" /></Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })
                )}
              </TableBody>
            </Table>
          </div>
        </div>
      </div>

      {/* Document Preview Dialog */}
      <Dialog open={!!previewDoc} onOpenChange={() => setPreviewDoc(null)}>
        <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto rounded-2xl">
          {previewDoc && (
            <>
              <DialogHeader>
                <DialogTitle className="text-xl font-bold">{previewDoc.name}</DialogTitle>
                <DialogDescription className="text-slate-500 space-y-2 pt-2">
                  <div className="flex flex-wrap gap-2 text-xs">
                    <Badge variant="outline" className="rounded-lg">{previewDoc.format}</Badge>
                    <Badge variant="outline" className="rounded-lg">{formatBytes(previewDoc.file_size)}</Badge>
                    <Badge variant="outline" className="rounded-lg">{previewDoc.status}</Badge>
                    <Badge variant="outline" className="rounded-lg">{previewDoc.chunk_count || 0} chunks</Badge>
                    {previewDoc.category && <Badge className="rounded-lg bg-blue-50 text-blue-700">{previewDoc.category}</Badge>}
                  </div>
                  {(previewDoc.tags || []).length > 0 && (
                    <div className="flex gap-1 flex-wrap">
                      {(previewDoc.tags || []).map((t: string) => (
                        <Badge key={t} variant="secondary" className="text-[10px] rounded-md">{t}</Badge>
                      ))}
                    </div>
                  )}
                </DialogDescription>
              </DialogHeader>
              <div className="mt-4 space-y-4">
                <h4 className="text-sm font-semibold text-slate-700">内容预览</h4>
                <div className="bg-slate-50 rounded-xl p-4 max-h-[400px] overflow-y-auto">
                  {previewDoc.preview_text ? (
                    <pre className="text-sm text-slate-700 whitespace-pre-wrap font-sans leading-relaxed">{previewDoc.preview_text}</pre>
                  ) : (
                    <p className="text-sm text-slate-400 text-center py-8">无可预览的文本内容</p>
                  )}
                </div>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
