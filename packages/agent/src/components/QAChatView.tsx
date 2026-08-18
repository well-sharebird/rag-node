import { useState, useRef, useEffect } from 'react';
import { flushSync } from 'react-dom';
import { useAppContext } from '@/lib/app-context';
import { useAuth } from '@/src/lib/auth-context';
import { useI18n } from '@/src/lib/i18n';
import { toast } from 'sonner';
import { Send, BookOpen, Loader2, ThumbsUp, ThumbsDown, X, Brain, AtSign, Check, Cpu, ChevronUp, ChevronDown, Bot } from 'lucide-react';
import { SourcePanel } from '@/src/components/SourcePanel';
import { cn } from '@/lib/utils';
import { submitFeedback, createConversation, addMessageToConversation } from '@/lib/api-client';
import { getApiUrl } from '@/src/lib/env';
import { ChatMessageList, type ChatMessage as ChatMessageType, type Step, type RunSummary } from '@/src/components/ChatMessageList';
import {
  isAgentSelected,
  isApprovalRequired,
  isCitations,
  isComplete,
  isDone,
  isErrorEvent,
  isOrchestratorPlan,
  isReasoning,
  isSubAgent,
  isToken,
  isToolEvent,
  type AgentStreamEvent,
} from '@/src/api/stream-events';
import { Modal } from '@/src/components/enterprise/Modal';

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

interface ToolEventFile {
  filename: string;
  relative_path: string;
}

interface ToolCall {
  tool: string;
  status: 'running' | 'success' | 'error' | 'denied' | 'limited' | 'circuit' | 'blocked';
  input?: Record<string, unknown>;
  result?: string;
  files?: ToolEventFile[];
  sandbox?: string;
  collapsed?: boolean;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  reasoning?: string;
  showReasoning?: boolean;
  sources?: ChatMessageSource[];
  toolEvents?: ToolCall[];
  steps?: Step[];
  runSummary?: RunSummary;
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

  // 智能体选择（统一入口：可选广场智能体 + 主从编排开关）
  const [selectedAgentId, setSelectedAgentId] = useState<string>('');
  const [selectedAgentInfo, setSelectedAgentInfo] = useState<{ id: string; name: string } | null>(null);
  const [agentOptions, setAgentOptions] = useState<{ id: string; name: string }[]>([]);
  const [showAgentSelector, setShowAgentSelector] = useState(false);
  const [orchestrator, setOrchestrator] = useState(false);
  const [orchestratorStatus, setOrchestratorStatus] = useState('');

  // 人工审批（HITL）
  const [approvalPending, setApprovalPending] = useState<any[]>([]);
  const [showApprovalModal, setShowApprovalModal] = useState(false);
  const [approving, setApproving] = useState(false);

  // @ mention selector state
  const [showKbSelector, setShowKbSelector] = useState(false);
  const [kbSelectorIndex, setKbSelectorIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  // 记录当前流式 assistant 消息 id，供审批后从断点续跑回写终答
  const assistantMsgIdRef = useRef<string | null>(null);

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

  // 智能体加载：从 URL/session 读取所选 agent_id，并加载可选智能体列表
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const agentFromUrl = urlParams.get('agent_id');
    const agentFromSession = sessionStorage.getItem('agent_chat_id');
    const initial = agentFromUrl || agentFromSession || '';
    if (initial) {
      setSelectedAgentId(initial);
      sessionStorage.removeItem('agent_chat_id');
    }
  }, []);

  useEffect(() => {
    if (!token) return;
    // 加载可选智能体列表（供统一界面选择）
    fetch(getApiUrl('/api/v1/agents'), {
      headers: { 'Authorization': `Bearer ${token}` },
    })
      .then(res => res.json())
      .then((data: any) => {
        const items = Array.isArray(data) ? data : data.items || [];
        setAgentOptions(items.filter((a: any) => a && a.id).map((a: any) => ({
          id: a.id, name: a.name || a.id,
        })));
      })
      .catch(() => {});
  }, [token]);

  // 加载所选智能体信息（显示其身份）
  useEffect(() => {
    if (!selectedAgentId || !token) {
      setSelectedAgentInfo(null);
      return;
    }
    fetch(getApiUrl(`/api/v1/agents/${selectedAgentId}`), {
      headers: { 'Authorization': `Bearer ${token}` },
    })
      .then(res => res.ok ? res.json() : null)
      .then((data: any) => {
        if (data && data.id) setSelectedAgentInfo({ id: data.id, name: data.name });
      })
      .catch(() => setSelectedAgentInfo(null));
  }, [selectedAgentId, token]);

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
    assistantMsgIdRef.current = assistantMsgId;
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

      // 统一执行入口请求：可选 agent_id（所选智能体）/ orchestrator（主从编排）
      const requestBody: any = {
        query,
        kb_ids: useRAG ? selectedKbs : undefined,
        top_k: 5,
        enable_rerank: useRAG,
        session_id: currentSessionId || undefined,
      };
      if (modelName) {
        requestBody.model_name = modelName;
      }
      if (selectedAgentId) {
        requestBody.agent_id = selectedAgentId;
      }
      if (orchestrator) {
        requestBody.orchestrator = true;
      }

      // 使用 Harness 统一入口：/api/v1/agents/execute/stream
      const res = await fetch(getApiUrl('/api/v1/agents/execute/stream'), {
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
      // 线性时间线：按事件到达顺序累积（思考/工具/总结），替代按类型聚合
      const steps: Step[] = [];
      let round = 0;
      const patchSteps = () => {
        flushSync(() => {
          setMessages(prev => prev.map(msg =>
            msg.messageId === messageId ? { ...msg, steps: [...steps] } : msg
          ));
        });
      };

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
              const ev = JSON.parse(data) as AgentStreamEvent;

              // 编排状态事件（主从编排进度反馈；不渲染则安全忽略）
              if (isOrchestratorPlan(ev)) {
                setOrchestratorStatus('编排中…');
                continue;
              }
              if (isSubAgent(ev) && ev.data) {
                const sd = ev.data;
                setOrchestratorStatus(
                  sd.status === 'done'
                    ? `子Agent「${sd.sub_agent_id}」完成`
                    : `调用子Agent「${sd.sub_agent_id}」…`
                );
                continue;
              }
              if (isAgentSelected(ev) && ev.agent_name) {
                // 指定智能体接管提示（不强制展示，token 仍正常）
                setOrchestratorStatus(`智能体「${ev.agent_name}」为您服务`);
                continue;
              }
              // 人工审批需求（HITL）→ 弹窗。pending 项补上 sub_agent_id/thread_id 定位信息，
              // 用于批准后调 /approvals/{id}/resume 从断点续跑。
              if (isApprovalRequired(ev) && ev.data?.pending) {
                const subAgentId = ev.data?.sub_agent_id;
                const next = ev.data.pending.map((p: any) => ({
                  ...p,
                  sub_agent_id: p?.sub_agent_id || subAgentId,
                }));
                setApprovalPending(next);
                setShowApprovalModal(true);
                continue;
              }

              // 工具调用链事件（tool_event）：实时渲染"哪个工具在跑/结果/产物文件"
              if (isToolEvent(ev) && ev.data) {
                const te = ev.data;
                const tc: ToolCall = {
                  tool: te.tool,
                  status: te.phase === 'start' ? 'running' : (te.status || 'success'),
                  input: te.input,
                  result: te.result,
                  files: te.files,
                  sandbox: te.sandbox,
                };
                flushSync(() => {
                  setMessages(prev => prev.map(msg =>
                    msg.messageId === messageId
                      ? {
                          ...msg,
                          toolEvents: (() => {
                            const list = msg.toolEvents ? [...msg.toolEvents] : [];
                            if (te.phase === 'start') {
                              list.push(tc);
                            } else {
                              // done：优先更新同名 running 条目，其次同名已结束条目，否则追加
                              const runIdx = list.findIndex(t => t.tool === te.tool && t.status === 'running');
                              const anyIdx = list.findIndex(t => t.tool === te.tool);
                              const at = runIdx >= 0 ? runIdx : anyIdx;
                              if (at >= 0) list[at] = { ...list[at], ...tc };
                              else list.push({ ...tc });
                            }
                            return list;
                          })(),
                        }
                      : msg
                  ));
                });
                // 线性时间线：工具步骤。start 推新 step，done 回填对应 step
                if (te.phase === 'start') {
                  steps.push({ kind: 'tool', tool: te.tool, status: 'running', input: te.input });
                } else {
                  const status = te.status || 'success';
                  let tIdx = -1;
                  for (let k = steps.length - 1; k >= 0; k--) {
                    const s = steps[k];
                    if (s.kind === 'tool' && s.tool === te.tool) { tIdx = k; break; }
                  }
                  const toolStep = { kind: 'tool' as const, tool: te.tool, status, result: te.result, files: te.files, sandbox: te.sandbox, input: te.input };
                  if (tIdx >= 0) steps[tIdx] = toolStep;
                  else steps.push(toolStep);
                }
                patchSteps();
                continue;
              }

              // Handle reasoning (thinking process) - 独立于答案渲染成思考块
              if (isReasoning(ev) && ev.content) {
                accumulatedReasoning += ev.content;
                const lastR = steps[steps.length - 1];
                if (lastR && lastR.kind === 'reasoning') {
                  lastR.content += ev.content;
                } else {
                  round += 1;
                  steps.push({ kind: 'reasoning', round, content: ev.content, show: false });
                }
                flushSync(() => {
                  setMessages(prev => prev.map(msg =>
                    msg.messageId === messageId
                      ? { ...msg, reasoning: accumulatedReasoning, showReasoning: true, steps: [...steps] }
                      : msg
                  ));
                });
                continue;
              }

              // Handle Agent API stream format: {"type": "token", "content": "..."}
              if (isToken(ev) && ev.content) {
                accumulatedContent += ev.content;
                const lastA = steps[steps.length - 1];
                if (lastA && lastA.kind === 'answer') {
                  lastA.content += ev.content;
                } else {
                  steps.push({ kind: 'answer', content: ev.content });
                }
                flushSync(() => {
                  setMessages(prev => prev.map(msg =>
                    msg.messageId === messageId
                      ? { ...msg, content: accumulatedContent, steps: [...steps] }
                      : msg
                  ));
                });
                continue;
              }

              // Handle done event — 干净停顿语义 + 运行验收单
              if (isDone(ev)) {
                const d = ev.data;
                const runSummary: RunSummary | undefined = d ? {
                  reason: d.reason === 'max_iterations' ? 'max_iterations' : 'completed',
                  rounds: d.rounds ?? 0,
                  toolsUsed: d.tools_used ?? [],
                  files: (d.files ?? []) as RunSummary['files'],
                } : undefined;
                setMessages(prev => prev.map(msg =>
                  msg.messageId === messageId
                    ? { ...msg, isStreaming: false, ...(runSummary ? { runSummary } : {}) }
                    : msg
                ));
                setLoading(false);
                setOrchestratorStatus('');

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
              if (isErrorEvent(ev) && ev.error) {
                // 如果已经有内容了，说明是后续的错误（如 checkpoint 保存失败），不删除消息
                if (accumulatedContent.trim().length === 0) {
                  toast.error(ev.error);
                  setMessages(prev => prev.filter(msg => msg.messageId !== messageId));
                } else {
                  // 已经有成功内容，只显示 toast 警告，不删除消息
                  console.warn('Stream completed with content, but got trailing error:', ev.error);
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
              if (isComplete(ev)) {
                // 只是标记完成，不改变 UI
                continue;
              }

              // Handle custom citations event (sent before streaming)
              if (isCitations(ev) && ev.citations) {
                sources = ev.citations as typeof sources;
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

              // Legacy / OpenAI 直连格式兜底（非 /execute/stream 协议，不纳入统一 schema）
              const parsed = ev as any;

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

  // 人工审批：批准/拒绝。pending 项 key 为后端下发的 request_id（非 id）。
  // 全部批准后从断点续跑（POST /approvals/{id}/resume），把终答写回流式 assistant 消息。
  const handleApproval = async (action: 'approve' | 'reject') => {
    setApproving(true);
    try {
      // 1) 逐个提交审批（approve/reject）
      for (const p of approvalPending) {
        const rid = (p as any)?.request_id;
        if (!rid) continue;
        const res = await fetch(getApiUrl(`/api/v1/approvals/${rid}/${action}`), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
          },
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          toast.error(data?.detail || `${action === 'approve' ? '批准' : '拒绝'}失败`);
        }
      }

      if (action === 'reject') {
        toast.success('已拒绝');
        setApprovalPending([]);
        setShowApprovalModal(false);
        return;
      }

      // 2) 批准后断点续跑：取同一 thread 的定位信息调 /resume，拿真实终答
      const first = approvalPending[0] as any;
      toast.success('已批准，正在从断点续跑…');
      if (first?.request_id && first?.thread_id && first?.sub_agent_id) {
        const res = await fetch(getApiUrl(`/api/v1/approvals/${first.request_id}/resume`), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
          },
          body: JSON.stringify({
            sub_agent_id: first.sub_agent_id,
            thread_id: first.thread_id,
          }),
        });
        const data = await res.json().catch(() => ({}));
        if (res.ok && data?.content) {
          const targetId = assistantMsgIdRef.current;
          setMessages(prev => prev.map(msg =>
            msg.messageId === targetId
              ? { ...msg, content: data.content, isStreaming: false }
              : msg
          ));
          setLoading(false);
        } else {
          toast.warning(data?.detail || data?.error || '续跑未返回内容，请重新提问');
          setLoading(false);
        }
      } else {
        toast.warning('缺少续跑定位信息（thread_id/sub_agent_id），请重新提问');
        setLoading(false);
      }

      setApprovalPending([]);
      setShowApprovalModal(false);
    } catch (e: any) {
      toast.error(`审批失败：${e?.message || ''}`);
    } finally {
      setApproving(false);
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
          {/* 智能体选择（统一入口：可选广场智能体 / AI 助手） */}
          <div className="relative">
            <button
              onClick={() => setShowAgentSelector(!showAgentSelector)}
              className="ml-2 px-2.5 py-1 rounded-lg text-[10px] font-medium border hover:bg-gray-50 transition-colors flex items-center gap-1.5"
              style={{ borderColor: '#e2e1dd', color: selectedAgentInfo ? '#0a7a3d' : '#9b9b9b' }}
            >
              <Bot className="w-3 h-3" />
              {selectedAgentInfo ? selectedAgentInfo.name : 'AI 助手'}
              {selectedAgentInfo ? (
                <button
                  onClick={(e) => { e.stopPropagation(); setSelectedAgentId(''); setSelectedAgentInfo(null); }}
                  className="text-[9px] ml-0.5 px-1 rounded hover:bg-red-50 hover:text-red-600"
                >✕</button>
              ) : null}
            </button>
            {showAgentSelector && (
              <div className="absolute top-full left-0 mt-1 w-56 bg-white rounded-lg shadow-lg border border-[#e2e1dd] z-50 overflow-hidden">
                <div className="max-h-64 overflow-y-auto py-1">
                  <button
                    onClick={() => { setSelectedAgentId(''); setSelectedAgentInfo(null); setShowAgentSelector(false); }}
                    className={`w-full px-3 py-2 text-left text-xs hover:bg-gray-50 ${!selectedAgentId ? 'bg-[#eeedfe]' : ''}`}
                  >AI 助手（自主决策）</button>
                  {agentOptions.map((a) => (
                    <button
                      key={a.id}
                      onClick={() => { setSelectedAgentId(a.id); setShowAgentSelector(false); }}
                      className={`w-full px-3 py-2 text-left text-xs hover:bg-gray-50 ${selectedAgentId === a.id ? 'bg-[#eeedfe]' : ''}`}
                    >{a.name}</button>
                  ))}
                </div>
              </div>
            )}
          </div>
          {/* 主从编排开关 */}
          <button
            onClick={() => setOrchestrator(!orchestrator)}
            className={`ml-2 px-2.5 py-1 rounded-lg text-[10px] font-medium border transition-colors ${orchestrator ? 'bg-purple-100 text-purple-700' : 'text-[#9b9b9b]'}`}
            style={{ borderColor: '#e2e1dd' }}
            title="主从编排（主Agent + 子Agent）"
          >{orchestrator ? '编排 ON' : '编排 OFF'}</button>
          {/* 编排状态指示 */}
          {orchestratorStatus && (
            <span className="ml-2 px-2 py-0.5 rounded-full text-[10px] font-medium bg-purple-100 text-purple-700">
              {orchestratorStatus}
            </span>
          )}
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
          toolEvents: m.toolEvents,
          steps: m.steps,
          runSummary: m.runSummary,
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
        onStepToggle={(messageId, stepIndex) => {
          setMessages(prev => prev.map(m =>
            m.messageId === messageId && m.steps && m.steps[stepIndex] && m.steps[stepIndex].kind === 'reasoning'
              ? {
                  ...m,
                  steps: m.steps.map((s, si) =>
                    si === stepIndex && s.kind === 'reasoning'
                      ? { ...s, show: s.show === false }
                      : s
                  ),
                }
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

      {/* 人工审批弹窗（HITL）*/}
      <Modal
        open={showApprovalModal}
        onOpenChange={setShowApprovalModal}
        title="需要人工审批"
        description="以下敏感调用需要你的批准后才能执行"
        footer={
          <div className="flex gap-2 justify-end">
            <button
              onClick={() => handleApproval('reject')}
              disabled={approving}
              className="px-3 py-1.5 rounded-lg text-xs border hover:bg-gray-50"
              style={{ borderColor: '#e2e1dd' }}
            >拒绝</button>
            <button
              onClick={() => handleApproval('approve')}
              disabled={approving}
              className="px-3 py-1.5 rounded-lg text-xs text-white"
              style={{ background: '#534ab7' }}
            >{approving ? '处理中…' : '批准'}</button>
          </div>
        }
      >
        <div className="space-y-2 max-h-60 overflow-y-auto">
          {approvalPending.map((p: any, i: number) => (
            <div key={i} className="p-2 rounded-lg text-xs border" style={{ borderColor: '#e8e6e6' }}>
              <div className="font-medium">{p?.tool || p?.name || '工具调用'}</div>
              {p?.risk_level && (
                <span className={`px-1.5 py-0.5 rounded text-[10px] mt-1 inline-block ${
                  p.risk_level === 'high' || p.risk_level === 'critical' ? 'bg-red-100 text-red-700' : 'bg-yellow-100 text-yellow-700'
                }`}>风险：{p.risk_level}</span>
              )}
              <div className="text-[#9b9b9b] mt-1 break-all">{JSON.stringify(p?.args ?? p?.parameters ?? '')}</div>
            </div>
          ))}
          {approvalPending.length === 0 && <div className="text-xs text-[#9b9b9b]">暂无待审批项</div>}
        </div>
      </Modal>
    </div>
  );
}
