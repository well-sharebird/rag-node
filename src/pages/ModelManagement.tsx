import { useState, useEffect } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { toast } from 'sonner';
import {
  Cpu, Database, RefreshCw, Plus, Search, Settings, Trash2,
  CheckCircle2, XCircle, AlertCircle, Loader2, Cloud, Server, Zap
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  ModelConfigSnake as ModelConfig,
  ModelPresetSnake as ModelPreset,
  fetchModels, fetchModelPresets, testModelConnection,
  deleteModel, updateModel, createModel
} from '@/lib/api-client';

const MODEL_TYPE_LABELS: Record<string, string> = {
  llm: 'LLM / 对话',
  embedding: 'Embedding / 向量',
  rerank: 'Rerank / 重排序',
  vision: 'Vision / 视觉',
  speech_to_text: 'Speech-to-Text / 语音识别',
  text_to_speech: 'Text-to-Speech / 语音合成',
};

const ADAPTER_TYPE_LABELS: Record<string, { label: string; icon: any }> = {
  local: { label: '本地推理', icon: Server },
  api: { label: 'API 调用', icon: Cloud },
  ollama: { label: 'Ollama', icon: Zap },
  vllm: { label: 'vLLM', icon: Zap },
  triton: { label: 'NVIDIA Triton', icon: Server },
  custom: { label: '自定义', icon: Settings },
};

const PROVIDER_LABELS: Record<string, string> = {
  // Open Source
  meta: 'Meta (Llama)',
  alibaba: 'Alibaba (Qwen)',
  mistral: 'Mistral AI',
  baichuan: '百川智能',
  zhipu: '智谱 AI',
  moonshot: '月之暗面',
  local: '本地模型',
  // Commercial APIs
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  google: 'Google',
  azure: 'Azure',
  aws: 'AWS',
  // Embedding
  baai: '智源研究院 (BAAI)',
  sentence_transformers: 'Sentence Transformers',
  // Rerank
  baai_rerank: 'BAAI Rerank',
  xeva: 'Xeva',
  // Vision
  stability: 'Stability AI',
  midjourney: 'Midjourney',
  // Speech
  whisper: 'Whisper',
  azure_speech: 'Azure Speech',
  elevenlabs: 'ElevenLabs',
};

export function ModelManagement() {
  const { t } = useI18n();
  const [models, setModels] = useState<ModelConfig[]>([]);
  const [presets, setPresets] = useState<ModelPreset[]>([]);
  const [loading, setLoading] = useState(true);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [isPresetOpen, setIsPresetOpen] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState<ModelPreset | null>(null);
  const [editingModel, setEditingModel] = useState<ModelConfig | null>(null);
  const [showApiKey, setShowApiKey] = useState(false);
  const [filterType, setFilterType] = useState<string>('all');

  // Form state
  const [formData, setFormData] = useState<Partial<ModelConfig> & {
    temperature?: number;
    max_tokens?: number;
    top_p?: number;
  }>({
    name: '',
    model_id: '',
    model_type: 'llm',
    adapter_type: 'api',
    provider: 'openai',
    description: '',
    api_url: '',
    api_key: '',
    is_enabled: true,
    is_default: false,
    embedding_dim: undefined,
    temperature: 0.7,
    max_tokens: 4096,
    top_p: 0.9,
  });

  const loadModels = async () => {
    try {
      const data = await fetchModels();
      setModels(data.items || []);
    } catch (e: any) {
      console.error('Failed to load models:', e);
    } finally {
      setLoading(false);
    }
  };

  const loadPresets = async (type?: string) => {
    try {
      const data = await fetchModelPresets(type && type !== 'all' ? type : undefined);
      setPresets(data);
    } catch (e: any) {
      console.error('Failed to load presets:', e);
    }
  };

  useEffect(() => {
    loadModels();
  }, []);

  useEffect(() => {
    loadPresets(filterType !== 'all' ? filterType : undefined);
  }, [filterType]);

  const handleTestConnection = async (modelId: number) => {
    setTestingId(modelId);
    try {
      const result = await testModelConnection(modelId);
      if (result.success) {
        toast.success(`连接成功！延迟：${result.latencyMs}ms`);
      } else {
        toast.error(`连接失败：${result.message}`);
      }
      loadModels();
    } catch (e: any) {
      toast.error(`测试失败：${e.message}`);
    } finally {
      setTestingId(null);
    }
  };

  const handleCreateFromPreset = (preset: ModelPreset) => {
    setSelectedPreset(preset);
    setFormData({
      name: preset.name,
      model_id: preset.model_id,
      model_type: preset.model_type,
      adapter_type: preset.adapter_type,
      provider: preset.provider,
      description: preset.description,
      is_enabled: true,
      is_default: false,
      ...preset.default_config,
    });
    setIsPresetOpen(false);
    setIsCreateOpen(true);
  };

  const handleCreate = async () => {
    try {
      await createModel(formData);
      setIsCreateOpen(false);
      loadModels();
      resetForm();
      toast.success('模型创建成功');
    } catch (e: any) {
      toast.error(`创建失败：${e.message}`);
    }
  };

  const handleDelete = async (modelId: number) => {
    if (!window.confirm('确定要删除此模型配置吗？')) return;
    try {
      await deleteModel(modelId);
      loadModels();
      toast.success('模型已删除');
    } catch (e: any) {
      toast.error(`删除失败：${e.message}`);
    }
  };

  const handleToggleDefault = async (modelId: number, modelType: string) => {
    try {
      await updateModel(modelId, { isDefault: true });
      loadModels();
      toast.success('已设为默认');
    } catch (e: any) {
      toast.error(`设置失败：${e.message}`);
    }
  };

  const handleToggleEnabled = async (modelId: number, current: boolean) => {
    try {
      await updateModel(modelId, { isEnabled: !current });
      loadModels();
      toast.success(current ? '已禁用' : '已启用');
    } catch (e: any) {
      toast.error(`设置失败：${e.message}`);
    }
  };

  const handleEdit = (model: ModelConfig) => {
    setEditingModel(model);
    setFormData({
      id: model.id,
      name: model.name,
      model_id: model.model_id,
      model_type: model.model_type,
      adapter_type: model.adapter_type,
      provider: model.provider,
      description: model.description || '',
      api_url: model.api_url || '',
      api_key: model.api_key || '', // Load existing API key for display (masked)
      is_enabled: model.is_enabled,
      is_default: model.is_default,
      embedding_dim: model.embedding_dim,
      temperature: 0.7,
      max_tokens: 4096,
      top_p: 0.9,
    });
    setIsEditOpen(true);
  };

  const handleUpdate = async () => {
    if (!editingModel) return;
    try {
      await updateModel(editingModel.id, formData);
      setIsEditOpen(false);
      loadModels();
      resetForm();
      toast.success('模型已更新');
    } catch (e: any) {
      toast.error(`更新失败：${e.message}`);
    }
  };

  const resetForm = () => {
    setFormData({
      name: '',
      model_id: '',
      model_type: 'llm',
      adapter_type: 'api',
      provider: 'openai',
      description: '',
      api_url: '',
      api_key: '',
      is_enabled: true,
      is_default: false,
      embedding_dim: undefined,
    });
    setSelectedPreset(null);
    setShowApiKey(false);
  };

  const maskApiKey = (key: string) => {
    if (!key || key.length <= 8) return '***';
    return key.substring(0, 4) + '•'.repeat(key.length - 8) + key.substring(key.length - 4);
  };

  const filteredModels = filterType === 'all'
    ? models
    : models.filter(m => m.model_type === filterType);

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-[#F8FAFC]">
      {/* Header */}
      <header className="h-20 px-8 bg-white/80 backdrop-blur-md border-b border-slate-200/60 flex items-center justify-between shrink-0 z-10">
        <div className="space-y-1">
          <h1 className="text-xl font-bold tracking-tight text-slate-900">模型管理</h1>
          <p className="text-[13px] text-slate-500">配置和管理各类 AI 模型，包括对话、向量、重排序、视觉、语音等</p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setIsPresetOpen(true)}
            className="rounded-xl shadow-sm border-slate-200 hover:bg-slate-50 font-medium"
          >
            <Plus className="w-4 h-4 mr-2" />
            从预设创建
          </Button>
          <Button
            size="sm"
            onClick={() => setIsCreateOpen(true)}
            className="bg-[#1677ff] hover:bg-[#0958d9] rounded-xl shadow-sm font-medium transition-colors"
          >
            <Plus className="w-4 h-4 mr-2" />
            新建模型
          </Button>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto p-8">
        {/* Filters */}
        <div className="mb-6 flex items-center gap-2">
          <Select value={filterType} onValueChange={setFilterType}>
            <SelectTrigger className="w-[200px] rounded-xl h-10 border-slate-200">
              <SelectValue placeholder="筛选类型" />
            </SelectTrigger>
            <SelectContent className="rounded-xl">
              <SelectItem value="all">全部类型</SelectItem>
              <SelectItem value="llm">LLM / 对话</SelectItem>
              <SelectItem value="embedding">Embedding / 向量</SelectItem>
              <SelectItem value="rerank">Rerank / 重排序</SelectItem>
              <SelectItem value="vision">Vision / 视觉</SelectItem>
              <SelectItem value="speech_to_text">语音识别</SelectItem>
              <SelectItem value="text_to_speech">语音合成</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Models Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {loading ? (
            <div className="col-span-full flex items-center justify-center py-20">
              <Loader2 className="w-8 h-8 animate-spin text-[#1677ff]" />
            </div>
          ) : filteredModels.length === 0 ? (
            <div className="col-span-full flex flex-col items-center justify-center py-20 text-center">
              <Database className="w-16 h-16 text-slate-300 mb-4" />
              <h3 className="text-lg font-semibold text-slate-700">暂无模型配置</h3>
              <p className="text-slate-500 text-sm mt-1">从预设创建或手动配置第一个模型</p>
            </div>
          ) : (
            filteredModels.map((model) => {
              const AdapterIcon = ADAPTER_TYPE_LABELS[model.adapter_type]?.icon || Server;
              return (
                <Card key={model.id} className="relative overflow-hidden rounded-2xl border-slate-200/60 hover:shadow-lg transition-shadow">
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-3">
                        <div className={cn(
                          "w-10 h-10 rounded-xl flex items-center justify-center",
                          model.status === 'active' ? 'bg-green-50 text-green-600' :
                          model.status === 'error' ? 'bg-red-50 text-red-600' :
                          'bg-slate-100 text-slate-500'
                        )}>
                          <AdapterIcon className="w-5 h-5" />
                        </div>
                        <div>
                          <CardTitle className="text-base font-semibold">{model.name}</CardTitle>
                          <CardDescription className="text-xs">
                            {MODEL_TYPE_LABELS[model.model_type]} • {PROVIDER_LABELS[model.provider] || model.provider}
                          </CardDescription>
                        </div>
                      </div>
                      <Badge
                        variant={model.is_default ? 'default' : 'secondary'}
                        className={cn(
                          "text-xs rounded-lg",
                          model.is_default ? 'bg-[#1677ff] text-white' : ''
                        )}
                      >
                        {model.is_default ? '默认' : model.status === 'active' ? '已激活' : model.status}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="text-xs text-slate-600">
                      <span className="font-mono bg-slate-100 px-2 py-1 rounded">{model.model_id}</span>
                    </div>

                    {model.description && (
                      <p className="text-xs text-slate-500 line-clamp-2">{model.description}</p>
                    )}

                    {model.embedding_dim && (
                      <div className="text-xs">
                        <span className="text-slate-500">维度：</span>
                        <Badge variant="outline" className="text-xs rounded-lg">{model.embedding_dim}D</Badge>
                      </div>
                    )}

                    <div className="flex items-center gap-2 pt-2 border-t border-slate-100">
                      <Button
                        size="sm"
                        variant="outline"
                        className="flex-1 h-8 text-xs rounded-lg"
                        onClick={() => handleTestConnection(model.id)}
                        disabled={testingId === model.id}
                      >
                        {testingId === model.id ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" />
                        ) : (
                          <RefreshCw className="w-3.5 h-3.5 mr-1" />
                        )}
                        测试连接
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-8 w-8 p-0 rounded-lg"
                        onClick={() => handleEdit(model)}
                      >
                        <Settings className="w-4 h-4 text-slate-600" />
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-8 w-8 p-0 rounded-lg"
                        onClick={() => handleDelete(model.id)}
                      >
                        <Trash2 className="w-4 h-4 text-red-500" />
                      </Button>
                    </div>

                    <div className="flex items-center justify-between pt-2 border-t border-slate-100">
                      <div className="flex items-center gap-2">
                        <Switch
                          checked={model.is_enabled}
                          onCheckedChange={() => handleToggleEnabled(model.id, model.is_enabled)}
                          className="scale-75"
                        />
                        <span className="text-xs text-slate-600">启用</span>
                      </div>
                      {!model.is_default && (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 text-xs rounded-lg"
                          onClick={() => handleToggleDefault(model.id, model.model_type)}
                        >
                          设为默认
                        </Button>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })
          )}
        </div>
      </div>

      {/* Preset Selection Dialog */}
      <Dialog open={isPresetOpen} onOpenChange={setIsPresetOpen}>
        <DialogContent className="max-w-7xl max-h-[85vh] overflow-y-auto rounded-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl font-bold">从预设创建模型</DialogTitle>
            <DialogDescription className="pt-2 text-slate-600">
              选择预配置的模型模板快速开始
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 py-4">
            {presets.map((preset) => {
              const AdapterIcon = ADAPTER_TYPE_LABELS[preset.adapter_type]?.icon || Server;
              return (
                <Card
                  key={preset.id}
                  className="cursor-pointer hover:border-[#1677ff] hover:shadow-md transition-all rounded-xl"
                  onClick={() => handleCreateFromPreset(preset)}
                >
                  <CardHeader className="pb-2">
                    <div className="flex items-center gap-2">
                      <AdapterIcon className="w-5 h-5 text-slate-500" />
                      <CardTitle className="text-base">{preset.name}</CardTitle>
                    </div>
                    <CardDescription className="text-xs line-clamp-2">
                      {preset.description}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="flex flex-wrap gap-1">
                      {preset.recommended_for.map((use) => (
                        <Badge key={use} variant="secondary" className="text-xs rounded-lg">
                          {use}
                        </Badge>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </DialogContent>
      </Dialog>

      {/* Create Model Dialog */}
      <Dialog open={isCreateOpen} onOpenChange={(open) => {
        setIsCreateOpen(open);
        if (!open) resetForm();
      }}>
        <DialogContent className="max-w-6xl max-h-[85vh] overflow-y-auto rounded-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl font-bold">
              {selectedPreset ? `配置：${selectedPreset.name}` : '新建模型配置'}
            </DialogTitle>
            <DialogDescription className="pt-2 text-slate-600">
              填写模型连接和参数配置
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-5 py-4">
            {/* Basic Info - 3 columns */}
            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label className="text-sm font-semibold">模型名称</Label>
                <Input
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="如：Qwen2.5-72B"
                  className="rounded-xl h-10"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-sm font-semibold">模型类型</Label>
                <Select
                  value={formData.model_type}
                  onValueChange={(v) => setFormData({ ...formData, model_type: v })}
                >
                  <SelectTrigger className="rounded-xl h-10">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="rounded-xl">
                    {Object.entries(MODEL_TYPE_LABELS).map(([key, label]) => (
                      <SelectItem key={key} value={key}>{label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label className="text-sm font-semibold">适配器类型</Label>
                <Select
                  value={formData.adapter_type}
                  onValueChange={(v) => setFormData({ ...formData, adapter_type: v })}
                >
                  <SelectTrigger className="rounded-xl h-10">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="rounded-xl">
                    {Object.entries(ADAPTER_TYPE_LABELS).map(([key, { label }]) => (
                      <SelectItem key={key} value={key}>{label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label className="text-sm font-semibold">模型 ID</Label>
                <Input
                  value={formData.model_id}
                  onChange={(e) => setFormData({ ...formData, model_id: e.target.value })}
                  placeholder="如：Qwen/Qwen2.5-72B-Instruct"
                  className="rounded-xl h-10"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-sm font-semibold">提供商</Label>
                <Select
                  value={formData.provider}
                  onValueChange={(v) => setFormData({ ...formData, provider: v })}
                >
                  <SelectTrigger className="rounded-xl h-10">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="rounded-xl max-h-[200px] overflow-y-auto">
                    {Object.entries(PROVIDER_LABELS).map(([key, label]) => (
                      <SelectItem key={key} value={key}>{label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label className="text-sm font-semibold">描述</Label>
                <Input
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="可选描述"
                  className="rounded-xl h-10"
                />
              </div>
            </div>

            {/* Connection Settings */}
            {(formData.adapter_type === 'api' || formData.adapter_type === 'ollama' || formData.adapter_type === 'vllm') && (
              <>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label className="text-sm font-semibold">API URL</Label>
                    <Input
                      value={formData.api_url}
                      onChange={(e) => setFormData({ ...formData, api_url: e.target.value })}
                      placeholder="https://api.example.com"
                      className="rounded-xl h-10"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label className="text-sm font-semibold">API Key</Label>
                    <div className="relative">
                      <Input
                        value={formData.api_key}
                        onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
                        type={showApiKey ? 'text' : 'password'}
                        placeholder="sk-..."
                        className="rounded-xl h-10 pr-20"
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="absolute right-1 top-1/2 -translate-y-1/2 h-8 w-8 p-0"
                        onClick={() => setShowApiKey(!showApiKey)}
                      >
                        {showApiKey ? (
                          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-slate-500"><path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/><path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/><line x1="2" x2="22" y1="2" y2="22"/></svg>
                        ) : (
                          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-slate-500"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>
                        )}
                      </Button>
                    </div>
                    {formData.api_key && !showApiKey && (
                      <p className="text-xs text-slate-500 mt-1">
                        当前：{maskApiKey(formData.api_key)}
                      </p>
                    )}
                  </div>
                </div>
              </>
            )}

            {/* Embedding specific */}
            {formData.model_type === 'embedding' && (
              <div className="space-y-2">
                <Label className="text-sm font-semibold">向量维度</Label>
                <Input
                  value={formData.embedding_dim || ''}
                  onChange={(e) => setFormData({ ...formData, embedding_dim: parseInt(e.target.value) || undefined })}
                  type="number"
                  placeholder="1024"
                  className="rounded-xl h-10"
                />
              </div>
            )}

            {/* Flags */}
            <div className="flex items-center gap-6 pt-2 border-t border-slate-100">
              <div className="flex items-center gap-2">
                <Switch
                  checked={formData.is_enabled}
                  onCheckedChange={(v) => setFormData({ ...formData, is_enabled: v })}
                />
                <Label className="text-sm">启用此模型</Label>
              </div>
              <div className="flex items-center gap-2">
                <Switch
                  checked={formData.is_default}
                  onCheckedChange={(v) => setFormData({ ...formData, is_default: v })}
                />
                <Label className="text-sm">设为默认</Label>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="ghost" onClick={() => setIsCreateOpen(false)} className="rounded-xl">取消</Button>
            <Button className="bg-[#1677ff] hover:bg-[#0958d9] rounded-xl" onClick={handleCreate}>
              创建
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Model Dialog */}
      <Dialog open={isEditOpen} onOpenChange={(open) => {
        setIsEditOpen(open);
        if (!open) resetForm();
      }}>
        <DialogContent className="max-w-6xl max-h-[85vh] overflow-y-auto rounded-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl font-bold">编辑模型配置</DialogTitle>
            <DialogDescription className="pt-2 text-slate-600">
              修改模型配置和参数
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-5 py-4">
            {/* Basic Info - 3 columns */}
            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label className="text-sm font-semibold">模型名称</Label>
                <Input
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="如：Qwen2.5-72B"
                  className="rounded-xl h-10"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-sm font-semibold">模型类型</Label>
                <Select
                  value={formData.model_type}
                  onValueChange={(v) => setFormData({ ...formData, model_type: v })}
                >
                  <SelectTrigger className="rounded-xl h-10">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="rounded-xl">
                    {Object.entries(MODEL_TYPE_LABELS).map(([key, label]) => (
                      <SelectItem key={key} value={key}>{label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label className="text-sm font-semibold">适配器类型</Label>
                <Select
                  value={formData.adapter_type}
                  onValueChange={(v) => setFormData({ ...formData, adapter_type: v })}
                >
                  <SelectTrigger className="rounded-xl h-10">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="rounded-xl">
                    {Object.entries(ADAPTER_TYPE_LABELS).map(([key, { label }]) => (
                      <SelectItem key={key} value={key}>{label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label className="text-sm font-semibold">模型 ID</Label>
                <Input
                  value={formData.model_id}
                  onChange={(e) => setFormData({ ...formData, model_id: e.target.value })}
                  placeholder="如：Qwen/Qwen2.5-72B-Instruct"
                  className="rounded-xl h-10"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-sm font-semibold">提供商</Label>
                <Select
                  value={formData.provider}
                  onValueChange={(v) => setFormData({ ...formData, provider: v })}
                >
                  <SelectTrigger className="rounded-xl h-10">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="rounded-xl max-h-[200px] overflow-y-auto">
                    {Object.entries(PROVIDER_LABELS).map(([key, label]) => (
                      <SelectItem key={key} value={key}>{label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label className="text-sm font-semibold">描述</Label>
                <Input
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="可选描述"
                  className="rounded-xl h-10"
                />
              </div>
            </div>

            {/* Connection Settings */}
            {(formData.adapter_type === 'api' || formData.adapter_type === 'ollama' || formData.adapter_type === 'vllm') && (
              <>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label className="text-sm font-semibold">API URL</Label>
                    <Input
                      value={formData.api_url}
                      onChange={(e) => setFormData({ ...formData, api_url: e.target.value })}
                      placeholder="https://api.example.com"
                      className="rounded-xl h-10"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label className="text-sm font-semibold">API Key</Label>
                    <div className="relative">
                      <Input
                        value={formData.api_key}
                        onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
                        type={showApiKey ? 'text' : 'password'}
                        placeholder="输入新的 API Key（留空表示不变）"
                        className="rounded-xl h-10 pr-20"
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="absolute right-1 top-1/2 -translate-y-1/2 h-8 w-8 p-0"
                        onClick={() => setShowApiKey(!showApiKey)}
                      >
                        {showApiKey ? (
                          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-slate-500"><path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/><path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/><line x1="2" x2="22" y1="2" y2="22"/></svg>
                        ) : (
                          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-slate-500"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>
                        )}
                      </Button>
                    </div>
                    {formData.api_key && !showApiKey && (
                      <p className="text-xs text-slate-500 mt-1">
                        当前：{maskApiKey(formData.api_key)}
                      </p>
                    )}
                  </div>
                </div>
              </>
            )}

            {/* Model Parameters */}
            <div className="grid grid-cols-3 gap-4 pt-4 border-t border-slate-100">
              <div className="space-y-2">
                <Label className="text-sm font-semibold">Temperature</Label>
                <Input
                  value={formData.temperature}
                  onChange={(e) => setFormData({ ...formData, temperature: parseFloat(e.target.value) || 0.7 })}
                  type="number"
                  step="0.1"
                  min="0"
                  max="2"
                  className="rounded-xl h-10"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-sm font-semibold">Max Tokens</Label>
                <Input
                  value={formData.max_tokens}
                  onChange={(e) => setFormData({ ...formData, max_tokens: parseInt(e.target.value) || 4096 })}
                  type="number"
                  className="rounded-xl h-10"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-sm font-semibold">Top-P</Label>
                <Input
                  value={formData.top_p}
                  onChange={(e) => setFormData({ ...formData, top_p: parseFloat(e.target.value) || 0.9 })}
                  type="number"
                  step="0.1"
                  min="0"
                  max="1"
                  className="rounded-xl h-10"
                />
              </div>
            </div>

            {/* Embedding specific */}
            {formData.model_type === 'embedding' && (
              <div className="space-y-2">
                <Label className="text-sm font-semibold">向量维度</Label>
                <Input
                  value={formData.embedding_dim || ''}
                  onChange={(e) => setFormData({ ...formData, embedding_dim: parseInt(e.target.value) || undefined })}
                  type="number"
                  placeholder="1024"
                  className="rounded-xl h-10"
                />
              </div>
            )}

            {/* Flags */}
            <div className="flex items-center gap-6 pt-2 border-t border-slate-100">
              <div className="flex items-center gap-2">
                <Switch
                  checked={formData.is_enabled}
                  onCheckedChange={(v) => setFormData({ ...formData, is_enabled: v })}
                />
                <Label className="text-sm">启用此模型</Label>
              </div>
              <div className="flex items-center gap-2">
                <Switch
                  checked={formData.is_default}
                  onCheckedChange={(v) => setFormData({ ...formData, is_default: v })}
                />
                <Label className="text-sm">设为默认</Label>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="ghost" onClick={() => setIsEditOpen(false)} className="rounded-xl">取消</Button>
            <Button className="bg-[#1677ff] hover:bg-[#0958d9] rounded-xl" onClick={handleUpdate}>
              保存更新
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
