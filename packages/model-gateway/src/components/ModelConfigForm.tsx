import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useEffect, useState } from 'react';
import { fetchApi } from '@/lib/api-client';

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

// 预设供应商配置（后备选项）
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

// 供应商默认配置
const PROVIDER_DEFAULTS: Record<string, { base_url?: string; api_key_name?: string }> = {
  openai: { base_url: 'https://api.openai.com/v1', api_key_name: 'Authorization' },
  anthropic: { base_url: 'https://api.anthropic.com', api_key_name: 'x-api-key' },
  google: { base_url: 'https://generativelanguage.googleapis.com/v1beta', api_key_name: 'Authorization' },
  azure: { base_url: 'https://{resource}.openai.azure.com', api_key_name: 'api-key' },
  zhipu: { base_url: 'https://open.bigmodel.cn/api/paas/v4', api_key_name: 'Authorization' },
  moonshot: { base_url: 'https://api.moonshot.cn/v1', api_key_name: 'Authorization' },
  aliyun: { base_url: 'https://dashscope.aliyuncs.com/api/v1', api_key_name: 'Authorization' },
  baichuan: { base_url: 'https://api.baichuan-ai.com/v1', api_key_name: 'Authorization' },
  deepseek: { base_url: 'https://api.deepseek.com/v1', api_key_name: 'Authorization' },
  ollama: { base_url: 'http://localhost:11434', api_key_name: '' },
  vllm: { base_url: 'http://localhost:8000/v1', api_key_name: '' },
};

export interface ModelProvider {
  id: number;
  name: string;
  code: string;
  provider_type: string;
  base_url: string;
  api_key?: string;
  api_key_name?: string;
  is_enabled: boolean;
  status: string;
}

export interface ModelConfigFormData {
  id?: number;
  name: string;
  model_id: string;
  model_type: string;
  adapter_type: string;
  provider: string;
  description: string;
  is_enabled: boolean;
  is_default: boolean;
  embedding_dim?: number;
  temperature?: number;
  max_tokens?: number;
  top_p?: number;
}

interface ModelConfigFormProps {
  formData: ModelConfigFormData;
  onChange: (data: Partial<ModelConfigFormData>) => void;
  errors?: Record<string, string>;
  isEdit?: boolean;
}

export function ModelConfigForm({
  formData,
  onChange,
  errors = {},
  isEdit = false,
}: ModelConfigFormProps) {
  const [providers, setProviders] = useState<ModelProvider[]>([]);
  const [loadingProviders, setLoadingProviders] = useState(false);

  // Load providers from model gateway on mount
  useEffect(() => {
    const loadProviders = async () => {
      setLoadingProviders(true);
      try {
        const response = await fetchApi('/api/v1/model-gateway/providers');
        const data = response as { items?: ModelProvider[] };
        setProviders(data.items || []);
      } catch (e) {
        console.error('Failed to load providers:', e);
      } finally {
        setLoadingProviders(false);
      }
    };
    loadProviders();
  }, []);

  const isEmbedding = formData.model_type === 'embedding';
  const needsAdvancedParams = ['llm', 'vision', 'text_to_speech'].includes(formData.model_type);

  // Handle provider change
  const handleProviderChange = (providerCode: string) => {
    const updates: Partial<ModelConfigFormData> = { provider: providerCode };
    onChange(updates);
  };

  const updateField = <K extends keyof ModelConfigFormData>(
    field: K,
    value: ModelConfigFormData[K]
  ) => {
    onChange({ [field]: value });
  };

  return (
    <div className="space-y-4 py-2">
      {/* 基本信息 - 参考图风格 */}
      <div className="rounded-3xl bg-[#f8f9fa] p-5">
        <h3 className="text-[15px] font-semibold text-[var(--text-primary)] mb-4">基本信息</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* 模型名称 */}
          <div className="space-y-2">
            <Label className="text-[12px] font-medium text-[#666666]">
              模型名称 <span className="text-red-500">*</span>
            </Label>
            <Input
              value={formData.name}
              onChange={(e) => updateField('name', e.target.value)}
              placeholder="如：Qwen2.5-72B"
              className={cn(
                "rounded-full h-11 border border-[#e0e0e0] bg-white px-4 text-[14px]",
                errors.name && "border-red-500"
              )}
            />
            {errors.name && <p className="text-xs text-red-500 ml-2">{errors.name}</p>}
          </div>

          {/* 模型类型 */}
          <div className="space-y-2">
            <Label className="text-[12px] font-medium text-[#666666]">
              模型类型 <span className="text-red-500">*</span>
            </Label>
            <Select
              value={formData.model_type}
              onValueChange={(v) => updateField('model_type', v)}
            >
              <SelectTrigger className="rounded-full h-11 border border-[#e0e0e0] bg-white px-4">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="rounded-xl border-[#e0e0e0]">
                {Object.entries(MODEL_TYPE_LABELS).map(([key, label]) => (
                  <SelectItem key={key} value={key}>{label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* 适配器类型 */}
          <div className="space-y-2">
            <Label className="text-[12px] font-medium text-[#666666]">
              适配器类型 <span className="text-red-500">*</span>
            </Label>
            <Select
              value={formData.adapter_type}
              onValueChange={(v) => updateField('adapter_type', v)}
            >
              <SelectTrigger className="rounded-full h-11 border border-[#e0e0e0] bg-white px-4">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="rounded-xl border-[#e0e0e0]">
                {Object.entries(ADAPTER_TYPE_LABELS).map(([key, label]) => (
                  <SelectItem key={key} value={key}>{label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* 提供商 */}
          <div className="space-y-2">
            <Label className="text-[12px] font-medium text-[#666666]">
              提供商 <span className="text-red-500">*</span>
            </Label>
            <Select
              value={formData.provider}
              onValueChange={handleProviderChange}
            >
              <SelectTrigger className="rounded-full h-11 border border-[#e0e0e0] bg-white px-4">
                <SelectValue placeholder={loadingProviders ? "加载中..." : "选择提供商"} />
              </SelectTrigger>
              <SelectContent className="rounded-xl max-h-[200px] overflow-y-auto border-[#e0e0e0]">
                {/* 从模型网关动态加载的供应商 */}
                {providers.length > 0 && providers.map((p) => (
                  <SelectItem key={p.code} value={p.code}>
                    <div className="flex items-center gap-2">
                      <span>{p.name}</span>
                      {p.is_enabled && p.status === 'active' && (
                        <span className="text-[10px] text-green-600 ml-auto">●</span>
                      )}
                    </div>
                  </SelectItem>
                ))}
                {/* 预设供应商（当网关中没有数据时） */}
                {providers.length === 0 && Object.entries(PROVIDER_LABELS).map(([key, label]) => (
                  <SelectItem key={key} value={key}>{label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {providers.length > 0 && (
              <p className="text-[11px] text-[var(--text-tertiary)] ml-2">
                已加载 {providers.length} 个供应商，选择后自动填充 API 配置
              </p>
            )}
          </div>

          {/* 模型 ID - 跨两列 */}
          <div className="md:col-span-2 space-y-2">
            <Label className="text-[12px] font-medium text-[#666666]">
              模型 ID <span className="text-red-500">*</span>
            </Label>
            <Input
              value={formData.model_id}
              onChange={(e) => updateField('model_id', e.target.value)}
              placeholder="如：Qwen/Qwen2.5-72B-Instruct"
              className={cn(
                "rounded-full h-11 border border-[#e0e0e0] bg-white px-4 text-[14px]",
                errors.model_id && "border-red-500"
              )}
            />
            {errors.model_id && <p className="text-xs text-red-500 ml-2">{errors.model_id}</p>}
          </div>

          {/* 描述 - 跨两列 */}
          <div className="md:col-span-2 space-y-2">
            <Label className="text-[12px] font-medium text-[#666666]">描述</Label>
            <Input
              value={formData.description}
              onChange={(e) => updateField('description', e.target.value)}
              placeholder="可选描述"
              className="rounded-full h-11 border border-[#e0e0e0] bg-white px-4 text-[14px]"
            />
          </div>
        </div>
      </div>

      {/* 连接设置提示 - API 配置在供应商管理中统一设置 */}
      <div className="rounded-3xl bg-[#f0f7ff] p-5 border border-[#d0e3f7]">
        <h3 className="text-[15px] font-semibold text-[var(--text-primary)] mb-2">连接设置</h3>
        <p className="text-[13px] text-[var(--text-tertiary)]">
          API URL 和 API Key 在 <strong>供应商管理</strong> 中统一配置，模型将继承所属供应商的连接设置。
        </p>
      </div>

      {/* 高级参数 - 参考图风格 */}
      {needsAdvancedParams && (
        <div className="rounded-3xl bg-[#f8f9fa] p-5">
          <h3 className="text-[15px] font-semibold text-[var(--text-primary)] mb-4">高级参数</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="space-y-2">
              <Label className="text-[12px] font-medium text-[#666666]">Temperature</Label>
              <Input
                value={formData.temperature}
                onChange={(e) => updateField('temperature', parseFloat(e.target.value) || 0.7)}
                type="number"
                step="0.1"
                min="0"
                max="2"
                className="rounded-full h-11 border border-[#e0e0e0] bg-white px-4 text-[14px]"
              />
              <p className="text-[11px] text-[var(--text-tertiary)] ml-2">随机性 (0-2，默认 0.7)</p>
            </div>

            <div className="space-y-2">
              <Label className="text-[12px] font-medium text-[#666666]">Max Tokens</Label>
              <Input
                value={formData.max_tokens}
                onChange={(e) => updateField('max_tokens', parseInt(e.target.value) || 4096)}
                type="number"
                className="rounded-full h-11 border border-[#e0e0e0] bg-white px-4 text-[14px]"
              />
              <p className="text-[11px] text-[var(--text-tertiary)] ml-2">最大生成长度 (默认 4096)</p>
            </div>

            <div className="space-y-2">
              <Label className="text-[12px] font-medium text-[#666666]">Top-P</Label>
              <Input
                value={formData.top_p}
                onChange={(e) => updateField('top_p', parseFloat(e.target.value) || 0.9)}
                type="number"
                step="0.1"
                min="0"
                max="1"
                className="rounded-full h-11 border border-[#e0e0e0] bg-white px-4 text-[14px]"
              />
              <p className="text-[11px] text-[var(--text-tertiary)] ml-2">核采样 (0-1，默认 0.9)</p>
            </div>
          </div>
        </div>
      )}

      {/* 向量配置 - 参考图风格 */}
      {isEmbedding && (
        <div className="rounded-3xl bg-[#f8f9fa] p-5">
          <h3 className="text-[15px] font-semibold text-[var(--text-primary)] mb-4">向量配置</h3>
          <div className="space-y-2">
            <Label className="text-[12px] font-medium text-[#666666]">
              向量维度 <span className="text-red-500">*</span>
            </Label>
            <Input
              value={formData.embedding_dim || ''}
              onChange={(e) => updateField('embedding_dim', parseInt(e.target.value) || undefined)}
              type="number"
              placeholder="1024"
              className={cn(
                "rounded-full h-11 border border-[#e0e0e0] bg-white px-4 text-[14px]",
                errors.embedding_dim && "border-red-500"
              )}
            />
            {errors.embedding_dim && <p className="text-xs text-red-500 ml-2">{errors.embedding_dim}</p>}
          </div>
        </div>
      )}

      {/* 启用设置 - 参考图风格 */}
      <div className="rounded-3xl bg-[#f8f9fa] p-5">
        <h3 className="text-[15px] font-semibold text-[var(--text-primary)] mb-4">启用设置</h3>
        <div className="flex flex-wrap items-center gap-6">
          <div className="flex items-center gap-3">
            <Switch
              checked={formData.is_enabled}
              onCheckedChange={(v) => updateField('is_enabled', v)}
            />
            <Label className="text-[14px] font-medium text-[#666666]">启用此模型</Label>
          </div>
          <div className="flex items-center gap-3">
            <Switch
              checked={formData.is_default}
              onCheckedChange={(v) => updateField('is_default', v)}
            />
            <Label className="text-[14px] font-medium text-[#666666]">设为默认</Label>
          </div>
        </div>
      </div>
    </div>
  );
}
