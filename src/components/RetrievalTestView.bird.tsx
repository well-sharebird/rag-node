import { useState, useRef, useEffect } from 'react';
import { useAppContext } from '@/lib/app-context';
import { searchChunks, fetchSearchHistory } from '@/lib/api-client';
import { Button, Card, CardHeader, CardBody, CardTitle, Badge, Input, Switch } from '@/src/components/bird';
import { Select } from '@/src/components/bird/Select';
import { cn } from '@/lib/utils';
import { Search, Send, Settings2, Clock, Copy, BookOpen, AlertCircle, History } from 'lucide-react';
import { SearchResult } from '@/src/types';
import { useI18n } from '@/src/lib/i18n';
import { toast } from 'sonner';

export function RetrievalTestViewBird() {
  const { knowledgeBases } = useAppContext();
  const { t } = useI18n();
  const [query, setQuery] = useState('');
  const [selectedKb, setSelectedKb] = useState<string>('');

  // Search parameters
  const [topK, setTopK] = useState(5);
  const [minScore, setMinScore] = useState(0.7);
  const [enableRerank, setEnableRerank] = useState(false);
  const [enableHybrid, setEnableHybrid] = useState(false);

  const [isSearching, setIsSearching] = useState(false);
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [searchTime, setSearchTime] = useState(0);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [historyItems, setHistoryItems] = useState<any[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  const loadHistory = async () => {
    setShowHistory(!showHistory);
    try {
      const data: any = await fetchSearchHistory(10);
      setHistoryItems(data?.items || []);
    } catch (e) {
      console.error('Failed to load history:', e);
    }
  };

  useEffect(() => {
    loadHistory();
    return () => { if (abortRef.current) abortRef.current.abort(); };
  }, []);

  const handleSearch = async () => {
    if (!query || !selectedKb) {
      toast.error('请选择知识库并输入查询');
      return;
    }

    if (abortRef.current) abortRef.current.abort();
    abortRef.current = new AbortController();

    setIsSearching(true);
    setResults(null);
    setSearchError(null);

    try {
      const response: any = await searchChunks({
        kb_id: selectedKb,
        query,
        top_k: topK,
        min_score: minScore,
        enable_hybrid: enableHybrid,
        enable_rerank: enableRerank,
      });

      const mapped = ((response as any).results || []).map((r: any) => ({
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
      setSearchTime((response as any).searchTimeMs || 0);
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        setSearchError(e.message || 'Search failed');
      }
    } finally {
      setIsSearching(false);
    }
  };

  const getScoreBadge = (score: number) => {
    if (score >= 0.9) return { variant: 'success' as const, label: '高相关' };
    if (score >= 0.7) return { variant: 'primary' as const, label: '中相关' };
    if (score >= 0.5) return { variant: 'warning' as const, label: '低相关' };
    return { variant: 'error' as const, label: '不相关' };
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    toast.success('内容已复制');
  };

  return (
    <div className="flex-1 flex flex-col lg:flex-row overflow-hidden bg-[#f9fafb]">
      {/* Left Panel - Parameters */}
      <div className="w-full lg:w-80 bg-white border-r border-[#e5e7eb] flex flex-col overflow-y-auto">
        <div className="p-4 border-b border-[#e5e7eb] flex items-center gap-2">
          <div className="w-8 h-8 rounded-xl bg-[#ede9fe] flex items-center justify-center">
            <Settings2 className="w-4 h-4 text-[#7c3aed]" />
          </div>
          <h3 className="text-[14px] font-semibold text-[#111827]">{t('retrieval.params')}</h3>
        </div>

        <div className="p-4 space-y-6 flex-1">
          {/* Knowledge Base Selector */}
          <div className="space-y-2">
            <label className="text-[12px] font-medium text-[#4b5563]">{t('retrieval.targetKb')}</label>
            <Select
              value={selectedKb}
              onChange={(e) => setSelectedKb(e.target.value)}
              className="w-full"
            >
              <option value="">{t('retrieval.selectKb')}</option>
              {knowledgeBases.map(kb => (
                <option key={kb.id} value={kb.id}>{kb.name}</option>
              ))}
            </Select>
          </div>

          {/* Top K */}
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <label className="text-[12px] font-medium text-[#4b5563]">{t('retrieval.topK')}</label>
              <span className="text-[13px] font-semibold text-[#7c3aed] bg-[#ede9fe] px-2 py-0.5 rounded-lg">{topK}</span>
            </div>
            <input
              type="range"
              min="1"
              max="20"
              step="1"
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
              className="w-full h-2 bg-[#e5e7eb] rounded-lg appearance-none cursor-pointer accent-[#7c3aed]"
            />
          </div>

          {/* Min Score */}
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <label className="text-[12px] font-medium text-[#4b5563]">{t('retrieval.minScore')}</label>
              <span className="text-[13px] font-semibold text-[#7c3aed] bg-[#ede9fe] px-2 py-0.5 rounded-lg">{minScore.toFixed(2)}</span>
            </div>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={minScore}
              onChange={(e) => setMinScore(Number(e.target.value))}
              className="w-full h-2 bg-[#e5e7eb] rounded-lg appearance-none cursor-pointer accent-[#7c3aed]"
            />
          </div>

          {/* Toggles */}
          <div className="space-y-4 pt-4 border-t border-[#e5e7eb]">
            <div className="flex items-center justify-between">
              <div>
                <label className="text-[13px] font-medium text-[#111827]">{t('retrieval.hybrid')}</label>
                <p className="text-[11px] text-[#9ca3af]">{t('retrieval.hybridDesc')}</p>
              </div>
              <Switch
                checked={enableHybrid}
                onCheckedChange={setEnableHybrid}
              />
            </div>

            <div className="flex items-center justify-between">
              <div>
                <label className="text-[13px] font-medium text-[#111827]">{t('retrieval.rerank')}</label>
                <p className="text-[11px] text-[#9ca3af]">{t('retrieval.rerankDesc')}</p>
              </div>
              <Switch
                checked={enableRerank}
                onCheckedChange={setEnableRerank}
              />
            </div>
          </div>

          {/* Search History */}
          <div className="pt-4 border-t border-[#e5e7eb]">
            <button
              onClick={loadHistory}
              className="w-full flex items-center justify-between p-2 rounded-lg hover:bg-[#f9fafb] transition-colors"
            >
              <span className="flex items-center gap-2 text-[13px] font-medium text-[#4b5563]">
                <History className="w-4 h-4" /> {t('retrieval.history')}
              </span>
              <span className="text-[11px] text-[#9ca3af]">{historyItems.length} 条</span>
            </button>
            {showHistory && historyItems.length > 0 && (
              <div className="mt-2 space-y-1 max-h-48 overflow-y-auto">
                {historyItems.slice(0, 10).map((item, i) => (
                  <button
                    key={i}
                    className="w-full text-left p-2 rounded-lg hover:bg-[#f3f4f6] transition-colors"
                    onClick={() => setQuery(item.query)}
                  >
                    <p className="text-[12px] font-medium text-[#111827] truncate">{item.query}</p>
                    <p className="text-[10px] text-[#9ca3af] mt-0.5">
                      {item.kb_name || item.kbName} · {(item.result_count || item.resultCount) || 0} 条结果
                    </p>
                  </button>
                ))}
              </div>
            )}
            {showHistory && historyItems.length === 0 && (
              <p className="text-[11px] text-[#9ca3af] p-2">暂无搜索历史</p>
            )}
          </div>
        </div>
      </div>

      {/* Right Panel - Main Search Area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Results Area */}
        <div className="flex-1 overflow-y-auto p-6">
          {!results && !isSearching && !searchError && (
            <div className="h-full flex flex-col items-center justify-center text-[#9ca3af]">
              <div className="w-20 h-20 rounded-2xl bg-[#ede9fe] flex items-center justify-center mb-6">
                <Search className="w-10 h-10 text-[#7c3aed]" />
              </div>
              <h3 className="text-[18px] font-semibold text-[#111827] mb-2">{t('retrieval.console')}</h3>
              <p className="text-[13px] text-center max-w-md">
                {t('retrieval.consoleDesc')}
              </p>
            </div>
          )}

          {isSearching && (
            <div className="h-full flex flex-col items-center justify-center">
              <div className="w-12 h-12 border-4 border-[#e5e7eb] border-t-[#7c3aed] rounded-full animate-spin mb-4"></div>
              <p className="text-[13px] text-[#6b7280] font-medium">搜索中...</p>
            </div>
          )}

          {searchError && (
            <div className="h-full flex flex-col items-center justify-center">
              <div className="w-20 h-20 rounded-2xl bg-[#fee2e2] flex items-center justify-center mb-4">
                <AlertCircle className="w-10 h-10 text-[#ef4444]" />
              </div>
              <h3 className="text-[16px] font-semibold text-[#111827] mb-2">搜索失败</h3>
              <p className="text-[13px] text-[#6b7280]">{searchError}</p>
            </div>
          )}

          {results && (
            <div className="max-w-4xl mx-auto space-y-6">
              {/* User Query */}
              <div className="flex justify-end">
                <div className="bg-[#7c3aed] text-white px-6 py-4 rounded-2xl rounded-tr-sm max-w-2xl font-medium text-[14px] shadow-sm">
                  "{query}"
                </div>
              </div>

              {/* Metadata */}
              <div className="flex items-center gap-4 text-[12px] text-[#6b7280] border-b border-[#e5e7eb] pb-4">
                <div className="flex items-center gap-2">
                  <Clock className="w-4 h-4" /> {searchTime}ms
                </div>
                <div className="flex items-center gap-2">
                  <BookOpen className="w-4 h-4" /> {results.length} 条结果
                </div>
              </div>

              {/* Results */}
              {results.length === 0 ? (
                <Card>
                  <CardBody className="py-12 text-center">
                    <p className="text-[14px] text-[#6b7280]">
                      没有找到相关结果（阈值：{minScore.toFixed(2)}）
                    </p>
                  </CardBody>
                </Card>
              ) : (
                <div className="space-y-4">
                  {results.map((result, idx) => {
                    const scoreBadge = getScoreBadge(result.score);
                    return (
                      <Card key={result.chunk_id}>
                        <CardBody>
                          <div className="flex items-start justify-between mb-3">
                            <div className="flex items-center gap-2">
                              <Badge variant="neutral" size="sm">#{idx + 1}</Badge>
                              <div className="flex items-center gap-2">
                                <BookOpen className="w-4 h-4 text-[#7c3aed]" />
                                <span className="text-[14px] font-medium text-[#111827]">
                                  {result.metadata.doc_name}
                                </span>
                              </div>
                              {result.metadata.chapter && (
                                <>
                                  <span className="text-[#9ca3af]">/</span>
                                  <span className="text-[13px] text-[#6b7280]">{result.metadata.chapter}</span>
                                </>
                              )}
                              {result.metadata.page && (
                                <>
                                  <span className="text-[#9ca3af]">/</span>
                                  <span className="text-[13px] text-[#6b7280]">P.{result.metadata.page}</span>
                                </>
                              )}
                            </div>
                            <div className="flex items-center gap-3">
                              <div className="flex items-center gap-2">
                                <span className="text-[11px] text-[#9ca3af] font-medium">相关度</span>
                                <div className="w-20 h-2 bg-[#e5e7eb] rounded-full overflow-hidden">
                                  <div
                                    className={cn(
                                      "h-full rounded-full transition-all",
                                      result.score >= 0.9 ? "bg-[#10b981]" :
                                      result.score >= 0.7 ? "bg-[#7c3aed]" :
                                      result.score >= 0.5 ? "bg-[#f59e0b]" :
                                      "bg-[#ef4444]"
                                    )}
                                    style={{ width: `${result.score * 100}%` }}
                                  />
                                </div>
                                <span className="text-[12px] font-mono font-semibold text-[#111827]">
                                  {result.score.toFixed(3)}
                                </span>
                              </div>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => copyToClipboard(result.content)}
                                icon={<Copy className="w-3.5 h-3.5" />}
                              />
                            </div>
                          </div>
                          <p className="text-[14px] text-[#374151] leading-relaxed whitespace-pre-wrap">
                            {result.content}
                          </p>
                        </CardBody>
                      </Card>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="p-4 bg-white border-t border-[#e5e7eb]">
          <div className="max-w-4xl mx-auto relative flex items-center">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder={selectedKb ? "输入查询内容..." : "请先选择知识库"}
              disabled={!selectedKb || isSearching}
              className="pr-14 py-6 text-[14px] rounded-2xl"
            />
            <Button
              onClick={handleSearch}
              disabled={!query || !selectedKb || isSearching}
              size="lg"
              className="absolute right-2 bg-[#7c3aed] hover:bg-[#6d28d9] text-white rounded-xl h-10 w-10"
              icon={<Send className="w-4 h-4" />}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
