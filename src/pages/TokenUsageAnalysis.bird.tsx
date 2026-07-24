import { useState, useEffect } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { Card, CardHeader, CardBody, CardTitle, Badge } from '@/src/components/bird';
import { Select } from '@/src/components/bird/Select';
import { cn } from '@/lib/utils';
import { Loader2, TrendingUp, DollarSign, Database, Activity } from 'lucide-react';
import {
  getMyTokenUsage,
  getMyTokenTrend,
  getMyQuota,
  TokenUsageStats,
  TokenUsageTrendItem,
  UserQuota,
} from '@/lib/api-client';

async function fetchMyTokenUsage(period: number) {
  const res = await fetch(`/api/v1/analytics/token-usage?period=${period}`);
  if (!res.ok) throw new Error('Failed to fetch token usage');
  return res.json();
}

async function fetchMyTokenTrend(period: number) {
  const res = await fetch(`/api/v1/analytics/token-trend?period=${period}`);
  if (!res.ok) throw new Error('Failed to fetch token trend');
  return res.json();
}

async function fetchMyQuota() {
  const res = await fetch('/api/v1/analytics/quota');
  if (!res.ok) throw new Error('Failed to fetch quota');
  return res.json();
}

export function TokenUsageAnalysisBird() {
  const { t } = useI18n();
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<TokenUsageStats | null>(null);
  const [trend, setTrend] = useState<TokenUsageTrendItem[]>([]);
  const [quota, setQuota] = useState<UserQuota | null>(null);
  const [period, setPeriod] = useState<string>('7');

  useEffect(() => {
    loadUsageData();
  }, [period]);

  const loadUsageData = async () => {
    setLoading(true);
    try {
      const [statsData, trendData, quotaData] = await Promise.all([
        fetchMyTokenUsage(parseInt(period)),
        fetchMyTokenTrend(parseInt(period)),
        fetchMyQuota().catch(() => null),
      ]);
      setStats(statsData);
      setTrend(trendData.items || []);
      setQuota(quotaData);
    } catch (e) {
      console.error('Failed to load usage data:', e);
    } finally {
      setLoading(false);
    }
  };

  const getQuotaPercentage = (used: number, limit?: number) => {
    if (!limit) return 0;
    return Math.min(100, Math.round((used / limit) * 100));
  };

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-[#7c3aed]" />
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-[#f9fafb]">
      {/* Header */}
      <header className="h-[60px] px-6 bg-white flex items-center justify-between shrink-0 border-b border-[#e5e7eb]">
        <div className="flex items-baseline gap-3">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-[#ede9fe] flex items-center justify-center">
              <TrendingUp className="w-5 h-5 text-[#7c3aed]" />
            </div>
            <div>
              <h1 className="text-[18px] font-semibold text-[#111827]">Token 使用分析</h1>
              <p className="text-[12px] text-[#6b7280]">查看和分析 Token 消耗情况</p>
            </div>
          </div>
        </div>
        <Select value={period} onValueChange={setPeriod} className="w-[140px]">
          <option value="7">最近 7 天</option>
          <option value="14">最近 14 天</option>
          <option value="30">最近 30 天</option>
          <option value="90">最近 90 天</option>
        </Select>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
          <StatCard
            icon={Database}
            label="总 Token"
            value={stats?.totalTokens ? stats.totalTokens.toLocaleString() : '-'}
            subValue={stats ? `${stats.inputTokens ?? 0} 输入 / ${stats.outputTokens ?? 0} 输出` : ''}
            color="primary"
          />
          <StatCard
            icon={DollarSign}
            label="总费用"
            value={stats?.totalCost !== undefined ? `$${stats.totalCost.toFixed(4)}` : '-'}
            subValue={stats?.requestCount ? `${stats.requestCount.toLocaleString()} 次请求` : ''}
            color="success"
          />
          <StatCard
            icon={Activity}
            label="日均请求"
            value={stats && stats.requestCount && period ? Math.round(stats.requestCount / parseInt(period)) : '-'}
            subValue="次/天"
            color="info"
          />
          <StatCard
            icon={TrendingUp}
            label="平均 Token/请求"
            value={stats && stats.requestCount > 0 && stats.totalTokens ? Math.round(stats.totalTokens / stats.requestCount) : '-'}
            subValue="tokens"
            color="warning"
          />
        </div>

        {/* Quota Progress */}
        {quota && (
          <Card className="mb-6">
            <CardHeader>
              <CardTitle>配额使用情况</CardTitle>
            </CardHeader>
            <CardBody>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Daily Quota */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[13px] text-[#6b7280]">今日配额</span>
                    <span className="text-[12px] text-[#9ca3af]">
                      {(quota.usedDailyTokens ?? 0).toLocaleString()} / {quota.dailyTokenLimit?.toLocaleString() ?? '∞'}
                    </span>
                  </div>
                  <div className="h-2 rounded-full bg-[#f3f4f6]">
                    <div
                      className={cn(
                        "h-2 rounded-full transition-all",
                        getQuotaPercentage(quota.usedDailyTokens ?? 0, quota.dailyTokenLimit) > 90 ? "bg-[#ef4444]" : "bg-[#7c3aed]"
                      )}
                      style={{ width: `${getQuotaPercentage(quota.usedDailyTokens ?? 0, quota.dailyTokenLimit)}%` }}
                    />
                  </div>
                  <div className="text-[11px] text-[#9ca3af]">
                    剩余：{(quota.dailyTokenLimit ?? 0) - (quota.usedDailyTokens ?? 0)} tokens
                  </div>
                </div>

                {/* Monthly Quota */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[13px] text-[#6b7280]">本月配额</span>
                    <span className="text-[12px] text-[#9ca3af]">
                      {(quota.usedMonthlyTokens ?? 0).toLocaleString()} / {quota.monthlyTokenLimit?.toLocaleString() ?? '∞'}
                    </span>
                  </div>
                  <div className="h-2 rounded-full bg-[#f3f4f6]">
                    <div
                      className={cn(
                        "h-2 rounded-full transition-all",
                        getQuotaPercentage(quota.usedMonthlyTokens ?? 0, quota.monthlyTokenLimit) > 90 ? "bg-[#ef4444]" : "bg-[#3b82f6]"
                      )}
                      style={{ width: `${getQuotaPercentage(quota.usedMonthlyTokens ?? 0, quota.monthlyTokenLimit)}%` }}
                    />
                  </div>
                  <div className="text-[11px] text-[#9ca3af]">
                    剩余：{(quota.monthlyTokenLimit ?? 0) - (quota.usedMonthlyTokens ?? 0)} tokens
                  </div>
                </div>
              </div>
            </CardBody>
          </Card>
        )}

        {/* Trend Chart */}
        <Card>
          <CardHeader>
            <CardTitle>使用趋势</CardTitle>
          </CardHeader>
          <CardBody>
            {trend.length === 0 ? (
              <div className="flex items-center justify-center py-12">
                <p className="text-[13px] text-[#9ca3af]">暂无数据</p>
              </div>
            ) : (
              <div className="flex items-end gap-2 h-40">
                {trend.map((item, i) => {
                  const maxTokens = Math.max(...trend.map(t => t.totalTokens), 1);
                  const height = Math.max(8, (item.totalTokens / maxTokens) * 100);
                  return (
                    <div key={i} className="flex-1 flex flex-col items-center gap-1 min-w-0 group">
                      <div
                        className="w-full rounded-t-lg bg-gradient-to-t from-[#7c3aed] to-[#a78bfa] transition-all hover:opacity-80 cursor-pointer"
                        style={{ height: `${height}%` }}
                        title={`${item.date}: ${(item.totalTokens ?? 0).toLocaleString()} tokens, $${(item.cost ?? 0).toFixed(4)}`}
                      />
                      <span className="text-[10px] text-[#9ca3af] truncate w-full text-center">
                        {item.date.slice(5)}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  subValue,
  color,
}: {
  icon: any;
  label: string;
  value: string | number;
  subValue?: string;
  color: 'primary' | 'success' | 'info' | 'warning';
}) {
  const colorMap = {
    primary: { bg: 'bg-[#ede9fe]', text: 'text-[#7c3aed]', icon: '#7c3aed' },
    success: { bg: 'bg-[#d1fae5]', text: 'text-[#10b981]', icon: '#10b981' },
    info: { bg: 'bg-[#dbeafe]', text: 'text-[#3b82f6]', icon: '#3b82f6' },
    warning: { bg: 'bg-[#fef3c7]', text: 'text-[#f59e0b]', icon: '#f59e0b' },
  };

  const c = colorMap[color];

  return (
    <Card>
      <CardBody>
        <div className="flex items-center gap-3 mb-3">
          <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center", c.bg)}>
            <Icon className={cn("w-5 h-5", c.text)} />
          </div>
          <span className="text-[13px] text-[#6b7280]">{label}</span>
        </div>
        <div className="text-[24px] font-semibold text-[#111827] mb-1">{value}</div>
        {subValue && <div className="text-[11px] text-[#9ca3af]">{subValue}</div>}
      </CardBody>
    </Card>
  );
}
