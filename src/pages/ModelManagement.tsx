import { useState, useEffect } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { toast } from 'sonner';
import {
  Database, RefreshCw, Plus, Settings, Trash2, Loader2, Server
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  ModelConfigSnake as ModelConfig,
  ModelPresetSnake as ModelPreset,
  fetchModels, fetchModelPresets, testModelConnection,
  deleteModel, updateModel, createModel
} from '@/lib/api-client';
import { ModelConfigForm, ModelConfigFormData } from '../components/ModelConfigForm';

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
  api: { label: 'API 调用', icon: Server },
  ollama: { label: 'Ollama', icon: Server },
  vllm: { label: 'vLLM', icon: Server },
  triton: { label: 'NVIDIA Triton', icon: Server },
  custom: { label: '自定义', icon: Settings },
};

const PROVIDER_LABELS: Record<string, string> = {
  meta: 'Meta (Llama)',
  alibaba: 'Alibaba (Qwen)',
  mistral: 'Mistral AI',
  baichuan: '百川智能',
  zhipu: '智谱 AI',
  moonshot: '月之暗面',
  local: '本地模型',
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  google: 'Google',
  azure: 'Azure',
  aws: 'AWS',
  baai: '智源研究院 (BAAI)',
  sentence_transformers: 'Sentence Transformers',
  baai_rerank: 'BAAI Rerank',
  xeva: 'Xeva',
  stability: 'Stability AI',
  midjourney: 'Midjourney',
  whisper: 'Whisper',
  azure_speech: 'Azure Speech',
  elevenlabs: 'ElevenLabs',
};

const DEFAULT_FORM_DATA: ModelConfigFormData = {
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
  const [filterType, setFilterType] = useState<string>('all');
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});

  // Form state
  const [formData, setFormData] = useState<ModelConfigFormData>(DEFAULT_FORM_DATA);

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
      ...DEFAULT_FORM_DATA,
      name: preset.name,
      model_id: preset.model_id,
      model_type: preset.model_type,
      adapter_type: preset.adapter_type,
      provider: preset.provider,
      description: preset.description,
      ...preset.default_config,
    });
    setIsPresetOpen(false);
    setIsCreateOpen(true);
  };

  const validateForm = (): boolean => {
    const errors: Record<string, string> = {};

    if (!formData.name || !formData.name.trim()) {
      errors.name = '模型名称为必填项';
    }
    if (!formData.model_id || !formData.model_id.trim()) {
      errors.model_id = '模型 ID 为必填项';
    }
    if (['api', 'ollama', 'vllm'].includes(formData.adapter_type)) {
      if (!formData.api_url || !formData.api_url.trim()) {
        errors.api_url = 'API URL 为必填项';
      }
      if (!formData.api_key || !formData.api_key.trim()) {
        errors.api_key = 'API Key 为必填项';
      }
    }
    if (formData.model_type === 'embedding' && !formData.embedding_dim) {
      errors.embedding_dim = '向量维度为必填项';
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
      await updateModel(modelId, { is_default: true });
      loadModels();
      toast.success('已设为默认');
    } catch (e: any) {
      toast.error(`设置失败：${e.message}`);
    }
  };

  const handleToggleEnabled = async (modelId: number, current: boolean) => {
    try {
      await updateModel(modelId, { is_enabled: !current });
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
      api_key: model.api_key || '',
      is_enabled: model.is_enabled,
      is_default: model.is_default,
      embedding_dim: model.embedding_dim,
      temperature: model.temperature ?? 0.7,
      max_tokens: model.max_tokens ?? 4096,
      top_p: model.top_p ?? 0.9,
    });
    setFormErrors({});
    setIsEditOpen(true);
  };

  const handleUpdate = async () => {
    if (!editingModel) return;

    // 编辑模式下，空 API Key 表示不修改
    const updateData = { ...formData };
    if (!updateData.api_key) {
      delete (updateData as any).api_key;
    }

    try {
      await updateModel(editingModel.id, updateData);
      setIsEditOpen(false);
      loadModels();
      resetForm();
      toast.success('模型已更新');
    } catch (e: any) {
      toast.error(`更新失败：${e.message}`);
    }
  };

  const resetForm = () => {
    setFormData(DEFAULT_FORM_DATA);
    setSelectedPreset(null);
    setFormErrors({});
  };

  const maskApiKey = (key: string) => {
    if (!key || key.length <= 8) return '***';
    return key.substring(0, 4) + '•'.repeat(key.length - 8) + key.substring(key.length - 4);
  };

  const filteredModels = filterType === 'all'
    ? models
    : models.filter(m => m.model_type === filterType);

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      {/* Header - MiMo style */}
      <header className="h-[60px] px-6 bg-white flex items-center justify-between shrink-0 border-b border-[#e5e5e5]">
        <h1 className="text-[18px] font-semibold text-[#1a1a1a]">{t('model.title')}</h1>

        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setIsPresetOpen(true)}
            className="rounded-xl border-[#e5e5e5] hover:bg-[#f5f5f5] font-medium text-[#666666]"
          >
            <Plus className="w-4 h-4 mr-2" />
            从预设创建
          </Button>
          <Button
            size="sm"
            onClick={() => setIsCreateOpen(true)}
            className="bg-[#1a1a1a] hover:bg-[#333333] rounded-xl font-medium text-white shadow-md"
          >
            <Plus className="w-4 h-4 mr-2" />
            新建模型
          </Button>
        </div>
      </header>

      {/* Main Content - MiMo style */}
      <div className="flex-1 overflow-y-auto p-6 bg-[#f7f7f7]">
        {/* Filters */}
        <div className="mb-6 flex items-center gap-2">
          <Select value={filterType} onValueChange={setFilterType}>
            <SelectTrigger className="w-[200px] rounded-xl h-11 border-[#e5e5e5] bg-white hover:border-[#d0d0d0]">
              <SelectValue placeholder="筛选类型" />
            </SelectTrigger>
            <SelectContent className="rounded-xl border-[#e5e5e5]">
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
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {loading ? (
            <div className="col-span-full flex items-center justify-center py-20">
              <Loader2 className="w-8 h-8 animate-spin text-[#1a1a1a]" />
            </div>
          ) : filteredModels.length === 0 ? (
            <div className="col-span-full flex flex-col items-center justify-center py-20 text-center">
              <Database className="w-16 h-16 text-[#d0d0d0] mb-4" />
              <h3 className="text-lg font-semibold text-[#1a1a1a]">暂无模型配置</h3>
              <p className="text-[#999999] text-sm mt-2">从预设创建或手动配置第一个模型</p>
            </div>
          ) : (
            filteredModels.map((model) => {
              const AdapterIcon = ADAPTER_TYPE_LABELS[model.adapter_type]?.icon || Server;
              return (
                <Card key={model.id} className="relative overflow-hidden rounded-2xl border border-[#e5e5e5] bg-white hover:shadow-lg transition-all duration-200">
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-3">
                        <div className={cn(
                          "w-11 h-11 rounded-xl flex items-center justify-center",
                          model.status === 'active' ? 'bg-[#e8f5e9] text-[#00c853]' :
                          model.status === 'error' ? 'bg-[#ffebee] text-[#ff5252]' :
                          'bg-[#f5f5f5] text-[#999999]'
                        )}>
                          <AdapterIcon className="w-5 h-5" />
                        </div>
                        <div>
                          <CardTitle className="text-[15px] font-semibold text-[#1a1a1a]">{model.name}</CardTitle>
                          <CardDescription className="text-[12px] text-[#999999] mt-0.5">
                            {MODEL_TYPE_LABELS[model.model_type]} • {PROVIDER_LABELS[model.provider] || model.provider}
                          </CardDescription>
                        </div>
                      </div>
                      <Badge
                        variant={model.is_default ? 'default' : 'secondary'}
                        className={cn(
                          "text-[11px] rounded-full px-2.5 py-1 font-medium",
                          model.is_default ? 'bg-[#1a1a1a] text-white' : 'bg-[#f0f0f0] text-[#666666]'
                        )}
                      >
                        {model.is_default ? '默认' : model.status === 'active' ? '已激活' : model.status}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="text-[12px] text-[#666666]">
                      <span className="font-mono bg-[#f5f5f5] px-2 py-1 rounded-lg">{model.model_id}</span>
                    </div>

                    {model.description && (
                      <p className="text-[12px] text-[#999999] line-clamp-2">{model.description}</p>
                    )}

                    {model.embedding_dim && (
                      <div className="text-[12px]">
                        <span className="text-[#999999]">维度：</span>
                        <Badge variant="outline" className="text-[11px] rounded-lg border-[#e5e5e5] bg-[#f5f5f5]">{model.embedding_dim}D</Badge>
                      </div>
                    )}

                    <div className="flex items-center gap-2 pt-3 border-t border-[#f0f0f0]">
                      <Button
                        size="sm"
                        variant="outline"
                        className="flex-1 h-9 text-[13px] rounded-xl border-[#e5e5e5]"
                        onClick={() => handleTestConnection(model.id)}
                        disabled={testingId === model.id}
                      >
                        {testingId === model.id ? (
                          <Loader2 className="w-4 h-4 animate-spin mr-1" />
                        ) : (
                          <RefreshCw className="w-4 h-4 mr-1" />
                        )}
                        测试连接
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-9 w-9 p-0 rounded-xl border-[#e5e5e5]"
                        onClick={() => handleEdit(model)}
                      >
                        <Settings className="w-4 h-4 text-[#666666]" />
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-9 w-9 p-0 rounded-xl hover:bg-[#ffebee]"
                        onClick={() => handleDelete(model.id)}
                      >
                        <Trash2 className="w-4 h-4 text-[#ff5252]" />
                      </Button>
                    </div>

                    <div className="flex items-center justify-between pt-3 border-t border-[#f0f0f0]">
                      <div className="flex items-center gap-2">
                        <Switch
                          checked={model.is_enabled}
                          onCheckedChange={() => handleToggleEnabled(model.id, model.is_enabled)}
                          className="scale-90"
                        />
                        <span className="text-[13px] text-[#666666]">启用</span>
                      </div>
                      {!model.is_default && (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-8 text-[12px] rounded-xl hover:bg-[#f5f5f5]"
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

      {/* Preset Selection Dialog - 参考图风格 */}
      <Dialog open={isPresetOpen} onOpenChange={setIsPresetOpen}>
        <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>从预设创建模型</DialogTitle>
            <DialogDescription>
              选择预配置的模型模板快速开始
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 px-6 pb-6">
            {presets.map((preset) => {
              const AdapterIcon = ADAPTER_TYPE_LABELS[preset.adapter_type]?.icon || Server;
              return (
                <Card
                  key={preset.id}
                  className="cursor-pointer hover:border-[#1a1a1a] hover:shadow-md transition-all rounded-2xl border border-[#e5e5e5] bg-white"
                  onClick={() => handleCreateFromPreset(preset)}
                >
                  <CardHeader className="pb-2">
                    <div className="flex items-center gap-2">
                      <AdapterIcon className="w-5 h-5 text-[#666666]" />
                      <CardTitle className="text-[15px] font-semibold text-[#1a1a1a]">{preset.name}</CardTitle>
                    </div>
                    <CardDescription className="text-[13px] text-[#999999] line-clamp-2 mt-1">
                      {preset.description}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="flex flex-wrap gap-1.5">
                      {preset.recommended_for.map((use) => (
                        <Badge key={use} variant="secondary" className="text-[11px] rounded-full bg-[#f5f5f5] text-[#666666]">
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

      {/* Create Model Dialog - 参考图风格 */}
      <Dialog open={isCreateOpen} onOpenChange={(open) => {
        setIsCreateOpen(open);
        if (!open) resetForm();
      }}>
        <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {selectedPreset ? `配置：${selectedPreset.name}` : '新建模型配置'}
            </DialogTitle>
            <DialogDescription>
              填写模型连接和参数配置，带 <span className="text-red-500">*</span> 为必填项
            </DialogDescription>
          </DialogHeader>

          <ModelConfigForm
            formData={formData}
            onChange={(data) => {
              setFormData(prev => ({ ...prev, ...data }));
              setFormErrors({});
            }}
            errors={formErrors}
          />

          <DialogFooter>
            <Button variant="outline" onClick={() => setIsCreateOpen(false)} className="rounded-full">取消</Button>
            <Button className="bg-[#1a1a1a] hover:bg-[#333333] rounded-full text-white" onClick={handleCreate}>
              创建
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Model Dialog - 参考图风格 */}
      <Dialog open={isEditOpen} onOpenChange={(open) => {
        setIsEditOpen(open);
        if (!open) resetForm();
      }}>
        <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>编辑模型配置</DialogTitle>
            <DialogDescription>
              修改模型配置和参数
            </DialogDescription>
          </DialogHeader>

          <ModelConfigForm
            formData={formData}
            onChange={(data) => {
              setFormData(prev => ({ ...prev, ...data }));
              setFormErrors({});
            }}
            errors={formErrors}
            isEdit
          />

          <DialogFooter>
            <Button variant="outline" onClick={() => setIsEditOpen(false)} className="rounded-full">取消</Button>
            <Button className="bg-[#1a1a1a] hover:bg-[#333333] rounded-full text-white" onClick={handleUpdate}>
              保存更新
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
