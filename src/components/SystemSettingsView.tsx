import { useState, useEffect } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Save, History, AlertCircle, Scissors, Search, ShieldCheck } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import { cn } from '@/lib/utils';
import { fetchSettings, updateSettings } from '@/lib/api-client';

// Convert backend nested settings to frontend flat draft
function apiToDraft(settings: Record<string, any>) {
  const c = settings.chunking || {};
  const r = settings.retrieval || {};
  const s = settings.security || {};
  return {
    chunkStrategy: c.strategy || 'semantic',
    chunkSize: String(c.chunkSize || 512),
    chunkOverlap: String(c.chunkOverlap || 50),
    separators: (c.separators || ['\\n\\n', '\\n', '.']).join(', '),
    topK: String(r.defaultTopK || 10),
    minScore: String(r.defaultMinScore ?? 0.6),
    enableRerank: r.enableRerank ?? true,
    rerankTopN: String(r.rerankTopN || 3),
    maxSize: `${s.maxUploadSizeMb || 50}MB`,
    formats: (s.allowedFormats || ['pdf', 'docx', 'txt', 'md', 'html']).join(','),
    rateLimit: `${s.rateLimitPerMinute || 100}/min`,
    timeout: String(s.searchTimeoutMs || 5000),
    logs: String(s.logRetentionDays || 30),
  };
}

// Convert frontend flat draft to backend nested format
function draftToApi(d: Record<string, any>) {
  return {
    chunking: {
      strategy: d.chunkStrategy,
      chunk_size: parseInt(String(d.chunkSize), 10) || 512,
      chunk_overlap: parseInt(String(d.chunkOverlap), 10) || 50,
      separators: d.separators.split(',').map((s: string) => s.trim()).filter(Boolean),
    },
    retrieval: {
      default_top_k: parseInt(String(d.topK), 10) || 10,
      default_min_score: parseFloat(String(d.minScore)) || 0.6,
      enable_rerank: d.enableRerank,
      rerank_top_n: parseInt(String(d.rerankTopN), 10) || 3,
    },
    security: {
      max_upload_size_mb: parseInt(String(d.maxSize), 10) || 50,
      allowed_formats: d.formats.split(',').map((s: string) => s.trim()).filter(Boolean),
      rate_limit_per_minute: parseInt(String(d.rateLimit), 10) || 100,
      search_timeout_ms: parseInt(String(d.timeout), 10) || 5000,
      log_retention_days: parseInt(String(d.logs), 10) || 30,
    },
  };
}

export function SystemSettingsView() {
  const { t } = useI18n();
  const [hasChanges, setHasChanges] = useState(false);
  const [isPublishOpen, setIsPublishOpen] = useState(false);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('chunk');
  const [settingsVersion, setSettingsVersion] = useState('v--');
  const [publishedAt, setPublishedAt] = useState('--');
  const [saving, setSaving] = useState(false);

  // Draft state
  const [draft, setDraft] = useState({
    chunkStrategy: 'semantic',
    chunkSize: '512',
    chunkOverlap: '50',
    separators: '\\n\\n, \\n, .',
    topK: '10',
    minScore: '0.6',
    enableRerank: true,
    rerankTopN: '3',
    maxSize: '50MB',
    formats: 'pdf,docx,txt,md,html',
    rateLimit: '100/min',
    timeout: '5000',
    logs: '30',
  });

  useEffect(() => {
    fetchSettings()
      .then((data) => {
        setDraft(apiToDraft(data.settings));
        setSettingsVersion(`v${data.version}`);
        if (data.publishedAt) {
          setPublishedAt(new Date(data.publishedAt).toLocaleString());
        }
      })
      .catch(() => {});
  }, []);

  const handleChange = (key: keyof typeof draft, value: any) => {
    setDraft((prev) => ({ ...prev, [key]: value }));
    setHasChanges(true);
  };

  const handlePublish = async () => {
    setSaving(true);
    try {
      const apiData = draftToApi(draft);
      const result = await updateSettings(apiData);
      setSettingsVersion(`v${result.version}`);
      if (result.publishedAt) {
        setPublishedAt(new Date(result.publishedAt).toLocaleString());
      }
      setHasChanges(false);
      toast.success('配置已发布');
    } catch (e: any) {
      toast.error(e.message || 'Failed to publish settings');
    } finally {
      setSaving(false);
      setIsPublishOpen(false);
    }
  };

  const categories = [
    { id: 'chunk', label: t('settings.group.chunk'), icon: Scissors },
    { id: 'retrieval', label: t('settings.group.retrieval'), icon: Search },
    { id: 'security', label: t('settings.group.security'), icon: ShieldCheck },
  ];

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-[#F8FAFC]">
      {/* Header */}
      <header className="h-20 px-8 bg-white/80 backdrop-blur-md border-b border-slate-200/60 flex items-center justify-between shrink-0 z-10">
        <div className="space-y-1">
          <h1 className="text-xl font-bold tracking-tight text-slate-900">{t('settings.title')}</h1>
          <p className="text-[13px] text-slate-500">{t('settings.desc')}</p>
        </div>
        
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-4 text-[11px] text-slate-500 font-mono tracking-tight font-semibold bg-slate-50 px-3 py-1.5 rounded-lg border border-slate-200/50 hidden md:flex">
            <span>{t('settings.status.version').replace('{v}', settingsVersion)}</span>
            <span className="w-1.5 h-1.5 rounded-full bg-slate-300"></span>
            <span>{t('settings.status.publishedAt').replace('{time}', publishedAt)}</span>
            {hasChanges && (
              <>
                <span className="w-1.5 h-1.5 rounded-full bg-orange-400"></span>
                <span className="text-orange-600">{t('settings.status.draft').replace('{n}', '1')}</span>
              </>
            )}
          </div>
          <div className="flex items-center gap-3">
            <Button variant="outline" size="sm" onClick={() => setIsHistoryOpen(true)} className="rounded-xl shadow-sm border-slate-200 hover:bg-slate-50 font-medium">
              <History className="w-4 h-4 mr-2" />
              {t('settings.action.history')}
            </Button>
            <Dialog open={isPublishOpen} onOpenChange={setIsPublishOpen}>
              <DialogTrigger render={
                <Button size="sm" className="bg-[#1677ff] hover:bg-[#0958d9] rounded-xl shadow-sm font-medium transition-colors" disabled={!hasChanges || saving}>
                  <Save className="w-4 h-4 mr-2" />
                  {saving ? 'Saving...' : t('settings.action.publish')}
                </Button>
              } />
              <DialogContent className="rounded-2xl">
                <DialogHeader>
                  <DialogTitle className="text-xl font-bold">{t('settings.alert.publishConfirm')}</DialogTitle>
                  <DialogDescription className="pt-2 text-slate-600">
                    <div className="flex items-start gap-2 bg-orange-50 p-4 rounded-xl text-orange-800 border border-orange-100">
                      <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
                      <span className="text-sm font-medium leading-relaxed">{t('settings.alert.publishDesc')}</span>
                    </div>
                  </DialogDescription>
                </DialogHeader>
                <DialogFooter className="mt-4">
                  <Button variant="ghost" onClick={() => setIsPublishOpen(false)} className="rounded-xl">Cancel</Button>
                  <Button className="bg-[#1677ff] hover:bg-[#0958d9] rounded-xl shadow-sm" onClick={handlePublish}>Confirm</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </header>

      {/* Main Content Two-Pane Layout */}
      <div className="flex-1 flex overflow-hidden max-w-7xl mx-auto w-full p-6 lg:p-8 gap-8">
        
        {/* Left Sidebar */}
        <div className="w-64 shrink-0 flex flex-col space-y-2">
          <nav className="flex-1 space-y-1">
            {categories.map((category) => {
              const isActive = activeTab === category.id;
              return (
                <button
                  key={category.id}
                  onClick={() => setActiveTab(category.id)}
                  className={cn(
                    "w-full flex items-center gap-3 px-4 py-3 text-sm rounded-xl transition-all duration-200 text-left font-medium",
                    isActive 
                      ? "bg-white text-[#1677ff] shadow-sm border border-slate-200/60" 
                      : "text-slate-600 hover:text-slate-900 hover:bg-slate-100/50 border border-transparent"
                  )}
                >
                  <category.icon className={cn("w-4.5 h-4.5", isActive ? "text-[#1677ff]" : "text-slate-400")} />
                  {category.label}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Right Content Area */}
        <div className="flex-1 overflow-y-auto bg-white border border-slate-200/60 rounded-3xl shadow-sm h-fit mb-8 relative">
          
          {/* Active Pane Content */}
          <div className="p-8 lg:p-10">
            {activeTab === 'chunk' && (
              <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-300">
                <div className="border-b border-slate-100/80 pb-4 mb-8">
                  <h2 className="text-xl font-bold tracking-tight text-slate-900">{t('settings.group.chunk')}</h2>
                  <p className="text-[13px] text-slate-500 mt-1">Define how documents are parsed and split into vectorizable tokens.</p>
                </div>
                <div className="grid gap-8">
                  <div className="space-y-3">
                    <Label className="font-semibold text-slate-700">{t('settings.chunk.strategy')}</Label>
                    <p className="text-[13px] text-slate-500 mb-2 leading-relaxed">{t('settings.chunk.strategyDesc')}</p>
                    <Select value={draft.chunkStrategy} onValueChange={(v) => handleChange('chunkStrategy', v)}>
                      <SelectTrigger className="w-full xl:w-1/2 rounded-xl h-11 border-slate-200 bg-slate-50/50 hover:bg-slate-50 transition-colors">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="rounded-xl">
                        <SelectItem value="semantic" className="rounded-lg">{t('settings.chunk.strategy.semantic')}</SelectItem>
                        <SelectItem value="fixed" className="rounded-lg">{t('settings.chunk.strategy.fixed')}</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="grid grid-cols-1 xl:grid-cols-2 gap-8 pt-6 border-t border-slate-100">
                    <div className="space-y-3">
                      <Label className="font-semibold text-slate-700">{t('settings.chunk.size')}</Label>
                      <p className="text-[13px] text-slate-500 mb-2 leading-relaxed">{t('settings.chunk.sizeDesc')}</p>
                      <Input value={draft.chunkSize} onChange={(e) => handleChange('chunkSize', e.target.value)} type="number" className="rounded-xl h-11 border-slate-200 bg-slate-50/50 focus-visible:bg-white" />
                    </div>
                    <div className="space-y-3">
                      <Label className="font-semibold text-slate-700">{t('settings.chunk.overlap')}</Label>
                      <p className="text-[13px] text-slate-500 mb-2 leading-relaxed">{t('settings.chunk.overlapDesc')}</p>
                      <Input value={draft.chunkOverlap} onChange={(e) => handleChange('chunkOverlap', e.target.value)} type="number" className="rounded-xl h-11 border-slate-200 bg-slate-50/50 focus-visible:bg-white" />
                    </div>
                  </div>

                  {draft.chunkStrategy === 'semantic' && (
                    <div className="space-y-3 pt-6 border-t border-slate-100">
                      <Label className="font-semibold text-slate-700">{t('settings.chunk.separators')}</Label>
                      <p className="text-[13px] text-slate-500 mb-2 leading-relaxed">{t('settings.chunk.separatorsDesc')}</p>
                      <Input value={draft.separators} onChange={(e) => handleChange('separators', e.target.value)} className="rounded-xl h-11 border-slate-200 bg-slate-50/50 focus-visible:bg-white font-mono text-sm" />
                    </div>
                  )}
                </div>
              </div>
            )}

            {activeTab === 'retrieval' && (
              <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-300">
                <div className="border-b border-slate-100/80 pb-4 mb-8">
                  <h2 className="text-xl font-bold tracking-tight text-slate-900">{t('settings.group.retrieval')}</h2>
                  <p className="text-[13px] text-slate-500 mt-1">Configure global default behavior for search and QA queries.</p>
                </div>
                <div className="grid gap-8">
                  <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
                    <div className="space-y-3">
                      <Label className="font-semibold text-slate-700">{t('settings.retrieval.topK')}</Label>
                      <p className="text-[13px] text-slate-500 mb-2 leading-relaxed">{t('settings.retrieval.topKDesc')}</p>
                      <Input value={draft.topK} onChange={(e) => handleChange('topK', e.target.value)} type="number" className="rounded-xl h-11 border-slate-200 bg-slate-50/50 focus-visible:bg-white" />
                    </div>
                    <div className="space-y-3">
                      <Label className="font-semibold text-slate-700">{t('settings.retrieval.minScore')}</Label>
                      <p className="text-[13px] text-slate-500 mb-2 leading-relaxed">{t('settings.retrieval.minScoreDesc')}</p>
                      <Input value={draft.minScore} onChange={(e) => handleChange('minScore', e.target.value)} type="number" step="0.1" className="rounded-xl h-11 border-slate-200 bg-slate-50/50 focus-visible:bg-white" />
                    </div>
                  </div>

                  <div className="pt-6 border-t border-slate-100 space-y-8">
                    <div className="flex items-center justify-between xl:w-1/2">
                      <div className="space-y-1">
                        <Label className="font-semibold text-slate-700">{t('settings.retrieval.rerank')}</Label>
                        <p className="text-[13px] text-slate-500 leading-relaxed">{t('settings.retrieval.rerankDesc')}</p>
                      </div>
                      <Switch checked={draft.enableRerank} onCheckedChange={(v) => handleChange('enableRerank', v)} />
                    </div>

                    {draft.enableRerank && (
                      <div className="space-y-3">
                        <Label className="font-semibold text-slate-700">{t('settings.retrieval.rerankTopN')}</Label>
                        <p className="text-[13px] text-slate-500 mb-2 leading-relaxed">{t('settings.retrieval.rerankTopNDesc')}</p>
                        <Input value={draft.rerankTopN} onChange={(e) => handleChange('rerankTopN', e.target.value)} type="number" className="rounded-xl h-11 border-slate-200 bg-slate-50/50 focus-visible:bg-white xl:w-[calc(50%-1rem)]" />
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'security' && (
              <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-300">
                <div className="border-b border-slate-100/80 pb-4 mb-8">
                  <h2 className="text-xl font-bold tracking-tight text-slate-900">{t('settings.group.security')}</h2>
                  <p className="text-[13px] text-slate-500 mt-1">Manage platform safeguards, file restrictions, and execution limits.</p>
                </div>
                <div className="grid gap-8">
                  <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
                    <div className="space-y-3">
                      <Label className="font-semibold text-slate-700">{t('settings.security.maxSize')}</Label>
                      <p className="text-[13px] text-slate-500 mb-2 leading-relaxed">{t('settings.security.maxSizeDesc')}</p>
                      <Input value={draft.maxSize} onChange={(e) => handleChange('maxSize', e.target.value)} className="rounded-xl h-11 border-slate-200 bg-slate-50/50 focus-visible:bg-white" />
                    </div>
                    <div className="space-y-3">
                      <Label className="font-semibold text-slate-700">{t('settings.security.rateLimit')}</Label>
                      <p className="text-[13px] text-slate-500 mb-2 leading-relaxed">{t('settings.security.rateLimitDesc')}</p>
                      <Input value={draft.rateLimit} onChange={(e) => handleChange('rateLimit', e.target.value)} className="rounded-xl h-11 border-slate-200 bg-slate-50/50 focus-visible:bg-white" />
                    </div>
                  </div>

                  <div className="space-y-3 pt-6 border-t border-slate-100">
                    <Label className="font-semibold text-slate-700">{t('settings.security.formats')}</Label>
                    <p className="text-[13px] text-slate-500 mb-2 leading-relaxed">{t('settings.security.formatsDesc')}</p>
                    <Input value={draft.formats} onChange={(e) => handleChange('formats', e.target.value)} className="rounded-xl h-11 border-slate-200 bg-slate-50/50 focus-visible:bg-white font-mono text-sm" />
                  </div>

                  <div className="grid grid-cols-1 xl:grid-cols-2 gap-8 pt-6 border-t border-slate-100">
                    <div className="space-y-3">
                      <Label className="font-semibold text-slate-700">{t('settings.security.timeout')}</Label>
                      <p className="text-[13px] text-slate-500 mb-2 leading-relaxed">{t('settings.security.timeoutDesc')}</p>
                      <Input value={draft.timeout} onChange={(e) => handleChange('timeout', e.target.value)} type="number" className="rounded-xl h-11 border-slate-200 bg-slate-50/50 focus-visible:bg-white" />
                    </div>
                    <div className="space-y-3">
                      <Label className="font-semibold text-slate-700">{t('settings.security.logs')}</Label>
                      <p className="text-[13px] text-slate-500 mb-2 leading-relaxed">{t('settings.security.logsDesc')}</p>
                      <Input value={draft.logs} onChange={(e) => handleChange('logs', e.target.value)} type="number" className="rounded-xl h-11 border-slate-200 bg-slate-50/50 focus-visible:bg-white" />
                    </div>
                  </div>
                </div>
              </div>
            )}
            
          </div>
        </div>
      </div>
    </div>
  );
}

