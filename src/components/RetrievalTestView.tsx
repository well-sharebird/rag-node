import { useState, useRef, useEffect } from 'react';
import { useAppContext } from '@/lib/app-context';
import { searchChunks, fetchSearchHistory } from '@/lib/api-client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Search, Send, Settings2, Clock, Copy, AlignLeft, BookOpen, ChevronRight, AlertCircle, History } from 'lucide-react';
import { SearchResult } from '@/src/types';
import { Badge } from '@/components/ui/badge';
import { useI18n } from '@/src/lib/i18n';

export function RetrievalTestView() {
  const { knowledgeBases } = useAppContext();
  const { t } = useI18n();
  const [query, setQuery] = useState('');
  const [selectedKb, setSelectedKb] = useState<string>('');
  
  // Search parameters
  const [topK, setTopK] = useState([5]);
  const [minScore, setMinScore] = useState([0.7]);
  const [enableRerank, setEnableRerank] = useState(false);
  const [enableHybrid, setEnableHybrid] = useState(false);
  
  const [isSearching, setIsSearching] = useState(false);
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [searchTime, setSearchTime] = useState(0);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [historyItems, setHistoryItems] = useState<any[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  const loadHistory = () => {
    setShowHistory(!showHistory);
    fetchSearchHistory(10).then(d => setHistoryItems(d.items)).catch(() => {});
  };

  useEffect(() => {
    fetchSearchHistory(10).then(d => setHistoryItems(d.items)).catch(() => {});
    return () => { if (abortRef.current) abortRef.current.abort(); };
  }, []);

  const handleSearch = async () => {
    if (!query || !selectedKb) return;

    if (abortRef.current) abortRef.current.abort();
    abortRef.current = new AbortController();

    setIsSearching(true);
    setResults(null);
    setSearchError(null);

    try {
      const response = await searchChunks({
        kbId: selectedKb,
        query,
        topK: topK[0],
        minScore: minScore[0],
        enableHybrid: enableHybrid,
        enableRerank: enableRerank,
      });

      const mapped = response.results.map((r: any) => ({
        chunk_id: r.chunk_id || r.chunkId,
        content: r.content,
        score: r.score,
        metadata: {
          doc_name: r.metadata?.doc_name || r.metadata?.docName || '',
          doc_id: r.metadata?.doc_id || r.metadata?.docId || '',
          page: r.metadata?.page,
          chapter: r.metadata?.chapter,
        },
      })) as SearchResult[];

      setResults(mapped);
      setSearchTime(response.searchTimeMs);
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        setSearchError(e.message || 'Search failed');
      }
    } finally {
      setIsSearching(false);
    }
  };

  const getScoreColor = (score: number) => {
    if (score >= 0.9) return 'bg-emerald-500';
    if (score >= 0.7) return 'bg-blue-500';
    if (score >= 0.5) return 'bg-amber-500';
    return 'bg-red-500';
  };

  return (
    <div className="flex-1 overflow-hidden flex flex-col md:flex-row p-6 lg:p-8 gap-6 lg:gap-8 bg-[#F8FAFC]">
      {/* Parameters Panel */}
      <div className="w-full md:w-80 bg-white/80 backdrop-blur-md border border-slate-200/60 rounded-3xl overflow-y-auto flex flex-col shadow-sm">
        <div className="p-6 border-b border-slate-100 flex items-center gap-2">
          <Settings2 className="w-4 h-4 text-indigo-500" />
          <h3 className="text-sm font-bold tracking-wide uppercase text-slate-900">{t('retrieval.params')}</h3>
        </div>
        
        <div className="p-6 space-y-8 flex-1">
          <div className="space-y-3">
            <Label className="text-[11px] uppercase tracking-wider text-slate-400 font-bold px-1">{t('retrieval.targetKb')}</Label>
            <Select value={selectedKb} onValueChange={setSelectedKb}>
              <SelectTrigger className="rounded-xl border-slate-200 h-12 shadow-sm bg-slate-50/50">
                <SelectValue placeholder={t('retrieval.selectKb')} />
              </SelectTrigger>
              <SelectContent className="rounded-xl shadow-lg border-slate-200/60">
                {knowledgeBases.map(kb => (
                  <SelectItem key={kb.id} value={kb.id} className="rounded-lg">{kb.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          
          <div className="space-y-5">
            <div className="flex justify-between items-center px-1">
              <Label className="text-[11px] uppercase tracking-wider text-slate-400 font-bold">{t('retrieval.topK')}</Label>
              <span className="font-mono text-indigo-600 font-bold bg-indigo-50 px-2 py-0.5 rounded-md text-xs">{topK[0]}</span>
            </div>
            <Slider max={20} min={1} step={1} value={topK} onValueChange={(v: number[]) => setTopK(v)} className="py-2" />
          </div>

          <div className="space-y-5">
            <div className="flex justify-between items-center px-1">
              <Label className="text-[11px] uppercase tracking-wider text-slate-400 font-bold">{t('retrieval.minScore')}</Label>
              <span className="font-mono text-indigo-600 font-bold bg-indigo-50 px-2 py-0.5 rounded-md text-xs">{minScore[0]}</span>
            </div>
            <Slider max={1} min={0} step={0.05} value={minScore} onValueChange={(v: number[]) => setMinScore(v)} className="py-2" />
          </div>

          <div className="space-y-5 pt-8 border-t border-slate-100">
            <div className="flex items-center justify-between px-1">
              <div className="space-y-1">
                <Label className="text-sm font-semibold text-slate-800">{t('retrieval.hybrid')}</Label>
                <p className="text-[11px] text-slate-400 uppercase tracking-widest font-medium">{t('retrieval.hybridDesc')}</p>
              </div>
              <Switch checked={enableHybrid} onCheckedChange={setEnableHybrid} />
            </div>
            
            <div className="flex items-center justify-between px-1">
              <div className="space-y-1">
                <Label className="text-sm font-semibold text-slate-800">{t('retrieval.rerank')}</Label>
                <p className="text-[11px] text-slate-400 uppercase tracking-widest font-medium">{t('retrieval.rerankDesc')}</p>
              </div>
              <Switch checked={enableRerank} onCheckedChange={setEnableRerank} />
            </div>
          </div>

          {/* Search History Toggle */}
          <div className="pt-4 border-t border-slate-100">
            <button onClick={loadHistory} className="w-full flex items-center justify-between px-1 py-2 text-sm font-semibold text-slate-600 hover:text-slate-900 transition-colors">
              <span className="flex items-center gap-2"><History className="w-4 h-4" /> {t('retrieval.history')}</span>
              <span className="text-[10px] text-slate-400">{historyItems.length} {t('retrieval.resultsCount').replace('{n}', String(historyItems.length))}</span>
            </button>
            {showHistory && (
              <div className="mt-2 space-y-1 max-h-48 overflow-y-auto">
                {historyItems.slice(0, 10).map((item, i) => (
                  <button key={i} className="w-full text-left px-2 py-1.5 rounded-lg hover:bg-slate-100 transition-colors" onClick={() => setQuery(item.query)}>
                    <p className="text-xs font-medium text-slate-700 truncate">{item.query}</p>
                    <p className="text-[10px] text-slate-400">{item.kb_name || item.kbName} · {t('retrieval.resultsCount').replace('{n}', item.result_count || item.resultCount)} · {t('retrieval.latencyMs').replace('{n}', item.latency_ms || item.latencyMs)}</p>
                  </button>
                ))}
                {historyItems.length === 0 && <p className="text-[10px] text-slate-400 px-2">{t('retrieval.noHistory')}</p>}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Main Search Area */}
      <div className="flex-1 bg-white border border-slate-200/60 rounded-3xl flex flex-col relative overflow-hidden shadow-sm">
        {/* Chat / Results Area */}
        <div className="flex-1 overflow-y-auto p-8 lg:p-10">
          {!results && !isSearching && (
            <div className="h-full flex flex-col items-center justify-center text-slate-400">
              <div className="w-20 h-20 rounded-2xl bg-slate-50 border border-slate-100 flex items-center justify-center mb-6 shadow-sm">
                <Search className="w-8 h-8 text-slate-300" />
              </div>
              <h3 className="text-xl font-bold text-slate-900 mb-3 tracking-tight">{t('retrieval.console')}</h3>
              <p className="max-w-md text-center text-sm leading-relaxed text-slate-500">
                {t('retrieval.consoleDesc')}
              </p>
            </div>
          )}

          {isSearching && (
            <div className="flex flex-col items-center justify-center py-24">
              <div className="w-10 h-10 border-4 border-slate-100 border-t-indigo-500 rounded-full animate-spin mb-6"></div>
              <p className="text-slate-500 font-mono text-xs uppercase tracking-widest font-semibold">{t('retrieval.executing')}</p>
            </div>
          )}

          {searchError && !isSearching && (
            <div className="flex flex-col items-center justify-center py-24">
              <div className="w-20 h-20 rounded-2xl bg-red-50 border border-red-100 flex items-center justify-center mb-6 shadow-sm">
                <AlertCircle className="w-8 h-8 text-red-400" />
              </div>
              <h3 className="text-lg font-bold text-slate-900 mb-2">{t('retrieval.searchError')}</h3>
              <p className="text-slate-500 text-sm">{searchError}</p>
            </div>
          )}

          {results && (
            <div className="space-y-8 max-w-4xl mx-auto pb-20">
              {/* User Query Echo */}
              <div className="flex justify-end">
                <div className="bg-gradient-to-r from-[#534ab7] to-indigo-600 text-white px-6 py-4 rounded-3xl rounded-tr-sm max-w-2xl font-medium text-[15px] shadow-sm leading-relaxed">
                  "{query}"
                </div>
              </div>

              {/* System Metadata Header */}
              <div className="flex items-center gap-4 text-[11px] font-mono text-slate-400 mb-6 border-b border-slate-100 pb-4 font-semibold uppercase tracking-wider">
                <div className="flex items-center gap-2">
                  <Clock className="w-3.5 h-3.5" /> {searchTime}ms
                </div>
                <div className="flex items-center gap-2">
                  <AlignLeft className="w-3.5 h-3.5" /> {results.length} {t('retrieval.recalled')}
                </div>
              </div>

              {/* Result Cards */}
              {results.length === 0 ? (
                <div className="bg-slate-50 border border-slate-200/60 rounded-2xl p-10 text-center text-slate-500 font-medium">
                  {t('retrieval.noMatch1')}{minScore[0]}{t('retrieval.noMatch2')}
                </div>
              ) : (
                <div className="space-y-6">
                  {results.map((result, idx) => (
                    <Card key={result.chunk_id} className="border-slate-200/60 shadow-sm rounded-2xl overflow-hidden bg-white hover:shadow-md transition-shadow">
                      <div className="px-6 py-4 bg-slate-50/80 border-b border-slate-100 flex items-center justify-between">
                        <div className="flex items-center gap-3 text-[13px]">
                          <span className="font-mono text-slate-400 font-bold">#{idx + 1}</span>
                          <div className="flex items-center gap-2 text-slate-700 font-semibold bg-white px-3 py-1.5 rounded-lg border border-slate-200/80 shadow-sm">
                            <BookOpen className="w-3.5 h-3.5 text-indigo-500" />
                            {result.metadata.doc_name}
                          </div>
                          {result.metadata.chapter && (
                            <>
                              <ChevronRight className="w-3.5 h-3.5 text-slate-300" />
                              <span className="text-slate-500 font-medium">{result.metadata.chapter}</span>
                            </>
                          )}
                          {result.metadata.page && (
                            <>
                              <ChevronRight className="w-3.5 h-3.5 text-slate-300" />
                              <span className="text-slate-500 font-medium">Page {result.metadata.page}</span>
                            </>
                          )}
                        </div>
                        
                        <div className="flex items-center gap-5">
                          <div className="flex items-center gap-3">
                            <span className="text-[10px] uppercase tracking-wider font-bold text-slate-400">{t('retrieval.score')}</span>
                            <div className="flex items-center gap-2">
                              <div className="w-16 h-1.5 bg-slate-200 rounded-full overflow-hidden">
                                <div className={`h-full rounded-full ${getScoreColor(result.score)}`} style={{ width: `${result.score * 100}%` }}></div>
                              </div>
                              <span className="text-xs font-mono font-bold text-slate-900">{result.score.toFixed(3)}</span>
                            </div>
                          </div>
                          <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-indigo-600 rounded-lg hover:bg-indigo-50">
                            <Copy className="w-4 h-4" />
                          </Button>
                        </div>
                      </div>
                      <CardContent className="p-6">
                        <p className="text-slate-700 text-[15px] leading-relaxed whitespace-pre-wrap font-medium">
                          {result.content}
                        </p>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="p-6 bg-white/50 backdrop-blur-md border-t border-slate-100">
          <div className="max-w-4xl mx-auto relative flex items-center shadow-lg shadow-slate-200/50 rounded-2xl group">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder={selectedKb ? t('retrieval.placeholder1') : t('retrieval.placeholder2')}
              disabled={!selectedKb || isSearching}
              className="pr-16 py-8 text-base bg-white border-slate-200/60 rounded-2xl focus-visible:ring-indigo-500/20 focus-visible:border-indigo-400 transition-all font-medium"
            />
            <Button
              onClick={handleSearch}
              disabled={!query || !selectedKb || isSearching}
              size="icon"
              className="absolute right-3 bg-[#534ab7] hover:bg-[#4438a0] text-white rounded-xl h-11 w-11 transition-all shadow-sm"
            >
              <Send className="w-4.5 h-4.5 ml-0.5" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
