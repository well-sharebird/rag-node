import { useState, useEffect } from 'react';
import { useAppContext } from '@/lib/app-context';
import { toast } from 'sonner';
import { fetchDashboard, fetchQualityMetrics, fetchTopDocs, DashboardData, QualityMetricsData, TopDocItem } from '@/lib/api-client';
import { cn } from '@/lib/utils';
import { useI18n } from '@/src/lib/i18n';
import { Card, CardHeader, CardTitle, CardBody } from '@/src/components/enterprise/Card';
import { Button } from '@/src/components/enterprise/Button';
import { Table, TableHeader, TableBody, TableRow, TableCell } from '@/src/components/enterprise/Table';
import { Badge } from '@/src/components/enterprise/Badge';
import { TrendingUp, Database, FileText, Zap, Activity, ChevronRight, HelpCircle } from 'lucide-react';

export function DashboardView({ onNavigate }: { onNavigate: (tab: string) => void }) {
  const { knowledgeBases, documents } = useAppContext();
  const { t } = useI18n();

  const [stats, setStats] = useState<DashboardData | null>(null);
  const [quality, setQuality] = useState<QualityMetricsData | null>(null);
  const [topDocs, setTopDocs] = useState<TopDocItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetchDashboard().catch((err) => {
        console.error('Failed to load dashboard stats:', err);
        toast.error('加载仪表盘数据失败');
        return null;
      }),
      fetchQualityMetrics().catch((err) => {
        console.error('Failed to load quality metrics:', err);
        toast.error('加载质量指标失败');
        return null;
      }),
      fetchTopDocs().catch((err) => {
        console.error('Failed to load top docs:', err);
        return { items: [] };
      }),
    ]).then(([dashboardData, qualityData, topDocsData]) => {
      setStats(dashboardData);
      setQuality(qualityData);
      setTopDocs(topDocsData?.items || []);
      setLoading(false);
    });
  }, []);

  const totalKbs = stats?.totalKnowledgeBases ?? knowledgeBases.length;
  const totalDocs = stats?.totalDocuments ?? documents.length;
  const totalVectors = stats?.totalVectors ?? knowledgeBases.reduce((acc, kb) => acc + kb.vectorCount, 0);
  const avgLatency = stats?.avgLatencyMs ?? 0;

  const metricCards = [
    {
      label: t('dashboard.totalKb'),
      tooltip: '知识库总数，每个知识库包含若干文档和向量',
      value: totalKbs,
      change: '+12.3%',
      icon: Database,
      color: 'var(--primary)',
      bgColor: 'var(--accent-light)'
    },
    {
      label: t('dashboard.processedDocs'),
      tooltip: '已处理的文档总数，包含所有上传并成功分块向量化后的文档',
      value: totalDocs,
      change: '+145',
      icon: FileText,
      color: 'var(--success)',
      bgColor: 'var(--success-bg)'
    },
    {
      label: t('dashboard.totalVectors'),
      tooltip: '向量总数，所有文档分块后生成的向量嵌入数量总和',
      value: totalVectors.toLocaleString(),
      change: '+2,340',
      icon: Zap,
      color: 'var(--warning)',
      bgColor: 'var(--warning-bg)'
    },
    {
      label: t('dashboard.avgLatency'),
      tooltip: '平均检索延迟，最近一段时间内检索请求的平均响应时间',
      value: `${avgLatency}ms`,
      change: avgLatency < 1000 ? '-0.3s' : '+0.5s',
      icon: Activity,
      color: avgLatency < 1000 ? 'var(--success)' : 'var(--error)',
      bgColor: avgLatency < 1000 ? 'var(--success-bg)' : 'var(--error-bg)'
    },
  ];

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-white">
      {/* Header - Bird 风格 */}
      <header className="h-[60px] px-6 bg-white flex items-center justify-between shrink-0 border-b border-[var(--sidebar-border)]">
        <div className="flex items-baseline gap-3">
          <h1 className="text-[18px] font-semibold text-[var(--text-primary)]">{t('dashboard.title')}</h1>
          <span className="text-[13px] text-[var(--text-tertiary)]">{t('dashboard.desc')}</span>
        </div>
        <Button variant="primary" size="md" onClick={() => onNavigate('knowledge-bases')}>
          <TrendingUp className="w-4 h-4 mr-2" />
          查看详情
        </Button>
      </header>

      {/* Content - Bird 风格 */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Metric Cards */}
        {loading ? (
          <div className="grid grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="rounded-xl bg-[var(--card-bg)] p-5 border border-[var(--card-border)] animate-pulse">
                <div className="h-4 w-24 bg-[var(--gray-200)] rounded mb-3" />
                <div className="h-8 w-32 bg-[var(--gray-200)] rounded mb-2" />
                <div className="h-3 w-16 bg-[var(--gray-200)] rounded" />
              </div>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
            {metricCards.map((m, i) => (
              <Card key={i} hover className="overflow-hidden">
                <CardBody>
                  <div className="flex items-center justify-between mb-3">
                    <div
                      className="w-10 h-10 rounded-xl flex items-center justify-center"
                      style={{ backgroundColor: m.bgColor }}
                    >
                      <m.icon className="w-5 h-5" style={{ color: m.color }} />
                    </div>
                    <Badge variant={m.change.startsWith('+') || m.change.startsWith('-') ? 'success' : 'neutral'}>
                      {m.change}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-1.5 mb-1">
                    <span className="text-[13px] text-[var(--text-secondary)]">{m.label}</span>
                    <div className="group relative">
                      <HelpCircle className="w-3.5 h-3.5 text-[var(--text-tertiary)] cursor-help" />
                      <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-[var(--gray-900)] text-white text-[11px] rounded-lg whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity z-10 pointer-events-none max-w-[250px] shadow-lg">
                        {m.tooltip}
                        <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-1 border-4 border-transparent border-t-[var(--gray-900)]" />
                      </div>
                    </div>
                  </div>
                  <div className="text-[24px] font-semibold text-[var(--text-primary)] tracking-tight">
                    {m.value}
                  </div>
                </CardBody>
              </Card>
            ))}
          </div>
        )}

        {/* Bottom Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Top Documents */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Top Documents</CardTitle>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onNavigate('qa-chat')}
                  className="text-[var(--primary)] hover:bg-[var(--accent-light)]"
                >
                  {t('dashboard.qaChat')}
                  <ChevronRight className="w-4 h-4 ml-1" />
                </Button>
              </div>
            </CardHeader>
            <CardBody>
              {topDocs.length === 0 ? (
                <div className="text-center py-10">
                  <Database className="w-12 h-12 text-[var(--text-tertiary)] mx-auto mb-3" />
                  <p className="text-[13px] text-[var(--text-tertiary)]">暂无数据</p>
                </div>
              ) : (
                <Table hover>
                  <TableHeader>
                    <TableRow>
                      <TableCell variant="header" className="text-[12px] font-medium text-[var(--text-tertiary)]">
                        {t('dashboard.docCol')}
                      </TableCell>
                      <TableCell variant="header" className="text-[12px] font-medium text-[var(--text-tertiary)] text-right">
                        {t('dashboard.searches')}
                      </TableCell>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {topDocs.map((doc) => (
                      <TableRow key={doc.docId} className="cursor-pointer hover:bg-[var(--gray-50)]">
                        <TableCell>
                          <div className="truncate max-w-[250px] font-medium text-[var(--text-primary)]">
                            {doc.docName}
                          </div>
                          <div className="text-[12px] text-[var(--text-tertiary)] mt-0.5">
                            {doc.kbName}
                          </div>
                        </TableCell>
                        <TableCell className="text-right font-medium tabular-nums text-[var(--text-secondary)]">
                          {doc.searchCount}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardBody>
          </Card>

          {/* Quality Metrics */}
          <Card>
            <CardHeader>
              <CardTitle>{t('dashboard.qualityMetrics')}</CardTitle>
            </CardHeader>
            <CardBody>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableCell variant="header" className="text-[12px] font-medium text-[var(--text-tertiary)]">
                      {t('dashboard.metricCol')}
                    </TableCell>
                    <TableCell variant="header" className="text-[12px] font-medium text-[var(--text-tertiary)] text-right">
                      {t('dashboard.valueCol')}
                    </TableCell>
                    <TableCell variant="header" className="text-[12px] font-medium text-[var(--text-tertiary)] text-right">
                      {t('dashboard.targetCol')}
                    </TableCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <tr className="border-b border-[var(--gray-100)] last:border-0">
                    <TableCell className="text-[14px] py-3.5 text-[var(--text-secondary)]">
                      {t('dashboard.avgScore')}
                    </TableCell>
                    <TableCell className="text-[14px] font-semibold text-right py-3.5 text-[var(--text-primary)]">
                      {(quality?.avgScore7d ?? 0).toFixed(2)}
                    </TableCell>
                    <TableCell className="text-[13px] text-[var(--text-tertiary)] text-right py-3.5">
                      ≥ 0.85
                    </TableCell>
                  </tr>
                  <tr className="border-b border-[var(--gray-100)] last:border-0">
                    <TableCell className="text-[14px] py-3.5 text-[var(--text-secondary)]">
                      {t('dashboard.avgLatency7d')}
                    </TableCell>
                    <TableCell className="text-[14px] font-semibold text-right py-3.5 text-[var(--text-primary)]">
                      {Math.round(quality?.avgLatency7d ?? 0)}ms
                    </TableCell>
                    <TableCell className="text-[13px] text-[var(--text-tertiary)] text-right py-3.5">
                      ≤ 2s
                    </TableCell>
                  </tr>
                  <tr className="border-b border-[var(--gray-100)] last:border-0">
                    <TableCell className="text-[14px] py-3.5 text-[var(--text-secondary)]">
                      {t('dashboard.searches7d')}
                    </TableCell>
                    <TableCell className="text-[14px] font-semibold text-right py-3.5 text-[var(--text-primary)]">
                      {quality?.totalSearches7d ?? 0}
                    </TableCell>
                    <TableCell className="text-[13px] text-[var(--text-tertiary)] text-right py-3.5">
                      —
                    </TableCell>
                  </tr>
                  <tr className="border-b border-[var(--gray-100)] last:border-0">
                    <TableCell className="text-[14px] py-3.5 text-[var(--text-secondary)]">
                      {t('dashboard.zeroResultRate')}
                    </TableCell>
                    <TableCell className="text-[14px] font-semibold text-right py-3.5 text-[var(--text-primary)]">
                      {((quality?.zeroResultRate ?? 0) * 100).toFixed(1)}%
                    </TableCell>
                    <TableCell className="text-[13px] text-[var(--text-tertiary)] text-right py-3.5">
                      ≤ 5%
                    </TableCell>
                  </tr>
                </TableBody>
              </Table>
            </CardBody>
          </Card>
        </div>

        {/* Quality Trend */}
        {quality?.trend && quality.trend.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>{t('dashboard.qualityTrend')}</CardTitle>
            </CardHeader>
            <CardBody>
              <div className="flex items-end gap-1 h-32">
                {quality.trend.map((point) => {
                  const maxCount = Math.max(...quality.trend.map(p => p.search_count), 1);
                  const height = Math.max(8, (point.search_count / maxCount) * 100);
                  return (
                    <div key={point.date} className="flex-1 flex flex-col items-center gap-1 min-w-0 group">
                      <span className="text-[11px] text-[var(--text-tertiary)] opacity-0 group-hover:opacity-100 transition-opacity">
                        {point.search_count}
                      </span>
                      <div
                        className="w-full rounded-t-lg bg-gradient-to-t from-[var(--primary)] to-[var(--primary-light)] transition-all duration-300 hover:opacity-80"
                        style={{ height: `${height}%` }}
                      />
                      <span className="text-[11px] text-[var(--text-tertiary)]">
                        {point.date.slice(5)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </CardBody>
          </Card>
        )}

        {/* Service Health */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <CardTitle>{t('dashboard.health')}</CardTitle>
              <div className="group relative">
                <HelpCircle className="w-4 h-4 text-[var(--text-tertiary)] cursor-help" />
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-[var(--gray-900)] text-white text-[11px] rounded-lg whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity z-10 pointer-events-none max-w-[300px] shadow-lg">
                  系统服务健康状态检测，包括向量数据库、嵌入模型和文档处理流水线
                  <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-1 border-4 border-transparent border-t-[var(--gray-900)]" />
                </div>
              </div>
            </div>
          </CardHeader>
          <CardBody>
            <div className="grid grid-cols-3 gap-6">
              {[
                {
                  label: t('dashboard.vectorDb'),
                  status: stats?.services?.milvus,
                  tooltip: 'Milvus 向量数据库，用于存储和检索文档向量的核心组件'
                },
                {
                  label: t('dashboard.embeddingApi'),
                  status: stats?.services?.embedding,
                  tooltip: '嵌入模型服务，负责将文本转换为向量表示，是 RAG 系统的核心能力'
                },
                {
                  label: t('dashboard.docProcessor'),
                  status: stats?.services?.doc_processor || stats?.services?.docProcessor,
                  tooltip: '文档处理器，负责解析上传的文档、分块、向量化并存入向量数据库'
                },
              ].map((svc, i) => {
                const isHealthy = svc.status === 'healthy' || svc.status === 'ok';
                return (
                  <div key={i} className="space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        <span className="text-[14px] text-[var(--text-secondary)]">{svc.label}</span>
                        <div className="group relative">
                          <HelpCircle className="w-3.5 h-3.5 text-[var(--text-tertiary)] cursor-help" />
                          <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-[var(--gray-900)] text-white text-[11px] rounded-lg whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity z-10 pointer-events-none max-w-[250px] shadow-lg">
                            {svc.tooltip}
                            <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-1 border-4 border-transparent border-t-[var(--gray-900)]" />
                          </div>
                        </div>
                      </div>
                      <Badge variant={isHealthy ? 'success' : 'error'}>
                        {isHealthy ? t('dashboard.healthy') : (svc.status ?? 'unknown')}
                      </Badge>
                    </div>
                    <div className="w-full h-2 rounded-full bg-[var(--gray-200)]">
                      <div
                        className="h-2 rounded-full transition-all duration-500"
                        style={{
                          width: isHealthy ? '100%' : '40%',
                          background: isHealthy ? 'var(--success)' : 'var(--error)'
                        }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
