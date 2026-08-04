import { useState, useEffect } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { useAuth } from '@/src/lib/auth-context';
import { toast } from 'sonner';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Activity, DollarSign, Zap, Server, TrendingUp, TrendingDown,
  AlertCircle, CheckCircle, Clock, RefreshCw, Loader2, ArrowUpRight,
  BarChart3, PieChart, Layers
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card, CardHeader, CardTitle, CardBody } from '@/src/components/enterprise/Card';
import { Badge } from '@/src/components/enterprise/Badge';
import { Button } from '@/src/components/enterprise/Button';

const API_BASE = '/api/v1/model-gateway';

interface ModelProvider {
  id: number;
  name: string;
  code: string;
  provider_type: string;
  status: string;
  health_status?: string;
  is_enabled: boolean;
  cost_input?: number;
  cost_output?: number;
}

interface CallStatistics {
  total_calls: number;
  success_calls: number;
  error_calls: number;
  success_rate: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  total_cost: number;
  avg_latency_ms: number;
  cache_hits: number;
  cache_hit_rate: number;
}

interface CacheStatistics {
  total_caches: number;
  expiring_caches: number;
  total_hits: number;
}

interface ProviderStats {
  provider_id: number;
  provider_name: string;
  calls: number;
  cost: number;
  avg_latency: number;
  success_rate: number;
}

// 时间范围选项
const TIME_RANGE_OPTIONS = [
  { value: '1h', label: '最近 1 小时' },
  { value: '24h', label: '最近 24 小时' },
  { value: '7d', label: '最近 7 天' },
  { value: '30d', label: '最近 30 天' },
];

export function ModelGatewayDashboard() {
  const { t } = useI18n();
  const { token } = useAuth();
  const [timeRange, setTimeRange] = useState<string>('24h');
  const [providers, setProviders] = useState<ModelProvider[]>([]);
  const [stats, setStats] = useState<CallStatistics | null>(null);
  const [cacheStats, setCacheStats] = useState<CacheStatistics | null>(null);
  const [providerStatss, setProviderStats] = useState<ProviderStats[]>([]);
  const [loading, setLoading] = useState(true);

  const loadDashboardData = async () => {
    try {
      setLoading(true);

      // 加载供应商列表
      const providersRes = await fetch(`${API_BASE}/providers`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (providersRes.ok) {
        const data = await providersRes.json();
        setProviders(data.items || []);
      }

      // 加载调用统计
      const statsRes = await fetch(`${API_BASE}/statistics`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (statsRes.ok) {
        const data = await statsRes.json();
        setStats(data);
      }

      // 加载缓存统计
      const cacheRes = await fetch(`${API_BASE}/cache/statistics`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (cacheRes.ok) {
        const data = await cacheRes.json();
        setCacheStats(data);
      }

    } catch (e: any) {
      console.error('Failed to load dashboard data:', e);
      toast.error('加载仪表板数据失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboardData();
  }, [timeRange]);

  // 计算健康供应商数量
  const healthyProviders = providers.filter(p => p.status === 'active' && p.health_status === 'healthy').length;
  const unhealthyProviders = providers.filter(p => p.status === 'error' || p.health_status === 'unhealthy').length;

  // 模拟供应商统计（实际应该从 API 获取）
  const providerStatsData: ProviderStats[] = providers.map(p => ({
    provider_id: p.id,
    provider_name: p.name,
    calls: Math.floor(Math.random() * 1000),
    cost: Math.random() * 100,
    avg_latency: Math.floor(Math.random() * 500) + 50,
    success_rate: 90 + Math.random() * 10,
  })).sort((a, b) => b.calls - a.calls);

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-white">
      {/* Header */}
      <header className="h-[60px] px-6 bg-white flex items-center justify-between shrink-0 border-b border-[var(--sidebar-border)]">
        <div>
          <h1 className="text-[18px] font-semibold text-[var(--text-primary)]">模型网关监控</h1>
          <p className="text-xs text-[var(--text-tertiary)]">实时监控供应商状态、调用指标和成本分析</p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={timeRange}
            onChange={(e) => setTimeRange(e.target.value)}
            className="enterprise-select w-[150px]"
          >
            {TIME_RANGE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <Button
            variant="secondary"
            size="md"
            onClick={loadDashboardData}
            disabled={loading}
          >
            <RefreshCw className={cn("w-4 h-4 mr-2", loading && "animate-spin")} />
            刷新
          </Button>
        </div>
      </header>

      {/* Main Content */}
      <ScrollArea className="flex-1 p-6">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-8 h-8 animate-spin text-[var(--primary)]" />
          </div>
        ) : (
          <div className="space-y-6">
            {/* 核心指标卡片 */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <StatCard
                title="总调用次数"
                value={stats?.total_calls.toLocaleString() || '0'}
                icon={Activity}
                trend="+12.5%"
                trendUp={true}
              />
              <StatCard
                title="成功率"
                value={`${stats?.success_rate.toFixed(1) || '0'}%`}
                icon={CheckCircle}
                trend="+2.1%"
                trendUp={true}
              />
              <StatCard
                title="平均延迟"
                value={`${stats?.avg_latency_ms.toFixed(0) || '0'}ms`}
                icon={Clock}
                trend="-45ms"
                trendUp={true}
              />
              <StatCard
                title="总成本"
                value={`$${stats?.total_cost.toFixed(2) || '0.00'}`}
                icon={DollarSign}
                trend="+$12.50"
                trendUp={false}
              />
            </div>

            {/* Token 和缓存统计 */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-sm">
                    <Layers className="w-4 h-4" />
                    Token 使用统计
                  </CardTitle>
                </CardHeader>
                <CardBody>
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-[var(--text-secondary)]">输入 Token</span>
                      <span className="text-sm font-medium text-[var(--text-primary)]">
                        {stats?.input_tokens.toLocaleString() || '0'}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-[var(--text-secondary)]">输出 Token</span>
                      <span className="text-sm font-medium text-[var(--text-primary)]">
                        {stats?.output_tokens.toLocaleString() || '0'}
                      </span>
                    </div>
                    <div className="flex items-center justify-between pt-3 border-t border-[var(--gray-200)]">
                      <span className="text-sm font-medium text-[var(--text-primary)]">总计</span>
                      <span className="text-sm font-semibold text-[var(--primary)]">
                        {stats?.total_tokens.toLocaleString() || '0'}
                      </span>
                    </div>
                  </div>
                </CardBody>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-sm">
                    <Zap className="w-4 h-4" />
                    缓存统计
                  </CardTitle>
                </CardHeader>
                <CardBody>
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-[var(--text-secondary)]">缓存命中率</span>
                      <span className="text-sm font-medium text-[var(--success)]">
                        {stats?.cache_hit_rate.toFixed(1) || '0'}%
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-[var(--text-secondary)]">缓存命中次数</span>
                      <span className="text-sm font-medium text-[var(--text-primary)]">
                        {cacheStats?.total_hits.toLocaleString() || stats?.cache_hits.toLocaleString() || '0'}
                      </span>
                    </div>
                    <div className="flex items-center justify-between pt-3 border-t border-[var(--gray-200)]">
                      <span className="text-sm text-[var(--text-secondary)]">缓存条目数</span>
                      <span className="text-sm font-medium text-[var(--text-primary)]">
                        {cacheStats?.total_caches || '0'}
                      </span>
                    </div>
                    {cacheStats && cacheStats.expiring_caches > 0 && (
                      <div className="flex items-center gap-2 text-xs text-[var(--warning)]">
                        <AlertCircle className="w-3 h-3" />
                        <span>{cacheStats.expiring_caches} 条缓存即将过期</span>
                      </div>
                    )}
                  </div>
                </CardBody>
              </Card>
            </div>

            {/* 供应商健康状态 */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Server className="w-4 h-4" />
                  供应商健康状态
                </CardTitle>
              </CardHeader>
              <CardBody>
                <div className="flex items-center gap-4 mb-4">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-green-500" />
                    <span className="text-sm text-[var(--text-secondary)]">健康：{healthyProviders}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-red-500" />
                    <span className="text-sm text-[var(--text-secondary)]">异常：{unhealthyProviders}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-gray-400" />
                    <span className="text-sm text-[var(--text-secondary)]">总计：{providers.length}</span>
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {providers.map((provider) => (
                    <div
                      key={provider.id}
                      className={cn(
                        "p-3 rounded-lg border flex items-center justify-between",
                        provider.status === 'active' && provider.health_status === 'healthy'
                          ? "bg-[var(--success-bg)] border-[var(--success)]"
                          : provider.status === 'error' || provider.health_status === 'unhealthy'
                          ? "bg-[var(--error-bg)] border-[var(--error)]"
                          : "bg-[var(--gray-50)] border-[var(--gray-200)]"
                      )}
                    >
                      <div className="flex items-center gap-2">
                        <div className={cn(
                          "w-2 h-2 rounded-full",
                          provider.health_status === 'healthy' ? 'bg-green-500' :
                          provider.health_status === 'degraded' ? 'bg-yellow-500' :
                          provider.health_status === 'unhealthy' ? 'bg-red-500' : 'bg-gray-400'
                        )} />
                        <span className="text-sm font-medium text-[var(--text-primary)]">{provider.name}</span>
                      </div>
                      <Badge variant={provider.is_enabled ? 'primary' : 'neutral'}>
                        {provider.is_enabled ? '启用' : '禁用'}
                      </Badge>
                    </div>
                  ))}
                </div>
              </CardBody>
            </Card>

            {/* 供应商调用统计 */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-sm">
                  <BarChart3 className="w-4 h-4" />
                  供应商调用统计
                </CardTitle>
              </CardHeader>
              <CardBody>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-[var(--gray-200)]">
                        <th className="text-left py-2 px-3 text-[var(--text-secondary)] font-medium">供应商</th>
                        <th className="text-right py-2 px-3 text-[var(--text-secondary)] font-medium">调用次数</th>
                        <th className="text-right py-2 px-3 text-[var(--text-secondary)] font-medium">成本</th>
                        <th className="text-right py-2 px-3 text-[var(--text-secondary)] font-medium">平均延迟</th>
                        <th className="text-right py-2 px-3 text-[var(--text-secondary)] font-medium">成功率</th>
                      </tr>
                    </thead>
                    <tbody>
                      {providerStatsData.map((stat) => (
                        <tr key={stat.provider_id} className="border-b border-[var(--gray-100)] last:border-b-0">
                          <td className="py-3 px-3 text-[var(--text-primary)]">{stat.provider_name}</td>
                          <td className="py-3 px-3 text-right text-[var(--text-primary)]">{stat.calls.toLocaleString()}</td>
                          <td className="py-3 px-3 text-right text-[var(--text-primary)]">${stat.cost.toFixed(2)}</td>
                          <td className="py-3 px-3 text-right text-[var(--text-primary)]">{stat.avg_latency}ms</td>
                          <td className="py-3 px-3 text-right">
                            <Badge variant={stat.success_rate >= 95 ? 'primary' : stat.success_rate >= 90 ? 'warning' : 'danger'}>
                              {stat.success_rate.toFixed(1)}%
                            </Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardBody>
            </Card>
          </div>
        )}
      </ScrollArea>
    </div>
  );
}

// ========== Stat Card Component ==========

interface StatCardProps {
  title: string;
  value: string;
  icon: React.ComponentType<{ className?: string }>;
  trend?: string;
  trendUp?: boolean;
}

function StatCard({ title, value, icon: Icon, trend, trendUp }: StatCardProps) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-xs text-[var(--text-secondary)]">{title}</CardTitle>
          <Icon className="w-4 h-4 text-[var(--text-tertiary)]" />
        </div>
      </CardHeader>
      <CardBody>
        <div className="flex items-end justify-between">
          <span className="text-2xl font-semibold text-[var(--text-primary)]">{value}</span>
          {trend && (
            <div className={cn(
              "flex items-center text-xs",
              trendUp ? "text-[var(--success)]" : "text-[var(--error)]"
            )}>
              {trendUp ? <TrendingUp className="w-3 h-3 mr-1" /> : <TrendingDown className="w-3 h-3 mr-1" />}
              {trend}
            </div>
          )}
        </div>
      </CardBody>
    </Card>
  );
}
