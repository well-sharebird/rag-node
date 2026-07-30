import { useState, useEffect, useRef } from 'react';
import { useAuth } from '@/src/lib/auth-context';
import { toast } from 'sonner';
import { fetchApi } from '@/lib/api-client';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import {
  Send, Bot, User, Loader2, Settings, ChevronDown, ChevronUp,
  MessageSquare, Trash2, Download, Copy, StopCircle, ArrowLeft, RefreshCw
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '../components/enterprise/Button';
import { Badge } from '../components/enterprise/Badge';
import { Select } from '../components/enterprise/Select';
import { Textarea } from '../components/enterprise/Textarea';
import { Label } from '../components/enterprise/Label';
import { Slider } from '../components/enterprise/Slider';

// ========== Types ==========

interface AgentConfig {
  id: string;
  name: string;
  description: string | null;
  icon: string | null;
  system_prompt: string;
  agent_type: string;
  default_model_config: any;
}

interface ModelProviderData {
  id: number;
  name: string;
  code: string;
  provider_type: string;
  is_enabled: boolean;
}

interface ModelConfigData {
  id: number;
  name: string;
  model_id: string;
  model_type: string;
  provider: string;
  is_enabled: boolean;
  tags?: string[];
}

interface Message {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
}

interface StreamEvent {
  type: 'token' | 'done' | 'error';
  content?: string;
  error?: string;
}

// ========== 模型类型映射 ==========

const MODEL_TYPE_FILTERS: Record<string, string[]> = {
  llm: ['llm'],
  embedding: ['embedding'],
  rerank: ['rerank'],
  vision: ['vision'],
};

// ========== Main Component ==========

export function AgentChat() {
  const { token } = useAuth();

  // URL 参数 或 sessionStorage
  const urlParams = new URLSearchParams(window.location.search);
  const agentIdFromUrl = urlParams.get('agent_id');
  const agentIdFromSession = sessionStorage.getItem('agent_chat_id');
  const initialAgentId = agentIdFromUrl || agentIdFromSession;

  const [loading, setLoading] = useState(true);
  const [agent, setAgent] = useState<AgentConfig | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string>(`session_${Date.now()}`);

  // 模型选择 - 从后端 API 获取
  const [showModelSettings, setShowModelSettings] = useState(false);
  const [modelProviders, setModelProviders] = useState<ModelProviderData[]>([]);
  const [modelConfigs, setModelConfigs] = useState<ModelConfigData[]>([]);
  const [selectedProvider, setSelectedProvider] = useState('');
  const [selectedModel, setSelectedModel] = useState('');
  const [temperature, setTemperature] = useState(0.7);
  const [maxTokens, setMaxTokens] = useState(4096);
  const [topP, setTopP] = useState(1.0);
  const [loadingModels, setLoadingModels] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (initialAgentId) {
      fetchAgent(initialAgentId);
      // 清除 sessionStorage
      sessionStorage.removeItem('agent_chat_id');
    } else {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // 从模型管理获取数据
  useEffect(() => {
    fetchModelData();
  }, []);

  // 当 provider 变化时，自动选择第一个模型
  useEffect(() => {
    const providerModels = modelConfigs.filter(m => m.provider === selectedProvider);
    if (providerModels.length > 0 && !selectedModel) {
      setSelectedModel(providerModels[0].model_id);
    }
  }, [selectedProvider, modelConfigs]);

  const fetchModelData = async () => {
    try {
      setLoadingModels(true);
      // 获取启用的供应商 - 使用正确的 API 路径
      const providersData = await fetchApi<{items: ModelProviderData[]}>('/api/v1/model-gateway/providers');
      const enabledProviders = (providersData?.items || []).filter(p => p.is_enabled);
      setModelProviders(enabledProviders);

      // 获取启用的模型配置
      const modelsData = await fetchApi<{items: ModelConfigData[]}>('/api/v1/models');
      const enabledModels = (modelsData?.items || []).filter(m => m.is_enabled && m.model_type === 'llm');
      setModelConfigs(enabledModels);

      // 设置默认值 - 优先选择 local_qwen 或有 API key 的 provider
      if (enabledProviders.length > 0 && !selectedProvider) {
        // 优先选择 local_qwen
        const localQwen = enabledProviders.find(p => p.code === 'local_qwen');
        if (localQwen) {
          setSelectedProvider(localQwen.code);
        } else {
          setSelectedProvider(enabledProviders[0].code);
        }
      }
      if (enabledModels.length > 0 && !selectedModel) {
        const providerModels = enabledModels.filter(m => m.provider === selectedProvider);
        if (providerModels.length > 0) {
          setSelectedModel(providerModels[0].model_id);
        } else {
          setSelectedModel(enabledModels[0].model_id);
        }
      }
    } catch (error: any) {
      console.error('Failed to fetch models:', error);
      toast.error(`获取模型列表失败：${error.message}`);
    } finally {
      setLoadingModels(false);
    }
  };

  // 自动调整 textarea 高度
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 120)}px`;
    }
  }, [input]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const fetchAgent = async (id: string) => {
    try {
      const data = await fetchApi(`/api/v1/agents/${id}`);
      setAgent(data);

      // 优先使用已保存的模型配置
      if (data.default_model_config?.provider) {
        setSelectedProvider(data.default_model_config.provider);
        if (data.default_model_config.model) {
          setSelectedModel(data.default_model_config.model);
        }
        if (data.default_model_config.temperature !== undefined) {
          setTemperature(data.default_model_config.temperature);
        }
        if (data.default_model_config.max_tokens !== undefined) {
          setMaxTokens(data.default_model_config.max_tokens);
        }
        if (data.default_model_config.top_p !== undefined) {
          setTopP(data.default_model_config.top_p);
        }
      }
    } catch (error: any) {
      toast.error(`获取 Agent 失败：${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleSendMessage = async () => {
    if (!input.trim() || !agent || isStreaming) return;

    const userMessage: Message = {
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsStreaming(true);

    // 添加空的助手消息占位
    setMessages(prev => [...prev, {
      role: 'assistant',
      content: '',
      timestamp: new Date(),
    }]);

    let hasReceivedContent = false;

    try {
      const controller = new AbortController();
      abortControllerRef.current = controller;

      await fetchEventSource(`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/api/v1/agents/${agent.id}/execute/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          query: userMessage.content,
          model_name: selectedModel || undefined,
          plan_mode: false,
          session_id: sessionId,
        }),
        signal: controller.signal,
        onmessage: (event) => {
          try {
            // 跳过空消息
            if (!event.data || event.data.trim() === '') {
              return;
            }
            const data: StreamEvent = JSON.parse(event.data);
            if (data.type === 'token' && data.content) {
              hasReceivedContent = true;
              setMessages(prev => {
                const newMessages = [...prev];
                const lastMessage = newMessages[newMessages.length - 1];
                if (lastMessage && lastMessage.role === 'assistant') {
                  // 如果是第一个 token，替换空内容；否则追加
                  if (lastMessage.content === '') {
                    lastMessage.content = data.content!;
                  } else {
                    lastMessage.content += data.content!;
                  }
                }
                return newMessages;
              });
            } else if (data.type === 'done') {
              setIsStreaming(false);
              abortControllerRef.current = null;
            } else if (data.type === 'error' && data.error) {
              toast.error(data.error);
              setIsStreaming(false);
              setMessages(prev => prev.filter(m => m.content !== ''));
            }
          } catch (e) {
            console.error('Parse error:', e, 'event.data:', event.data);
          }
        },
        onerror: (error) => {
          console.error('SSE error:', error);
          toast.error('连接中断');
          setIsStreaming(false);
          setMessages(prev => prev.filter(m => m.content !== ''));
        },
        onclose: () => {
          setIsStreaming(false);
          abortControllerRef.current = null;
        },
      });
    } catch (error: any) {
      if (error.name !== 'AbortError') {
        toast.error(`发送失败：${error.message}`);
      }
      setIsStreaming(false);
      setMessages(prev => prev.filter(m => m.content !== ''));
    }
  };

  const handleStopGeneration = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setIsStreaming(false);
    }
  };

  const handleClearChat = () => {
    setMessages([]);
    setSessionId(`session_${Date.now()}`);
    toast.success('对话已清空');
  };

  const handleCopyMessage = (content: string) => {
    navigator.clipboard.writeText(content);
    toast.success('已复制');
  };

  const handleSaveModelConfig = async () => {
    if (!selectedProvider || !selectedModel) {
      toast.error('请选择模型供应商和模型');
      return;
    }

    try {
      await fetchApi(`/api/v1/agents/${agent.id}/model-config`, {
        method: 'PUT',
        body: JSON.stringify({
          provider: selectedProvider,
          model: selectedModel,
          temperature,
          max_tokens: maxTokens,
          top_p: topP,
        }),
      });
      toast.success('模型配置已保存');
    } catch (error: any) {
      toast.error(`保存失败：${error.message}`);
    }
  };

  const handleExportChat = () => {
    const chatText = messages.map(m =>
      `[${m.role === 'user' ? '用户' : '助手'}] ${m.content}`
    ).join('\n\n');

    const blob = new Blob([chatText], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `chat_${agent?.name || 'unknown'}_${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success('已导出对话');
  };

  const handleBackToPlaza = () => {
    // 尝试通过 history 返回，如果不行则切换到 plaza
    if (window.history.length > 2) {
      window.history.back();
    } else {
      // 直接切换到广场 tab
      window.location.href = '/?tab=agent-plaza';
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    );
  }

  if (!agent) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-center">
          <Bot className="w-16 h-16 mx-auto mb-4 text-[var(--gray-200)]" />
          <h2 className="text-xl font-bold text-[var(--text-primary)] mb-2">未找到智能体</h2>
          <p className="text-[var(--text-secondary)] mb-4">请从智能体广场选择一个智能体开始对话</p>
          <Button onClick={handleBackToPlaza}>
            <ArrowLeft className="w-4 h-4 mr-2" />
            前往广场
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen bg-white">
      {/* Header */}
      <header className="h-[52px] px-5 bg-white flex items-center justify-between shrink-0 border-b border-[var(--gray-200)]">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={handleBackToPlaza}>
            <ArrowLeft className="w-4 h-4" />
          </Button>
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[var(--primary)] to-[var(--accent)] flex items-center justify-center text-lg">
              {agent.icon || '🤖'}
            </div>
            <div>
              <h1 className="font-medium text-[var(--text-primary)]">{agent.name}</h1>
              <p className="text-xs text-[var(--text-tertiary)] truncate max-w-[200px]">{agent.description}</p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleClearChat} title="清空对话">
            <Trash2 className="w-4 h-4" />
          </Button>
          <Button variant="outline" size="sm" onClick={handleExportChat} title="导出对话">
            <Download className="w-4 h-4" />
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowModelSettings(!showModelSettings)}
            title="模型设置"
          >
            <Settings className="w-4 h-4" />
          </Button>
        </div>
      </header>

      {/* Model Settings Panel */}
      {showModelSettings && (
        <div className="bg-white border-b border-[var(--gray-200)] px-5 py-4">
          <div className="flex items-center justify-between mb-3">
            <Label className="text-sm font-semibold">模型设置</Label>
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={fetchModelData}>
                <RefreshCw className={cn("w-3.5 h-3.5 mr-1", loadingModels && "animate-spin")} />
                刷新
              </Button>
              <Button variant="secondary" size="sm" onClick={handleSaveModelConfig}>
                <Settings className="w-3.5 h-3.5 mr-1" />
                保存配置
              </Button>
            </div>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 max-w-4xl">
            <div>
              <Label className="text-xs">模型供应商</Label>
              <Select
                value={selectedProvider}
                onChange={(e) => setSelectedProvider(e.target.value)}
                className="mt-1"
              >
                <option value="">请选择供应商</option>
                {modelProviders.map((p) => (
                  <option key={p.id} value={p.code}>{p.name} ({p.code})</option>
                ))}
              </Select>
            </div>
            <div>
              <Label className="text-xs">模型</Label>
              <Select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="mt-1"
              >
                <option value="">请选择模型</option>
                {modelConfigs
                  .filter(m => m.provider === selectedProvider)
                  .map((m) => (
                    <option key={m.id} value={m.model_id}>{m.name || m.model_id}</option>
                  ))}
              </Select>
            </div>
            <div>
              <Label className="text-xs">Temperature: {temperature.toFixed(1)}</Label>
              <Slider
                value={temperature}
                onChange={(e) => setTemperature(parseFloat(e.target.value))}
                min={0}
                max={2}
                step={0.1}
                className="mt-2"
              />
            </div>
            <div>
              <Label className="text-xs">Max Tokens: {maxTokens}</Label>
              <Select
                value={maxTokens.toString()}
                onChange={(e) => setMaxTokens(parseInt(e.target.value))}
                className="mt-1"
              >
                <option value="1024">1024</option>
                <option value="2048">2048</option>
                <option value="4096">4096</option>
                <option value="8192">8192</option>
              </Select>
            </div>
          </div>
          <div className="mt-4 flex items-center justify-between">
            <p className="text-xs text-[var(--text-secondary)]">
              当前选择：{selectedProvider} / {selectedModel}
            </p>
            {modelProviders.length === 0 && !loadingModels && (
              <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-lg text-sm text-yellow-800">
                <p>暂无可用模型，请先在 <a href="/?tab=model-management" className="underline font-medium">模型管理</a> 中配置并启用模型</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Chat Messages */}
      <div className="flex-1 overflow-y-auto p-4">
        <div className="max-w-3xl mx-auto">
          {messages.length === 0 && (
            <div className="text-center py-12">
              <div className="w-20 h-20 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-[var(--primary)] to-[var(--accent)] flex items-center justify-center text-4xl">
                {agent.icon || '🤖'}
              </div>
              <h3 className="text-lg font-medium text-[var(--text-primary)] mb-1">开始与 {agent.name} 对话</h3>
              <p className="text-[var(--text-secondary)] text-sm mb-4">
                当前模型：{selectedProvider} / {selectedModel}
              </p>
              <div className="flex justify-center gap-2 flex-wrap">
                {['介绍一下你自己', '你能帮我做什么？', '有什么功能？'].map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => setInput(suggestion)}
                    className="px-3 py-1.5 bg-white border border-[var(--gray-200)] rounded-full text-sm text-[var(--text-secondary)] hover:border-blue-500 hover:text-blue-500 transition-colors"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((message, index) => (
            <div
              key={index}
              className={cn(
                "flex items-start gap-3 mb-4",
                message.role === 'user' ? "flex-row-reverse" : ""
              )}
            >
              <div className={cn(
                "w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0",
                message.role === 'user'
                  ? "bg-blue-500 text-white"
                  : "bg-gradient-to-br from-[var(--primary)] to-[var(--accent)] text-white"
              )}>
                {message.role === 'user' ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
              </div>
              <div className={cn(
                "flex-1 max-w-[80%]",
                message.role === 'user' ? "text-right" : "text-left"
              )}>
                <div className={cn(
                  "inline-block px-4 py-2.5 rounded-2xl text-sm",
                  message.role === 'user'
                    ? "bg-blue-500 text-white rounded-tr-sm"
                    : "bg-white border border-[var(--gray-200)] rounded-tl-sm text-[var(--text-primary)]"
                )}>
                  <p className="whitespace-pre-wrap break-words">{message.content}</p>
                </div>
                {message.role === 'assistant' && message.content && (
                  <div className="mt-1.5 flex items-center gap-2">
                    <button
                      className="text-xs text-[var(--text-tertiary)] hover:text-[var(--text-primary)] transition-colors flex items-center gap-1"
                      onClick={() => handleCopyMessage(message.content)}
                    >
                      <Copy className="w-3 h-3" />
                      复制
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input Area */}
      <div className="bg-white border-t border-[var(--gray-200)] px-4 py-4">
        <div className="max-w-3xl mx-auto">
          <div className="flex items-end gap-3">
            <div className="flex-1 relative">
              <Textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="输入你的问题..."
                rows={1}
                className="resize-none pr-16 max-h-[120px]"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSendMessage();
                  }
                }}
              />
            </div>
            {isStreaming ? (
              <Button onClick={handleStopGeneration} variant="danger" size="sm" className="h-[40px] w-[40px] p-0">
                <StopCircle className="w-5 h-5" />
              </Button>
            ) : (
              <Button
                onClick={handleSendMessage}
                size="sm"
                disabled={!input.trim()}
                className="h-[40px] w-[40px] p-0"
              >
                <Send className="w-5 h-5" />
              </Button>
            )}
          </div>
          <div className="flex justify-between items-center mt-2">
            <p className="text-xs text-[var(--text-tertiary)]">
              按 Enter 发送，Shift+Enter 换行
            </p>
            <Badge variant="secondary" size="sm" className="flex items-center gap-1">
              <Settings className="w-2.5 h-2.5" />
              {selectedProvider && selectedModel ? `${selectedProvider} / ${selectedModel}` : '请在设置中选择模型'}
            </Badge>
          </div>
        </div>
      </div>
    </div>
  );
}
