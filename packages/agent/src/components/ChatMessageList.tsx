import { useRef, useEffect } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { Bot, User, Loader2, Brain, ChevronDown, ChevronRight, BookOpen } from 'lucide-react';
import { cn } from '@/lib/utils';
import { MarkdownRenderer } from '@/src/components/MarkdownRenderer';

export interface ChatMessage {
  id?: string;
  role: 'user' | 'assistant';
  content: string;
  reasoning?: string;
  showReasoning?: boolean;
  sources?: Array<{
    index: number;
    doc_name: string;
    doc_id?: string;
    chunk_id?: string;
  }>;
  timestamp?: string;
  isStreaming?: boolean;
}

interface ChatMessageListProps {
  messages: ChatMessage[];
  loading?: boolean;
  showReasoningToggle?: boolean;
  onReasoningToggle?: (messageId: string) => void;
  onSourceClick?: (sources: ChatMessage['sources']) => void;
  emptyState?: {
    icon?: React.ReactNode;
    title: string;
    description?: string;
  };
  className?: string;
}

export function ChatMessageList({
  messages,
  loading = false,
  showReasoningToggle = true,
  onReasoningToggle,
  onSourceClick,
  emptyState,
  className,
}: ChatMessageListProps) {
  const { t } = useI18n();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className={cn('flex-1 flex flex-col items-center justify-center text-center p-10', className)}>
        {emptyState?.icon || (
          <div className="w-12 h-12 rounded-full flex items-center justify-center mb-4" style={{ background: '#eeedfe' }}>
            <Bot className="w-6 h-6" style={{ color: '#534ab7' }} />
          </div>
        )}
        <p className="font-medium text-[var(--text-secondary)] text-sm">{emptyState?.title || t('qa.empty.title')}</p>
        {emptyState?.description && (
          <p className="text-[13px] text-[#9b9b9b] text-center max-w-sm mt-2">
            {emptyState.description}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className={cn('flex-1 overflow-y-auto p-5 bg-white', className)}>
      <div className="max-w-3xl mx-auto space-y-4">
        {messages.map((msg, i) => (
          <div key={msg.id || `msg_${i}`} className={`flex ${msg.role === 'user' ? 'justify-end' : ''}`}>
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
                {msg.role === 'assistant' && msg.reasoning && showReasoningToggle && (
                  <div className="mb-2">
                    <button
                      onClick={() => onReasoningToggle?.(msg.id || `msg_${i}`)}
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
                <MarkdownRenderer content={msg.content} />
                {msg.sources && msg.sources.length > 0 && (
                  <div className="mt-2 pt-2 flex flex-wrap gap-1.5" style={{ borderTop: '0.5px solid #e2e1dd' }}>
                    {msg.sources.map((s, j) => (
                      <button
                        key={j}
                        onClick={() => onSourceClick?.(msg.sources)}
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
              {/* Loading indicator for streaming messages */}
              {msg.isStreaming && (
                <div className="flex items-center gap-2 mt-2 ml-1">
                  <Loader2 className="w-3 h-3 animate-spin text-[#9b9b9b]" />
                  <span className="text-[11px] text-[#9b9b9b]">{t('qa.loading')}</span>
                </div>
              )}
            </div>
            {msg.role === 'user' && (
              <div className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-1" style={{ background: '#f1f0ed' }}>
                <User className="w-3.5 h-3.5 text-[var(--text-secondary)]" />
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div className="flex items-center gap-2 text-[13px] text-[#9b9b9b] ml-10">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            {t('qa.loading')}
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>
    </div>
  );
}
