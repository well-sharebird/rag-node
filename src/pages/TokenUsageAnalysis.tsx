import { useState, useEffect } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Loader2, TrendingUp, DollarSign, Database, Activity } from 'lucide-react';
import {
  fetchMyTokenUsage,
  fetchMyTokenTrend,
  fetchMyQuota,
  TokenUsageStats,
  TokenUsageTrendItem,
  UserQuota,
} from '@/lib/api-client';
import { cn } from '@/lib/utils';

export function TokenUsageAnalysis() {
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
        <Loader2 className="w-8 h-8 animate-spin text-[#ff6a00]" />
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <header className="h-[60px] px-6 bg-white flex items-center justify-between shrink-0 border-b border-[#e5e5e5]">
        <div className="flex items-baseline gap-3">
          <h1 className="text-[18px] font-semibold text-[#1a1a1a]">Token 使用分析</h1>
          <span className="text-[13px] text-[#999999]">查看和分析 Token 消耗情况</span>
        </div>
        <Select value={period} onValueChange={setPeriod}>
          <SelectTrigger className="w-[140px] rounded-full h-9 border-[#e5e5e5] bg-white">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="rounded-xl border-[#e5e5e5]">
            <SelectItem value="7">最近 7 天</SelectItem>
            <SelectItem value="14">最近 14 天</SelectItem>
            <SelectItem value="30">最近 30 天</SelectItem>
            <SelectItem value="90">最近 90 天</SelectItem>
          </SelectContent>
        </Select>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6 bg-[#f7f7f7]">
        {/* Stats Cards */}
        <div className="grid grid-cols-4 gap-4 mb-6">
          <StatCard
            icon={Database}
            label="总 Token"
            value={stats?.totalTokens ? stats.totalTokens.toLocaleString() : '-'}
            subValue={stats ? `${stats.inputTokens ?? 0} 输入 / ${stats.outputTokens ?? 0} 输出` : ''}
            color="#ff6a00"
          />
          <StatCard
            icon={DollarSign}
            label="总费用"
            value={stats?.totalCost !== undefined ? `$${stats.totalCost.toFixed(4)}` : '-'}
            subValue={stats?.requestCount ? `${stats.requestCount.toLocaleString()} 次请求` : ''}
            color="#00c853"
          />
          <StatCard
            icon={Activity}
            label="日均请求"
            value={stats && stats.requestCount && period ? Math.round(stats.requestCount / parseInt(period)) : '-'}
            subValue="次/天"
            color="#2196f3"
          />
          <StatCard
            icon={TrendingUp}
            label="平均 Token/请求"
            value={stats && stats.requestCount > 0 && stats.totalTokens ? Math.round(stats.totalTokens / stats.requestCount) : '-'}
            subValue="tokens"
            color="#7c4dff"
          />
        </div>

        {/* Quota Progress */}
        {quota && (
          <Card className="rounded-2xl border border-[#e5e5e5] bg-white p-5 mb-6">
            <h3 className="text-[15px] font-semibold text-[#1a1a1a] mb-4">配额使用情况</h3>
            <div className="grid grid-cols-2 gap-6">
              {/* Daily Quota */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[13px] text-[#666666]">今日配额</span>
                  <span className="text-[12px] text-[#999999]">
                    {(quota.usedDailyTokens ?? 0).toLocaleString()} / {quota.dailyTokenLimit?.toLocaleString() ?? '∞'}
                  </span>
                </div>
                <div className="h-2 rounded-full bg-[#f0f0f0]">
                  <div
                    className={cn(
                      "h-2 rounded-full transition-all",
                      getQuotaPercentage(quota.usedDailyTokens ?? 0, quota.dailyTokenLimit) > 90 ? "bg-[#ff5252]" : "bg-[#ff6a00]"
                    )}
                    style={{ width: `${getQuotaPercentage(quota.usedDailyTokens ?? 0, quota.dailyTokenLimit)}%` }}
                  />
                </div>
                <div className="text-[11px] text-[#999999]">
                  剩余：{(quota.dailyTokenLimit ?? 0) - (quota.usedDailyTokens ?? 0)} tokens
                </div>
              </div>

              {/* Monthly Quota */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[13px] text-[#666666]">本月配额</span>
                  <span className="text-[12px] text-[#999999]">
                    {(quota.usedMonthlyTokens ?? 0).toLocaleString()} / {quota.monthlyTokenLimit?.toLocaleString() ?? '∞'}
                  </span>
                </div>
                <div className="h-2 rounded-full bg-[#f0f0f0]">
                  <div
                    className={cn(
                      "h-2 rounded-full transition-all",
                      getQuotaPercentage(quota.usedMonthlyTokens ?? 0, quota.monthlyTokenLimit) > 90 ? "bg-[#ff5252]" : "bg-[#2196f3]"
                    )}
                    style={{ width: `${getQuotaPercentage(quota.usedMonthlyTokens ?? 0, quota.monthlyTokenLimit)}%` }}
                  />
                </div>
                <div className="text-[11px] text-[#999999]">
                  剩余：{(quota.monthlyTokenLimit ?? 0) - (quota.usedMonthlyTokens ?? 0)} tokens
                </div>
              </div>
            </div>
          </Card>
        )}

        {/* Trend Chart */}
        <Card className="rounded-2xl border border-[#e5e5e5] bg-white p-5">
          <h3 className="text-[15px] font-semibold text-[#1a1a1a] mb-4">使用趋势</h3>
          {trend.length === 0 ? (
            <div className="flex items-center justify-center py-12">
              <p className="text-[13px] text-[#999999]">暂无数据</p>
            </div>
          ) : (
            <div className="flex items-end gap-2 h-40">
              {trend.map((item, i) => {
                const maxTokens = Math.max(...trend.map(t => t.totalTokens), 1);
                const height = Math.max(8, (item.totalTokens / maxTokens) * 100);
                return (
                  <div key={i} className="flex-1 flex flex-col items-center gap-1 min-w-0 group">
                    <div
                      className="w-full rounded-t-lg bg-gradient-to-t from-[#ff6a00] to-[#ff9f4d] transition-all hover:opacity-80 cursor-pointer"
                      style={{ height: `${height}%` }}
                      title={`${item.date}: ${(item.totalTokens ?? 0).toLocaleString()} tokens, $${(item.cost ?? 0).toFixed(4)}`}
                    />
                    <span className="text-[10px] text-[#999999] truncate w-full text-center">
                      {item.date.slice(5)}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
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
  color: string;
}) {
  return (
    <Card className="rounded-2xl border border-[#e5e5e5] bg-white p-4">
      <div className="flex items-center gap-3 mb-3">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center"
          style={{ background: `${color}15` }}
        >
          <Icon className="w-5 h-5" style={{ color }} />
        </div>
        <span className="text-[13px] text-[#666666]">{label}</span>
      </div>
      <div className="text-[24px] font-semibold text-[#1a1a1a] mb-1">{value}</div>
      {subValue && <div className="text-[11px] text-[#999999]">{subValue}</div>}
    </Card>
  );
}
