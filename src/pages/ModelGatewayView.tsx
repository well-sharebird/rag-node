import { useState, useEffect } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { useAuth } from '@/src/lib/auth-context';
import { toast } from 'sonner';
import {
  Plus, Settings, Trash2, Loader2, Server, RefreshCw, Check, X,
  ChevronRight, ChevronDown, DollarSign, Zap, Activity, AlertCircle
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '../components/enterprise/Button';
import { Modal } from '../components/enterprise/Modal';
import { Card, CardHeader, CardTitle, CardBody, CardFooter, CardDescription } from '../components/enterprise/Card';
import { Badge } from '../components/enterprise/Badge';

// API 调用函数
const API_BASE = '/api/v1/model-gateway';

interface ModelProvider {
  id: number;
  name: string;
  code: string;
  description?: string;
  provider_type: string;
  region?: string;
  base_url: string;
  api_version?: string;
  auth_type: string;
  api_key_name?: string;
  api_key?: string;
  config?: Record<string, any>;
  is_enabled: boolean;
  is_default: boolean;
  status: string;
  health_status?: string;
  last_health_check?: string;
  consecutive_failures: number;
  rate_limit_enabled: boolean;
  rate_limit_requests?: number;
  rate_limit_tokens?: number;
  cost_input?: number;
  cost_output?: number;
  tags?: string;
  metadata_json?: Record<string, any>;
  created_at: string;
  updated_at: string;
}

interface ModelProviderFormData {
  name: string;
  code: string;
  description: string;
  provider_type: string;
  region: string;
  base_url: string;
  api_version: string;
  auth_type: string;
  api_key_name: string;
  api_key: string;
  is_enabled: boolean;
  is_default: boolean;
  rate_limit_enabled: boolean;
  rate_limit_requests?: number;
  rate_limit_tokens?: number;
  cost_input?: number;
  cost_output?: number;
}

const PROVIDER_TYPE_OPTIONS = [
  { value: 'cloud', label: '国际云服务' },
  { value: 'domestic', label: '国内云服务' },
  { value: 'self_hosted', label: '自托管服务' },
];

const PROVIDER_TYPE_LABELS: Record<string, string> = {
  cloud: '国际云服务',
  domestic: '国内云服务',
  self_hosted: '自托管服务',
};

const CLOUD_PROVIDERS = [
  { code: 'openai', name: 'OpenAI', type: 'cloud' },
  { code: 'anthropic', name: 'Anthropic', type: 'cloud' },
  { code: 'google', name: 'Google AI', type: 'cloud' },
  { code: 'azure', name: 'Azure OpenAI', type: 'cloud' },
  { code: 'aws', name: 'AWS Bedrock', type: 'cloud' },
  { code: 'cohere', name: 'Cohere', type: 'cloud' },
];

const DOMESTIC_PROVIDERS = [
  { code: 'zhipu', name: '智谱 AI', type: 'domestic' },
  { code: 'moonshot', name: '月之暗面 (Kimi)', type: 'domestic' },
  { code: 'aliyun', name: '阿里云百炼', type: 'domestic' },
  { code: 'baichuan', name: '百川智能', type: 'domestic' },
  { code: 'minimax', name: 'MiniMax', type: 'domestic' },
  { code: '01ai', name: '零一万物', type: 'domestic' },
];

const SELF_HOSTED_PROVIDERS = [
  { code: 'ollama', name: 'Ollama', type: 'self_hosted' },
  { code: 'vllm', name: 'vLLM', type: 'self_hosted' },
  { code: 'triton', name: 'NVIDIA Triton', type: 'self_hosted' },
  { code: 'local', name: '本地部署', type: 'self_hosted' },
];

const DEFAULT_FORM_DATA: ModelProviderFormData = {
  name: '',
  code: '',
  description: '',
  provider_type: 'cloud',
  region: '',
  base_url: '',
  api_version: '',
  auth_type: 'api_key',
  api_key_name: 'Authorization',
  api_key: '',
  is_enabled: true,
  is_default: false,
  rate_limit_enabled: false,
  rate_limit_requests: undefined,
  rate_limit_tokens: undefined,
  cost_input: undefined,
  cost_output: undefined,
};

export function ModelGatewayView() {
  const { t } = useI18n();
  const { token } = useAuth();
  const [providers, setProviders] = useState<ModelProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [editingProvider, setEditingProvider] = useState<ModelProvider | null>(null);
  const [formData, setFormData] = useState<ModelProviderFormData>(DEFAULT_FORM_DATA);
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [filterType, setFilterType] = useState<string>('all');
  const [testingId, setTestingId] = useState<number | null>(null);

  const loadProviders = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE}/providers`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        setProviders(data.items || []);
      }
    } catch (e: any) {
      console.error('Failed to load providers:', e);
      toast.error('加载供应商列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProviders();
  }, []);

  const handleOpenCreate = (presetProvider?: { code: string; name: string; type: string }) => {
    if (presetProvider) {
      const baseUrl = getProviderBaseUrl(presetProvider.code);
      setFormData({
        ...DEFAULT_FORM_DATA,
        name: presetProvider.name,
        code: presetProvider.code,
        provider_type: presetProvider.type,
        base_url: baseUrl,
      });
    } else {
      setFormData(DEFAULT_FORM_DATA);
    }
    setFormErrors({});
    setIsCreateOpen(true);
  };

  const handleOpenEdit = (provider: ModelProvider) => {
    setEditingProvider(provider);
    setFormData({
      name: provider.name,
      code: provider.code,
      description: provider.description || '',
      provider_type: provider.provider_type,
      region: provider.region || '',
      base_url: provider.base_url,
      api_version: provider.api_version || '',
      auth_type: provider.auth_type,
      api_key_name: provider.api_key_name || 'Authorization',
      api_key: '', // Don't load existing API key for security
      is_enabled: provider.is_enabled,
      is_default: provider.is_default,
      rate_limit_enabled: provider.rate_limit_enabled,
      rate_limit_requests: provider.rate_limit_requests,
      rate_limit_tokens: provider.rate_limit_tokens,
      cost_input: provider.cost_input,
      cost_output: provider.cost_output,
    });
    setFormErrors({});
    setIsEditOpen(true);
  };

  const validateForm = (): boolean => {
    const errors: Record<string, string> = {};
    if (!formData.name || !formData.name.trim()) {
      errors.name = '供应商名称为必填项';
    }
    if (!formData.code || !formData.code.trim()) {
      errors.code = '供应商代码为必填项';
    }
    if (!formData.base_url || !formData.base_url.trim()) {
      errors.base_url = 'API 基础 URL 为必填项';
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
      const response = await fetch(`${API_BASE}/providers`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(formData),
      });
      if (response.ok) {
        setIsCreateOpen(false);
        loadProviders();
        toast.success('供应商创建成功');
      } else {
        const error = await response.json().catch(() => ({ detail: '创建失败' }));
        toast.error(`创建失败：${error.detail}`);
      }
    } catch (e: any) {
      toast.error(`创建失败：${e.message}`);
    }
  };

  const handleUpdate = async () => {
    if (!editingProvider || !validateForm()) {
      toast.error('请填写所有必填项');
      return;
    }
    try {
      const response = await fetch(`${API_BASE}/providers/${editingProvider.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(formData),
      });
      if (response.ok) {
        setIsEditOpen(false);
        loadProviders();
        toast.success('供应商已更新');
      } else {
        const error = await response.json().catch(() => ({ detail: '更新失败' }));
        toast.error(`更新失败：${error.detail}`);
      }
    } catch (e: any) {
      toast.error(`更新失败：${e.message}`);
    }
  };

  const handleDelete = async (providerId: number) => {
    if (!window.confirm('确定要删除此供应商吗？删除后相关路由规则将失效。')) return;
    try {
      const response = await fetch(`${API_BASE}/providers/${providerId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (response.ok) {
        loadProviders();
        toast.success('供应商已删除');
      } else {
        toast.error('删除失败');
      }
    } catch (e: any) {
      toast.error(`删除失败：${e.message}`);
    }
  };

  const handleToggleEnabled = async (providerId: number, current: boolean) => {
    try {
      const response = await fetch(`${API_BASE}/providers/${providerId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ is_enabled: !current }),
      });
      if (response.ok) {
        loadProviders();
        toast.success(current ? '已禁用' : '已启用');
      }
    } catch (e: any) {
      toast.error(`设置失败：${e.message}`);
    }
  };

  const handleTestConnection = async (providerId: number) => {
    setTestingId(providerId);
    try {
      // Simple health check - just verify the provider exists and is configured
      const response = await fetch(`${API_BASE}/providers/${providerId}`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        if (data.item.base_url) {
          toast.success('供应商配置有效');
        } else {
          toast.warning('供应商配置不完整');
        }
      } else {
        toast.error('供应商不存在');
      }
    } catch (e: any) {
      toast.error(`测试失败：${e.message}`);
    } finally {
      setTestingId(null);
    }
  };

  const getProviderBaseUrl = (code: string): string => {
    const urls: Record<string, string> = {
      openai: 'https://api.openai.com/v1',
      anthropic: 'https://api.anthropic.com',
      google: 'https://generativelanguage.googleapis.com/v1beta',
      azure: 'https://{resource}.openai.azure.com',
      zhipu: 'https://open.bigmodel.cn/api/paas/v4',
      moonshot: 'https://api.moonshot.cn/v1',
      aliyun: 'https://dashscope.aliyuncs.com/api/v1',
      ollama: 'http://localhost:11434',
      vllm: 'http://localhost:8000/v1',
    };
    return urls[code] || '';
  };

  const filteredProviders = filterType === 'all'
    ? providers
    : providers.filter(p => p.provider_type === filterType);

  const getStatusBadgeVariant = (status: string) => {
    if (status === 'active') return 'primary';
    if (status === 'error') return 'danger';
    if (status === 'rate_limited') return 'warning';
    return 'neutral';
  };

  const getHealthStatusColor = (healthStatus?: string) => {
    if (!healthStatus) return 'bg-gray-400';
    if (healthStatus === 'healthy') return 'bg-green-500';
    if (healthStatus === 'degraded') return 'bg-yellow-500';
    if (healthStatus === 'unhealthy') return 'bg-red-500';
    return 'bg-gray-400';
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-white">
      {/* Header */}
      <header className="h-[60px] px-6 bg-white flex items-center justify-between shrink-0 border-b border-[var(--sidebar-border)]">
        <div>
          <h1 className="text-[18px] font-semibold text-[var(--text-primary)]">模型网关</h1>
          <p className="text-xs text-[var(--text-tertiary)]">统一管理 LLM 供应商和路由配置</p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="secondary"
            size="md"
            onClick={() => toast.info('路由规则功能开发中')}
          >
            <Activity className="w-4 h-4 mr-2" />
            路由规则
          </Button>
          <Button
            variant="primary"
            size="md"
            onClick={() => setIsCreateOpen(true)}
          >
            <Plus className="w-4 h-4 mr-2" />
            添加供应商
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
            <option value="cloud">国际云服务</option>
            <option value="domestic">国内云服务</option>
            <option value="self_hosted">自托管服务</option>
          </select>
        </div>

        {/* Providers Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {loading ? (
            <div className="col-span-full flex items-center justify-center py-20">
              <Loader2 className="w-8 h-8 animate-spin text-[var(--primary)]" />
            </div>
          ) : filteredProviders.length === 0 ? (
            <div className="col-span-full flex flex-col items-center justify-center py-20 text-center">
              <Server className="w-16 h-16 text-[var(--text-tertiary)] mb-4" />
              <h3 className="text-lg font-semibold text-[var(--text-primary)]">暂无供应商配置</h3>
              <p className="text-[var(--text-tertiary)] text-sm mt-2">添加第一个 LLM 供应商开始使用</p>
            </div>
          ) : (
            filteredProviders.map((provider) => (
              <Card key={provider.id} hover className="overflow-hidden">
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div className={cn(
                        "w-11 h-11 rounded-xl flex items-center justify-center",
                        provider.status === 'active' ? 'bg-[var(--success-bg)] text-[var(--success)]' :
                        provider.status === 'error' ? 'bg-[var(--error-bg)] text-[var(--error)]' :
                        'bg-[var(--gray-100)] text-[var(--text-tertiary)]'
                      )}>
                        <Server className="w-5 h-5" />
                      </div>
                      <div>
                        <CardTitle>{provider.name}</CardTitle>
                        <CardDescription>
                          {PROVIDER_TYPE_LABELS[provider.provider_type]} • {provider.code}
                        </CardDescription>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className={cn("w-2 h-2 rounded-full", getHealthStatusColor(provider.health_status))}
                           title={`健康状态：${provider.health_status || '未知'}`} />
                      <Badge variant={provider.is_default ? 'primary' : 'neutral'}>
                        {provider.is_default ? '默认' : provider.status}
                      </Badge>
                    </div>
                  </div>
                </CardHeader>
                <CardBody>
                  <div className="text-xs text-[var(--text-secondary)] mb-3">
                    <code className="px-2 py-1 bg-[var(--gray-100)] rounded-lg break-all">
                      {provider.base_url}
                    </code>
                  </div>
                  {provider.description && (
                    <p className="text-xs text-[var(--text-tertiary)] line-clamp-2 mb-3">{provider.description}</p>
                  )}
                  {(provider.cost_input !== undefined || provider.cost_output !== undefined) && (
                    <div className="flex items-center gap-2 text-xs mb-3">
                      <DollarSign className="w-3 h-3 text-[var(--text-tertiary)]" />
                      <span className="text-[var(--text-tertiary)]">
                        输入：${provider.cost_input?.toFixed(4) || 'N/A'} / 1K tokens
                      </span>
                      <span className="text-[var(--text-tertiary)]">
                        输出：${provider.cost_output?.toFixed(4) || 'N/A'} / 1K tokens
                      </span>
                    </div>
                  )}
                  {provider.rate_limit_enabled && (
                    <div className="flex items-center gap-2 text-xs">
                      <Zap className="w-3 h-3 text-[var(--text-tertiary)]" />
                      <span className="text-[var(--text-tertiary)]">
                        限速：{provider.rate_limit_requests || '∞'} req/min
                      </span>
                    </div>
                  )}
                </CardBody>
                <CardFooter>
                  <Button
                    size="sm"
                    variant="secondary"
                    className="flex-1"
                    onClick={() => handleTestConnection(provider.id)}
                    disabled={testingId === provider.id}
                  >
                    {testingId === provider.id ? (
                      <Loader2 className="w-4 h-4 mr-1 animate-spin" />
                    ) : (
                      <RefreshCw className="w-4 h-4 mr-1" />
                    )}
                    测试
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => handleOpenEdit(provider)}
                  >
                    <Settings className="w-4 h-4" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-[var(--error)] hover:bg-[var(--error-bg)]"
                    onClick={() => handleDelete(provider.id)}
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </CardFooter>
                <div className="px-6 py-3 border-t border-[var(--gray-100)] flex items-center justify-between">
                  <label className="flex items-center gap-2 text-xs text-[var(--text-secondary)] cursor-pointer">
                    <input
                      type="checkbox"
                      checked={provider.is_enabled}
                      onChange={() => handleToggleEnabled(provider.id, provider.is_enabled)}
                      className="enterprise-switch"
                    />
                    启用
                  </label>
                  {!provider.is_default && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-xs"
                      onClick={async () => {
                        try {
                          const response = await fetch(`${API_BASE}/providers/${provider.id}`, {
                            method: 'PUT',
                            headers: {
                              'Content-Type': 'application/json',
                              'Authorization': `Bearer ${token}`,
                            },
                            body: JSON.stringify({ is_default: true }),
                          });
                          if (response.ok) {
                            loadProviders();
                            toast.success('已设为默认供应商');
                          }
                        } catch (e: any) {
                          toast.error(`设置失败：${e.message}`);
                        }
                      }}
                    >
                      设为默认
                    </Button>
                  )}
                </div>
              </Card>
            ))
          )}
        </div>
      </div>

      {/* Create Provider Modal */}
      <Modal
        open={isCreateOpen}
        onOpenChange={(open) => {
          setIsCreateOpen(open);
          if (!open) setFormData(DEFAULT_FORM_DATA);
        }}
        title="添加供应商"
        description="选择供应商类型并填写 API 配置信息"
        width="800px"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsCreateOpen(false)}>取消</Button>
            <Button variant="primary" onClick={handleCreate}>创建</Button>
          </>
        }
      >
        <ProviderForm
          formData={formData}
          onChange={(data) => {
            setFormData(prev => ({ ...prev, ...data }));
            setFormErrors({});
          }}
          errors={formErrors}
          presetProviders={[...CLOUD_PROVIDERS, ...DOMESTIC_PROVIDERS, ...SELF_HOSTED_PROVIDERS]}
        />
      </Modal>

      {/* Edit Provider Modal */}
      <Modal
        open={isEditOpen}
        onOpenChange={(open) => {
          setIsEditOpen(open);
          if (!open) setFormData(DEFAULT_FORM_DATA);
        }}
        title="编辑供应商配置"
        description="修改供应商配置和参数"
        width="800px"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsEditOpen(false)}>取消</Button>
            <Button variant="primary" onClick={handleUpdate}>保存更新</Button>
          </>
        }
      >
        <ProviderForm
          formData={formData}
          onChange={(data) => {
            setFormData(prev => ({ ...prev, ...data }));
            setFormErrors({});
          }}
          errors={formErrors}
          isEdit
        />
      </Modal>
    </div>
  );
}

// ========== Provider Form Component ==========

interface ProviderFormProps {
  formData: ModelProviderFormData;
  onChange: (data: Partial<ModelProviderFormData>) => void;
  errors: Record<string, string>;
  isEdit?: boolean;
  presetProviders?: Array<{ code: string; name: string; type: string }>;
}

function ProviderForm({ formData, onChange, errors, isEdit, presetProviders }: ProviderFormProps) {
  const { t } = useI18n();

  return (
    <div className="space-y-4">
      {/* 预设供应商选择 (仅创建模式) */}
      {!isEdit && presetProviders && (
          <div>
            <label className="text-sm font-medium text-[var(--text-secondary)] mb-2 block">
              快速选择
            </label>
            <div className="grid grid-cols-3 gap-2">
              {presetProviders.map((p) => (
                <button
                  key={p.code}
                  onClick={() => onChange({
                    name: p.name,
                    code: p.code,
                    provider_type: p.type,
                  })}
                  className={cn(
                    "px-3 py-2 text-xs rounded-lg border transition-colors",
                    formData.code === p.code
                      ? "bg-[var(--accent-light)] border-[var(--primary)] text-[var(--primary)]"
                      : "border-[var(--gray-200)] hover:bg-[var(--gray-50)]"
                  )}
                >
                  {p.name}
                </button>
              ))}
            </div>
          </div>
        )}

      {/* 基本信息 */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="text-sm font-medium text-[var(--text-secondary)] mb-1 block">
            供应商名称 *
          </label>
          <input
            type="text"
            className={cn("enterprise-input w-full", errors.name && "border-red-500")}
            value={formData.name}
            onChange={(e) => onChange({ name: e.target.value })}
            placeholder="如：OpenAI"
          />
          {errors.name && <p className="text-xs text-red-500 mt-1">{errors.name}</p>}
        </div>
        <div>
          <label className="text-sm font-medium text-[var(--text-secondary)] mb-1 block">
            供应商代码 *
          </label>
          <input
            type="text"
            className={cn("enterprise-input w-full", errors.code && "border-red-500")}
            value={formData.code}
            onChange={(e) => onChange({ code: e.target.value.toLowerCase() })}
            placeholder="如：openai"
            disabled={isEdit}
          />
          {errors.code && <p className="text-xs text-red-500 mt-1">{errors.code}</p>}
        </div>
      </div>

      <div>
        <label className="text-sm font-medium text-[var(--text-secondary)] mb-1 block">
          描述
        </label>
        <textarea
          className="enterprise-input w-full min-h-[60px]"
          value={formData.description}
          onChange={(e) => onChange({ description: e.target.value })}
          placeholder="供应商描述信息"
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="text-sm font-medium text-[var(--text-secondary)] mb-1 block">
            供应商类型
          </label>
          <select
            className="enterprise-select w-full"
            value={formData.provider_type}
            onChange={(e) => onChange({ provider_type: e.target.value })}
          >
            {PROVIDER_TYPE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-sm font-medium text-[var(--text-secondary)] mb-1 block">
            区域
          </label>
          <select
            className="enterprise-select w-full"
            value={formData.region}
            onChange={(e) => onChange({ region: e.target.value })}
          >
            <option value="">不限</option>
            <option value="international">国际</option>
            <option value="china">中国大陆</option>
            <option value="us-east">美国东部</option>
            <option value="ap-southeast">亚太</option>
          </select>
        </div>
      </div>

      {/* API 配置 */}
      <div className="border-t border-[var(--gray-200)] pt-4">
        <h4 className="text-sm font-medium text-[var(--text-primary)] mb-3">API 配置</h4>

        <div className="space-y-3">
          <div>
            <label className="text-sm font-medium text-[var(--text-secondary)] mb-1 block">
              API 基础 URL *
            </label>
            <input
              type="text"
              className={cn("enterprise-input w-full", errors.base_url && "border-red-500")}
              value={formData.base_url}
              onChange={(e) => onChange({ base_url: e.target.value })}
              placeholder="https://api.example.com/v1"
            />
            {errors.base_url && <p className="text-xs text-red-500 mt-1">{errors.base_url}</p>}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-[var(--text-secondary)] mb-1 block">
                API 版本
              </label>
              <input
                type="text"
                className="enterprise-input w-full"
                value={formData.api_version}
                onChange={(e) => onChange({ api_version: e.target.value })}
                placeholder="如：2024-01-01"
              />
            </div>
            <div>
              <label className="text-sm font-medium text-[var(--text-secondary)] mb-1 block">
                认证类型
              </label>
              <select
                className="enterprise-select w-full"
                value={formData.auth_type}
                onChange={(e) => onChange({ auth_type: e.target.value })}
              >
                <option value="api_key">API Key</option>
                <option value="oauth">OAuth 2.0</option>
                <option value="aws_sigv4">AWS SigV4</option>
                <option value="azure_ad">Azure AD</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-[var(--text-secondary)] mb-1 block">
                API Key 名称
              </label>
              <input
                type="text"
                className="enterprise-input w-full"
                value={formData.api_key_name}
                onChange={(e) => onChange({ api_key_name: e.target.value })}
                placeholder="Authorization"
              />
            </div>
            <div>
              <label className="text-sm font-medium text-[var(--text-secondary)] mb-1 block">
                API Key
              </label>
              <input
                type="password"
                className="enterprise-input w-full"
                value={formData.api_key}
                onChange={(e) => onChange({ api_key: e.target.value })}
                placeholder={isEdit ? "留空则不修改" : "sk-..."}
              />
            </div>
          </div>
        </div>
      </div>

      {/* 速率限制 */}
      <div className="border-t border-[var(--gray-200)] pt-4">
        <div className="flex items-center gap-2 mb-3">
          <input
            type="checkbox"
            id="rate_limit_enabled"
            checked={formData.rate_limit_enabled}
            onChange={(e) => onChange({ rate_limit_enabled: e.target.checked })}
            className="rounded border-gray-300"
          />
          <label htmlFor="rate_limit_enabled" className="text-sm font-medium text-[var(--text-secondary)]">
            启用速率限制
          </label>
        </div>

        {formData.rate_limit_enabled && (
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-[var(--text-secondary)] mb-1 block">
                请求数限制 (次/分钟)
              </label>
              <input
                type="number"
                className="enterprise-input w-full"
                value={formData.rate_limit_requests || ''}
                onChange={(e) => onChange({ rate_limit_requests: parseInt(e.target.value) || undefined })}
                placeholder="60"
              />
            </div>
            <div>
              <label className="text-sm font-medium text-[var(--text-secondary)] mb-1 block">
                Token 数限制 (个/分钟)
              </label>
              <input
                type="number"
                className="enterprise-input w-full"
                value={formData.rate_limit_tokens || ''}
                onChange={(e) => onChange({ rate_limit_tokens: parseInt(e.target.value) || undefined })}
                placeholder="100000"
              />
            </div>
          </div>
        )}
      </div>

      {/* 成本配置 */}
      <div className="border-t border-[var(--gray-200)] pt-4">
        <h4 className="text-sm font-medium text-[var(--text-secondary)] mb-3">成本配置 (每 1K tokens)</h4>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-sm font-medium text-[var(--text-secondary)] mb-1 block">
              输入成本 (美元)
            </label>
            <input
              type="number"
              step="0.0001"
              className="enterprise-input w-full"
              value={formData.cost_input || ''}
              onChange={(e) => onChange({ cost_input: parseFloat(e.target.value) || undefined })}
              placeholder="0.0010"
            />
          </div>
          <div>
            <label className="text-sm font-medium text-[var(--text-secondary)] mb-1 block">
              输出成本 (美元)
            </label>
            <input
              type="number"
              step="0.0001"
              className="enterprise-input w-full"
              value={formData.cost_output || ''}
              onChange={(e) => onChange({ cost_output: parseFloat(e.target.value) || undefined })}
              placeholder="0.0030"
            />
          </div>
        </div>
      </div>

      {/* 开关选项 */}
      <div className="border-t border-[var(--gray-200)] pt-4 space-y-2">
        <label className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
          <input
            type="checkbox"
            checked={formData.is_enabled}
            onChange={(e) => onChange({ is_enabled: e.target.checked })}
            className="rounded border-gray-300"
          />
          启用此供应商
        </label>
        <label className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
          <input
            type="checkbox"
            checked={formData.is_default}
            onChange={(e) => onChange({ is_default: e.target.checked })}
            className="rounded border-gray-300"
          />
          设为默认供应商
        </label>
      </div>
    </div>
  );
}
