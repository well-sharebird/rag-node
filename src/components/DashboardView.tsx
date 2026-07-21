import { useState, useEffect } from 'react';
import { useAppContext } from '@/lib/app-context';
import { toast } from 'sonner';
import { fetchDashboard, fetchQualityMetrics, fetchTopDocs, DashboardData, QualityMetricsData, TopDocItem } from '@/lib/api-client';
import { cn } from '@/lib/utils';
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
      {/* Header — MiMo style */}
      <header className="h-[60px] px-6 bg-white flex items-center justify-between shrink-0 border-b border-[#e5e5e5]">
        <div className="flex items-baseline gap-3">
          <h1 className="text-[18px] font-semibold text-[#1a1a1a]">{t('dashboard.title')}</h1>
          <span className="text-[13px] text-[#999999]">{t('dashboard.desc')}</span>
        </div>
      </header>

      {/* Content — MiMo style cards */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-[#f7f7f7]">
        {/* Metric Cards — MiMo style */}
        <div className="grid grid-cols-4 gap-4">
          {[
            { label: t('dashboard.totalKb'), value: totalKbs, change: '+12.3%' },
            { label: t('dashboard.processedDocs'), value: totalDocs, change: '+145' },
            { label: t('dashboard.totalVectors'), value: totalVectors.toLocaleString(), change: '+2,340' },
            { label: t('dashboard.avgLatency'), value: `${stats?.avgLatencyMs ?? 0}ms`, change: '-0.3s' },
          ].map((m, i) => (
            <div key={i} className="rounded-2xl bg-white p-5 border border-[#e5e5e5] shadow-sm">
              <div className="text-[13px] text-[#999999] mb-2">{m.label}</div>
              <div className="text-[28px] font-semibold text-[#1a1a1a] tracking-tight">{m.value}</div>
              <div className="text-[12px] mt-2 font-medium text-[#00c853]">{m.change}</div>
            </div>
          ))}
        </div>

        {/* Bottom Row */}
        <div className="grid grid-cols-2 gap-6">
          {/* Top Documents */}
          <div className="rounded-2xl bg-white p-6 border border-[#e5e5e5] shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-[15px] font-semibold text-[#1a1a1a]">Top Documents</h3>
              <button
                onClick={() => onNavigate('qa-chat')}
                className="text-[13px] text-[#ff6a00] hover:text-[#ff7b1f] font-medium bg-transparent border-0 cursor-pointer"
              >
                {t('dashboard.qaChat')} →
              </button>
            </div>
            {topDocs.length === 0 ? (
              <p className="text-[13px] text-[#999999] text-center py-10">暂无数据</p>
            ) : (
              <table className="w-full">
                <thead>
                  <tr>
                    <th className="text-left text-[12px] font-medium text-[#999999] pb-3 border-b border-[#e5e5e5]">{t('dashboard.docCol')}</th>
                    <th className="text-right text-[12px] font-medium text-[#999999] pb-3 border-b border-[#e5e5e5]">{t('dashboard.searches')}</th>
                  </tr>
                </thead>
                <tbody>
                  {topDocs.map((doc) => (
                    <tr key={doc.docId} className="border-b border-[#f0f0f0] last:border-0 hover:bg-[#fafafa]">
                      <td className="text-[14px] text-[#1a1a1a] py-3 pr-3">
                        <div className="truncate max-w-[280px] font-medium">{doc.docName}</div>
                        <div className="text-[12px] text-[#999999] mt-0.5">{doc.kbName}</div>
                      </td>
                      <td className="text-[14px] text-[#666666] text-right py-3 font-medium tabular-nums">{doc.searchCount}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Quality Metrics */}
          <div className="rounded-2xl bg-white p-6 border border-[#e5e5e5] shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-[15px] font-semibold text-[#1a1a1a]">{t('dashboard.qualityMetrics')}</h3>
            </div>
            <table className="w-full">
              <thead>
                <tr>
                  <th className="text-left text-[12px] font-medium text-[#999999] pb-3 border-b border-[#e5e5e5]">{t('dashboard.metricCol')}</th>
                  <th className="text-right text-[12px] font-medium text-[#999999] pb-3 border-b border-[#e5e5e5]">{t('dashboard.valueCol')}</th>
                  <th className="text-right text-[12px] font-medium text-[#999999] pb-3 border-b border-[#e5e5e5]">{t('dashboard.targetCol')}</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-b border-[#f0f0f0] last:border-0">
                  <td className="text-[14px] py-3.5 text-[#666666]">{t('dashboard.avgScore')}</td>
                  <td className="text-[14px] font-semibold text-right py-3.5 text-[#1a1a1a]">{(quality?.avgScore7d ?? 0).toFixed(2)}</td>
                  <td className="text-[13px] text-[#999999] text-right py-3.5">≥ 0.85</td>
                </tr>
                <tr className="border-b border-[#f0f0f0] last:border-0">
                  <td className="text-[14px] py-3.5 text-[#666666]">{t('dashboard.avgLatency7d')}</td>
                  <td className="text-[14px] font-semibold text-right py-3.5 text-[#1a1a1a]">{Math.round(quality?.avgLatency7d ?? 0)}ms</td>
                  <td className="text-[13px] text-[#999999] text-right py-3.5">≤ 2s</td>
                </tr>
                <tr className="border-b border-[#f0f0f0] last:border-0">
                  <td className="text-[14px] py-3.5 text-[#666666]">{t('dashboard.searches7d')}</td>
                  <td className="text-[14px] font-semibold text-right py-3.5 text-[#1a1a1a]">{quality?.totalSearches7d ?? 0}</td>
                  <td className="text-[13px] text-[#999999] text-right py-3.5">—</td>
                </tr>
                <tr className="border-b border-[#f0f0f0] last:border-0">
                  <td className="text-[14px] py-3.5 text-[#666666]">{t('dashboard.zeroResultRate')}</td>
                  <td className="text-[14px] font-semibold text-right py-3.5 text-[#1a1a1a]">{((quality?.zeroResultRate ?? 0) * 100).toFixed(1)}%</td>
                  <td className="text-[13px] text-[#999999] text-right py-3.5">≤ 5%</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        {/* Quality Trend */}
        {quality?.trend && quality.trend.length > 0 && (
          <div className="rounded-2xl bg-white p-6 border border-[#e5e5e5] shadow-sm">
            <h3 className="text-[15px] font-semibold text-[#1a1a1a] mb-4">{t('dashboard.qualityTrend')}</h3>
            <div className="flex items-end gap-1 h-28">
              {quality.trend.map((point, i) => {
                const maxCount = Math.max(...quality.trend.map(p => p.searchCount), 1);
                const height = Math.max(8, (point.searchCount / maxCount) * 100);
                return (
                  <div key={i} className="flex-1 flex flex-col items-center gap-1 min-w-0 group">
                    <span className="text-[11px] text-[#999999] opacity-0 group-hover:opacity-100 transition-opacity">{point.searchCount}</span>
                    <div className="w-full rounded-t-lg bg-gradient-to-t from-[#ff6a00] to-[#ff9f4d] transition-all duration-300 hover:opacity-80"
                         style={{ height: `${height}%` }} />
                    <span className="text-[11px] text-[#999999]">{point.date.slice(5)}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Service Health — MiMo style */}
        <div className="rounded-2xl bg-white p-6 border border-[#e5e5e5] shadow-sm">
          <h3 className="text-[15px] font-semibold text-[#1a1a1a] mb-5">{t('dashboard.health')}</h3>
          <div className="grid grid-cols-3 gap-6">
            {[
              { label: t('dashboard.vectorDb'), status: stats?.services?.milvus },
              { label: t('dashboard.embeddingApi'), status: stats?.services?.embedding },
              { label: t('dashboard.docProcessor'), status: stats?.services?.docProcessor },
            ].map((svc, i) => {
              const isHealthy = svc.status === 'healthy' || svc.status === 'ok';
              return (
                <div key={i} className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[14px] text-[#666666]">{svc.label}</span>
                    <span className={cn("text-[12px] font-medium px-2.5 py-1 rounded-full",
                      isHealthy ? "bg-[#e8f5e9] text-[#00c853]" : "bg-[#ffebee] text-[#ff5252]")}>
                      {isHealthy ? t('dashboard.healthy') : (svc.status ?? 'unknown')}
                    </span>
                  </div>
                  <div className="w-full h-1.5 rounded-full bg-[#f0f0f0]">
                    <div className="h-1.5 rounded-full transition-all duration-500"
                         style={{ width: isHealthy ? '100%' : '40%', background: isHealthy ? '#00c853' : '#ff5252' }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
