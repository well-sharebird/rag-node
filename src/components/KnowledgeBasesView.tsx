import { useState } from 'react';
import { useAppContext } from '@/lib/app-context';
import { toast } from 'sonner';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Plus, Search, Database, FileText, Clock, MoreVertical, Trash2, Settings } from 'lucide-react';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { useI18n } from '@/src/lib/i18n';

export function KnowledgeBasesView() {
  const { knowledgeBases, addKnowledgeBase, deleteKnowledgeBase, setCurrentKbId } = useAppContext();
  const { t } = useI18n();
  const [searchTerm, setSearchTerm] = useState('');
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  
  const [newKbName, setNewKbName] = useState('');
  const [newKbDesc, setNewKbDesc] = useState('');
  const [newKbPerms, setNewKbPerms] = useState<'read'|'write'|'admin'>('write');
  const [detailKb, setDetailKb] = useState<typeof knowledgeBases[0] | null>(null);

  const filteredKbs = knowledgeBases.filter(kb => 
    kb.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    kb.description.toLowerCase().includes(searchTerm.toLowerCase())
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
      <header className="h-20 px-8 bg-white/80 backdrop-blur-md border-b border-slate-200/60 flex items-center justify-between sticky top-0 z-10">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">{t('kb.title')}</h1>
          <p className="text-sm text-slate-500">{t('kb.desc')}</p>
        </div>
        
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
              <DialogDescription>
                {t('kb.create.desc')}
              </DialogDescription>
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
              <Button onClick={handleCreate} disabled={!newKbName} className="bg-[#1677ff] hover:bg-[#0958d9] rounded-xl">{t('kb.create')}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </header>

      <div className="flex-1 overflow-y-auto p-8 lg:p-10">
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
            <Card key={kb.id} className="bg-white border-slate-200/60 shadow-sm rounded-2xl hover:shadow-xl hover:shadow-slate-200/40 hover:-translate-y-1 transition-all duration-300 group relative overflow-hidden flex flex-col">
              <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-blue-500 to-indigo-500 opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
              <CardHeader className="pb-4 pt-6 flex flex-row items-start justify-between space-y-0 relative z-10">
                <div className="flex gap-4">
                  <div className="w-12 h-12 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center shrink-0">
                    <Database className="w-6 h-6" />
                  </div>
                  <div>
                    <CardTitle className="text-lg font-bold tracking-tight text-slate-900 mt-0.5">
                      {kb.name}
                    </CardTitle>
                    <div className="text-sm text-slate-500 mt-1 line-clamp-2 leading-relaxed">{kb.description || t('kb.noDescription')}</div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <DropdownMenu>
                    <DropdownMenuTrigger render={
                      <Button variant="ghost" size="icon" className="h-8 w-8 -mt-1 -mr-2 opacity-0 group-hover:opacity-100 transition-opacity rounded-lg hover:bg-slate-100">
                        <MoreVertical className="w-4 h-4 text-slate-500" />
                      </Button>
                    } />
                    <DropdownMenuContent align="end" className="rounded-xl">
                      <DropdownMenuItem className="rounded-lg cursor-pointer" onClick={() => setDetailKb(kb)}>
                        <Settings className="w-4 h-4 mr-2" /> {t('kb.settings')}
                      </DropdownMenuItem>
                      <DropdownMenuItem className="text-red-600 rounded-lg cursor-pointer" onClick={() => deleteKnowledgeBase(kb.id)}>
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

        {/* KB Detail Dialog */}
        <Dialog open={!!detailKb} onOpenChange={() => setDetailKb(null)}>
          <DialogContent className="max-w-2xl rounded-2xl">
            {detailKb && (
              <>
                <DialogHeader>
                  <div className="flex items-center gap-4 mb-2">
                    <div className="w-14 h-14 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center">
                      <Database className="w-7 h-7" />
                    </div>
                    <div>
                      <DialogTitle className="text-xl font-bold">{detailKb.name}</DialogTitle>
                      <DialogDescription className="text-slate-500">{detailKb.description || t('kb.noDescription')}</DialogDescription>
                    </div>
                  </div>
                </DialogHeader>
                <div className="py-4 space-y-6">
                  <div className="grid grid-cols-4 gap-4">
                    <Card className="rounded-xl border-slate-200/60">
                      <CardContent className="p-4 text-center">
                        <p className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">{t('kb.docs')}</p>
                        <p className="text-2xl font-bold text-slate-900 mt-1">{detailKb.documentCount}</p>
                      </CardContent>
                    </Card>
                    <Card className="rounded-xl border-slate-200/60">
                      <CardContent className="p-4 text-center">
                        <p className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">{t('kb.vectors')}</p>
                        <p className="text-2xl font-bold text-slate-900 mt-1">{detailKb.vectorCount.toLocaleString()}</p>
                      </CardContent>
                    </Card>
                    <Card className="rounded-xl border-slate-200/60">
                      <CardContent className="p-4 text-center">
                        <p className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">{t('kb.perms')}</p>
                        <Badge className="mt-1 text-xs rounded-lg">{detailKb.permissions}</Badge>
                      </CardContent>
                    </Card>
                    <Card className="rounded-xl border-slate-200/60">
                      <CardContent className="p-4 text-center">
                        <p className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">{t('kb.active')}</p>
                        <div className="flex items-center justify-center gap-1.5 mt-1">
                          <div className="w-2 h-2 rounded-full bg-emerald-500"></div>
                          <Badge className="text-xs rounded-lg bg-emerald-50 text-emerald-700">Active</Badge>
                        </div>
                      </CardContent>
                    </Card>
                  </div>
                  <div className="space-y-2">
                    <Label className="text-sm font-semibold text-slate-700">知识库 ID</Label>
                    <p className="text-xs font-mono text-slate-500 bg-slate-50 rounded-lg p-2">{detailKb.id}</p>
                  </div>
                  <div className="space-y-2">
                    <Label className="text-sm font-semibold text-slate-700">操作</Label>
                    <div className="flex gap-2">
                      <Button variant="outline" className="rounded-xl text-sm" onClick={() => { setCurrentKbId(detailKb.id); setDetailKb(null); }}>
                        设为当前知识库
                      </Button>
                      <Button variant="outline" className="rounded-xl text-sm text-red-600 border-red-200 hover:bg-red-50" onClick={async () => { if (await window.confirm('确定要删除此知识库吗？')) { deleteKnowledgeBase(detailKb.id); toast.success('知识库已删除'); setDetailKb(null); }}}>
                        <Trash2 className="w-4 h-4 mr-1" /> 删除
                      </Button>
                    </div>
                  </div>
                </div>
              </>
            )}
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
}
