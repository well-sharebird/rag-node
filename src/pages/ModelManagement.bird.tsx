import { useState, useEffect, useRef, useMemo } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { useAuth } from '@/src/lib/auth-context';
import { toast } from 'sonner';
import { fetchApi } from '@/lib/api-client';
import { cn } from '@/lib/utils';
import {
  Cpu, Plus, Search, Trash2, Loader2, Server, RefreshCw, Edit,
  MessageSquare, Zap, Terminal, AlertCircle, Settings,
  TrendingUp, Calendar, Activity, ChevronRight, Package, X, Eye,
  ChevronLeft, Filter
} from 'lucide-react';
import { Button } from '../components/bird/Button';
import { Modal } from '../components/bird/Modal';
import { Badge } from '../components/bird/Badge';
import { Input } from '../components/bird/Input';
import { Label } from '../components/bird/Label';
import { Switch } from '../components/bird/Switch';
import { Select } from '../components/bird/Select';
import { Card, CardHeader, CardTitle, CardBody, CardDescription } from '../components/bird/Card';

// ========== Types ==========

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
  is_enabled: boolean;
  is_default: boolean;
  status: string;
  health_status?: string;
  created_at: string;
  updated_at: string;
}

interface ModelConfig {
  id: number;
  name: string;
  model_id: string;
  model_type: string;
  adapter_type: string;
  provider: string;
  description?: string;
  api_url?: string;
  api_key?: string;
  is_enabled: boolean;
  is_default: boolean;
  temperature?: number;
  max_tokens?: number;
  top_p?: number;
  status: string;
  created_at: string;
  updated_at: string;
}

interface ModelFormData {
  id?: number;
  name: string;
  model_id: string;
  model_type: string;
  adapter_type: string;
  provider: string;
  provider_name: string;
  description: string;
  api_url: string;
  api_key: string;
  is_enabled: boolean;
  is_default: boolean;
  temperature?: number;
  max_tokens?: number;
  top_p?: number;
}

interface ProviderFormData {
  id?: number;
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
}

// ========== Constants ==========

const PROVIDER_TYPE_LABELS: Record<string, string> = {
  cloud: '国际云服务',
  domestic: '国内云服务',
  self_hosted: '自托管服务',
};

const MODEL_TYPE_LABELS: Record<string, string> = {
  llm: 'LLM / 对话',
  embedding: 'Embedding / 向量',
  rerank: 'Rerank / 重排序',
  vision: 'Vision / 视觉',
  speech_to_text: 'Speech-to-Text / 语音识别',
  text_to_speech: 'Text-to-Speech / 语音合成',
};

const ADAPTER_TYPE_LABELS: Record<string, string> = {
  local: '本地推理',
  api: 'API 调用',
  ollama: 'Ollama',
  vllm: 'vLLM',
  triton: 'NVIDIA Triton',
  custom: '自定义',
};

const DEFAULT_MODEL_FORM: ModelFormData = {
  name: '',
  model_id: '',
  model_type: 'llm',
  adapter_type: 'api',
  provider: '',
  provider_name: '',
  description: '',
  api_url: '',
  api_key: '',
  is_enabled: true,
  is_default: false,
  temperature: 0.7,
  max_tokens: 4096,
  top_p: 0.9,
};

const DEFAULT_PROVIDER_FORM: ProviderFormData = {
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
};

const MODELS_PER_PAGE = 10;

// ========== Main Component ==========

export function ModelManagementBird() {
  const { t } = useI18n();
  const { token } = useAuth();

  // Data state
  const [providers, setProviders] = useState<ModelProvider[]>([]);
  const [models, setModels] = useState<ModelConfig[]>([]);
  const [loading, setLoading] = useState(true);

  // Selection state - null means "all providers"
  const [selectedProvider, setSelectedProvider] = useState<ModelProvider | null>(null);

  // Provider filter
  const [providerTypeFilter, setProviderTypeFilter] = useState<string>('all');

  // Search & filter
  const [searchTerm, setSearchTerm] = useState('');
  const [filterType, setFilterType] = useState('all');

  // Pagination
  const [currentPage, setCurrentPage] = useState(1);

  // Modal state - Model
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState<'create' | 'edit'>('create');
  const [modelForm, setModelForm] = useState<ModelFormData>(DEFAULT_MODEL_FORM);
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});

  // Modal state - Provider
  const [isProviderModalOpen, setIsProviderModalOpen] = useState(false);
  const [providerModalMode, setProviderModalMode] = useState<'create' | 'edit'>('create');
  const [editingProvider, setEditingProvider] = useState<ModelProvider | null>(null);
  const [providerForm, setProviderForm] = useState<ProviderFormData>(DEFAULT_PROVIDER_FORM);
  const [providerFormErrors, setProviderFormErrors] = useState<Record<string, string>>({});

  // Test dialog state
  const [isTestOpen, setIsTestOpen] = useState(false);
  const [testMode, setTestMode] = useState<'stream' | 'normal'>('stream');
  const [testInput, setTestInput] = useState('你好，请简单介绍一下你自己');
  const [testOutput, setTestOutput] = useState('');
  const [isTesting, setIsTesting] = useState(false);
  const [testError, setTestError] = useState('');
  const [testingModel, setTestingModel] = useState<ModelConfig | null>(null);
  const outputEndRef = useRef<HTMLDivElement>(null);

  // Detail modal state
  const [isDetailModalOpen, setIsDetailModalOpen] = useState(false);
  const [viewingModel, setViewingModel] = useState<ModelConfig | null>(null);

  // Ref to track latest form data for save operation
  const modelFormRef = useRef<ModelFormData>(DEFAULT_MODEL_FORM);
  // Ref to track latest providers
  const providersRef = useRef<ModelProvider[]>([]);

  // Update providers ref
  useEffect(() => {
    providersRef.current = providers;
  }, [providers]);

  // Load data
  const loadProviders = async () => {
    try {
      const data = await fetchApi('/api/v1/model-gateway/providers');
      setProviders((data as any).items || []);
    } catch (e: any) {
      console.error('Failed to load providers:', e);
    }
  };

  const loadModels = async () => {
    try {
      const data = await fetchApi('/api/v1/models');
      setModels((data as any).items || []);
    } catch (e: any) {
      console.error('Failed to load models:', e);
    }
  };

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([loadProviders(), loadModels()]);
      setLoading(false);
    };
    loadData();
  }, []);

  // Debug: log when models or selectedProvider changes
  useEffect(() => {
    console.log('Models updated:', models.length, 'items');
    console.log('Selected provider:', selectedProvider?.name || 'none');
    console.log('Display models count:', displayModels.length);
  }, [models, selectedProvider, displayModels]);

  // Reset pagination when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [selectedProvider, searchTerm, filterType, providerTypeFilter]);

  // Filter providers by type
  const filteredProviders = useMemo(() => {
    let result = providers;

    // Filter by type
    if (providerTypeFilter !== 'all') {
      result = result.filter(p => p.provider_type === providerTypeFilter);
    }

    // Filter by search term
    if (searchTerm) {
      result = result.filter(p =>
        p.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        p.code.toLowerCase().includes(searchTerm.toLowerCase())
      );
    }

    return result;
  }, [providers, providerTypeFilter, searchTerm]);

  // Get models for selected provider (or all if none selected)
  const displayModels = useMemo(() => {
    if (selectedProvider) {
      return models.filter(m => m.provider === selectedProvider.code);
    }
    return models;
  }, [models, selectedProvider]);

  // Filtered models
  const filteredModels = useMemo(() => {
    return displayModels.filter(m => {
      const matchesSearch = m.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                           m.model_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
                           m.provider.toLowerCase().includes(searchTerm.toLowerCase());
      const matchesType = filterType === 'all' || m.model_type === filterType;
      return matchesSearch && matchesType;
    });
  }, [displayModels, searchTerm, filterType]);

  // Pagination
  const totalPages = Math.ceil(filteredModels.length / MODELS_PER_PAGE);
  const paginatedModels = useMemo(() => {
    const start = (currentPage - 1) * MODELS_PER_PAGE;
    return filteredModels.slice(start, start + MODELS_PER_PAGE);
  }, [filteredModels, currentPage]);

  // Get provider name by code
  const getProviderName = (providerCode: string) => {
    const provider = providers.find(p => p.code === providerCode);
    return provider?.name || providerCode;
  };

  // Model CRUD
  const handleSaveModel = async () => {
    // Use ref to get latest form data
    const currentForm = modelFormRef.current;

    console.log('handleSaveModel called, currentForm:', currentForm);

    const errors: Record<string, string> = {};
    if (!currentForm.name.trim()) errors.name = '模型名称为必填项';
    if (!currentForm.model_id.trim()) errors.model_id = '模型 ID 为必填项';
    if (!currentForm.api_url.trim()) errors.api_url = 'API URL 为必填项';
    if (!currentForm.provider.trim()) errors.provider = '必须选择供应商';

    if (Object.keys(errors).length > 0) {
      setFormErrors(errors);
      toast.error('请填写所有必填项');
      return;
    }

    try {
      const submitData = {
        id: currentForm.id,
        name: currentForm.name,
        model_id: currentForm.model_id,
        model_type: currentForm.model_type,
        adapter_type: currentForm.adapter_type,
        provider: currentForm.provider,
        description: currentForm.description,
        api_url: currentForm.api_url,
        api_key: currentForm.api_key,
        is_enabled: currentForm.is_enabled,
        is_default: currentForm.is_default,
        temperature: currentForm.model_type === 'llm' ? currentForm.temperature : undefined,
        max_tokens: currentForm.model_type === 'llm' ? currentForm.max_tokens : undefined,
        top_p: currentForm.model_type === 'llm' ? currentForm.top_p : undefined,
      };

      console.log('Submitting to API:', `/api/v1/models/${currentForm.id}`, submitData);

      const response = await fetchApi(`/api/v1/models/${currentForm.id}`, {
        method: 'PUT',
        body: JSON.stringify(submitData),
      });

      console.log('API response:', response);
      toast.success('模型已更新');

      // Reload models first to get updated data
      await loadModels();

      // Then switch to the new provider
      if (currentForm.provider) {
        const newProvider = providersRef.current.find(p => p.code === currentForm.provider);
        if (newProvider) {
          console.log('Switching to provider:', newProvider.name);
          setSelectedProvider(newProvider);
        }
      }

      setIsModalOpen(false);
      setModelForm(DEFAULT_MODEL_FORM);
      setFormErrors({});
    } catch (e: any) {
      console.error('Save failed:', e);
      toast.error(`保存失败：${e.message}`);
    }
  };

  const handleDeleteModel = async (id: number) => {
    if (!window.confirm('确定要删除此模型吗？')) return;
    try {
      await fetchApi(`/api/v1/models/${id}`, { method: 'DELETE' });
      toast.success('模型已删除');
      await loadModels();
    } catch (e: any) {
      toast.error(`删除失败：${e.message}`);
    }
  };

  const handleEditModel = (model: ModelConfig) => {
    setModalMode('edit');
    const provider = providers.find(p => p.code === model.provider);
    const newForm = {
      id: model.id,
      name: model.name,
      model_id: model.model_id,
      model_type: model.model_type,
      adapter_type: model.adapter_type,
      provider: model.provider,
      provider_name: provider?.name || model.provider,
      description: model.description || '',
      api_url: model.api_url || '',
      api_key: model.api_key || '',
      is_enabled: model.is_enabled,
      is_default: model.is_default,
      temperature: model.temperature ?? 0.7,
      max_tokens: model.max_tokens ?? 4096,
      top_p: model.top_p ?? 0.9,
    };
    console.log('Opening edit modal for model:', model.name, 'provider:', model.provider);
    console.log('Form data:', newForm);
    setModelForm(newForm);
    modelFormRef.current = newForm;
    setFormErrors({});
    setIsModalOpen(true);
  };

  const handleViewDetail = (model: ModelConfig) => {
    setViewingModel(model);
    setIsDetailModalOpen(true);
  };

  const handleToggleModelEnabled = async (id: number, current: boolean) => {
    try {
      await fetchApi(`/api/v1/models/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ is_enabled: !current }),
      });
      toast.success(current ? '已禁用' : '已启用');
      await loadModels();
    } catch (e: any) {
      toast.error(`设置失败：${e.message}`);
    }
  };

  const handleToggleProviderEnabled = async (id: number, current: boolean) => {
    try {
      await fetchApi(`/api/v1/model-gateway/providers/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ is_enabled: !current }),
      });
      toast.success(current ? '已禁用' : '已启用');
      await loadProviders();
    } catch (e: any) {
      toast.error(`设置失败：${e.message}`);
    }
  };

  // Test functions
  const handleOpenTest = (model: ModelConfig) => {
    setTestingModel(model);
    setTestOutput('');
    setTestError('');
    setTestMode('stream');
    setTestInput('你好，请简单介绍一下你自己');
    setIsTestOpen(true);
  };

  const handleTestModel = async () => {
    if (!testingModel) return;
    setIsTesting(true);
    setTestError('');
    setTestOutput('');

    try {
      if (testMode === 'stream') {
        await testStreamModel();
      } else {
        await testNormalModel();
      }
    } catch (e: any) {
      setTestError(e.message || '测试失败');
      toast.error(`测试失败：${e.message}`);
    } finally {
      setIsTesting(false);
    }
  };

  const testStreamModel = async () => {
    if (!testingModel) return;

    const response = await fetch('/api/v1/model-gateway/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('auth_token')}`,
      },
      body: JSON.stringify({
        model_id: testingModel.model_id,
        messages: [{ role: 'user', content: testInput }],
        stream: true,
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error('No reader');

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          if (data === '[DONE]') continue;
          try {
            const parsed = JSON.parse(data);
            const content = parsed.choices?.[0]?.delta?.content || parsed.content || '';
            if (content) {
              setTestOutput(prev => prev + content);
            }
          } catch {
            // Ignore parse errors
          }
        }
      }
    }
  };

  const testNormalModel = async () => {
    if (!testingModel) return;

    const response = await fetch('/api/v1/model-gateway/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('auth_token')}`,
      },
      body: JSON.stringify({
        model_id: testingModel.model_id,
        messages: [{ role: 'user', content: testInput }],
        stream: false,
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    const content = data.content || data.choices?.[0]?.message?.content || '';
    setTestOutput(content);
  };

  const openCreateModal = () => {
    setModalMode('create');
    if (selectedProvider) {
      setModelForm({
        ...DEFAULT_MODEL_FORM,
        provider: selectedProvider.code,
        provider_name: selectedProvider.name,
        api_url: selectedProvider.base_url,
      });
    } else {
      setModelForm(DEFAULT_MODEL_FORM);
    }
    setFormErrors({});
    setIsModalOpen(true);
  };

  const handleProviderChangeInForm = (providerCode: string) => {
    const provider = providers.find(p => p.code === providerCode);
    console.log('Provider changed to:', providerCode, provider);
    setModelForm((prev) => {
      const newForm = {
        ...prev,
        provider: providerCode,
        provider_name: provider?.name || providerCode,
        api_url: provider?.base_url || '',
      };
      console.log('New form data:', newForm);
      modelFormRef.current = newForm;
      return newForm;
    });
  };

  // Provider CRUD
  const handleSaveProvider = async () => {
    const errors: Record<string, string> = {};
    if (!providerForm.name.trim()) errors.name = '供应商名称为必填项';
    if (!providerForm.code.trim()) errors.code = '供应商代码为必填项';
    if (!providerForm.base_url.trim()) errors.base_url = 'API 基础 URL 为必填项';

    if (Object.keys(errors).length > 0) {
      setProviderFormErrors(errors);
      toast.error('请填写所有必填项');
      return;
    }

    try {
      const submitData = {
        name: providerForm.name,
        code: providerForm.code,
        description: providerForm.description,
        provider_type: providerForm.provider_type,
        region: providerForm.region,
        base_url: providerForm.base_url,
        api_version: providerForm.api_version,
        auth_type: providerForm.auth_type,
        api_key_name: providerForm.api_key_name,
        api_key: providerForm.api_key,
        is_enabled: providerForm.is_enabled,
        is_default: providerForm.is_default,
      };

      if (providerModalMode === 'edit' && editingProvider) {
        await fetchApi(`/api/v1/model-gateway/providers/${editingProvider.id}`, {
          method: 'PUT',
          body: JSON.stringify(submitData),
        });
        toast.success('供应商已更新');
      } else {
        await fetchApi('/api/v1/model-gateway/providers', {
          method: 'POST',
          body: JSON.stringify(submitData),
        });
        toast.success('供应商已创建');
      }
      setIsProviderModalOpen(false);
      setProviderForm(DEFAULT_PROVIDER_FORM);
      setProviderFormErrors({});
      await loadProviders();
      setEditingProvider(null);
    } catch (e: any) {
      toast.error(`保存失败：${e.message}`);
    }
  };

  const handleDeleteProvider = async (id: number) => {
    if (!window.confirm('确定要删除此供应商吗？删除后其下的模型将无法正常调用。')) return;
    try {
      await fetchApi(`/api/v1/model-gateway/providers/${id}`, { method: 'DELETE' });
      toast.success('供应商已删除');
      await loadProviders();
      if (selectedProvider?.id === id) {
        setSelectedProvider(null);
      }
    } catch (e: any) {
      toast.error(`删除失败：${e.message}`);
    }
  };

  const handleEditProvider = (provider: ModelProvider) => {
    setProviderModalMode('edit');
    setEditingProvider(provider);
    setProviderForm({
      id: provider.id,
      name: provider.name,
      code: provider.code,
      description: provider.description || '',
      provider_type: provider.provider_type,
      region: provider.region || '',
      base_url: provider.base_url,
      api_version: provider.api_version || '',
      auth_type: provider.auth_type,
      api_key_name: provider.api_key_name || 'Authorization',
      api_key: '',
      is_enabled: provider.is_enabled,
      is_default: provider.is_default,
    });
    setProviderFormErrors({});
    setIsProviderModalOpen(true);
  };

  const openCreateProviderModal = () => {
    setProviderModalMode('create');
    setProviderForm(DEFAULT_PROVIDER_FORM);
    setProviderFormErrors({});
    setIsProviderModalOpen(true);
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-[var(--bird-bg-primary)]">
      {/* Header */}
      <header className="h-[60px] px-6 bg-[var(--bird-sidebar-bg)] flex items-center justify-between shrink-0 border-b border-[var(--bird-sidebar-border)]">
        <div className="flex items-baseline gap-3">
          <h1 className="text-[18px] font-semibold text-[var(--bird-text-primary)]">模型管理</h1>
          <span className="text-[13px] text-[var(--bird-text-tertiary)]">管理供应商及其下的模型配置</span>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" onClick={openCreateProviderModal}>
            <Server className="w-4 h-4 mr-2" />
            添加供应商
          </Button>
          <Button variant="primary" size="md" onClick={openCreateModal}>
            <Plus className="w-4 h-4 mr-2" />
            添加模型
          </Button>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left - Provider List with Filter */}
        <div className="w-80 border-r border-[var(--bird-neutral-200)] bg-[var(--bird-card-bg)] flex flex-col">
          <div className="p-4 border-b border-[var(--bird-neutral-200)] space-y-3">
            <div className="flex items-center justify-between">
              <Label className="text-[12px] font-medium">供应商列表</Label>
              <Badge variant="neutral">{filteredProviders.length}</Badge>
            </div>

            {/* Provider Type Filter */}
            <Select
              value={providerTypeFilter}
              onChange={(e) => setProviderTypeFilter(e.target.value)}
              options={[
                { value: 'all', label: '全部类型' },
                { value: 'cloud', label: '国际云服务' },
                { value: 'domestic', label: '国内云服务' },
                { value: 'self_hosted', label: '自托管服务' },
              ]}
            />

            {/* Search */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--bird-text-tertiary)]" />
              <Input
                placeholder="搜索供应商..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10"
              />
            </div>
          </div>

          {/* All Providers Option */}
          <div
            className={cn(
              "px-4 py-3 cursor-pointer transition-colors border-b border-[var(--bird-neutral-100)]",
              !selectedProvider
                ? "bg-[var(--bird-primary-50)] border-l-4 border-l-[var(--bird-primary-500)]"
                : "hover:bg-[var(--bird-neutral-50)]"
            )}
            onClick={() => {
              setSelectedProvider(null);
              setSearchTerm('');
              setProviderTypeFilter('all');
            }}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Package className={cn(
                  "w-4 h-4",
                  !selectedProvider ? "text-[var(--bird-primary-600)]" : "text-[var(--bird-text-tertiary)]"
                )} />
                <span className={cn(
                  "text-[14px] font-medium",
                  !selectedProvider ? "text-[var(--bird-primary-600)]" : "text-[var(--bird-text-primary)]"
                )}>
                  全部供应商
                </span>
              </div>
              <Badge variant={selectedProvider ? 'neutral' : 'primary'}>
                {models.length}
              </Badge>
            </div>
          </div>

          {/* Provider List */}
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {loading ? (
              <div className="flex items-center justify-center py-10">
                <Loader2 className="w-6 h-6 animate-spin text-[var(--bird-primary-600)]" />
              </div>
            ) : filteredProviders.length === 0 ? (
              <div className="text-center py-10">
                <Server className="w-12 h-12 text-[var(--bird-text-tertiary)] mx-auto mb-3" />
                <p className="text-[13px] text-[var(--bird-text-tertiary)]">暂无供应商</p>
              </div>
            ) : (
              filteredProviders.map((provider) => {
                const modelCount = models.filter(m => m.provider === provider.code).length;
                return (
                  <div
                    key={provider.id}
                    className={cn(
                      "p-3 rounded-xl cursor-pointer transition-colors border group",
                      selectedProvider?.id === provider.id
                        ? "bg-[var(--bird-primary-100)] border-[var(--bird-primary-300)]"
                        : "bg-[var(--bird-card-bg)] border-[var(--bird-card-border)] hover:bg-[var(--bird-neutral-50)]"
                    )}
                    onClick={() => {
                      setSelectedProvider(provider);
                    }}
                  >
                    <div className="flex items-start justify-between mb-2">
                      <h3 className="text-[14px] font-medium text-[var(--bird-text-primary)] truncate flex-1">
                        {provider.name}
                      </h3>
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 w-6 p-0"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleEditProvider(provider);
                          }}
                        >
                          <Edit className="w-3.5 h-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 w-6 p-0 text-[var(--bird-error)]"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteProvider(provider.id);
                          }}
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                      <div className={cn(
                        "w-2 h-2 rounded-full mt-1.5",
                        provider.health_status === 'healthy' ? 'bg-green-500' :
                        provider.health_status === 'degraded' ? 'bg-yellow-500' :
                        provider.health_status === 'unhealthy' ? 'bg-red-500' : 'bg-gray-400'
                      )} />
                    </div>
                    <p className="text-[12px] text-[var(--bird-text-tertiary)] line-clamp-2 mb-2">
                      {provider.description || PROVIDER_TYPE_LABELS[provider.provider_type]}
                    </p>
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] text-[var(--bird-text-tertiary)]">
                        {modelCount} 个模型
                      </span>
                      <Switch
                        checked={provider.is_enabled}
                        onCheckedChange={(v) => handleToggleProviderEnabled(provider.id, provider.is_enabled)}
                        onClick={(e) => e.stopPropagation()}
                        size="sm"
                      />
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right - Model Table */}
        <div className="flex-1 flex flex-col overflow-hidden bg-[var(--bird-bg-primary)]">
          {/* Toolbar */}
          <div className="h-[60px] px-6 border-b border-[var(--bird-neutral-200)] bg-[var(--bird-card-bg)] flex items-center justify-between shrink-0">
            <div>
              <h2 className="text-[16px] font-semibold text-[var(--bird-text-primary)]">
                {selectedProvider ? selectedProvider.name : '全部模型'}
              </h2>
              <p className="text-[12px] text-[var(--bird-text-tertiary)]">
                {selectedProvider ? selectedProvider.base_url : `${filteredModels.length} 个模型`}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--bird-text-tertiary)]" />
                <Input
                  placeholder="搜索模型..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-9 h-8 w-48 text-xs"
                />
              </div>
              <Select
                value={filterType}
                onChange={(e) => setFilterType(e.target.value)}
                options={[
                  { value: 'all', label: '全部类型' },
                  { value: 'llm', label: 'LLM' },
                  { value: 'embedding', label: 'Embedding' },
                  { value: 'rerank', label: 'Rerank' },
                  { value: 'vision', label: 'Vision' },
                ]}
              />
            </div>
          </div>

          {/* Model Table */}
          <div className="flex-1 overflow-y-auto">
            <table className="w-full">
              <thead className="bg-[var(--bird-neutral-50)] sticky top-0 z-10">
                <tr className="border-b border-[var(--bird-neutral-200)]">
                  <th className="text-left text-[12px] font-medium text-[var(--bird-text-tertiary)] px-6 py-3">
                    模型名称
                  </th>
                  <th className="text-left text-[12px] font-medium text-[var(--bird-text-tertiary)] px-6 py-3">
                    模型 ID
                  </th>
                  <th className="text-left text-[12px] font-medium text-[var(--bird-text-tertiary)] px-6 py-3">
                    供应商
                  </th>
                  <th className="text-left text-[12px] font-medium text-[var(--bird-text-tertiary)] px-6 py-3">
                    类型
                  </th>
                  <th className="text-left text-[12px] font-medium text-[var(--bird-text-tertiary)] px-6 py-3">
                    适配器
                  </th>
                  <th className="text-left text-[12px] font-medium text-[var(--bird-text-tertiary)] px-6 py-3">
                    状态
                  </th>
                  <th className="text-right text-[12px] font-medium text-[var(--bird-text-tertiary)] px-6 py-3">
                    操作
                  </th>
                </tr>
              </thead>
              <tbody>
                {paginatedModels.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="text-center py-10">
                      <Cpu className="w-10 h-10 text-[var(--bird-text-tertiary)] mx-auto mb-2" />
                      <p className="text-[13px] text-[var(--bird-text-tertiary)]">
                        {displayModels.length === 0 ? '暂无模型' : '没有找到匹配的模型'}
                      </p>
                      {displayModels.length === 0 && (
                        <Button
                          variant="secondary"
                          size="sm"
                          className="mt-3"
                          onClick={openCreateModal}
                        >
                          <Plus className="w-3.5 h-3.5 mr-1" />
                          添加模型
                        </Button>
                      )}
                    </td>
                  </tr>
                ) : (
                  paginatedModels.map((model) => (
                    <tr
                      key={model.id}
                      className="border-b border-[var(--bird-neutral-100)] hover:bg-[var(--bird-neutral-50)]"
                    >
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          <div className="w-8 h-8 rounded-lg bg-[var(--bird-primary-100)] flex items-center justify-center">
                            <Cpu className="w-4 h-4 text-[var(--bird-primary-600)]" />
                          </div>
                          <div>
                            <p className="text-[14px] font-medium text-[var(--bird-text-primary)]">
                              {model.name}
                            </p>
                            {model.is_default && (
                              <Badge variant="primary" className="text-[9px] px-1 mt-0.5">默认</Badge>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <code className="text-[12px] bg-[var(--bird-neutral-100)] px-2 py-1 rounded">
                          {model.model_id}
                        </code>
                      </td>
                      <td className="px-6 py-4">
                        <span className="text-[13px] text-[var(--bird-text-secondary)]">
                          {getProviderName(model.provider)}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <Badge
                          variant={model.model_type === 'llm' ? 'primary' : 'neutral'}
                          className="text-[10px] px-2 py-0.5"
                        >
                          {MODEL_TYPE_LABELS[model.model_type].split('/')[0]}
                        </Badge>
                      </td>
                      <td className="px-6 py-4">
                        <span className="text-[13px] text-[var(--bird-text-secondary)]">
                          {ADAPTER_TYPE_LABELS[model.adapter_type]}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          <div className={cn(
                            "w-2 h-2 rounded-full",
                            model.status === 'active' ? 'bg-green-500' : 'bg-red-500'
                          )} />
                          <span className="text-[13px] text-[var(--bird-text-secondary)]">
                            {model.status}
                          </span>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 px-2"
                            onClick={() => handleViewDetail(model)}
                          >
                            <Eye className="w-3.5 h-3.5 mr-1" />
                            详情
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 px-2"
                            onClick={() => handleEditModel(model)}
                          >
                            <Edit className="w-3.5 h-3.5 mr-1" />
                            编辑
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 px-2 text-[var(--bird-error)]"
                            onClick={() => handleDeleteModel(model.id)}
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </Button>
                          <div className="w-px h-4 bg-[var(--bird-neutral-200)] mx-1" />
                          <Switch
                            checked={model.is_enabled}
                            onCheckedChange={(v) => handleToggleModelEnabled(model.id, model.is_enabled)}
                            size="sm"
                          />
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="h-[50px] px-6 border-t border-[var(--bird-neutral-200)] bg-[var(--bird-card-bg)] flex items-center justify-between shrink-0">
              <p className="text-[12px] text-[var(--bird-text-tertiary)]">
                第 {(currentPage - 1) * MODELS_PER_PAGE + 1} - {Math.min(currentPage * MODELS_PER_PAGE, filteredModels.length)} 条，共 {filteredModels.length} 条
              </p>
              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={currentPage === 1}
                  onClick={() => setCurrentPage(currentPage - 1)}
                >
                  <ChevronLeft className="w-4 h-4 mr-1" />
                  上一页
                </Button>
                <div className="flex items-center gap-1">
                  {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                    let pageNum;
                    if (totalPages <= 5) {
                      pageNum = i + 1;
                    } else if (currentPage <= 3) {
                      pageNum = i + 1;
                    } else if (currentPage >= totalPages - 2) {
                      pageNum = totalPages - 4 + i;
                    } else {
                      pageNum = currentPage - 2 + i;
                    }
                    return (
                      <Button
                        key={pageNum}
                        variant={currentPage === pageNum ? 'primary' : 'secondary'}
                        size="sm"
                        className="w-8 h-8 p-0"
                        onClick={() => setCurrentPage(pageNum)}
                      >
                        {pageNum}
                      </Button>
                    );
                  })}
                </div>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={currentPage === totalPages}
                  onClick={() => setCurrentPage(currentPage + 1)}
                >
                  下一页
                  <ChevronRight className="w-4 h-4 ml-1" />
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Create/Edit Model Modal */}
      <Modal
        open={isModalOpen}
        onOpenChange={(open) => {
          setIsModalOpen(open);
          if (!open) {
            setFormErrors({});
          }
        }}
        title={modalMode === 'create' ? '添加模型' : '编辑模型'}
        description={modalMode === 'create'
          ? '配置新的模型实例'
          : '修改模型配置信息'}
        width="700px"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsModalOpen(false)}>取消</Button>
            <Button variant="primary" onClick={handleSaveModel}>保存</Button>
          </>
        }
      >
        <div className="space-y-4 py-2">
          {/* Provider Selection - Required */}
          <div>
            <Label>所属供应商 *</Label>
            <Select
              value={modelForm.provider}
              onChange={(e) => handleProviderChangeInForm(e.target.value)}
              options={providers.map(p => ({ value: p.code, label: p.name }))}
              placeholder="选择供应商"
            />
            {formErrors.provider && <p className="text-xs text-red-500 mt-1">{formErrors.provider}</p>}
            {modelForm.provider && (
              <p className="text-xs text-[var(--bird-text-tertiary)] mt-1">
                已选择：{modelForm.provider_name} - {modelForm.api_url}
              </p>
            )}
          </div>

          {/* Basic Info */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>模型名称 *</Label>
              <Input
                value={modelForm.name}
                onChange={(e) => setModelForm({ ...modelForm, name: e.target.value })}
                placeholder="如：Qwen2.5-72B"
              />
              {formErrors.name && <p className="text-xs text-red-500 mt-1">{formErrors.name}</p>}
            </div>
            <div>
              <Label>模型类型</Label>
              <Select
                value={modelForm.model_type}
                onChange={(e) => setModelForm({ ...modelForm, model_type: e.target.value })}
                options={Object.entries(MODEL_TYPE_LABELS).map(([v, l]) => ({ value: v, label: l }))}
              />
            </div>
          </div>

          <div>
            <Label>模型 ID *</Label>
            <Input
              value={modelForm.model_id}
              onChange={(e) => setModelForm({ ...modelForm, model_id: e.target.value })}
              placeholder="如：Qwen/Qwen2.5-72B-Instruct"
            />
            {formErrors.model_id && <p className="text-xs text-red-500 mt-1">{formErrors.model_id}</p>}
          </div>

          <div>
            <Label>适配器类型</Label>
            <Select
              value={modelForm.adapter_type}
              onChange={(e) => setModelForm({ ...modelForm, adapter_type: e.target.value })}
              options={Object.entries(ADAPTER_TYPE_LABELS).map(([v, l]) => ({ value: v, label: l }))}
            />
          </div>

          <div>
            <Label>描述</Label>
            <Input
              value={modelForm.description}
              onChange={(e) => setModelForm({ ...modelForm, description: e.target.value })}
              placeholder="可选描述"
            />
          </div>

          {/* Connection - Auto-filled from provider */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>API URL *</Label>
              <Input
                value={modelForm.api_url}
                onChange={(e) => setModelForm({ ...modelForm, api_url: e.target.value })}
                placeholder="https://api.example.com/v1"
              />
              {formErrors.api_url && <p className="text-xs text-red-500 mt-1">{formErrors.api_url}</p>}
            </div>
            <div>
              <Label>API Key</Label>
              <Input
                type="password"
                value={modelForm.api_key}
                onChange={(e) => setModelForm({ ...modelForm, api_key: e.target.value })}
                placeholder={modalMode === 'edit' ? "留空则不修改" : "sk-..."}
              />
            </div>
          </div>

          {/* LLM Parameters */}
          {modelForm.model_type === 'llm' && (
            <div className="grid grid-cols-3 gap-4 pt-4 border-t">
              <div>
                <Label>Temperature</Label>
                <Input
                  type="number"
                  step="0.1"
                  min="0"
                  max="2"
                  value={modelForm.temperature}
                  onChange={(e) => setModelForm({ ...modelForm, temperature: parseFloat(e.target.value) || 0.7 })}
                />
              </div>
              <div>
                <Label>Max Tokens</Label>
                <Input
                  type="number"
                  value={modelForm.max_tokens}
                  onChange={(e) => setModelForm({ ...modelForm, max_tokens: parseInt(e.target.value) || 4096 })}
                />
              </div>
              <div>
                <Label>Top-P</Label>
                <Input
                  type="number"
                  step="0.1"
                  min="0"
                  max="1"
                  value={modelForm.top_p}
                  onChange={(e) => setModelForm({ ...modelForm, top_p: parseFloat(e.target.value) || 0.9 })}
                />
              </div>
            </div>
          )}

          {/* Toggles */}
          <div className="flex items-center gap-4 pt-4 border-t">
            <label className="flex items-center gap-2 text-sm">
              <Switch
                checked={modelForm.is_enabled}
                onCheckedChange={(v) => setModelForm({ ...modelForm, is_enabled: v })}
              />
              启用此模型
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Switch
                checked={modelForm.is_default}
                onCheckedChange={(v) => setModelForm({ ...modelForm, is_default: v })}
              />
              设为默认模型
            </label>
          </div>
        </div>
      </Modal>

      {/* Model Detail Modal */}
      <Modal
        open={isDetailModalOpen}
        onOpenChange={(open) => {
          setIsDetailModalOpen(open);
          if (!open) {
            setViewingModel(null);
          }
        }}
        title="模型详情"
        description="查看模型配置详情"
        width="800px"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsDetailModalOpen(false)}>关闭</Button>
            <Button
              variant="primary"
              onClick={() => {
                setIsDetailModalOpen(false);
                if (viewingModel) handleEditModel(viewingModel);
              }}
            >
              <Edit className="w-4 h-4 mr-2" />
              编辑
            </Button>
          </>
        }
      >
        {viewingModel && (
          <div className="space-y-6 py-2">
            {/* Basic Info */}
            <Card>
              <CardHeader>
                <CardTitle>基本信息</CardTitle>
                <CardDescription>模型配置和类型信息</CardDescription>
              </CardHeader>
              <CardBody className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-[12px] text-[var(--bird-text-tertiary)] mb-1">模型名称</p>
                    <p className="text-[14px] font-medium">{viewingModel.name}</p>
                  </div>
                  <div>
                    <p className="text-[12px] text-[var(--bird-text-tertiary)] mb-1">模型 ID</p>
                    <code className="text-[13px] bg-[var(--bird-neutral-100)] px-2 py-1 rounded">
                      {viewingModel.model_id}
                    </code>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-[12px] text-[var(--bird-text-tertiary)] mb-1">模型类型</p>
                    <Badge variant="primary">{MODEL_TYPE_LABELS[viewingModel.model_type]}</Badge>
                  </div>
                  <div>
                    <p className="text-[12px] text-[var(--bird-text-tertiary)] mb-1">适配器类型</p>
                    <span className="text-[14px]">{ADAPTER_TYPE_LABELS[viewingModel.adapter_type]}</span>
                  </div>
                </div>
                <div>
                  <p className="text-[12px] text-[var(--bird-text-tertiary)] mb-1">描述</p>
                  <p className="text-[14px]">{viewingModel.description || '-'}</p>
                </div>
              </CardBody>
            </Card>

            {/* Provider & Connection */}
            <Card>
              <CardHeader>
                <CardTitle>供应商与连接</CardTitle>
                <CardDescription>所属供应商和 API 配置</CardDescription>
              </CardHeader>
              <CardBody className="space-y-4">
                <div className="flex items-center gap-2 p-3 bg-[var(--bird-neutral-50)] rounded-lg">
                  <Server className="w-4 h-4 text-[var(--bird-text-tertiary)]" />
                  <span className="text-[14px] font-medium">{viewingModel.provider}</span>
                  <ChevronRight className="w-4 h-4 text-[var(--bird-text-tertiary)]" />
                  <span className="text-[13px] text-[var(--bird-text-secondary)]">
                    {getProviderName(viewingModel.provider)}
                  </span>
                </div>
                <div>
                  <p className="text-[12px] text-[var(--bird-text-tertiary)] mb-1">API URL</p>
                  <code className="text-[13px] bg-[var(--bird-neutral-100)] px-3 py-2 rounded-lg block break-all">
                    {viewingModel.api_url}
                  </code>
                </div>
              </CardBody>
            </Card>

            {/* Model Parameters */}
            {viewingModel.model_type === 'llm' && (
              <Card>
                <CardHeader>
                  <CardTitle>推理参数</CardTitle>
                  <CardDescription>默认生成参数配置</CardDescription>
                </CardHeader>
                <CardBody>
                  <div className="grid grid-cols-3 gap-4">
                    <div className="p-3 bg-[var(--bird-neutral-50)] rounded-lg">
                      <p className="text-[11px] text-[var(--bird-text-tertiary)] mb-1">Temperature</p>
                      <p className="text-[16px] font-semibold">{viewingModel.temperature ?? 0.7}</p>
                    </div>
                    <div className="p-3 bg-[var(--bird-neutral-50)] rounded-lg">
                      <p className="text-[11px] text-[var(--bird-text-tertiary)] mb-1">Max Tokens</p>
                      <p className="text-[16px] font-semibold">{viewingModel.max_tokens ?? 4096}</p>
                    </div>
                    <div className="p-3 bg-[var(--bird-neutral-50)] rounded-lg">
                      <p className="text-[11px] text-[var(--bird-text-tertiary)] mb-1">Top-P</p>
                      <p className="text-[16px] font-semibold">{viewingModel.top_p ?? 0.9}</p>
                    </div>
                  </div>
                </CardBody>
              </Card>
            )}

            {/* Status */}
            <Card>
              <CardHeader>
                <CardTitle>状态</CardTitle>
                <CardDescription>运行状态和启用控制</CardDescription>
              </CardHeader>
              <CardBody>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <p className="text-[12px] text-[var(--bird-text-tertiary)]">运行状态</p>
                    <div className="flex items-center gap-2">
                      <div className={cn(
                        "w-2 h-2 rounded-full",
                        viewingModel.status === 'active' ? 'bg-green-500' : 'bg-red-500'
                      )} />
                      <span className="text-[14px] font-medium">{viewingModel.status}</span>
                    </div>
                  </div>
                  <div className="space-y-1">
                    <p className="text-[12px] text-[var(--bird-text-tertiary)]">启用状态</p>
                    <Switch
                      checked={viewingModel.is_enabled}
                      onCheckedChange={(v) => handleToggleModelEnabled(viewingModel.id, viewingModel.is_enabled)}
                    />
                  </div>
                </div>
              </CardBody>
            </Card>

            {/* Meta */}
            <Card>
              <CardHeader>
                <CardTitle>元信息</CardTitle>
              </CardHeader>
              <CardBody>
                <div className="grid grid-cols-2 gap-4">
                  <div className="flex items-center gap-2">
                    <Calendar className="w-4 h-4 text-[var(--bird-text-tertiary)]" />
                    <div>
                      <p className="text-[11px] text-[var(--bird-text-tertiary)]">创建时间</p>
                      <p className="text-[13px]">
                        {new Date(viewingModel.created_at).toLocaleString('zh-CN')}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <RefreshCw className="w-4 h-4 text-[var(--bird-text-tertiary)]" />
                    <div>
                      <p className="text-[11px] text-[var(--bird-text-tertiary)]">更新时间</p>
                      <p className="text-[13px]">
                        {new Date(viewingModel.updated_at).toLocaleString('zh-CN')}
                      </p>
                    </div>
                  </div>
                </div>
              </CardBody>
            </Card>
          </div>
        )}
      </Modal>

      {/* Test Dialog */}
      <Modal
        open={isTestOpen}
        onOpenChange={(open) => {
          setIsTestOpen(open);
          if (!open) {
            setTestOutput('');
            setTestError('');
          }
        }}
        title={testingModel?.name || '模型测试'}
        description="测试模型对话效果（支持流式和非流式模式）"
        width="800px"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsTestOpen(false)}>关闭</Button>
            <Button
              variant="primary"
              onClick={handleTestModel}
              disabled={isTesting || !testInput.trim()}
            >
              {isTesting ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  生成中...
                </>
              ) : (
                <>
                  <MessageSquare className="w-4 h-4 mr-2" />
                  开始测试
                </>
              )}
            </Button>
          </>
        }
      >
        <div className="space-y-4 py-2">
          <div className="flex items-center gap-2">
            <Button
              variant={testMode === 'stream' ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => setTestMode('stream')}
            >
              <Zap className="w-4 h-4 mr-2" />
              流式模式
            </Button>
            <Button
              variant={testMode === 'normal' ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => setTestMode('normal')}
            >
              <Terminal className="w-4 h-4 mr-2" />
              非流式模式
            </Button>
          </div>

          <div>
            <Label>输入问题</Label>
            <textarea
              className="w-full bird-input min-h-[80px]"
              value={testInput}
              onChange={(e) => setTestInput(e.target.value)}
              placeholder="输入你的问题..."
              rows={3}
            />
          </div>

          <div>
            <Label>模型输出</Label>
            <div className="w-full min-h-[200px] p-4 rounded-lg border border-[var(--bird-neutral-200)] bg-[var(--bird-neutral-50)]">
              {isTesting && !testOutput && (
                <div className="flex items-center justify-center h-full">
                  <Loader2 className="w-6 h-6 animate-spin text-[var(--bird-primary-600)]" />
                </div>
              )}
              {testError && (
                <div className="text-red-500 text-sm">
                  <AlertCircle className="w-4 h-4 inline mr-2" />
                  {testError}
                </div>
              )}
              {testOutput && (
                <div className="text-sm whitespace-pre-wrap leading-relaxed">
                  {testOutput}
                </div>
              )}
              <div ref={outputEndRef} />
            </div>
          </div>
        </div>
      </Modal>
    </div>
  );
}
