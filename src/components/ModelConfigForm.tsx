import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

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

export interface ModelConfigFormData {
  id?: number;
  name: string;
  model_id: string;
  model_type: string;
  adapter_type: string;
  provider: string;
  description: string;
  api_url: string;
  api_key: string;
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
  const needsApiFields = ['api', 'ollama', 'vllm'].includes(formData.adapter_type);
  const isEmbedding = formData.model_type === 'embedding';
  const needsAdvancedParams = ['llm', 'vision', 'text_to_speech'].includes(formData.model_type);

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
        <h3 className="text-[15px] font-semibold text-[#1a1a1a] mb-4">基本信息</h3>
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
              onValueChange={(v) => updateField('provider', v)}
            >
              <SelectTrigger className="rounded-full h-11 border border-[#e0e0e0] bg-white px-4">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="rounded-xl max-h-[200px] overflow-y-auto border-[#e0e0e0]">
                {Object.entries(PROVIDER_LABELS).map(([key, label]) => (
                  <SelectItem key={key} value={key}>{label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
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

      {/* 连接设置 - 参考图风格 */}
      {needsApiFields && (
        <div className="rounded-3xl bg-[#f8f9fa] p-5">
          <h3 className="text-[15px] font-semibold text-[#1a1a1a] mb-4">连接设置</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label className="text-[12px] font-medium text-[#666666]">
                API URL <span className="text-red-500">*</span>
              </Label>
              <Input
                value={formData.api_url}
                onChange={(e) => updateField('api_url', e.target.value)}
                placeholder="https://api.example.com"
                className={cn(
                  "rounded-full h-11 border border-[#e0e0e0] bg-white px-4 text-[14px]",
                  errors.api_url && "border-red-500"
                )}
              />
              {errors.api_url && <p className="text-xs text-red-500 ml-2">{errors.api_url}</p>}
            </div>

            <div className="space-y-2">
              <Label className="text-[12px] font-medium text-[#666666]">
                API Key <span className="text-red-500">*</span>
              </Label>
              <Input
                value={formData.api_key}
                onChange={(e) => updateField('api_key', e.target.value)}
                type="password"
                placeholder={isEdit ? "输入新的 API Key，留空表示保持不变" : "sk-..."}
                className={cn(
                  "rounded-full h-11 border border-[#e0e0e0] bg-white px-4 text-[14px]",
                  errors.api_key && "border-red-500"
                )}
              />
              {errors.api_key && <p className="text-xs text-red-500 ml-2">{errors.api_key}</p>}
              {isEdit && formData.api_key && (
                <p className="text-xs text-[#999999] ml-2">当前：{maskApiKey(formData.api_key)}</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 高级参数 - 参考图风格 */}
      {needsAdvancedParams && (
        <div className="rounded-3xl bg-[#f8f9fa] p-5">
          <h3 className="text-[15px] font-semibold text-[#1a1a1a] mb-4">高级参数</h3>
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
              <p className="text-[11px] text-[#999999] ml-2">随机性 (0-2，默认 0.7)</p>
            </div>

            <div className="space-y-2">
              <Label className="text-[12px] font-medium text-[#666666]">Max Tokens</Label>
              <Input
                value={formData.max_tokens}
                onChange={(e) => updateField('max_tokens', parseInt(e.target.value) || 4096)}
                type="number"
                className="rounded-full h-11 border border-[#e0e0e0] bg-white px-4 text-[14px]"
              />
              <p className="text-[11px] text-[#999999] ml-2">最大生成长度 (默认 4096)</p>
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
              <p className="text-[11px] text-[#999999] ml-2">核采样 (0-1，默认 0.9)</p>
            </div>
          </div>
        </div>
      )}

      {/* 向量配置 - 参考图风格 */}
      {isEmbedding && (
        <div className="rounded-3xl bg-[#f8f9fa] p-5">
          <h3 className="text-[15px] font-semibold text-[#1a1a1a] mb-4">向量配置</h3>
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
        <h3 className="text-[15px] font-semibold text-[#1a1a1a] mb-4">启用设置</h3>
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

function maskApiKey(key: string): string {
  if (!key || key.length <= 8) return '***';
  return key.substring(0, 4) + '•'.repeat(key.length - 8) + key.substring(key.length - 4);
}
