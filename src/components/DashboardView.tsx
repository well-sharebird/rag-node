import { useState, useEffect } from 'react';
import { useAppContext } from '@/lib/app-context';
import { toast } from 'sonner';
import { fetchDashboard, fetchQualityMetrics, fetchTopDocs, DashboardData, QualityMetricsData, TopDocItem } from '@/lib/api-client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Database, FileText, Search, Activity, ArrowUpRight, TrendingUp, Clock, Zap } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useI18n } from '@/src/lib/i18n';

export function DashboardView({ onNavigate }: { onNavigate: (tab: string) => void }) {
  const { knowledgeBases, documents } = useAppContext();
  const { t } = useI18n();

  const [stats, setStats] = useState<DashboardData | null>(null);
  const [quality, setQuality] = useState<QualityMetricsData | null>(null);
  const [topDocs, setTopDocs] = useState<TopDocItem[]>([]);

  useEffect(() => {
    fetchDashboard()
      .then(setStats)
      .catch((err) => {
        console.error('Failed to load dashboard stats:', err);
        toast.error('加载仪表盘数据失败');
      });
    fetchQualityMetrics()
      .then(setQuality)
      .catch((err) => {
        console.error('Failed to load quality metrics:', err);
        toast.error('加载质量指标失败');
      });
    fetchTopDocs()
      .then((d) => setTopDocs(d.items))
      .catch((err) => {
        console.error('Failed to load top docs:', err);
      });
  }, []);

  const totalKbs = stats?.totalKnowledgeBases ?? knowledgeBases.length;
  const totalDocs = stats?.totalDocuments ?? documents.length;
  const totalVectors = stats?.totalVectors ?? knowledgeBases.reduce((acc, kb) => acc + kb.vectorCount, 0);

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <header className="h-20 px-8 bg-white/80 backdrop-blur-md border-b border-slate-200/60 flex items-center justify-between sticky top-0 z-10 shrink-0">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">{t('dashboard.title')}</h1>
          <p className="text-sm text-slate-500">{t('dashboard.desc')}</p>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto p-8 lg:p-10 bg-[#F8FAFC]">
        {/* Stats Row */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <Card className="border-slate-200/60 shadow-sm hover:shadow-md transition-shadow rounded-3xl bg-white">
            <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
              <CardTitle className="text-sm font-semibold text-slate-500 uppercase tracking-wider">{t('dashboard.totalKb')}</CardTitle>
              <div className="p-2 bg-blue-50 rounded-xl"><Database className="w-5 h-5 text-blue-600" /></div>
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-bold text-slate-900 tracking-tight">{totalKbs}</div>
            </CardContent>
          </Card>
          <Card className="border-slate-200/60 shadow-sm hover:shadow-md transition-shadow rounded-3xl bg-white">
            <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
              <CardTitle className="text-sm font-semibold text-slate-500 uppercase tracking-wider">{t('dashboard.processedDocs')}</CardTitle>
              <div className="p-2 bg-emerald-50 rounded-xl"><FileText className="w-5 h-5 text-emerald-600" /></div>
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-bold text-slate-900 tracking-tight">{totalDocs}</div>
            </CardContent>
          </Card>
          <Card className="border-slate-200/60 shadow-sm hover:shadow-md transition-shadow rounded-3xl bg-white">
            <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
              <CardTitle className="text-sm font-semibold text-slate-500 uppercase tracking-wider">{t('dashboard.totalVectors')}</CardTitle>
              <div className="p-2 bg-amber-50 rounded-xl"><Search className="w-5 h-5 text-amber-600" /></div>
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-bold text-slate-900 tracking-tight">{totalVectors.toLocaleString()}</div>
            </CardContent>
          </Card>
          <Card className="border-slate-200/60 shadow-sm hover:shadow-md transition-shadow rounded-3xl bg-white">
            <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
              <CardTitle className="text-sm font-semibold text-slate-500 uppercase tracking-wider">{t('dashboard.avgLatency')}</CardTitle>
              <div className="p-2 bg-indigo-50 rounded-xl"><Activity className="w-5 h-5 text-indigo-600" /></div>
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-bold text-slate-900 tracking-tight">
                {stats?.avgLatencyMs ?? 0}<span className="text-xl font-normal text-slate-400 ml-1">ms</span>
              </div>
              <p className="text-[13px] font-medium text-emerald-600 mt-2 flex items-center gap-1 bg-emerald-50 w-fit px-2 py-0.5 rounded-lg">
                <ArrowUpRight className="w-3.5 h-3.5" /> {t('dashboard.sla')}
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Quality Metrics Row */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <Card className="border-slate-200/60 shadow-sm rounded-2xl bg-white">
            <CardContent className="p-5">
              <div className="flex items-center gap-3">
                <div className="p-2.5 bg-emerald-50 rounded-xl"><TrendingUp className="w-4 h-4 text-emerald-600" /></div>
                <div>
                  <p className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">{t('dashboard.avgScore')}</p>
                  <p className="text-xl font-bold text-slate-900">{(quality?.avgScore7d ?? 0).toFixed(2)}</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-slate-200/60 shadow-sm rounded-2xl bg-white">
            <CardContent className="p-5">
              <div className="flex items-center gap-3">
                <div className="p-2.5 bg-blue-50 rounded-xl"><Clock className="w-4 h-4 text-blue-600" /></div>
                <div>
                  <p className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">{t('dashboard.avgLatency7d')}</p>
                  <p className="text-xl font-bold text-slate-900">{(quality?.avgLatency7d ?? 0).toFixed(0)}ms</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-slate-200/60 shadow-sm rounded-2xl bg-white">
            <CardContent className="p-5">
              <div className="flex items-center gap-3">
                <div className="p-2.5 bg-indigo-50 rounded-xl"><Zap className="w-4 h-4 text-indigo-600" /></div>
                <div>
                  <p className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">{t('dashboard.searches7d')}</p>
                  <p className="text-xl font-bold text-slate-900">{quality?.totalSearches7d ?? 0}</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-slate-200/60 shadow-sm rounded-2xl bg-white">
            <CardContent className="p-5">
              <div className="flex items-center gap-3">
                <div className="p-2.5 bg-amber-50 rounded-xl"><Search className="w-4 h-4 text-amber-600" /></div>
                <div>
                  <p className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">{t('dashboard.zeroResultRate')}</p>
                  <p className="text-xl font-bold text-slate-900">{((quality?.zeroResultRate ?? 0) * 100).toFixed(1)}%</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Quality Trend Chart */}
        {quality?.trend && quality.trend.length > 0 && (
          <Card className="border-slate-200/60 shadow-sm rounded-3xl bg-white mb-8">
            <CardHeader className="border-b border-slate-100 bg-slate-50/50 p-6">
              <CardTitle className="text-lg font-bold text-slate-800">{t('dashboard.qualityTrend')}</CardTitle>
            </CardHeader>
            <CardContent className="p-6">
              <div className="flex items-end gap-1 h-32">
                {quality.trend.map((point, i) => {
                  const maxCount = Math.max(...quality.trend.map(p => p.searchCount), 1);
                  const height = Math.max(4, (point.searchCount / maxCount) * 100);
                  const alpha = point.searchCount > 0 ? 1 : 0.3;
                  return (
                    <div key={i} className="flex-1 flex flex-col items-center gap-1 min-w-0" title={`${point.date}: ${point.searchCount} searches, avg score ${point.avgScore}`}>
                      <span className="text-[9px] text-slate-400">{point.searchCount}</span>
                      <div className="w-full rounded-t-md bg-[#1677ff]" style={{ height: `${height}%`, opacity: alpha }} />
                      <span className="text-[9px] text-slate-400 truncate w-full text-center">{point.date.slice(5)}</span>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Bottom Row: Quick Actions + System Health + Top Docs */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 lg:gap-8">
          {/* Quick Actions */}
          <Card className="border-slate-200/60 shadow-sm rounded-3xl bg-white overflow-hidden">
            <CardHeader className="border-b border-slate-100 bg-slate-50/50 p-6">
              <CardTitle className="text-lg font-bold text-slate-800">{t('dashboard.quickActions')}</CardTitle>
            </CardHeader>
            <CardContent className="p-6 grid grid-cols-2 gap-4">
              <Button variant="outline" className="h-24 flex flex-col items-center justify-center gap-2 bg-white hover:bg-slate-50 hover:border-[#1677ff]/30 rounded-2xl border-slate-200/60 shadow-sm hover:shadow transition-all group" onClick={() => onNavigate('knowledge-bases')}>
                <div className="p-2.5 bg-blue-50 rounded-xl group-hover:scale-110 transition-transform"><Database className="w-5 h-5 text-[#1677ff]" /></div>
                <span className="font-semibold text-slate-700 text-xs">{t('dashboard.createKb')}</span>
              </Button>
              <Button variant="outline" className="h-24 flex flex-col items-center justify-center gap-2 bg-white hover:bg-slate-50 hover:border-emerald-500/30 rounded-2xl border-slate-200/60 shadow-sm hover:shadow transition-all group" onClick={() => onNavigate('documents')}>
                <div className="p-2.5 bg-emerald-50 rounded-xl group-hover:scale-110 transition-transform"><FileText className="w-5 h-5 text-emerald-600" /></div>
                <span className="font-semibold text-slate-700 text-xs">{t('dashboard.uploadDocs')}</span>
              </Button>
              <Button variant="outline" className="h-24 flex flex-col items-center justify-center gap-2 bg-white hover:bg-slate-50 hover:border-amber-500/30 rounded-2xl border-slate-200/60 shadow-sm hover:shadow transition-all group" onClick={() => onNavigate('retrieval-test')}>
                <div className="p-2.5 bg-amber-50 rounded-xl group-hover:scale-110 transition-transform"><Search className="w-5 h-5 text-amber-500" /></div>
                <span className="font-semibold text-slate-700 text-xs">{t('dashboard.testRetrieval')}</span>
              </Button>
              <Button variant="outline" className="h-24 flex flex-col items-center justify-center gap-2 bg-white hover:bg-slate-50 hover:border-indigo-500/30 rounded-2xl border-slate-200/60 shadow-sm hover:shadow transition-all group" onClick={() => onNavigate('settings')}>
                <div className="p-2.5 bg-indigo-50 rounded-xl group-hover:scale-110 transition-transform"><Activity className="w-5 h-5 text-indigo-600" /></div>
                <span className="font-semibold text-slate-700 text-xs">{t('nav.settings')}</span>
              </Button>
            </CardContent>
          </Card>

          {/* System Health */}
          <Card className="border-slate-200/60 shadow-sm rounded-3xl bg-white overflow-hidden">
            <CardHeader className="border-b border-slate-100 bg-slate-50/50 p-6">
              <CardTitle className="text-lg font-bold text-slate-800">{t('dashboard.health')}</CardTitle>
            </CardHeader>
            <CardContent className="p-6 space-y-5">
              <ServiceHealthBar label={t('dashboard.vectorDb')} status={stats?.services?.milvus ?? 'unknown'} healthyText={t('dashboard.healthy')} />
              <ServiceHealthBar label={t('dashboard.embeddingApi')} status={stats?.services?.embedding ?? 'unknown'} healthyText={t('dashboard.healthy')} />
              <ServiceHealthBar label={t('dashboard.docProcessor')} status={stats?.services?.docProcessor ?? 'unknown'} healthyText={t('dashboard.healthy')} />
            </CardContent>
          </Card>

          {/* Top Documents */}
          <Card className="border-slate-200/60 shadow-sm rounded-3xl bg-white overflow-hidden">
            <CardHeader className="border-b border-slate-100 bg-slate-50/50 p-6">
              <CardTitle className="text-lg font-bold text-slate-800">{t('dashboard.topDocs')}</CardTitle>
            </CardHeader>
            <CardContent className="p-4 space-y-2 max-h-[280px] overflow-y-auto">
              {topDocs.length === 0 && (
                <p className="text-sm text-slate-400 text-center py-6">{t('dashboard.noTopDocs')}</p>
              )}
              {topDocs.map((doc, i) => (
                <div key={doc.docId} className="flex items-center justify-between p-2.5 rounded-xl hover:bg-slate-50 transition-colors">
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="text-[11px] font-bold text-slate-300 w-5 text-right">{i + 1}</span>
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-slate-700 truncate">{doc.docName}</p>
                      <p className="text-[10px] text-slate-400 truncate">{doc.kbName}</p>
                    </div>
                  </div>
                  <div className="text-right shrink-0 ml-2">
                    <p className="text-xs font-bold text-slate-700">{doc.searchCount}</p>
                    <p className="text-[10px] text-slate-400">{t('dashboard.searches')}</p>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function ServiceHealthBar({ label, status, healthyText, progress = 100 }: { label: string; status: string; healthyText: string; progress?: number }) {
  const isHealthy = status === 'healthy' || status === 'ok';
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-sm">
        <span className="text-slate-700 font-semibold">{label}</span>
        <span className={`font-bold px-3 py-1 rounded-lg text-xs ${isHealthy ? 'text-emerald-700 bg-emerald-100' : 'text-red-700 bg-red-100'}`}>
          {isHealthy ? healthyText : status}
        </span>
      </div>
      <div className="w-full bg-slate-100 rounded-full h-2">
        <div className={`h-2 rounded-full transition-all ${isHealthy ? 'bg-emerald-500' : 'bg-red-500'}`} style={{ width: `${isHealthy ? progress : 100}%` }} />
      </div>
    </div>
  );
}
