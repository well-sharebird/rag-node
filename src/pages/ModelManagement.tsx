import { useState, useEffect, useRef, useMemo } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { useAuth } from '@/src/lib/auth-context';
import { toast } from 'sonner';
import { fetchApi } from '@/lib/api-client';
import { getApiUrl } from '@/src/lib/env';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { cn } from '@/lib/utils';
import {
  Cpu, Plus, Search, Trash2, Loader2, Server, RefreshCw, Edit,
  MessageSquare, Zap, Terminal, AlertCircle, Settings,
  TrendingUp, Calendar, Activity, ChevronRight, Package, X, Eye,
  ChevronLeft, Filter
} from 'lucide-react';
import { Button } from '../components/enterprise/Button';
import { Modal } from '../components/enterprise/Modal';
import { Badge } from '../components/enterprise/Badge';
import { Input } from '../components/enterprise/Input';
import { Label } from '../components/enterprise/Label';
import { Switch } from '../components/enterprise/Switch';
import { Select } from '../components/enterprise/Select';
import { Card, CardHeader, CardTitle, CardBody, CardDescription } from '../components/enterprise/Card';

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
  api_key?: string;  // 后端返回的掩码值（如 sk-D••••••yjlg），仅用于展示
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
  last_tested_at?: string;
  tags?: string[];
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

export function ModelManagement() {
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
  const [streamDebug, setStreamDebug] = useState('');
  const [showRaw, setShowRaw] = useState(false);        // 是否显示后端返回的原始 SSE 数据
  const [rawEvents, setRawEvents] = useState<string[]>([]); // 收集到的原始事件（带时间戳）
  const outputEndRef = useRef<HTMLDivElement>(null);
  // Use ref to accumulate content for immediate updates
  const testOutputRef = useRef('');
  const chunkCountRef = useRef(0);

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
      const filtered = models.filter(m => m.provider === selectedProvider.code);
      console.log('[ModelManagement] selectedProvider.code =', selectedProvider.code, '| models count =', models.length, '| filtered count =', filtered.length);
      return filtered;
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
    const currentForm = modelFormRef.current;

    const errors: Record<string, string> = {};
    if (!currentForm.name.trim()) errors.name = '模型名称为必填项';
    if (!currentForm.model_id.trim()) errors.model_id = '模型 ID 为必填项';
    if (!currentForm.provider.trim()) errors.provider = '必须选择供应商';
    if (!currentForm.adapter_type.trim()) errors.adapter_type = '适配器类型为必填项';

    if (Object.keys(errors).length > 0) {
      setFormErrors(errors);
      toast.error('请填写所有必填项');
      return;
    }

    try {
      const submitData = {
        name: currentForm.name,
        model_id: currentForm.model_id,
        model_type: currentForm.model_type,
        adapter_type: currentForm.adapter_type,
        provider: currentForm.provider,
        description: currentForm.description,
        is_enabled: currentForm.is_enabled,
        is_default: currentForm.is_default,
        temperature: currentForm.model_type === 'llm' ? currentForm.temperature : undefined,
        max_tokens: currentForm.model_type === 'llm' ? currentForm.max_tokens : undefined,
        top_p: currentForm.model_type === 'llm' ? currentForm.top_p : undefined,
      };

      if (modalMode === 'edit' && currentForm.id) {
        // Edit mode - PUT request
        await fetchApi(`/api/v1/models/${currentForm.id}`, {
          method: 'PUT',
          body: JSON.stringify(submitData),
        });
        toast.success('模型已更新');
      } else {
        // Create mode - POST request
        await fetchApi('/api/v1/models', {
          method: 'POST',
          body: JSON.stringify(submitData),
        });
        toast.success('模型已创建');
      }

      // Reload models and providers to get updated data
      await Promise.all([loadModels(), loadProviders()]);

      // Switch to the new provider if changed
      if (currentForm.provider) {
        const newProvider = providersRef.current.find(p => p.code === currentForm.provider);
        if (newProvider) {
          setSelectedProvider(newProvider);
        }
      }

      setIsModalOpen(false);
      setModelForm(DEFAULT_MODEL_FORM);
      setFormErrors({});
    } catch (e: any) {
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
      is_enabled: model.is_enabled,
      is_default: model.is_default,
      temperature: model.temperature ?? 0.7,
      max_tokens: model.max_tokens ?? 4096,
      top_p: model.top_p ?? 0.9,
    };
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
    // 非 LLM 模型不支持流式模式
    setTestMode(model.model_type === 'llm' || model.model_type === 'vision' ? 'stream' : 'normal');
    // 根据模型类型设置默认输入
    if (model.model_type === 'embedding') {
      setTestInput('你好，世界');
    } else if (model.model_type === 'rerank') {
      setTestInput('什么是人工智能？');
    } else {
      setTestInput('你好，请简单介绍一下你自己');
    }
    testOutputRef.current = '';
    setIsTestOpen(true);
  };

  const handleTestModel = async () => {
    if (!testingModel) return;
    setIsTesting(true);
    setTestError('');
    setTestOutput('');
    testOutputRef.current = '';

    try {
      // 根据模型类型选择不同的测试接口
      if (testingModel.model_type === 'embedding') {
        await testEmbeddingModel();
      } else if (testingModel.model_type === 'rerank') {
        await testRerankModel();
      } else if (testMode === 'stream') {
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

    testOutputRef.current = '';
    chunkCountRef.current = 0;
    setTestOutput('');
    setRawEvents([]);   // 清空上次的原始数据
    setStreamDebug('Connecting...');

    const startTime = Date.now();
    let lastEventTime = startTime;   // 上一个事件到达时间，用于计算事件间隔
    const el = () => ((Date.now() - startTime) / 1000).toFixed(3);

    console.log(`[SSE] ▶ 开始请求 model=${testingModel.model_id} @ ${new Date().toISOString()}`);

    // 用 fetchEventSource 处理 POST 形式的 SSE：它内部按事件解析，
    // 每收到一个 SSE 事件就触发一次 onmessage，逐条更新 UI 实现流式效果
    await fetchEventSource(getApiUrl('/api/v1/model-gateway/chat/completions'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('auth_token')}`,
      },
      body: JSON.stringify({
        model_type: testingModel.model_type,
        model_id: testingModel.model_id,
        messages: [{ role: 'user', content: testInput }],
        stream: true,
      }),
      // 页面切到后台时保持连接（默认会在 visibilitychange 时重连）
      openWhenHidden: true,

      onopen: async (response) => {
        const contentType = response.headers.get('content-type') || '';
        console.log(`[SSE] ⚡ onopen @ ${el()}s status=${response.status} content-type="${contentType}"`);
        console.log('[SSE]   响应头:', Object.fromEntries(response.headers.entries()));
        if (response.ok && contentType.includes('text/event-stream')) {
          setStreamDebug(`Connected, status: ${response.status}`);
          return;
        }
        // 非流式或错误响应：读取 body 抛出可读错误
        const errText = await response.text().catch(() => '');
        console.error(`[SSE] ✗ onopen 非流式响应 @ ${el()}s body=`, errText.substring(0, 200));
        let detail = errText;
        try { detail = JSON.parse(errText).detail || errText; } catch { /* keep raw */ }
        throw new Error(detail || `HTTP ${response.status}`);
      },

      onmessage: (ev) => {
        const now = Date.now();
        const sinceLast = ((now - lastEventTime) / 1000).toFixed(3);  // 距上个事件的间隔
        lastEventTime = now;

        // 收集原始数据（带到达时间与间隔），供"显示原始数据"面板展示
        setRawEvents((prev) => [...prev, `[@${el()}s Δ${sinceLast}s] ${ev.data}`]);

        // ev.data 是单个 SSE 事件的 data 字段（fetchEventSource 已去掉 "data: " 前缀）
        if (!ev.data || ev.data === '[DONE]') {
          console.log(`[SSE] ■ [DONE] @ ${el()}s (间隔 ${sinceLast}s)`);
          return;
        }
        try {
          const parsed = JSON.parse(ev.data);
          if (parsed.error) {
            console.error(`[SSE] ✗ 服务端错误 @ ${el()}s`, parsed.error);
            throw new Error(parsed.error.message || parsed.error);
          }
          const delta = parsed.choices?.[0]?.delta;
          const reasoning = delta?.reasoning_content || delta?.reasoning || delta?.thinking || '';
          const content = delta?.content || '';
          if (reasoning || content) {
            chunkCountRef.current++;
            testOutputRef.current += reasoning + content;
            // 每个事件到达即更新 UI —— 事件是分批到达的，React 会逐批重绘
            setTestOutput(testOutputRef.current);
            const kind = reasoning ? 'reasoning' : 'content';
            console.log(
              `[SSE] #${chunkCountRef.current} @ ${el()}s (间隔 ${sinceLast}s) [${kind}] ` +
              `"${(reasoning || content).replace(/\n/g, '\\n')}" 累计=${testOutputRef.current.length}字`
            );
            setStreamDebug(`#${chunkCountRef.current} ${testOutputRef.current.length} chars @ ${el()}s`);
          } else {
            console.log(`[SSE] · 空 delta @ ${el()}s (间隔 ${sinceLast}s) finish_reason=${parsed.choices?.[0]?.finish_reason ?? '-'}`);
          }
        } catch (e: any) {
          // JSON 解析失败的行忽略；显式抛出的 error 需要中断
          if (e?.message && !(e instanceof SyntaxError)) throw e;
          console.warn(`[SSE] ⚠ JSON 解析失败 @ ${el()}s data=`, ev.data.substring(0, 80));
        }
      },

      onclose: () => {
        console.log(`[SSE] ✔ onclose @ ${el()}s — 连接正常关闭`);
      },

      onerror: (err) => {
        console.error(`[SSE] ✗ onerror @ ${el()}s`, err);
        // 抛出以停止自动重连，交由外层 catch 处理
        throw err;
      },
    });

    const elapsed = el();
    console.log(`[SSE] ✅ 完成 @ ${elapsed}s — 共 ${chunkCountRef.current} 个事件, ${testOutputRef.current.length} 字`);
    setStreamDebug(`Done. ${chunkCountRef.current} chunks, ${testOutputRef.current.length} chars @ ${elapsed}s`);
  };

  const testNormalModel = async () => {
    if (!testingModel) return;

    const response = await fetch(getApiUrl('/api/v1/model-gateway/chat/completions'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('auth_token')}`,
      },
      body: JSON.stringify({
        model_type: testingModel.model_type,
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

  const testEmbeddingModel = async () => {
    if (!testingModel) return;

    const response = await fetch(getApiUrl('/api/v1/model-gateway/test/embedding'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('auth_token')}`,
      },
      body: JSON.stringify({
        model_config_id: testingModel.id,
        input: testInput,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: '请求失败' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    const data = await response.json();
    // 显示向量前 20 个值和维度
    const preview = data.embedding?.slice(0, 20).map((v: number) => v.toFixed(6)).join(', ');
    setTestOutput(`维度：${data.dimension}\n向量前 20 个值：[${preview}...]`);
  };

  const testRerankModel = async () => {
    if (!testingModel) return;

    // Rerank 需要额外的 documents 参数
    const defaultDocuments = [
      '人工智能是模拟人类智能的科学技术',
      '机器学习是人工智能的一个分支',
      '今天天气很好',
    ];

    const response = await fetch(getApiUrl('/api/v1/model-gateway/test/rerank'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('auth_token')}`,
      },
      body: JSON.stringify({
        model_config_id: testingModel.id,
        query: testInput,
        documents: defaultDocuments,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: '请求失败' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    const data = await response.json();
    // 格式化输出结果
    const results = data.results?.map((r: any) =>
      `[${r.index}] score=${r.score.toFixed(4)}: ${r.document}`
    ).join('\n') || '无结果';
    setTestOutput(`重排序结果:\n${results}`);
  };

  const openCreateModal = () => {
    setModalMode('create');
    if (selectedProvider) {
      setModelForm({
        ...DEFAULT_MODEL_FORM,
        provider: selectedProvider.code,
        provider_name: selectedProvider.name,
      });
    } else {
      setModelForm(DEFAULT_MODEL_FORM);
    }
    setFormErrors({});
    setIsModalOpen(true);
  };

  // 更新表单时同步更新 state 和 ref
  const updateModelForm = (updates: Partial<ModelFormData>) => {
    setModelForm((prev) => {
      const newForm = { ...prev, ...updates };
      modelFormRef.current = newForm;
      return newForm;
    });
  };

  const handleProviderChangeInForm = (providerCode: string) => {
    const provider = providers.find(p => p.code === providerCode);
    updateModelForm({
      provider: providerCode,
      provider_name: provider?.name || providerCode,
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
      const submitData: Record<string, any> = {
        name: providerForm.name,
        code: providerForm.code,
        description: providerForm.description,
        provider_type: providerForm.provider_type,
        region: providerForm.region,
        base_url: providerForm.base_url,
        api_version: providerForm.api_version,
        auth_type: providerForm.auth_type,
        api_key_name: providerForm.api_key_name,
        is_enabled: providerForm.is_enabled,
        is_default: providerForm.is_default,
      };

      // API Key 不回显：仅当用户填写了新值时才提交，留空则保留原有 key
      if (providerForm.api_key.trim()) {
        submitData.api_key = providerForm.api_key;
      }

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
      // Clear selection if deleted provider was selected
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
    <div className="flex-1 flex flex-col overflow-hidden bg-white">
      {/* Header */}
      <header className="h-[60px] px-6 bg-white flex items-center justify-between shrink-0 border-b border-[var(--sidebar-border)]">
        <div className="flex items-baseline gap-3">
          <h1 className="text-[18px] font-semibold text-[var(--text-primary)]">模型管理</h1>
          <span className="text-[13px] text-[var(--text-tertiary)]">管理供应商及其下的模型配置</span>
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
        <div className="w-80 border-r border-[var(--gray-200)] bg-[var(--card-bg)] flex flex-col">
          <div className="p-4 border-b border-[var(--gray-200)] space-y-3">
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
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text-tertiary)]" />
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
              "px-4 py-3 cursor-pointer transition-colors border-b border-[var(--gray-100)]",
              !selectedProvider
                ? "bg-[var(--accent-light)] border-l-4 border-l-[var(--accent-light0)]"
                : "hover:bg-[var(--gray-50)]"
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
                  !selectedProvider ? "text-[var(--primary)]" : "text-[var(--text-tertiary)]"
                )} />
                <span className={cn(
                  "text-[14px] font-medium",
                  !selectedProvider ? "text-[var(--primary)]" : "text-[var(--text-primary)]"
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
                <Loader2 className="w-6 h-6 animate-spin text-[var(--primary)]" />
              </div>
            ) : filteredProviders.length === 0 ? (
              <div className="text-center py-10">
                <Server className="w-12 h-12 text-[var(--text-tertiary)] mx-auto mb-3" />
                <p className="text-[13px] text-[var(--text-tertiary)]">暂无供应商</p>
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
                        ? "bg-[var(--accent-light)] border-[var(--primary-light)]"
                        : "bg-[var(--card-bg)] border-[var(--card-border)] hover:bg-[var(--gray-50)]"
                    )}
                    onClick={() => {
                      setSelectedProvider(provider);
                    }}
                  >
                    <div className="flex items-center justify-between mb-2 gap-2">
                      <div className="flex items-center gap-1.5 min-w-0 flex-1">
                        <div className={cn(
                          "w-2 h-2 rounded-full shrink-0",
                          provider.health_status === 'healthy' ? 'bg-green-500' :
                          provider.health_status === 'degraded' ? 'bg-yellow-500' :
                          provider.health_status === 'unhealthy' ? 'bg-red-500' : 'bg-gray-400'
                        )} />
                        <h3 className="text-[14px] font-medium text-[var(--text-primary)] truncate">
                          {provider.name}
                        </h3>
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        <Button
                          variant="secondary"
                          size="sm"
                          className="h-7 px-2 text-xs"
                          title="编辑供应商"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleEditProvider(provider);
                          }}
                        >
                          <Edit className="w-3.5 h-3.5 mr-1" />
                          编辑
                        </Button>
                        <Button
                          variant="secondary"
                          size="sm"
                          className="h-7 px-2 text-xs text-[var(--error)]"
                          title="删除供应商"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteProvider(provider.id);
                          }}
                        >
                          <Trash2 className="w-3.5 h-3.5 mr-1" />
                          删除
                        </Button>
                      </div>
                    </div>
                    <p className="text-[12px] text-[var(--text-tertiary)] line-clamp-2 mb-2">
                      {provider.description || PROVIDER_TYPE_LABELS[provider.provider_type]}
                    </p>
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] text-[var(--text-tertiary)]">
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
        <div className="flex-1 flex flex-col overflow-hidden bg-white">
          {/* Toolbar */}
          <div className="h-[60px] px-6 border-b border-[var(--gray-200)] bg-[var(--card-bg)] flex items-center justify-between shrink-0">
            <div>
              <h2 className="text-[16px] font-semibold text-[var(--text-primary)]">
                {selectedProvider ? selectedProvider.name : '全部模型'}
              </h2>
              <p className="text-[12px] text-[var(--text-tertiary)]">
                {selectedProvider ? selectedProvider.base_url : `${filteredModels.length} 个模型`}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--text-tertiary)]" />
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
              <thead className="bg-[var(--gray-50)] sticky top-0 z-10">
                <tr className="border-b border-[var(--gray-200)]">
                  <th className="text-left text-[12px] font-medium text-[var(--text-tertiary)] px-6 py-3">
                    模型名称
                  </th>
                  <th className="text-left text-[12px] font-medium text-[var(--text-tertiary)] px-6 py-3">
                    模型 ID
                  </th>
                  <th className="text-left text-[12px] font-medium text-[var(--text-tertiary)] px-6 py-3">
                    供应商
                  </th>
                  <th className="text-left text-[12px] font-medium text-[var(--text-tertiary)] px-6 py-3">
                    类型
                  </th>
                  <th className="text-left text-[12px] font-medium text-[var(--text-tertiary)] px-6 py-3">
                    适配器
                  </th>
                  <th className="text-left text-[12px] font-medium text-[var(--text-tertiary)] px-6 py-3">
                    状态
                  </th>
                  <th className="text-right text-[12px] font-medium text-[var(--text-tertiary)] px-6 py-3">
                    操作
                  </th>
                </tr>
              </thead>
              <tbody>
                {paginatedModels.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="text-center py-10">
                      <Cpu className="w-10 h-10 text-[var(--text-tertiary)] mx-auto mb-2" />
                      <p className="text-[13px] text-[var(--text-tertiary)]">
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
                      className="border-b border-[var(--gray-100)] hover:bg-[var(--gray-50)]"
                    >
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          <div className="w-8 h-8 rounded-lg bg-[var(--accent-light)] flex items-center justify-center">
                            <Cpu className="w-4 h-4 text-[var(--primary)]" />
                          </div>
                          <div>
                            <p className="text-[14px] font-medium text-[var(--text-primary)]">
                              {model.name}
                            </p>
                            {model.is_default && (
                              <Badge variant="primary" className="text-[9px] px-1 mt-0.5">默认</Badge>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <code className="text-[12px] bg-[var(--gray-100)] px-2 py-1 rounded">
                          {model.model_id}
                        </code>
                      </td>
                      <td className="px-6 py-4">
                        <span className="text-[13px] text-[var(--text-secondary)]">
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
                        <span className="text-[13px] text-[var(--text-secondary)]">
                          {ADAPTER_TYPE_LABELS[model.adapter_type]}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          <div className={cn(
                            "w-2 h-2 rounded-full",
                            model.status === 'active' ? 'bg-green-500' : 'bg-red-500'
                          )} />
                          <span className="text-[13px] text-[var(--text-secondary)]">
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
                            onClick={() => handleOpenTest(model)}
                          >
                            <MessageSquare className="w-3.5 h-3.5 mr-1" />
                            测试
                          </Button>
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
                            className="h-7 px-2 text-[var(--error)]"
                            onClick={() => handleDeleteModel(model.id)}
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </Button>
                          <div className="w-px h-4 bg-[var(--gray-200)] mx-1" />
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
            <div className="h-[50px] px-6 border-t border-[var(--gray-200)] bg-[var(--card-bg)] flex items-center justify-between shrink-0">
              <p className="text-[12px] text-[var(--text-tertiary)]">
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
              <p className="text-xs text-[var(--text-tertiary)] mt-1">
                已选择：{modelForm.provider_name}
              </p>
            )}
          </div>

          {/* Basic Info */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>模型名称 *</Label>
              <Input
                value={modelForm.name}
                onChange={(e) => updateModelForm({ name: e.target.value })}
                placeholder="如：Qwen2.5-72B"
              />
              {formErrors.name && <p className="text-xs text-red-500 mt-1">{formErrors.name}</p>}
            </div>
            <div>
              <Label>模型类型</Label>
              <Select
                value={modelForm.model_type}
                onChange={(e) => updateModelForm({ model_type: e.target.value })}
                options={Object.entries(MODEL_TYPE_LABELS).map(([v, l]) => ({ value: v, label: l }))}
              />
            </div>
          </div>

          <div>
            <Label>模型 ID *</Label>
            <Input
              value={modelForm.model_id}
              onChange={(e) => updateModelForm({ model_id: e.target.value })}
              placeholder="如：Qwen/Qwen2.5-72B-Instruct"
            />
            {formErrors.model_id && <p className="text-xs text-red-500 mt-1">{formErrors.model_id}</p>}
          </div>

          <div>
            <Label>适配器类型</Label>
            <Select
              value={modelForm.adapter_type}
              onChange={(e) => updateModelForm({ adapter_type: e.target.value })}
              options={Object.entries(ADAPTER_TYPE_LABELS).map(([v, l]) => ({ value: v, label: l }))}
            />
            {formErrors.adapter_type && <p className="text-xs text-red-500 mt-1">{formErrors.adapter_type}</p>}
          </div>

          <div>
            <Label>描述</Label>
            <Input
              value={modelForm.description}
              onChange={(e) => updateModelForm({ description: e.target.value })}
              placeholder="可选描述"
            />
          </div>

          {/* 连接信息由所属供应商统一管理，模型不再单独配置 */}
          <div className="rounded-lg bg-[var(--gray-50)] border border-[var(--gray-200)] px-3 py-2 text-xs text-[var(--text-tertiary)]">
            请求地址与认证信息由所属供应商统一管理，如需修改请编辑对应供应商。
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
                  onChange={(e) => updateModelForm({ temperature: parseFloat(e.target.value) || 0.7 })}
                />
              </div>
              <div>
                <Label>Max Tokens</Label>
                <Input
                  type="number"
                  value={modelForm.max_tokens}
                  onChange={(e) => updateModelForm({ max_tokens: parseInt(e.target.value) || 4096 })}
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
                  onChange={(e) => updateModelForm({ top_p: parseFloat(e.target.value) || 0.9 })}
                />
              </div>
            </div>
          )}

          {/* Toggles */}
          <div className="flex items-center gap-4 pt-4 border-t">
            <label className="flex items-center gap-2 text-sm">
              <Switch
                checked={modelForm.is_enabled}
                onCheckedChange={(v) => updateModelForm({ is_enabled: v })}
              />
              启用此模型
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Switch
                checked={modelForm.is_default}
                onCheckedChange={(v) => updateModelForm({ is_default: v })}
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
                    <p className="text-[12px] text-[var(--text-tertiary)] mb-1">模型名称</p>
                    <p className="text-[14px] font-medium">{viewingModel.name}</p>
                  </div>
                  <div>
                    <p className="text-[12px] text-[var(--text-tertiary)] mb-1">模型 ID</p>
                    <code className="text-[13px] bg-[var(--gray-100)] px-2 py-1 rounded">
                      {viewingModel.model_id}
                    </code>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-[12px] text-[var(--text-tertiary)] mb-1">模型类型</p>
                    <Badge variant="primary">{MODEL_TYPE_LABELS[viewingModel.model_type]}</Badge>
                  </div>
                  <div>
                    <p className="text-[12px] text-[var(--text-tertiary)] mb-1">适配器类型</p>
                    <span className="text-[14px]">{ADAPTER_TYPE_LABELS[viewingModel.adapter_type]}</span>
                  </div>
                </div>
                <div>
                  <p className="text-[12px] text-[var(--text-tertiary)] mb-1">描述</p>
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
                <div className="flex items-center gap-2 p-3 bg-[var(--gray-50)] rounded-lg">
                  <Server className="w-4 h-4 text-[var(--text-tertiary)]" />
                  <span className="text-[14px] font-medium">{viewingModel.provider}</span>
                  <ChevronRight className="w-4 h-4 text-[var(--text-tertiary)]" />
                  <span className="text-[13px] text-[var(--text-secondary)]">
                    {getProviderName(viewingModel.provider)}
                  </span>
                </div>
                <div>
                  <p className="text-[12px] text-[var(--text-tertiary)] mb-1">API 基础 URL（来自供应商）</p>
                  <code className="text-[13px] bg-[var(--gray-100)] px-3 py-2 rounded-lg block break-all">
                    {providers.find(p => p.code === viewingModel.provider)?.base_url || '-'}
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
                    <div className="p-3 bg-[var(--gray-50)] rounded-lg">
                      <p className="text-[11px] text-[var(--text-tertiary)] mb-1">Temperature</p>
                      <p className="text-[16px] font-semibold">{viewingModel.temperature ?? 0.7}</p>
                    </div>
                    <div className="p-3 bg-[var(--gray-50)] rounded-lg">
                      <p className="text-[11px] text-[var(--text-tertiary)] mb-1">Max Tokens</p>
                      <p className="text-[16px] font-semibold">{viewingModel.max_tokens ?? 4096}</p>
                    </div>
                    <div className="p-3 bg-[var(--gray-50)] rounded-lg">
                      <p className="text-[11px] text-[var(--text-tertiary)] mb-1">Top-P</p>
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
                    <p className="text-[12px] text-[var(--text-tertiary)]">运行状态</p>
                    <div className="flex items-center gap-2">
                      <div className={cn(
                        "w-2 h-2 rounded-full",
                        viewingModel.status === 'active' ? 'bg-green-500' : 'bg-red-500'
                      )} />
                      <span className="text-[14px] font-medium">{viewingModel.status}</span>
                    </div>
                  </div>
                  <div className="space-y-1">
                    <p className="text-[12px] text-[var(--text-tertiary)]">启用状态</p>
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
                    <Calendar className="w-4 h-4 text-[var(--text-tertiary)]" />
                    <div>
                      <p className="text-[11px] text-[var(--text-tertiary)]">创建时间</p>
                      <p className="text-[13px]">
                        {new Date(viewingModel.created_at).toLocaleString('zh-CN')}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <RefreshCw className="w-4 h-4 text-[var(--text-tertiary)]" />
                    <div>
                      <p className="text-[11px] text-[var(--text-tertiary)]">更新时间</p>
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
        description={
          testingModel?.model_type === 'embedding' ? '测试向量化模型效果' :
          testingModel?.model_type === 'rerank' ? '测试重排序模型效果' :
          '测试模型对话效果（支持流式和非流式模式）'
        }
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
                  测试中...
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
          {/* 模式选择 - 仅 LLM 和 Vision 模型支持流式 */}
          {(testingModel?.model_type === 'llm' || testingModel?.model_type === 'vision') && (
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
              <div className="flex-1" />
              <Button
                variant={showRaw ? 'primary' : 'secondary'}
                size="sm"
                onClick={() => setShowRaw((v) => !v)}
                title="显示后端返回的原始 SSE 数据（含到达时间与间隔）"
              >
                <Terminal className="w-4 h-4 mr-2" />
                {showRaw ? '隐藏原始数据' : '显示原始数据'}
              </Button>
            </div>
          )}

          <div>
            <Label>
              {testingModel?.model_type === 'embedding' ? '输入文本' :
               testingModel?.model_type === 'rerank' ? '查询文本' :
               '输入问题'}
            </Label>
            <textarea
              className="w-full enterprise-input min-h-[80px]"
              value={testInput}
              onChange={(e) => setTestInput(e.target.value)}
              placeholder={
                testingModel?.model_type === 'embedding' ? '输入要向量化的文本...' :
                testingModel?.model_type === 'rerank' ? '输入查询文本...' :
                '输入你的问题...'
              }
              rows={3}
            />
            {testingModel?.model_type === 'rerank' && (
              <p className="text-xs text-[var(--text-tertiary)] mt-1">
                默认测试文档：["人工智能是模拟人类智能的科学技术", "机器学习是人工智能的一个分支", "今天天气很好"]
              </p>
            )}
          </div>

          <div>
            <Label>
              {testingModel?.model_type === 'embedding' ? '向量输出' :
               testingModel?.model_type === 'rerank' ? '排序结果' :
               '模型输出'}
            </Label>
            <div className="w-full min-h-[200px] p-4 rounded-lg border border-[var(--gray-200)] bg-[var(--gray-50)]">
              {testError && (
                <div className="text-red-500 text-sm mb-2">
                  <AlertCircle className="w-4 h-4 inline mr-2" />
                  {testError}
                </div>
              )}
              {isTesting && testOutput === '' && (
                <div className="flex items-center justify-center h-full">
                  <Loader2 className="w-6 h-6 animate-spin text-[var(--primary)]" />
                </div>
              )}
              {testOutput !== '' && (
                <div className="text-sm whitespace-pre-wrap leading-relaxed font-mono" data-testid="test-output">
                  {testOutput}
                </div>
              )}
              {!isTesting && testOutput === '' && !testError && (
                <div className="text-center text-gray-400 text-sm py-10">
                  点击"开始测试"查看输出
                </div>
              )}
              <div ref={outputEndRef} />
            </div>
            {streamDebug && (
              <p className="text-xs text-gray-400 mt-1">{streamDebug}</p>
            )}
          </div>

          {/* 原始数据面板：展示后端返回的每条原始 SSE 数据（含到达时间与间隔） */}
          {showRaw && (
            <div>
              <div className="flex items-center justify-between mb-1">
                <Label>原始 SSE 数据（共 {rawEvents.length} 条）</Label>
                <span className="text-xs text-gray-400">格式：[@到达时间 Δ距上条间隔] data</span>
              </div>
              <div className="w-full max-h-[300px] overflow-auto p-3 rounded-lg border border-[var(--gray-200)] bg-black/90 font-mono text-xs leading-relaxed">
                {rawEvents.length === 0 ? (
                  <div className="text-gray-500">暂无数据，点击"开始测试"（流式模式）后显示</div>
                ) : (
                  rawEvents.map((line, i) => (
                    <div key={i} className="text-green-400 whitespace-pre-wrap break-all border-b border-white/5 py-0.5">
                      <span className="text-gray-500 mr-2">#{i + 1}</span>{line}
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      </Modal>

      {/* Create/Edit Provider Modal */}
      <Modal
        open={isProviderModalOpen}
        onOpenChange={(open) => {
          setIsProviderModalOpen(open);
          if (!open) {
            setProviderFormErrors({});
            setEditingProvider(null);
          }
        }}
        title={providerModalMode === 'create' ? '添加供应商' : '编辑供应商'}
        description={providerModalMode === 'create' ? '配置新的模型供应商' : '修改供应商的连接与认证信息'}
        width="700px"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsProviderModalOpen(false)}>取消</Button>
            <Button variant="primary" onClick={handleSaveProvider}>保存</Button>
          </>
        }
      >
        <div className="space-y-4 py-2">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>供应商名称 *</Label>
              <Input
                value={providerForm.name}
                onChange={(e) => setProviderForm({ ...providerForm, name: e.target.value })}
                placeholder="如：本地 Qwen"
              />
              {providerFormErrors.name && <p className="text-xs text-red-500 mt-1">{providerFormErrors.name}</p>}
            </div>
            <div>
              <Label>供应商代码 *</Label>
              <Input
                value={providerForm.code}
                onChange={(e) => setProviderForm({ ...providerForm, code: e.target.value })}
                placeholder="如：local_qwen"
                disabled={providerModalMode === 'edit'}
              />
              {providerFormErrors.code && <p className="text-xs text-red-500 mt-1">{providerFormErrors.code}</p>}
            </div>
          </div>

          <div>
            <Label>描述</Label>
            <Input
              value={providerForm.description}
              onChange={(e) => setProviderForm({ ...providerForm, description: e.target.value })}
              placeholder="可选描述"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>供应商类型</Label>
              <Select
                value={providerForm.provider_type}
                onChange={(e) => setProviderForm({ ...providerForm, provider_type: e.target.value })}
                options={Object.entries(PROVIDER_TYPE_LABELS).map(([v, l]) => ({ value: v, label: l }))}
              />
            </div>
            <div>
              <Label>区域</Label>
              <Input
                value={providerForm.region}
                onChange={(e) => setProviderForm({ ...providerForm, region: e.target.value })}
                placeholder="如：cn-hangzhou"
              />
            </div>
          </div>

          <div>
            <Label>API 基础 URL *</Label>
            <Input
              value={providerForm.base_url}
              onChange={(e) => setProviderForm({ ...providerForm, base_url: e.target.value })}
              placeholder="如：http://100.4.17.13:8892 或 https://api.openai.com"
            />
            {providerFormErrors.base_url && <p className="text-xs text-red-500 mt-1">{providerFormErrors.base_url}</p>}
            <p className="text-xs text-[var(--text-tertiary)] mt-1">
              该供应商下所有模型的请求都会发送到此地址（自动追加 /v1/chat/completions）
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>API 版本</Label>
              <Input
                value={providerForm.api_version}
                onChange={(e) => setProviderForm({ ...providerForm, api_version: e.target.value })}
                placeholder="可选，如：2024-02-01"
              />
            </div>
            <div>
              <Label>认证类型</Label>
              <Select
                value={providerForm.auth_type}
                onChange={(e) => setProviderForm({ ...providerForm, auth_type: e.target.value })}
                options={[
                  { value: 'api_key', label: 'API Key' },
                  { value: 'none', label: '无需认证' },
                ]}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>认证头名称</Label>
              <Input
                value={providerForm.api_key_name}
                onChange={(e) => setProviderForm({ ...providerForm, api_key_name: e.target.value })}
                placeholder="Authorization"
              />
            </div>
            <div>
              <Label>API Key</Label>
              <Input
                type="password"
                value={providerForm.api_key}
                onChange={(e) => setProviderForm({ ...providerForm, api_key: e.target.value })}
                placeholder={providerModalMode === 'edit' ? '留空则不修改' : 'sk-...'}
              />
              {providerModalMode === 'edit' && (
                <p className="text-xs text-[var(--text-tertiary)] mt-1">
                  {editingProvider?.api_key
                    ? <>当前已配置：<code className="bg-[var(--gray-100)] px-1 rounded">{editingProvider.api_key}</code>，留空则保留不变</>
                    : '当前未配置 API Key'}
                </p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-4 pt-4 border-t">
            <label className="flex items-center gap-2 text-sm">
              <Switch
                checked={providerForm.is_enabled}
                onCheckedChange={(v) => setProviderForm({ ...providerForm, is_enabled: v })}
              />
              启用此供应商
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Switch
                checked={providerForm.is_default}
                onCheckedChange={(v) => setProviderForm({ ...providerForm, is_default: v })}
              />
              设为默认供应商
            </label>
          </div>
        </div>
      </Modal>
    </div>
  );
}
