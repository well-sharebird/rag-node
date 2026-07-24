import { useState, useEffect } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { Card, CardHeader, CardBody, CardTitle, Badge, Button, Input, Modal, Switch } from '@/src/components/bird';
import { Select } from '@/src/components/bird/Select';
import { cn } from '@/lib/utils';
import { Loader2, Users, Settings2, AlertCircle } from 'lucide-react';
import {
  fetchAllQuotas,
  setUserQuota,
  UserQuota,
  UserData,
  fetchUsers,
} from '@/lib/api-client';
import { toast } from 'sonner';

export function QuotaManagementBird() {
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
    if (!quota.isActive) return { label: '未启用', variant: 'neutral' as const };
    const usage = quota.monthlyTokenLimit ? quota.usedMonthlyTokens / quota.monthlyTokenLimit : 0;
    if (usage > 0.9) return { label: '即将超额', variant: 'error' as const };
    if (usage > 0.7) return { label: '使用中', variant: 'warning' as const };
    return { label: '正常', variant: 'success' as const };
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
              <Settings2 className="w-5 h-5 text-[#7c3aed]" />
            </div>
            <div>
              <h1 className="text-[18px] font-semibold text-[#111827]">配额管理</h1>
              <p className="text-[12px] text-[#6b7280]">管理用户 Token 使用配额</p>
            </div>
          </div>
        </div>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {/* Summary Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <Card>
            <CardBody>
              <div className="flex items-center gap-3 mb-2">
                <div className="w-9 h-9 rounded-xl flex items-center justify-center bg-[#dbeafe]">
                  <Users className="w-5 h-5 text-[#3b82f6]" />
                </div>
                <span className="text-[13px] text-[#6b7280]">总用户数</span>
              </div>
              <div className="text-[24px] font-semibold text-[#111827]">{users.length}</div>
            </CardBody>
          </Card>
          <Card>
            <CardBody>
              <div className="flex items-center gap-3 mb-2">
                <div className="w-9 h-9 rounded-xl flex items-center justify-center bg-[#d1fae5]">
                  <Settings2 className="w-5 h-5 text-[#10b981]" />
                </div>
                <span className="text-[13px] text-[#6b7280]">已配置配额</span>
              </div>
              <div className="text-[24px] font-semibold text-[#111827]">{quotas.filter(q => q.isActive).length}</div>
            </CardBody>
          </Card>
          <Card>
            <CardBody>
              <div className="flex items-center gap-3 mb-2">
                <div className="w-9 h-9 rounded-xl flex items-center justify-center bg-[#fef3c7]">
                  <AlertCircle className="w-5 h-5 text-[#f59e0b]" />
                </div>
                <span className="text-[13px] text-[#6b7280]">即将超额</span>
              </div>
              <div className="text-[24px] font-semibold text-[#111827]">
                {quotas.filter(q => {
                  const status = getQuotaStatus(q);
                  return status.label === '即将超额';
                }).length}
              </div>
            </CardBody>
          </Card>
        </div>

        {/* Quotas List */}
        <Card>
          <CardHeader>
            <CardTitle>用户配额列表</CardTitle>
          </CardHeader>
          <CardBody className="p-0">
            {quotas.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-[#9ca3af]">
                <Settings2 className="w-12 h-12 mb-4" />
                <p className="text-[14px]">暂无配额配置</p>
              </div>
            ) : (
              <div className="divide-y divide-[#f3f4f6]">
                {quotas.map((quota) => {
                  const status = getQuotaStatus(quota);
                  return (
                    <div key={quota.userId} className="p-4 hover:bg-[#f9fafb]">
                      <div className="flex items-center justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-3">
                            <h4 className="text-[14px] font-medium text-[#111827]">{quota.username}</h4>
                            <Badge variant={status.variant} size="sm">{status.label}</Badge>
                          </div>
                          <p className="text-[12px] text-[#6b7280] mt-1">{quota.email}</p>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-3">
                            <div>
                              <span className="text-[11px] text-[#9ca3af]">日 Token</span>
                              <p className="text-[13px] font-medium text-[#111827]">
                                {(quota.usedDailyTokens ?? 0).toLocaleString()} / {(quota.dailyTokenLimit ?? '∞').toLocaleString()}
                              </p>
                            </div>
                            <div>
                              <span className="text-[11px] text-[#9ca3af]">月 Token</span>
                              <p className="text-[13px] font-medium text-[#111827]">
                                {(quota.usedMonthlyTokens ?? 0).toLocaleString()} / {(quota.monthlyTokenLimit ?? '∞').toLocaleString()}
                              </p>
                            </div>
                            <div>
                              <span className="text-[11px] text-[#9ca3af]">日费用</span>
                              <p className="text-[13px] font-medium text-[#111827]">
                                ${(quota.usedDailyCost ?? 0).toFixed(4)} / ${(quota.dailyCostLimit ?? '∞')}
                              </p>
                            </div>
                            <div>
                              <span className="text-[11px] text-[#9ca3af]">月费用</span>
                              <p className="text-[13px] font-medium text-[#111827]">
                                ${(quota.usedMonthlyCost ?? 0).toFixed(4)} / ${(quota.monthlyCostLimit ?? '∞')}
                              </p>
                            </div>
                          </div>
                        </div>
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => handleEdit(quota)}
                          icon={<Settings2 className="w-4 h-4" />}
                        >
                          编辑
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </CardBody>
        </Card>
      </div>

      {/* Edit Modal */}
      <Modal
        open={isEditOpen}
        onOpenChange={setIsEditOpen}
        title="编辑配额"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsEditOpen(false)}>取消</Button>
            <Button onClick={handleSave} className="bg-[#7c3aed] hover:bg-[#6d28d9] text-white">
              保存
            </Button>
          </>
        }
      >
        <div className="space-y-4 py-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-[12px] font-medium text-[#4b5563]">日 Token 限额</label>
              <Input
                type="number"
                value={formData.dailyTokenLimit}
                onChange={(e) => setFormData({ ...formData, dailyTokenLimit: e.target.value })}
                placeholder="不填表示无限制"
              />
            </div>
            <div className="space-y-2">
              <label className="text-[12px] font-medium text-[#4b5563]">月 Token 限额</label>
              <Input
                type="number"
                value={formData.monthlyTokenLimit}
                onChange={(e) => setFormData({ ...formData, monthlyTokenLimit: e.target.value })}
                placeholder="不填表示无限制"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-[12px] font-medium text-[#4b5563]">日费用限额 ($)</label>
              <Input
                type="number"
                step="0.0001"
                value={formData.dailyCostLimit}
                onChange={(e) => setFormData({ ...formData, dailyCostLimit: e.target.value })}
                placeholder="不填表示无限制"
              />
            </div>
            <div className="space-y-2">
              <label className="text-[12px] font-medium text-[#4b5563]">月费用限额 ($)</label>
              <Input
                type="number"
                step="0.0001"
                value={formData.monthlyCostLimit}
                onChange={(e) => setFormData({ ...formData, monthlyCostLimit: e.target.value })}
                placeholder="不填表示无限制"
              />
            </div>
          </div>
          <div className="space-y-2">
            <label className="text-[12px] font-medium text-[#4b5563]">超额处理</label>
            <Select
              value={formData.exceededAction}
              onChange={(e) => setFormData({ ...formData, exceededAction: e.target.value })}
              className="w-full"
            >
              <option value="block">阻止</option>
              <option value="warn">警告</option>
              <option value="log">仅记录</option>
            </Select>
          </div>
          <div className="flex items-center justify-between py-2">
            <label className="text-[14px] font-medium text-[#4b5563]">启用配额</label>
            <Switch
              checked={formData.isActive}
              onCheckedChange={(checked) => setFormData({ ...formData, isActive: checked })}
            />
          </div>
        </div>
      </Modal>
    </div>
  );
}
