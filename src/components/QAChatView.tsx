import { useState, useRef, useEffect } from 'react';
import { useAppContext } from '@/lib/app-context';
import { useAuth } from '@/src/lib/auth-context';
import { useI18n } from '@/src/lib/i18n';
import { toast } from 'sonner';
import { Send, Bot, User, BookOpen, Loader2, ThumbsUp, ThumbsDown, X, Brain, ChevronDown, ChevronRight, AtSign, Check } from 'lucide-react';
import { SourcePanel } from './SourcePanel';
import { cn } from '@/lib/utils';

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

  // Close KB selector on Escape
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setShowKbSelector(false);
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, []);

  const handleSend = async () => {
    if (!input.trim() || selectedKbs.length === 0) {
      toast.error(language === 'zh' ? '请选择知识库' : 'Please select a knowledge base');
      return;
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
      const res = await fetch('/api/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          query,
          kb_ids: selectedKbs,
          top_k: 5,
          enable_rerank: true,
          enable_expansion: true,
          stream: true,
        }),
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

            try {
              const parsed = JSON.parse(data);

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

              // Handle OpenAI-style chat.completion.chunk
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

                // Handle reasoning_content (thinking process)
                if (delta?.reasoning_content) {
                  accumulatedReasoning += delta.reasoning_content;
                  setMessages(prev => prev.map(msg =>
                    msg.messageId === messageId
                      ? { ...msg, reasoning: accumulatedReasoning, showReasoning: true }
                      : msg
                  ));
                }

                // Handle content
                if (delta?.content) {
                  accumulatedContent += delta.content;
                  setMessages(prev => prev.map(msg =>
                    msg.messageId === messageId
                      ? { ...msg, content: accumulatedContent }
                      : msg
                  ));
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
      const res = await fetch('/api/v1/feedback', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          session_id: `session_${Date.now()}`,
          message_id: messageId,
          feedback_type: feedbackType,
          reason_category: reason,
        }),
      });

      if (!res.ok) throw new Error('Feedback failed');

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

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      {/* Header */}
      <header className="h-[52px] px-5 bg-white flex items-center justify-between shrink-0" style={{ borderBottom: '0.5px solid #e2e1dd' }}>
        <div className="flex items-baseline gap-3">
          <h1 className="text-[15px] font-medium text-[#1a1a1a]">{t('qa.title')}</h1>
          <span className="text-[11px] text-[#9b9b9b] hidden sm:inline">{t('qa.desc')}</span>
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
      <div className="flex-1 overflow-y-auto p-5 bg-[#f7f7f5]">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <div className="w-12 h-12 rounded-full flex items-center justify-center" style={{ background: '#eeedfe' }}>
              <Bot className="w-6 h-6" style={{ color: '#534ab7' }} />
            </div>
            <p className="font-medium text-[#6b6b6b] text-sm">{t('qa.empty.title')}</p>
            <p className="text-[13px] text-[#9b9b9b]">{t('qa.empty.desc')}</p>
          </div>
        ) : (
          <div className="max-w-3xl mx-auto space-y-4">
            {messages.map((msg, i) => (
              <div key={i} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`}>
                {msg.role === 'assistant' && (
                  <div className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-1" style={{ background: '#eeedfe' }}>
                    <Bot className="w-3.5 h-3.5" style={{ color: '#534ab7' }} />
                  </div>
                )}
                <div className="max-w-[80%]">
                  <div
                    className="rounded-xl px-4 py-2.5 text-[13px] leading-relaxed"
                    style={
                      msg.role === 'user'
                        ? { background: '#534ab7', color: '#fff' }
                        : { background: '#fff', border: '0.5px solid #e2e1dd' }
                    }
                  >
                    {/* Reasoning / Thinking Process Toggle */}
                    {msg.role === 'assistant' && msg.reasoning && (
                      <div className="mb-2">
                        <button
                          onClick={() => {
                            setMessages(prev => prev.map(m =>
                              m.messageId === msg.messageId
                                ? { ...m, showReasoning: !m.showReasoning }
                                : m
                            ));
                          }}
                          className="flex items-center gap-1.5 text-[11px] font-medium mb-1.5 hover:opacity-70 transition-opacity"
                          style={{ color: '#9b6bff' }}
                        >
                          <Brain className="w-3.5 h-3.5" />
                          {t('qa.reasoning')}
                          {msg.showReasoning !== false ? (
                            <ChevronDown className="w-3 h-3" />
                          ) : (
                            <ChevronRight className="w-3 h-3" />
                          )}
                        </button>
                        {msg.showReasoning !== false && (
                          <div
                            className="rounded-lg px-3 py-2 text-[12px] leading-relaxed italic overflow-auto max-h-48"
                            style={{
                              background: '#f8f7ff',
                              borderLeft: '2px solid #9b6bff',
                              color: '#6b5b8a',
                              whiteSpace: 'pre-wrap',
                            }}
                          >
                            {msg.reasoning}
                          </div>
                        )}
                      </div>
                    )}
                    {/* Answer content */}
                    {msg.content}
                    {msg.sources && msg.sources.length > 0 && (
                      <div className="mt-2 pt-2 flex flex-wrap gap-1.5" style={{ borderTop: '0.5px solid #e2e1dd' }}>
                        {msg.sources.map((s, j) => (
                          <button
                            key={j}
                            onClick={() => {
                              setSelectedCitation(s);
                              setSourcePanelOpen(true);
                            }}
                            className="text-[11px] px-1.5 py-0.5 rounded cursor-pointer hover:opacity-80 transition-opacity"
                            style={{ background: '#eeedfe', color: '#534ab7' }}
                            title={t('qa.viewSource')}
                          >
                            [{s.index}] {s.doc_name}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                  {/* Feedback buttons for assistant messages */}
                  {msg.role === 'assistant' && !msg.isStreaming && (
                    <div className="flex items-center gap-2 mt-2 ml-1">
                      {showFeedback === msg.messageId ? (
                        <>
                          <button
                            onClick={() => handleFeedback(msg.messageId!, 'thumbs_up')}
                            className="text-[11px] px-2 py-1 rounded hover:bg-green-50 text-green-600 flex items-center gap-1"
                          >
                            <ThumbsUp className="w-3 h-3" />
                            {t('feedback.helpful')}
                          </button>
                          <button
                            onClick={() => handleFeedback(msg.messageId!, 'thumbs_down', 'other')}
                            className="text-[11px] px-2 py-1 rounded hover:bg-red-50 text-red-600 flex items-center gap-1"
                          >
                            <ThumbsDown className="w-3 h-3" />
                            {t('feedback.notHelpful')}
                          </button>
                          <button
                            onClick={() => setShowFeedback(null)}
                            className="text-[11px] px-2 py-1 rounded hover:bg-gray-100 text-gray-500"
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </>
                      ) : (
                        <span className="text-[11px] text-gray-400">{t('qa.feedbackPrompt')}</span>
                      )}
                    </div>
                  )}
                </div>
                {msg.role === 'user' && (
                  <div className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-1" style={{ background: '#f1f0ed' }}>
                    <User className="w-3.5 h-3.5 text-[#6b6b6b]" />
                  </div>
                )}
              </div>
            ))}
            {loading && (
              <div className="flex items-center gap-2 text-[13px] text-[#9b9b9b] ml-10">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                {t('qa.loading')}
                <button
                  onClick={handleStop}
                  className="ml-2 text-[11px] px-2 py-0.5 rounded border hover:bg-gray-50"
                  style={{ borderColor: '#e2e1dd' }}
                >
                  {t('qa.stop')}
                </button>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

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
                disabled={selectedKbs.length === 0}
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
              <div className="bg-white rounded-xl shadow-2xl border border-[#e5e5e5] overflow-hidden">
                <div className="px-3 py-2 border-b border-[#e5e5e5] bg-[#f9f9f9] flex items-center justify-between">
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
                            idx === kbSelectorIndex ? "bg-[#f5f5f5]" : "",
                            isSelected ? "bg-[#eeedfe]" : "hover:bg-[#f9f9f9]"
                          )}
                        >
                          <BookOpen className={cn(
                            "w-4 h-4",
                            isSelected ? "text-[#534ab7]" : "text-[#999]"
                          )} />
                          <span className={cn(
                            "flex-1 text-left truncate",
                            isSelected ? "text-[#534ab7] font-medium" : "text-[#1a1a1a]"
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
                <div className="px-3 py-2 border-t border-[#e5e5e5] bg-[#f9f9f9]">
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
