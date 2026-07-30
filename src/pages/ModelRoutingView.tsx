import { useState, useEffect } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { useAuth } from '@/src/lib/auth-context';
import { toast } from 'sonner';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Plus, Settings, Trash2, Loader2, RefreshCw, Check, X,
  Activity, GitBranch, AlertCircle, Zap, Shield, Clock
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '../components/enterprise/Button';
import { Modal } from '../components/enterprise/Modal';
import { Card, CardHeader, CardTitle, CardBody, CardFooter, CardDescription } from '../components/enterprise/Card';
import { Badge } from '../components/enterprise/Badge';
import { getApiUrl } from '@/src/lib/env';

const API_BASE = getApiUrl('/api/v1/model-gateway');

interface ModelProvider {
  id: number;
  name: string;
  code: string;
  provider_type: string;
  base_url: string;
  is_enabled: boolean;
  status: string;
}

interface ModelRoutingRule {
  id: number;
  name: string;
  description?: string;
  provider_id: number;
  model_type: string;
  priority: number;
  match_conditions?: Record<string, any>;
  traffic_weight: number;
  failover_enabled: boolean;
  failover_provider_id?: number;
  failover_threshold: number;
  failover_window_seconds: number;
  timeout_ms: number;
  retry_enabled: boolean;
  retry_max_attempts: number;
  retry_delay_ms: number;
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
}

interface ModelRoutingRuleFormData {
  name: string;
  description: string;
  provider_id: number;
  model_type: string;
  priority: number;
  match_conditions: Record<string, any>;
  traffic_weight: number;
  failover_enabled: boolean;
  failover_provider_id?: number;
  failover_threshold: number;
  failover_window_seconds: number;
  timeout_ms: number;
  retry_enabled: boolean;
  retry_max_attempts: number;
  retry_delay_ms: number;
  is_enabled: boolean;
}

const MODEL_TYPE_OPTIONS = [
  { value: 'llm', label: 'LLM / 对话' },
  { value: 'embedding', label: 'Embedding / 向量' },
  { value: 'rerank', label: 'Rerank / 重排序' },
  { value: 'vision', label: 'Vision / 视觉' },
  { value: 'speech_to_text', label: '语音识别' },
  { value: 'text_to_speech', label: '语音合成' },
];

const DEFAULT_FORM_DATA: ModelRoutingRuleFormData = {
  name: '',
  description: '',
  provider_id: 0,
  model_type: 'llm',
  priority: 100,
  match_conditions: {},
  traffic_weight: 100,
  failover_enabled: false,
  failover_provider_id: undefined,
  failover_threshold: 3,
  failover_window_seconds: 60,
  timeout_ms: 30000,
  retry_enabled: false,
  retry_max_attempts: 3,
  retry_delay_ms: 1000,
  is_enabled: true,
};

export function ModelRoutingView() {
  const { t } = useI18n();
  const { token } = useAuth();
  const [rules, setRules] = useState<ModelRoutingRule[]>([]);
  const [providers, setProviders] = useState<ModelProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<ModelRoutingRule | null>(null);
  const [formData, setFormData] = useState<ModelRoutingRuleFormData>(DEFAULT_FORM_DATA);
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [filterType, setFilterType] = useState<string>('all');

  const loadProviders = async () => {
    try {
      const response = await fetch(`${API_BASE}/providers`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        setProviders(data.items || []);
      }
    } catch (e: any) {
      console.error('Failed to load providers:', e);
    }
  };

  const loadRules = async () => {
    try {
      setLoading(true);
      const modelTypeParam = filterType !== 'all' ? `?model_type=${filterType}` : '';
      const response = await fetch(`${API_BASE}/routing-rules${modelTypeParam}`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        setRules(data.items || []);
      }
    } catch (e: any) {
      console.error('Failed to load routing rules:', e);
      toast.error('加载路由规则失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProviders();
    loadRules();
  }, [filterType]);

  const handleOpenCreate = () => {
    setFormData(DEFAULT_FORM_DATA);
    setFormErrors({});
    setIsCreateOpen(true);
  };

  const handleOpenEdit = (rule: ModelRoutingRule) => {
    setEditingRule(rule);
    setFormData({
      name: rule.name,
      description: rule.description || '',
      provider_id: rule.provider_id,
      model_type: rule.model_type,
      priority: rule.priority,
      match_conditions: rule.match_conditions || {},
      traffic_weight: rule.traffic_weight,
      failover_enabled: rule.failover_enabled,
      failover_provider_id: rule.failover_provider_id,
      failover_threshold: rule.failover_threshold,
      failover_window_seconds: rule.failover_window_seconds,
      timeout_ms: rule.timeout_ms,
      retry_enabled: rule.retry_enabled,
      retry_max_attempts: rule.retry_max_attempts,
      retry_delay_ms: rule.retry_delay_ms,
      is_enabled: rule.is_enabled,
    });
    setFormErrors({});
    setIsEditOpen(true);
  };

  const validateForm = (): boolean => {
    const errors: Record<string, string> = {};
    if (!formData.name || !formData.name.trim()) {
      errors.name = '规则名称为必填项';
    }
    if (!formData.provider_id) {
      errors.provider_id = '请选择供应商';
    }
    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleCreate = async () => {
    if (!validateForm()) {
      toast.error('请填写所有必填项');
      return;
    }
    try {
      const response = await fetch(`${API_BASE}/routing-rules`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(formData),
      });
      if (response.ok) {
        setIsCreateOpen(false);
        loadRules();
        toast.success('路由规则创建成功');
      } else {
        const error = await response.json().catch(() => ({ detail: '创建失败' }));
        toast.error(`创建失败：${error.detail}`);
      }
    } catch (e: any) {
      toast.error(`创建失败：${e.message}`);
    }
  };

  const handleUpdate = async () => {
    if (!editingRule || !validateForm()) {
      toast.error('请填写所有必填项');
      return;
    }
    try {
      const response = await fetch(`${API_BASE}/routing-rules/${editingRule.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(formData),
      });
      if (response.ok) {
        setIsEditOpen(false);
        loadRules();
        toast.success('路由规则已更新');
      } else {
        const error = await response.json().catch(() => ({ detail: '更新失败' }));
        toast.error(`更新失败：${error.detail}`);
      }
    } catch (e: any) {
      toast.error(`更新失败：${e.message}`);
    }
  };

  const handleDelete = async (ruleId: number) => {
    if (!window.confirm('确定要删除此路由规则吗？')) return;
    try {
      const response = await fetch(`${API_BASE}/routing-rules/${ruleId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (response.ok) {
        loadRules();
        toast.success('路由规则已删除');
      } else {
        toast.error('删除失败');
      }
    } catch (e: any) {
      toast.error(`删除失败：${e.message}`);
    }
  };

  const handleToggleEnabled = async (ruleId: number, current: boolean) => {
    try {
      const response = await fetch(`${API_BASE}/routing-rules/${ruleId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ is_enabled: !current }),
      });
      if (response.ok) {
        loadRules();
        toast.success(current ? '已禁用' : '已启用');
      }
    } catch (e: any) {
      toast.error(`设置失败：${e.message}`);
    }
  };

  const getProviderName = (providerId: number) => {
    const provider = providers.find(p => p.id === providerId);
    return provider ? provider.name : '未知供应商';
  };

  const getProviderBadgeColor = (providerId: number) => {
    const provider = providers.find(p => p.id === providerId);
    if (!provider) return 'bg-gray-400';
    if (provider.provider_type === 'cloud') return 'bg-blue-500';
    if (provider.provider_type === 'domestic') return 'bg-green-500';
    if (provider.provider_type === 'self_hosted') return 'bg-[var(--accent)]';
    return 'bg-gray-400';
  };

  const filteredRules = filterType === 'all'
    ? rules
    : rules.filter(r => r.model_type === filterType);

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-white">
      {/* Header */}
      <header className="h-[60px] px-6 bg-white flex items-center justify-between shrink-0 border-b border-[var(--sidebar-border)]">
        <div>
          <h1 className="text-[18px] font-semibold text-[var(--text-primary)]">路由配置</h1>
          <p className="text-xs text-[var(--text-tertiary)]">配置模型请求的路由规则和故障转移策略</p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="secondary"
            size="md"
            onClick={() => loadRules()}
            disabled={loading}
          >
            <RefreshCw className={cn("w-4 h-4 mr-2", loading && "animate-spin")} />
            刷新
          </Button>
          <Button
            variant="primary"
            size="md"
            onClick={handleOpenCreate}
          >
            <Plus className="w-4 h-4 mr-2" />
            新建规则
          </Button>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {/* Filters */}
        <div className="mb-6 flex items-center gap-2">
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="enterprise-select w-[200px]"
          >
            <option value="all">全部类型</option>
            {MODEL_TYPE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>

        {/* Rules List */}
        <div className="space-y-4">
          {loading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="w-8 h-8 animate-spin text-[var(--primary)]" />
            </div>
          ) : filteredRules.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <GitBranch className="w-16 h-16 text-[var(--text-tertiary)] mb-4" />
              <h3 className="text-lg font-semibold text-[var(--text-primary)]">暂无路由规则</h3>
              <p className="text-[var(--text-tertiary)] text-sm mt-2">创建第一个路由规则开始使用</p>
            </div>
          ) : (
            filteredRules.map((rule) => (
              <Card key={rule.id} className="overflow-hidden">
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-11 h-11 rounded-xl flex items-center justify-center bg-[var(--accent-light)] text-[var(--primary)]">
                        <GitBranch className="w-5 h-5" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <CardTitle>{rule.name}</CardTitle>
                          <Badge variant={rule.is_enabled ? 'primary' : 'neutral'}>
                            {rule.is_enabled ? '已启用' : '已禁用'}
                          </Badge>
                          {rule.failover_enabled && (
                            <Badge variant="warning">
                              <Shield className="w-3 h-3 mr-1" />
                              故障转移
                            </Badge>
                          )}
                        </div>
                        <CardDescription className="mt-1">
                          {MODEL_TYPE_OPTIONS.find(o => o.value === rule.model_type)?.label} • 优先级：{rule.priority} • {getProviderName(rule.provider_id)}
                        </CardDescription>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => handleOpenEdit(rule)}
                      >
                        <Settings className="w-4 h-4" />
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-[var(--error)] hover:bg-[var(--error-bg)]"
                        onClick={() => handleDelete(rule.id)}
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardBody>
                  {rule.description && (
                    <p className="text-sm text-[var(--text-secondary)] mb-3">{rule.description}</p>
                  )}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
                    <div className="flex items-center gap-2">
                      <Activity className="w-3.5 h-3.5 text-[var(--text-tertiary)]" />
                      <span className="text-[var(--text-secondary)]">流量权重：{rule.traffic_weight}%</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Clock className="w-3.5 h-3.5 text-[var(--text-tertiary)]" />
                      <span className="text-[var(--text-secondary)]">超时：{rule.timeout_ms}ms</span>
                    </div>
                    {rule.retry_enabled && (
                      <div className="flex items-center gap-2">
                        <RefreshCw className="w-3.5 h-3.5 text-[var(--text-tertiary)]" />
                        <span className="text-[var(--text-secondary)]">重试：{rule.retry_max_attempts}次</span>
                      </div>
                    )}
                    {rule.failover_enabled && rule.failover_provider_id && (
                      <div className="flex items-center gap-2">
                        <Shield className="w-3.5 h-3.5 text-[var(--text-tertiary)]" />
                        <span className="text-[var(--text-secondary)]">
                          故障转移：{getProviderName(rule.failover_provider_id)}
                        </span>
                      </div>
                    )}
                  </div>
                </CardBody>
                <CardFooter>
                  <div className="flex items-center justify-between w-full">
                    <label className="flex items-center gap-2 text-sm text-[var(--text-secondary)] cursor-pointer">
                      <input
                        type="checkbox"
                        checked={rule.is_enabled}
                        onChange={() => handleToggleEnabled(rule.id, rule.is_enabled)}
                        className="rounded border-gray-300"
                      />
                      启用
                    </label>
                    <div className="flex items-center gap-2">
                      <div className={cn("w-2 h-2 rounded-full", getProviderBadgeColor(rule.provider_id))} />
                      <span className="text-xs text-[var(--text-tertiary)]">主供应商</span>
                    </div>
                  </div>
                </CardFooter>
              </Card>
            ))
          )}
        </div>
      </div>

      {/* Create/Edit Modal */}
      <Modal
        open={isCreateOpen || isEditOpen}
        onOpenChange={(open) => {
          if (!open) {
            setIsCreateOpen(false);
            setIsEditOpen(false);
            setFormData(DEFAULT_FORM_DATA);
            setFormErrors({});
          }
        }}
        title={isEditOpen ? '编辑路由规则' : '新建路由规则'}
        description="配置模型请求的路由策略"
        width="800px"
        footer={
          <>
            <Button variant="secondary" onClick={() => {
              setIsCreateOpen(false);
              setIsEditOpen(false);
            }}>取消</Button>
            <Button variant="primary" onClick={isEditOpen ? handleUpdate : handleCreate}>
              {isEditOpen ? '保存更新' : '创建'}
            </Button>
          </>
        }
      >
        <RoutingRuleForm
          formData={formData}
          onChange={(data) => {
            setFormData(prev => ({ ...prev, ...data }));
            setFormErrors({});
          }}
          errors={formErrors}
          providers={providers}
          isEdit={isEditOpen}
        />
      </Modal>
    </div>
  );
}

// ========== Routing Rule Form Component ==========

interface RoutingRuleFormProps {
  formData: ModelRoutingRuleFormData;
  onChange: (data: Partial<ModelRoutingRuleFormData>) => void;
  errors: Record<string, string>;
  providers: ModelProvider[];
  isEdit?: boolean;
}

function RoutingRuleForm({ formData, onChange, errors, providers, isEdit }: RoutingRuleFormProps) {
  const { t } = useI18n();

  const availableProviders = providers.filter(p => p.is_enabled && p.status === 'active');

  return (
    <ScrollArea className="max-h-[550px]">
      <div className="space-y-5 p-1">
        {/* 基本信息 */}
        <div>
          <h4 className="text-sm font-medium text-[var(--text-primary)] mb-3">基本信息</h4>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-[var(--text-secondary)] mb-1 block">
                规则名称 *
              </label>
              <input
                type="text"
                className={cn("enterprise-input w-full", errors.name && "border-red-500")}
                value={formData.name}
                onChange={(e) => onChange({ name: e.target.value })}
                placeholder="如：OpenAI 主路由"
              />
              {errors.name && <p className="text-xs text-red-500 mt-1">{errors.name}</p>}
            </div>
            <div>
              <label className="text-sm font-medium text-[var(--text-secondary)] mb-1 block">
                模型类型 *
              </label>
              <select
                className="enterprise-select w-full"
                value={formData.model_type}
                onChange={(e) => onChange({ model_type: e.target.value })}
              >
                {MODEL_TYPE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="mt-3">
            <label className="text-sm font-medium text-[var(--text-secondary)] mb-1 block">
              描述
            </label>
            <textarea
              className="enterprise-input w-full min-h-[60px]"
              value={formData.description}
              onChange={(e) => onChange({ description: e.target.value })}
              placeholder="规则描述信息"
            />
          </div>
        </div>

        {/* 供应商配置 */}
        <div className="border-t border-[var(--gray-200)] pt-4">
          <h4 className="text-sm font-medium text-[var(--text-primary)] mb-3">供应商配置</h4>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-[var(--text-secondary)] mb-1 block">
                主供应商 *
              </label>
              <select
                className="enterprise-select w-full"
                value={formData.provider_id}
                onChange={(e) => onChange({ provider_id: parseInt(e.target.value) })}
              >
                <option value={0}>请选择供应商</option>
                {availableProviders.map((p) => (
                  <option key={p.id} value={p.id}>{p.name} ({p.code})</option>
                ))}
              </select>
              {errors.provider_id && <p className="text-xs text-red-500 mt-1">{errors.provider_id}</p>}
            </div>
            <div>
              <label className="text-sm font-medium text-[var(--text-secondary)] mb-1 block">
                优先级
              </label>
              <input
                type="number"
                className="enterprise-input w-full"
                value={formData.priority}
                onChange={(e) => onChange({ priority: parseInt(e.target.value) })}
                placeholder="100"
              />
              <p className="text-xs text-[var(--text-tertiary)] mt-1">数字越小优先级越高</p>
            </div>
          </div>
          <div className="mt-3">
            <label className="text-sm font-medium text-[var(--text-secondary)] mb-1 block">
              流量权重 ({formData.traffic_weight}%)
            </label>
            <input
              type="range"
              min="0"
              max="100"
              value={formData.traffic_weight}
              onChange={(e) => onChange({ traffic_weight: parseInt(e.target.value) })}
              className="w-full"
            />
            <div className="flex justify-between text-xs text-[var(--text-tertiary)] mt-1">
              <span>0%</span>
              <span>50%</span>
              <span>100%</span>
            </div>
          </div>
        </div>

        {/* 故障转移配置 */}
        <div className="border-t border-[var(--gray-200)] pt-4">
          <div className="flex items-center gap-2 mb-3">
            <input
              type="checkbox"
              id="failover_enabled"
              checked={formData.failover_enabled}
              onChange={(e) => onChange({ failover_enabled: e.target.checked })}
              className="rounded border-gray-300"
            />
            <label htmlFor="failover_enabled" className="text-sm font-medium text-[var(--text-secondary)]">
              启用故障转移
            </label>
          </div>

          {formData.failover_enabled && (
            <div className="space-y-3 pl-6">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium text-[var(--text-secondary)] mb-1 block">
                    备用供应商
                  </label>
                  <select
                    className="enterprise-select w-full"
                    value={formData.failover_provider_id || 0}
                    onChange={(e) => onChange({ failover_provider_id: parseInt(e.target.value) || undefined })}
                  >
                    <option value={0}>请选择备用供应商</option>
                    {availableProviders.filter(p => p.id !== formData.provider_id).map((p) => (
                      <option key={p.id} value={p.id}>{p.name} ({p.code})</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-sm font-medium text-[var(--text-secondary)] mb-1 block">
                    故障阈值
                  </label>
                  <input
                    type="number"
                    className="enterprise-input w-full"
                    value={formData.failover_threshold}
                    onChange={(e) => onChange({ failover_threshold: parseInt(e.target.value) })}
                    placeholder="3"
                  />
                  <p className="text-xs text-[var(--text-tertiary)] mt-1">连续失败次数</p>
                </div>
              </div>
              <div>
                <label className="text-sm font-medium text-[var(--text-secondary)] mb-1 block">
                  故障判断时间窗口 (秒)
                </label>
                <input
                  type="number"
                  className="enterprise-input w-full"
                  value={formData.failover_window_seconds}
                  onChange={(e) => onChange({ failover_window_seconds: parseInt(e.target.value) })}
                  placeholder="60"
                />
              </div>
            </div>
          )}
        </div>

        {/* 超时和重试配置 */}
        <div className="border-t border-[var(--gray-200)] pt-4">
          <h4 className="text-sm font-medium text-[var(--text-primary)] mb-3">超时和重试</h4>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-[var(--text-secondary)] mb-1 block">
                超时时间 (ms)
              </label>
              <input
                type="number"
                className="enterprise-input w-full"
                value={formData.timeout_ms}
                onChange={(e) => onChange({ timeout_ms: parseInt(e.target.value) })}
                placeholder="30000"
              />
            </div>
            <div>
              <label className="text-sm font-medium text-[var(--text-secondary)] mb-1 block">
                重试延迟 (ms)
              </label>
              <input
                type="number"
                className="enterprise-input w-full"
                value={formData.retry_delay_ms}
                onChange={(e) => onChange({ retry_delay_ms: parseInt(e.target.value) })}
                placeholder="1000"
              />
            </div>
          </div>
          <div className="mt-3">
            <label className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
              <input
                type="checkbox"
                checked={formData.retry_enabled}
                onChange={(e) => onChange({ retry_enabled: e.target.checked })}
                className="rounded border-gray-300"
              />
              启用自动重试
            </label>
          </div>
          {formData.retry_enabled && (
            <div className="mt-3 pl-6">
              <label className="text-sm font-medium text-[var(--text-secondary)] mb-1 block">
                最大重试次数
              </label>
              <input
                type="number"
                className="enterprise-input w-full"
                value={formData.retry_max_attempts}
                onChange={(e) => onChange({ retry_max_attempts: parseInt(e.target.value) })}
                placeholder="3"
              />
            </div>
          )}
        </div>

        {/* 开关选项 */}
        <div className="border-t border-[var(--gray-200)] pt-4">
          <label className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
            <input
              type="checkbox"
              checked={formData.is_enabled}
              onChange={(e) => onChange({ is_enabled: e.target.checked })}
              className="rounded border-gray-300"
            />
            启用此路由规则
          </label>
        </div>
      </div>
    </ScrollArea>
  );
}
