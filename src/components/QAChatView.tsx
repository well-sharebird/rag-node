import { useState, useRef, useEffect } from 'react';
import { flushSync } from 'react-dom';
import { useAppContext } from '@/lib/app-context';
import { useAuth } from '@/src/lib/auth-context';
import { useI18n } from '@/src/lib/i18n';
import { toast } from 'sonner';
import { Send, BookOpen, Loader2, ThumbsUp, ThumbsDown, X, Brain, AtSign, Check, Cpu, ChevronUp, ChevronDown } from 'lucide-react';
import { SourcePanel } from './SourcePanel';
import { cn } from '@/lib/utils';
import { submitFeedback, createConversation, addMessageToConversation } from '@/lib/api-client';
import { getApiUrl } from '@/src/lib/env';
import { ChatMessageList, type ChatMessage as ChatMessageType } from './ChatMessageList';

interface Citation {
  index: number;
  doc_name: string;
  doc_id?: string;
  chunk_id?: string;
  page?: number;
  content?: string;
  score?: number;
}

interface ChatMessageSource {
  index: number;
  doc_name: string;
  doc_id?: string;
  chunk_id?: string;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  reasoning?: string;
  showReasoning?: boolean;
  sources?: ChatMessageSource[];
  messageId?: string;
  isStreaming?: boolean;
}

function parseReasoningAndAnswer(text: string): { reasoning: string; answer: string } {
  // Detect "Thinking Process:" or "思考过程" followed by numbered steps
  const thinkPatterns = [
    /^Thinking Process:\s*\n([\s\S]*?)(?=\n\n(?:Based on|According|根据|Answer|回答|The|该|丁|测评))/i,
    /^思考过程[：:]\s*\n([\s\S]*?)(?=\n\n(?:基于|根据|综上|回答|答案))/,
  ];

  for (const pattern of thinkPatterns) {
    const match = text.match(pattern);
    if (match) {
      const reasoning = match[1].trim();
      const answer = text.slice(match[0].length).trim();
      return { reasoning, answer };
    }
  }

  // If "Thinking Process:" appears but doesn't match the full pattern
  const thinkIdx = text.search(/(?:Thinking Process:|思考过程[：:])\s*\n/i);
  if (thinkIdx >= 0) {
    // Find the answer start: look for "Based on", "根据", "Answer:", "回答:", or a blank line after numbered list
    const afterThink = text.slice(thinkIdx);
    const answerStart = afterThink.search(/\n\n(?:Based on|According|根据|Answer|回答|The |该|[A-Z])/i);
    if (answerStart > 0) {
      const reasoning = afterThink.slice(0, answerStart).replace(/^(?:Thinking Process:|思考过程[：:])\s*\n/i, '').trim();
      const answer = afterThink.slice(answerStart).trim();
      return { reasoning, answer };
    }
  }

  return { reasoning: '', answer: text };
}

interface FeedbackData {
  messageId: string;
  feedbackType: 'thumbs_up' | 'thumbs_down';
  reason?: string;
}

interface ModelConfig {
  id: number;
  name: string;
  model_id: string;
  model_type: string;
  provider: string;
  is_enabled: boolean;
}

export function QAChatView() {
  const { knowledgeBases } = useAppContext();
  const { token } = useAuth();
  const { t, language } = useI18n();
  const [selectedKbs, setSelectedKbs] = useState<string[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [showFeedback, setShowFeedback] = useState<string | null>(null);
  const [sourcePanelOpen, setSourcePanelOpen] = useState(false);
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const [allCitations, setAllCitations] = useState<Citation[]>([]);

  // Session management state
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [isSavingMessage, setIsSavingMessage] = useState(false);

  // Model selection state
  const [availableModels, setAvailableModels] = useState<ModelConfig[]>([]);
  const [selectedModelId, setSelectedModelId] = useState<string>(''); // 存储模型的 model_id 字符串
  const [showModelSelector, setShowModelSelector] = useState(false);
  const [isLoadingModels, setIsLoadingModels] = useState(false);

  // 注意：AI 助手使用 Meta Agent 接口 (/api/v1/agents/meta/execute/stream)
  // 不需要预先加载 agent_id，直接在请求时调用即可

  // @ mention selector state
  const [showKbSelector, setShowKbSelector] = useState(false);
  const [kbSelectorIndex, setKbSelectorIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Load available models
  useEffect(() => {
    const loadModels = async () => {
      setIsLoadingModels(true);
      try {
        const data = await fetch(getApiUrl('/api/v1/models?enabled_only=true'), {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        }).then(res => res.json());
        const llmModels = (data.items || []).filter((m: ModelConfig) => m.model_type === 'llm');
        setAvailableModels(llmModels);
        // Set default model (first one or previously selected) - store model_id string
        if (llmModels.length > 0 && !selectedModelId) {
          setSelectedModelId(llmModels[0].model_id); // 使用 model_id 字符串
        }
      } catch (e: any) {
        console.error('Failed to load models:', e);
      } finally {
        setIsLoadingModels(false);
      }
    };
    loadModels();
  }, [token]);

  // Close KB selector on Escape
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setShowKbSelector(false);
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [showKbSelector]);

  // Close model selector when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (showModelSelector && !target.closest('button') && !target.closest('.absolute')) {
        setShowModelSelector(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showModelSelector]);

  // 每次进入 AI 助手页面都创建新会话（即使刷新页面也创建新的）
  useEffect(() => {
    // 不检查 currentSessionId，每次都创建新的
    createNewSession();
  }, []);

  // Create new session
  const createNewSession = async () => {
    try {
      const newSession = await createConversation({ title: '新对话' });
      setCurrentSessionId(newSession.id);
      setMessages([]);
      setAllCitations([]);
    } catch (e: any) {
      console.error('Failed to create session:', e);
    }
  };

  // Save message to current session
  const saveMessageToSession = async (role: string, content: string, sources?: any[], modelUsed?: string, latencyMs?: number) => {
    if (!currentSessionId || isSavingMessage) {
      console.log('Skip saving: currentSessionId=', currentSessionId, 'isSavingMessage=', isSavingMessage);
      return;
    }
    try {
      setIsSavingMessage(true);
      console.log('Saving message to session', currentSessionId, role, content.substring(0, 50));
      await addMessageToConversation(currentSessionId, {
        role,
        content,
        sources,
        model_used: modelUsed,
        latency_ms: latencyMs,
      });
      console.log('Message saved successfully');
    } catch (e: any) {
      console.error('Failed to save message to session:', e);
    } finally {
      setIsSavingMessage(false);
    }
  };

  const handleSend = async () => {
    if (!input.trim()) {
      return;
    }

    // 等待会话创建完成
    if (!currentSessionId) {
      console.log('Waiting for session to be created...');
      await new Promise(resolve => setTimeout(resolve, 500));
      if (!currentSessionId) {
        toast.error('会话创建中，请稍后');
        return;
      }
    }

    const query = input.trim();
    setInput('');

    const userMsg: ChatMessage = { role: 'user', content: query };
    setMessages(prev => [...prev, userMsg]);
    setLoading(true);

    // Create assistant message placeholder
    const assistantMsgId = `msg_${Date.now()}`;
    const assistantMsg: ChatMessage = {
      role: 'assistant',
      content: '',
      sources: [],
      messageId: assistantMsgId,
      isStreaming: true,
    };
    setMessages(prev => [...prev, assistantMsg]);

    // Abort any ongoing stream
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    try {
      // If no KB selected, use direct LLM chat without RAG
      const useRAG = selectedKbs.length > 0;
      // 确保模型名称正确传递 - 使用 model_id 而不是 name
      const modelName = availableModels.find(m => m.model_id === selectedModelId)?.model_id || availableModels[0]?.model_id;

      // 使用 Meta Agent 接口进行问答（系统内置的 AI 助手入口，不需要 agent_id）
      const requestBody: any = {
        query,
        kb_ids: useRAG ? selectedKbs : undefined,
        top_k: 5,
        enable_rerank: useRAG,
      };
      // 只在有选择模型时传递 model_name，让 Agent 使用默认配置
      if (modelName) {
        requestBody.model_name = modelName;
      }

      // 使用 Meta Agent 接口：/api/v1/agents/meta/execute/stream
      const res = await fetch(getApiUrl('/api/v1/agents/meta/execute/stream'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(requestBody),
        signal: abortControllerRef.current.signal,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'Chat request failed');
      }

      // Handle SSE stream
      const reader = res.body?.getReader();
      if (!reader) {
        throw new Error('No response body');
      }

      const decoder = new TextDecoder();
      let accumulatedContent = '';
      let accumulatedReasoning = '';
      let sources: Citation[] = [];
      let messageId = assistantMsgId;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data === '[DONE]') continue;
            // Skip debug lines - they use a different format
            if (data.startsWith('[DEBUG:')) continue;

            try {
              const parsed = JSON.parse(data);

              // Handle Agent API stream format: {"type": "token", "content": "..."}
              if (parsed.type === 'token' && parsed.content) {
                accumulatedContent += parsed.content;
                flushSync(() => {
                  setMessages(prev => prev.map(msg =>
                    msg.messageId === messageId
                      ? { ...msg, content: accumulatedContent }
                      : msg
                  ));
                });
                continue;
              }

              // Handle done event
              if (parsed.type === 'done') {
                setMessages(prev => prev.map(msg =>
                  msg.messageId === messageId
                    ? { ...msg, isStreaming: false }
                    : msg
                ));
                setLoading(false);

                // Save messages to session after streaming completes
                if (currentSessionId) {
                  // Save user message and assistant message in parallel
                  Promise.all([
                    saveMessageToSession('user', query),
                    saveMessageToSession('assistant', accumulatedContent, sources, modelName),
                  ]).catch(err => console.error('Failed to save messages:', err));
                }
                continue;
              }

              // Handle error event - 只在没有收到任何内容时才删除消息
              if (parsed.type === 'error' && parsed.error) {
                // 如果已经有内容了，说明是后续的错误（如 checkpoint 保存失败），不删除消息
                if (accumulatedContent.trim().length === 0) {
                  toast.error(parsed.error);
                  setMessages(prev => prev.filter(msg => msg.messageId !== messageId));
                } else {
                  // 已经有成功内容，只显示 toast 警告，不删除消息
                  console.warn('Stream completed with content, but got trailing error:', parsed.error);
                  setMessages(prev => prev.map(msg =>
                    msg.messageId === messageId
                      ? { ...msg, isStreaming: false }
                      : msg
                  ));
                  setLoading(false);
                }
                setLoading(false);
                continue;
              }

              // Handle complete event (Meta Agent 执行完成)
              if (parsed.type === 'complete') {
                // 只是标记完成，不改变 UI
                continue;
              }

              // Handle custom citations event (sent before streaming)
              if (parsed.type === 'citations' && parsed.citations) {
                sources = parsed.citations;
                setMessages(prev => prev.map(msg =>
                  msg.messageId === assistantMsgId
                    ? { ...msg, sources }
                    : msg
                ));
                // Collect all citations for the panel
                setAllCitations(prev => {
                  const existing = new Set(prev.map(c => c.chunk_id || `${c.index}`));
                  const newCitations = sources.filter(s => !existing.has(s.chunk_id || `${s.index}`))
                    .map(s => ({
                      ...s,
                      chunk_id: s.chunk_id,
                    }));
                  return [...prev, ...newCitations];
                });
                continue;
              }

              // Handle OpenAI-style chat.completion.chunk (fallback for direct LLM calls)
              if (parsed.object === 'chat.completion.chunk' && parsed.choices) {
                const choice = parsed.choices[0];
                const delta = choice?.delta;
                const finishReason = choice?.finish_reason;

                // Update message ID if provided
                if (parsed.id && messageId === assistantMsgId) {
                  messageId = parsed.id;
                  setMessages(prev => prev.map(msg =>
                    msg.messageId === assistantMsgId
                      ? { ...msg, messageId: parsed.id }
                      : msg
                  ));
                }

                // Handle reasoning_content / reasoning (thinking process)
                // For Qwen model: reasoning contains both thinking AND final answer
                const reasoningChunk = delta?.reasoning_content || delta?.reasoning || '';
                if (reasoningChunk) {
                  accumulatedReasoning += reasoningChunk;
                  flushSync(() => {
                    setMessages(prev => prev.map(msg =>
                      msg.messageId === messageId
                        ? { ...msg, reasoning: accumulatedReasoning, showReasoning: true }
                        : msg
                    ));
                  });
                }

                // Handle content (final answer)
                if (delta?.content) {
                  accumulatedContent += delta.content;
                  flushSync(() => {
                    setMessages(prev => prev.map(msg =>
                      msg.messageId === messageId
                        ? { ...msg, content: accumulatedContent }
                        : msg
                    ));
                  });
                }

                // For Qwen: if we have reasoning but no content, parse the reasoning
                // to extract the actual answer when streaming is complete
                if (finishReason && accumulatedReasoning && !accumulatedContent) {
                  const extractedAnswer = extractAnswerFromReasoning(accumulatedReasoning);
                  if (extractedAnswer && extractedAnswer !== accumulatedReasoning) {
                    accumulatedContent = extractedAnswer;
                    setMessages(prev => prev.map(msg =>
                      msg.messageId === messageId
                        ? { ...msg, content: extractedAnswer }
                        : msg
                    ));
                  } else {
                    // Use full reasoning as content if no answer extracted
                    accumulatedContent = accumulatedReasoning;
                    setMessages(prev => prev.map(msg =>
                      msg.messageId === messageId
                        ? { ...msg, content: accumulatedReasoning }
                        : msg
                    ));
                  }
                }

                // Handle finish_reason - mark streaming as complete
                if (finishReason) {
                  setMessages(prev => prev.map(msg =>
                    msg.messageId === messageId
                      ? { ...msg, isStreaming: false }
                      : msg
                  ));
                }
              }

              // Handle legacy message_id event (fallback)
              if (parsed.message_id) {
                messageId = parsed.message_id;
                setMessages(prev => prev.map(msg =>
                  msg.messageId === assistantMsgId
                    ? { ...msg, messageId: parsed.message_id }
                    : msg
                ));
              }

              // Handle legacy citations event (fallback)
              if (parsed.citations || parsed.sources) {
                sources = parsed.citations || parsed.sources;
                setMessages(prev => prev.map(msg =>
                  msg.messageId === messageId
                    ? { ...msg, sources }
                    : msg
                ));
                setAllCitations(prev => {
                  const existing = new Set(prev.map(c => c.chunk_id || `${c.index}`));
                  const newCitations = sources.filter(s => !existing.has(s.chunk_id || `${s.index}`))
                    .map(s => ({
                      ...s,
                      chunk_id: s.chunk_id,
                    }));
                  return [...prev, ...newCitations];
                });
              }
            } catch (e) {
              // Skip invalid JSON lines
              console.warn('Failed to parse SSE line:', line, e);
            }
          }
        }
      }

    } catch (e: any) {
      if (e.name === 'AbortError') {
        return;  // Stream was aborted, don't show error
      }
      toast.error(e.message || 'Chat failed');
      // Update assistant message with error
      setMessages(prev => prev.map(msg =>
        msg.messageId === assistantMsgId
          ? { ...msg, content: t('qa.error'), isStreaming: false }
          : msg
      ));
    } finally {
      setLoading(false);
      abortControllerRef.current = null;
    }
  };

  const handleFeedback = async (messageId: string, feedbackType: 'thumbs_up' | 'thumbs_down', reason?: string) => {
    try {
      await submitFeedback({
        session_id: `session_${Date.now()}`,
        message_id: messageId,
        feedback_type: feedbackType,
        reason_category: reason,
      });

      toast.success(feedbackType === 'thumbs_up' ? t('feedback.up') : t('feedback.down'));
      setShowFeedback(null);
    } catch (e: any) {
      toast.error(e.message || 'Feedback failed');
    }
  };

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setMessages(prev => {
      const lastAssistantMsg = [...prev].reverse().find(m => m.role === 'assistant' && m.isStreaming);
      if (lastAssistantMsg) {
        return prev.map(msg =>
          msg.messageId === lastAssistantMsg.messageId
            ? { ...msg, isStreaming: false }
            : msg
        );
      }
      return prev;
    });
    setLoading(false);
  };

  // Handle @ key to show KB selector
  const handleInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (showKbSelector) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setKbSelectorIndex(prev => (prev + 1) % knowledgeBases.length);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setKbSelectorIndex(prev => (prev - 1 + knowledgeBases.length) % knowledgeBases.length);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const selected = knowledgeBases[kbSelectorIndex];
        if (selected && !selectedKbs.includes(selected.id)) {
          setSelectedKbs(prev => [...prev, selected.id]);
        }
        setShowKbSelector(false);
        setInput(prev => prev.replace(/@$/, ''));
      } else if (e.key === 'Escape') {
        setShowKbSelector(false);
      }
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setInput(value);
    // Show KB selector when @ is typed
    if (value.endsWith('@')) {
      setShowKbSelector(true);
      setKbSelectorIndex(0);
    } else {
      setShowKbSelector(false);
    }
  };

  const toggleKbSelection = (kbId: string) => {
    setSelectedKbs(prev =>
      prev.includes(kbId)
        ? prev.filter(id => id !== kbId)
        : [...prev, kbId]
    );
  };

  const removeKb = (kbId: string) => {
    setSelectedKbs(prev => prev.filter(id => id !== kbId));
  };

  // Extract answer from Qwen-style reasoning
  // Format: "Thinking Process:\n\n1. ...\n2. ...\n\n*Draft:*\n[actual answer]"
  const extractAnswerFromReasoning = (reasoning: string): string => {
    // Try to find common patterns that mark the start of the answer
    const patterns = [
      /\*Draft:\*\s*\n/i,
      /\*\*Final Answer\*\*:\s*\n/i,
      /\n\n(?:Based on|According to|In summary|综上 | 因此 | 所以 | 答案 | 回答)[:：]?/i,
    ];

    for (const pattern of patterns) {
      const match = reasoning.match(pattern);
      if (match) {
        const answer = reasoning.slice(match.index! + match[0].length).trim();
        if (answer && answer.length > 10) {
          return answer;
        }
      }
    }

    // If no pattern found, return the last 1-2 paragraphs
    const paragraphs = reasoning.split('\n\n');
    if (paragraphs.length > 1) {
      return paragraphs.slice(-2).join('\n\n').trim();
    }

    return reasoning;
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      {/* Header */}
      <header className="h-[52px] px-5 bg-white flex items-center justify-between shrink-0" style={{ borderBottom: '0.5px solid #e2e1dd' }}>
        <div className="flex items-baseline gap-3">
          <h1 className="text-[15px] font-medium text-[var(--text-primary)]">{t('qa.title')}</h1>
          <span className="text-[11px] text-[#9b9b9b] hidden sm:inline">{t('qa.desc')}</span>
          {/* Mode indicator */}
          <span className={`ml-2 px-2 py-0.5 rounded-full text-[10px] font-medium ${
            selectedKbs.length > 0
              ? 'bg-green-100 text-green-700'
              : 'bg-blue-100 text-blue-700'
          }`}>
            {selectedKbs.length > 0 ? 'RAG 模式' : 'LLM 模式'}
          </span>
          {/* Model selector */}
          <div className="relative">
            <button
              onClick={() => setShowModelSelector(!showModelSelector)}
              className="ml-2 px-2.5 py-1 rounded-lg text-[10px] font-medium border hover:bg-gray-50 transition-colors flex items-center gap-1.5"
              style={{ borderColor: '#e2e1dd', color: '#534ab7' }}
              disabled={isLoadingModels}
            >
              <Cpu className="w-3 h-3" />
              {isLoadingModels ? '加载中...' :
               availableModels.find(m => String(m.id) === selectedModelId)?.name ||
               availableModels[0]?.name || '选择模型'}
              {showModelSelector ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>

            {/* Model selector dropdown */}
            {showModelSelector && (
              <div className="absolute top-full left-0 mt-1 w-56 bg-white rounded-lg shadow-lg border border-[#e2e1dd] z-50 overflow-hidden">
                <div className="max-h-64 overflow-y-auto py-1">
                  {availableModels.map((model) => (
                    <button
                      key={model.id}
                      onClick={() => {
                        setSelectedModelId(String(model.id));
                        setShowModelSelector(false);
                      }}
                      className={`w-full px-3 py-2 text-left text-xs hover:bg-gray-50 flex items-center justify-between ${
                        String(selectedModelId) === String(model.id) ? 'bg-[#eeedfe]' : ''
                      }`}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-[var(--text-primary)] truncate">{model.name}</div>
                        <div className="text-[#9b9b9b] text-[10px] truncate">{model.model_id}</div>
                      </div>
                      {selectedModelId === model.model_id && (
                        <Check className="w-3.5 h-3.5 text-[#534ab7] shrink-0 ml-2" />
                      )}
                    </button>
                  ))}
                  {availableModels.length === 0 && (
                    <div className="px-3 py-4 text-center text-xs text-[#9b9b9b]">
                      暂无可用模型
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3">
          {allCitations.length > 0 && (
            <button
              onClick={() => setSourcePanelOpen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-gray-50 transition-colors"
              style={{ color: '#534ab7' }}
            >
              <BookOpen className="w-3.5 h-3.5" />
              来源 ({allCitations.length})
            </button>
          )}
        </div>
      </header>

      {/* Messages */}
      <ChatMessageList
        messages={messages.map((m): ChatMessageType => ({
          id: m.messageId,
          role: m.role,
          content: m.content,
          reasoning: m.reasoning,
          showReasoning: m.showReasoning,
          sources: m.sources,
          isStreaming: m.isStreaming,
        }))}
        loading={loading}
        onReasoningToggle={(messageId) => {
          setMessages(prev => prev.map(m =>
            m.messageId === messageId
              ? { ...m, showReasoning: m.showReasoning === false }
              : m
          ));
        }}
        onSourceClick={(sources) => {
          if (sources && sources.length > 0) {
            setSelectedCitation(sources[0]);
            setSourcePanelOpen(true);
          }
        }}
        emptyState={{
          title: t('qa.empty.title'),
          description: selectedKbs.length > 0
            ? `已选择 ${selectedKbs.length} 个知识库，开始提问吧。`
            : '未选择知识库，将使用 LLM 直接回答。选择知识库可启用 RAG 检索增强模式。',
        }}
      />

      {/* Feedback bar - shown after assistant response */}
      {messages.some(m => m.role === 'assistant' && !m.isStreaming) && (
        <div className="px-5 py-3 bg-white border-t border-gray-100">
          <div className="max-w-3xl mx-auto">
            {messages.filter(m => m.role === 'assistant' && !m.isStreaming).slice(-1)[0] && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500">{t('qa.feedbackPrompt')}</span>
                <button
                  onClick={() => {
                    const lastMsg = messages.filter(m => m.role === 'assistant' && !m.isStreaming).slice(-1)[0];
                    if (lastMsg) handleFeedback(lastMsg.messageId!, 'thumbs_up');
                  }}
                  className="p-1.5 rounded hover:bg-green-50 text-green-600"
                >
                  <ThumbsUp className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => {
                    const lastMsg = messages.filter(m => m.role === 'assistant' && !m.isStreaming).slice(-1)[0];
                    if (lastMsg) handleFeedback(lastMsg.messageId!, 'thumbs_down', 'other');
                  }}
                  className="p-1.5 rounded hover:bg-red-50 text-red-600"
                >
                  <ThumbsDown className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Input */}
      <div className="p-4 bg-white shrink-0" style={{ borderTop: '0.5px solid #e2e1dd' }}>
        <div className="max-w-3xl mx-auto">
          {/* Selected KBs display */}
          {selectedKbs.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-3">
              {selectedKbs.map(kbId => {
                const kb = knowledgeBases.find(k => k.id === kbId);
                return (
                  <span
                    key={kbId}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium"
                    style={{ background: '#eeedfe', color: '#534ab7' }}
                  >
                    <BookOpen className="w-3 h-3" />
                    {kb?.name || kbId}
                    <button
                      onClick={() => removeKb(kbId)}
                      className="hover:opacity-70"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </span>
                );
              })}
            </div>
          )}

          <div className="flex gap-2 relative">
            <div className="flex-1 relative">
              <input
                ref={inputRef}
                value={input}
                onChange={handleInputChange}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    handleSend();
                  }
                  handleInputKeyDown(e);
                }}
                placeholder={selectedKbs.length === 0 ? `${t('qa.placeholder')} · @ 选择知识库` : t('qa.placeholder')}
                disabled={loading}
                className="w-full px-4 py-2.5 text-[13px] rounded-lg border outline-none disabled:opacity-50 pr-10"
                style={{ borderColor: '#e2e1dd' }}
              />
              <AtSign
                className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#999]"
              />
            </div>
            {loading ? (
              <button
                onClick={handleStop}
                className="px-4 py-2.5 rounded-lg text-white font-medium transition-colors text-[13px]"
                style={{ background: '#dc2626' }}
              >
                {t('qa.stop')}
              </button>
            ) : (
              <button
                onClick={handleSend}
                disabled={!input.trim()}
                className="px-4 py-2.5 rounded-lg text-white font-medium transition-colors disabled:opacity-50 flex items-center gap-1.5 text-[13px]"
                style={{ background: '#534ab7' }}
              >
                <Send className="w-3.5 h-3.5" />
                {t('qa.send')}
              </button>
            )}
          </div>

          {/* KB Selector Popup - shows when @ is typed */}
          {showKbSelector && (
            <div
              className="absolute bottom-28 left-1/2 -translate-x-1/2 w-full max-w-lg z-50"
              style={{ pointerEvents: 'auto' }}
            >
              <div className="bg-white rounded-xl shadow-2xl border border-[var(--gray-200)] overflow-hidden">
                <div className="px-3 py-2 border-b border-[var(--gray-200)] bg-[#f9f9f9] flex items-center justify-between">
                  <span className="text-xs font-medium text-[#666]">
                    {language === 'zh' ? '选择知识库' : 'Select Knowledge Base'}
                  </span>
                  <button
                    onClick={() => setShowKbSelector(false)}
                    className="text-[#999] hover:text-[#666]"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
                <div className="max-h-64 overflow-y-auto p-1.5">
                  {knowledgeBases.length === 0 ? (
                    <div className="py-8 text-center text-sm text-[#999]">
                      {language === 'zh' ? '暂无知识库' : 'No knowledge bases'}
                    </div>
                  ) : (
                    knowledgeBases.map((kb, idx) => {
                      const isSelected = selectedKbs.includes(kb.id);
                      return (
                        <button
                          key={kb.id}
                          onClick={() => toggleKbSelection(kb.id)}
                          className={cn(
                            "w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors",
                            idx === kbSelectorIndex ? "bg-[var(--gray-50)]" : "",
                            isSelected ? "bg-[#eeedfe]" : "hover:bg-[#f9f9f9]"
                          )}
                        >
                          <BookOpen className={cn(
                            "w-4 h-4",
                            isSelected ? "text-[#534ab7]" : "text-[#999]"
                          )} />
                          <span className={cn(
                            "flex-1 text-left truncate",
                            isSelected ? "text-[#534ab7] font-medium" : "text-[var(--text-primary)]"
                          )}>
                            {kb.name}
                          </span>
                          {isSelected && (
                            <Check className="w-4 h-4 text-[#534ab7]" />
                          )}
                        </button>
                      );
                    })
                  )}
                </div>
                <div className="px-3 py-2 border-t border-[var(--gray-200)] bg-[#f9f9f9]">
                  <p className="text-[10px] text-[#999]">
                    {language === 'zh'
                      ? '↑↓ 导航，Enter 选择，Esc 关闭'
                      : '↑↓ Navigate, Enter to select, Esc to close'}
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Source Panel */}
      <SourcePanel
        isOpen={sourcePanelOpen}
        onClose={() => {
          setSourcePanelOpen(false);
          setSelectedCitation(null);
        }}
        citations={allCitations}
        selectedCitation={selectedCitation}
        onSelectCitation={(citation) => {
          setSelectedCitation(citation);
          // TODO: Scroll to and highlight the citation in the message
        }}
      />
    </div>
  );
}
