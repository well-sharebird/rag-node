import { useState, useEffect } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Loader2, Users, Settings2, AlertCircle } from 'lucide-react';
import {
  fetchAllQuotas,
  setUserQuota,
  UserQuota,
  UserData,
  fetchUsers,
} from '@/lib/api-client';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';

export function QuotaManagement() {
  const { t } = useI18n();
  const [loading, setLoading] = useState(true);
  const [quotas, setQuotas] = useState<Array<UserQuota & { username: string; email: string }>>([]);
  const [users, setUsers] = useState<UserData[]>([]);
  const [editingQuota, setEditingQuota] = useState<UserQuota | null>(null);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [formData, setFormData] = useState({
    dailyTokenLimit: '',
    monthlyTokenLimit: '',
    dailyCostLimit: '',
    monthlyCostLimit: '',
    isActive: true,
    exceededAction: 'block',
  });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [quotasData, usersData] = await Promise.all([
        fetchAllQuotas().catch(() => ({ items: [] })),
        fetchUsers().catch(() => ({ items: [] })),
      ]);
      setQuotas(quotasData?.items || []);
      setUsers(usersData?.items || []);
    } catch (e) {
      console.error('Failed to load data:', e);
      toast.error('加载数据失败');
    } finally {
      setLoading(false);
    }
  };

  const handleEdit = (quota: UserQuota) => {
    setEditingQuota(quota);
    setFormData({
      dailyTokenLimit: quota.dailyTokenLimit?.toString() ?? '',
      monthlyTokenLimit: quota.monthlyTokenLimit?.toString() ?? '',
      dailyCostLimit: quota.dailyCostLimit?.toString() ?? '',
      monthlyCostLimit: quota.monthlyCostLimit?.toString() ?? '',
      isActive: quota.isActive,
      exceededAction: quota.exceededAction,
    });
    setIsEditOpen(true);
  };

  const handleSave = async () => {
    if (!editingQuota) return;

    try {
      await setUserQuota(editingQuota.userId, {
        dailyTokenLimit: formData.dailyTokenLimit ? parseInt(formData.dailyTokenLimit) : undefined,
        monthlyTokenLimit: formData.monthlyTokenLimit ? parseInt(formData.monthlyTokenLimit) : undefined,
        dailyCostLimit: formData.dailyCostLimit ? parseFloat(formData.dailyCostLimit) : undefined,
        monthlyCostLimit: formData.monthlyCostLimit ? parseFloat(formData.monthlyCostLimit) : undefined,
        isActive: formData.isActive,
        exceededAction: formData.exceededAction as 'block' | 'warn' | 'log',
      });
      toast.success('配额已更新');
      setIsEditOpen(false);
      loadData();
    } catch (e: any) {
      toast.error(`更新失败：${e.message}`);
    }
  };

  const getQuotaStatus = (quota: UserQuota) => {
    if (!quota.isActive) return { label: '未启用', color: '#999999', bg: '#f0f0f0' };
    const usage = quota.monthlyTokenLimit ? quota.usedMonthlyTokens / quota.monthlyTokenLimit : 0;
    if (usage > 0.9) return { label: '即将超额', color: '#ff5252', bg: '#ffebee' };
    if (usage > 0.7) return { label: '使用中', color: '#ff9800', bg: '#fff3e0' };
    return { label: '正常', color: '#00c853', bg: '#e8f5e9' };
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
          <h1 className="text-[18px] font-semibold text-[#1a1a1a]">配额管理</h1>
          <span className="text-[13px] text-[#999999]">管理用户 Token 使用配额</span>
        </div>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6 bg-[#f7f7f7]">
        {/* Summary Cards */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          <Card className="rounded-2xl border border-[#e5e5e5] bg-white p-4">
            <div className="flex items-center gap-3 mb-2">
              <div className="w-9 h-9 rounded-xl flex items-center justify-center bg-[#e3f2fd]">
                <Users className="w-5 h-5 text-[#2196f3]" />
              </div>
              <span className="text-[13px] text-[#666666]">总用户数</span>
            </div>
            <div className="text-[24px] font-semibold text-[#1a1a1a]">{users.length}</div>
          </Card>
          <Card className="rounded-2xl border border-[#e5e5e5] bg-white p-4">
            <div className="flex items-center gap-3 mb-2">
              <div className="w-9 h-9 rounded-xl flex items-center justify-center bg-[#e8f5e9]">
                <Settings2 className="w-5 h-5 text-[#00c853]" />
              </div>
              <span className="text-[13px] text-[#666666]">已配置配额</span>
            </div>
            <div className="text-[24px] font-semibold text-[#1a1a1a]">{quotas.filter(q => q.isActive).length}</div>
          </Card>
          <Card className="rounded-2xl border border-[#e5e5e5] bg-white p-4">
            <div className="flex items-center gap-3 mb-2">
              <div className="w-9 h-9 rounded-xl flex items-center justify-center bg-[#fff3e0]">
                <AlertCircle className="w-5 h-5 text-[#ff9800]" />
              </div>
              <span className="text-[13px] text-[#666666]">即将超额</span>
            </div>
            <div className="text-[24px] font-semibold text-[#1a1a1a]">
              {quotas.filter(q => {
                const status = getQuotaStatus(q);
                return status.label === '即将超额';
              }).length}
            </div>
          </Card>
        </div>

        {/* Quota List */}
        <Card className="rounded-2xl border border-[#e5e5e5] bg-white">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[#e5e5e5]">
                  <th className="text-left text-[12px] font-medium text-[#999999] px-5 py-3">用户</th>
                  <th className="text-left text-[12px] font-medium text-[#999999] px-5 py-3">状态</th>
                  <th className="text-right text-[12px] font-medium text-[#999999] px-5 py-3">每日配额</th>
                  <th className="text-right text-[12px] font-medium text-[#999999] px-5 py-3">每月配额</th>
                  <th className="text-right text-[12px] font-medium text-[#999999] px-5 py-3">已用 (日/月)</th>
                  <th className="text-right text-[12px] font-medium text-[#999999] px-5 py-3">超额处理</th>
                  <th className="text-right text-[12px] font-medium text-[#999999] px-5 py-3">操作</th>
                </tr>
              </thead>
              <tbody>
                {quotas.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="text-center py-12">
                      <p className="text-[13px] text-[#999999]">暂无配额配置</p>
                    </td>
                  </tr>
                ) : (
                  quotas.map((quota) => {
                    const status = getQuotaStatus(quota);
                    return (
                      <tr key={quota.id} className="border-b border-[#f0f0f0] hover:bg-[#fafafa]">
                        <td className="px-5 py-4">
                          <div>
                            <div className="text-[14px] font-medium text-[#1a1a1a]">{quota.username}</div>
                            <div className="text-[12px] text-[#999999]">{quota.email}</div>
                          </div>
                        </td>
                        <td className="px-5 py-4">
                          <Badge
                            className="rounded-full text-[11px] px-2.5 py-1"
                            style={{ background: status.bg, color: status.color }}
                          >
                            {status.label}
                          </Badge>
                        </td>
                        <td className="px-5 py-4 text-right">
                          <div className="text-[14px] text-[#1a1a1a]">
                            {quota.dailyTokenLimit?.toLocaleString() ?? '∞'}
                          </div>
                          <div className="text-[11px] text-[#999999]">
                            ${quota.dailyCostLimit?.toFixed(2) ?? '∞'}
                          </div>
                        </td>
                        <td className="px-5 py-4 text-right">
                          <div className="text-[14px] text-[#1a1a1a]">
                            {quota.monthlyTokenLimit?.toLocaleString() ?? '∞'}
                          </div>
                          <div className="text-[11px] text-[#999999]">
                            ${quota.monthlyCostLimit?.toFixed(2) ?? '∞'}
                          </div>
                        </td>
                        <td className="px-5 py-4 text-right">
                          <div className="text-[14px] text-[#1a1a1a]">
                            {quota.usedDailyTokens.toLocaleString()} / {quota.usedMonthlyTokens.toLocaleString()}
                          </div>
                        </td>
                        <td className="px-5 py-4 text-right">
                          <Badge variant="secondary" className="rounded-full text-[11px] bg-[#f5f5f5] text-[#666666]">
                            {quota.exceededAction === 'block' ? '阻断' : quota.exceededAction === 'warn' ? '警告' : '记录'}
                          </Badge>
                        </td>
                        <td className="px-5 py-4 text-right">
                          <Button
                            size="sm"
                            variant="outline"
                            className="rounded-full h-8 text-[13px]"
                            onClick={() => handleEdit(quota)}
                          >
                            编辑
                          </Button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      {/* Edit Dialog */}
      <Dialog open={isEditOpen} onOpenChange={setIsEditOpen}>
        <DialogContent className="max-w-lg rounded-3xl">
          <DialogHeader>
            <DialogTitle>编辑配额</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="text-[13px] text-[#666666]">每日 Token 限制</Label>
                <Input
                  type="number"
                  value={formData.dailyTokenLimit}
                  onChange={(e) => setFormData({ ...formData, dailyTokenLimit: e.target.value })}
                  placeholder="如：100000"
                  className="rounded-full h-10 border-[#e5e5e5]"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-[13px] text-[#666666]">每月 Token 限制</Label>
                <Input
                  type="number"
                  value={formData.monthlyTokenLimit}
                  onChange={(e) => setFormData({ ...formData, monthlyTokenLimit: e.target.value })}
                  placeholder="如：1000000"
                  className="rounded-full h-10 border-[#e5e5e5]"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="text-[13px] text-[#666666]">每日费用限制</Label>
                <Input
                  type="number"
                  step="0.01"
                  value={formData.dailyCostLimit}
                  onChange={(e) => setFormData({ ...formData, dailyCostLimit: e.target.value })}
                  placeholder="如：10.00"
                  className="rounded-full h-10 border-[#e5e5e5]"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-[13px] text-[#666666]">每月费用限制</Label>
                <Input
                  type="number"
                  step="0.01"
                  value={formData.monthlyCostLimit}
                  onChange={(e) => setFormData({ ...formData, monthlyCostLimit: e.target.value })}
                  placeholder="如：100.00"
                  className="rounded-full h-10 border-[#e5e5e5]"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label className="text-[13px] text-[#666666]">超额处理方式</Label>
              <Select
                value={formData.exceededAction}
                onValueChange={(v) => setFormData({ ...formData, exceededAction: v })}
              >
                <SelectTrigger className="rounded-full h-10 border-[#e5e5e5]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="rounded-xl border-[#e5e5e5]">
                  <SelectItem value="block">阻断 - 禁止超额使用</SelectItem>
                  <SelectItem value="warn">警告 - 允许但发送警告</SelectItem>
                  <SelectItem value="log">记录 - 仅记录日志</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-3 pt-2">
              <Switch
                checked={formData.isActive}
                onCheckedChange={(v) => setFormData({ ...formData, isActive: v })}
              />
              <Label className="text-[14px] text-[#666666]">启用配额限制</Label>
            </div>
          </div>
          <DialogFooter className="rounded-b-3xl">
            <Button variant="outline" onClick={() => setIsEditOpen(false)} className="rounded-full">取消</Button>
            <Button onClick={handleSave} className="rounded-full bg-[#1a1a1a] hover:bg-[#333333]">保存</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
