import { useRef, useEffect, useState } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { Bot, User, Loader2, Brain, ChevronDown, ChevronRight, BookOpen, Sparkles, Hammer, FileText } from 'lucide-react';
import { cn } from '@/lib/utils';
import { MarkdownRenderer } from '@/src/components/MarkdownRenderer';

export interface ToolCallFile {
  filename: string;
  relative_path: string;
}

export interface ToolCall {
  tool: string;
  status: 'running' | 'success' | 'error' | 'denied' | 'limited' | 'circuit' | 'blocked';
  input?: Record<string, unknown>;
  result?: string;
  files?: ToolCallFile[];
  sandbox?: string;
}

export type ToolStatus = ToolCall['status'];

/** 线性时间线步骤：思考/工具/总结，按执行时序排列 */
export type Step =
  | { kind: 'reasoning'; round: number; content: string; show?: boolean }
  | { kind: 'tool'; tool: string; status: ToolStatus; input?: Record<string, unknown>; result?: string; files?: ToolCallFile[]; sandbox?: string }
  | { kind: 'answer'; content: string };

/** 运行验收单：干净停顿语义 + 本次运行产物汇总（来自流末 done 事件） */
export interface RunSummary {
  reason: 'completed' | 'max_iterations' | 'interrupted';
  rounds: number;
  toolsUsed: string[];
  files: ToolCallFile[];
}

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
  toolEvents?: ToolCall[];
  steps?: Step[];
  runSummary?: RunSummary;
  timestamp?: string;
  isStreaming?: boolean;
}

const TOOL_STATUS_LABEL: Record<ToolCall['status'], string> = {
  running: '运行中',
  success: '完成',
  error: '失败',
  denied: '已拒绝',
  limited: '限流',
  circuit: '熔断',
  blocked: '安全拦截',
};

/** 状态圆点颜色：成功绿、运行紫脉冲、错误/拒绝/拦截红、限流琥珀、熔断橙 */
const TOOL_STATUS_COLOR: Record<ToolCall['status'], string> = {
  running: '#9b6bff',
  success: '#22c55e',
  error: '#ef4444',
  denied: '#ef4444',
  blocked: '#ef4444',
  limited: '#f59e0b',
  circuit: '#f97316',
};

function ToolStepCard({ tool, status, input, result, files, sandbox }: {
  tool: string;
  status: ToolStatus;
  input?: Record<string, unknown>;
  result?: string;
  files?: ToolCallFile[];
  sandbox?: string;
}) {
  return (
    <div
      className="rounded-lg px-2.5 py-2 text-[11px] mb-1.5"
      style={{ background: '#f3f4f6', border: '0.5px solid #e5e7eb' }}
    >
      <div className="flex items-center gap-2">
        {status === 'running' ? (
          <span className="inline-block w-2 h-2 rounded-full animate-pulse" style={{ background: TOOL_STATUS_COLOR.running }} />
        ) : (
          <span className="inline-block w-2 h-2 rounded-full" style={{ background: TOOL_STATUS_COLOR[status] || '#ef4444' }} />
        )}
        <span className="font-medium" style={{ color: '#374151' }}>{tool}</span>
        <span className="text-[10px]" style={{ color: '#9ca3af' }}>
          {TOOL_STATUS_LABEL[status]} {sandbox ? `· ${sandbox}` : ''}
        </span>
      </div>

      {status === 'running' && (
        <div className="mt-1 flex items-center gap-1.5 text-[10px]" style={{ color: '#9b6bff' }}>
          <Sparkles className="w-3 h-3" />
          <span>执行中…</span>
        </div>
      )}

      {result !== undefined && (
        <pre
          className="mt-1.5 rounded-md px-2 py-1.5 text-[10px] text-left overflow-auto max-h-24 whitespace-pre-wrap break-words"
          style={{ background: '#fff', border: '0.5px solid #e5e7eb', color: '#374151' }}
        >
          {result.length > 800 ? `${result.slice(0, 800)}\n…(已截断)` : result}
        </pre>
      )}

      {files && files.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {files.map(f => (
            <span
              key={f.relative_path}
              className="inline-flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] rounded"
              style={{ background: '#eeedfe', color: '#534ab7', border: '0.5px solid #e5e7eb' }}
              title={`工作空间 ${f.relative_path}`}
            >
              <FileText className="w-2.5 h-2.5" />
              {f.filename}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function ThinkingBlock({ round, rounds, content, show, onToggle }: {
  round: number;
  rounds: number;
  content: string;
  show?: boolean;
  onToggle?: () => void;
}) {
  // 直接使用 show prop，移除内部状态（避免与外部不同步）
  // 默认展开（show 为 undefined 或 true 时都展开）
  const isExpanded = show !== false;
  
  const handleToggle = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onToggle?.();
  };
  
  return (
    <div className="mb-2.5 rounded-lg border overflow-hidden" style={{ borderColor: '#e5e7eb', background: '#f9fafb' }}>
      <button
        onClick={handleToggle}
        className="w-full flex items-center gap-2 px-3 py-2 text-xs font-medium hover:bg-gray-50 transition-colors"
        style={{ color: '#6b7280' }}
        type="button"
      >
        <Brain className="w-3.5 h-3.5 flex-shrink-0" style={{ color: '#9b6bff' }} />
        <span>思考过程</span>
        {rounds > 1 && (
          <span className="text-[10px] px-1.5 py-0.5 rounded-full flex-shrink-0" style={{ background: '#eeedfe', color: '#534ab7' }}>
            第 {round} 轮
          </span>
        )}
        {isExpanded ? (
          <ChevronDown className="w-3 h-3 ml-auto flex-shrink-0" />
        ) : (
          <ChevronRight className="w-3 h-3 ml-auto flex-shrink-0" />
        )}
      </button>
      {isExpanded && (
        <div
          className="px-3 pb-3 text-[12px] leading-relaxed"
          style={{
            color: '#4b5563',
            whiteSpace: 'pre-wrap',
          }}
        >
          {content}
        </div>
      )}
    </div>
  );
}

function ToolCallChain({ tools }: { tools: ToolCall[] }) {
  return (
    <div className="mt-2 space-y-1.5">
      {tools.map((tc, idx) => (
        <ToolStepCard
          key={`${tc.tool}_${idx}`}
          tool={tc.tool}
          status={tc.status}
          input={tc.input}
          result={tc.result}
          files={tc.files}
          sandbox={tc.sandbox}
        />
      ))}
    </div>
  );
}

const RUN_REASON_META: Record<RunSummary['reason'], { label: string; color: string; bg: string }> = {
  completed: { label: '任务完成', color: '#16a34a', bg: '#f0fdf4' },
  max_iterations: { label: '已达最大执行轮次，自动停止（可能未完成任务）', color: '#b45309', bg: '#fffbeb' },
  interrupted: { label: '已中断', color: '#6b7280', bg: '#f3f4f6' },
};

/** 运行验收单：干净停顿语义 + 本次运行的工具/轮数/产物文件汇总 */
function RunSummaryCard({ summary }: { summary: RunSummary }) {
  const meta = RUN_REASON_META[summary.reason] || RUN_REASON_META.interrupted;
  return (
    <div
      className="mt-3 rounded-lg px-3 py-2.5 text-[11px]"
      style={{ background: meta.bg, border: `1px solid ${meta.color}40` }}
    >
      <div className="flex items-center gap-2 mb-1.5">
        <span className="inline-block w-2 h-2 rounded-full" style={{ background: meta.color }} />
        <span className="font-medium" style={{ color: meta.color }}>{meta.label}</span>
      </div>
      <div className="flex items-center gap-3 text-[10px]" style={{ color: '#6b7280' }}>
        <span>共 {summary.rounds ?? 0} 轮</span>
        {summary.toolsUsed && summary.toolsUsed.length > 0 && (
          <>
            <span>·</span>
            <span>使用 {summary.toolsUsed.length} 个工具</span>
          </>
        )}
      </div>
      {summary.toolsUsed && summary.toolsUsed.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {summary.toolsUsed.map(t => (
            <span
              key={t}
              className="inline-flex items-center rounded px-2 py-1 text-[10px] font-medium"
              style={{ background: '#fff', color: '#534ab7', border: '0.5px solid #e5e7eb' }}
            >
              <Hammer className="w-2.5 h-2.5 mr-1" />
              {t}
            </span>
          ))}
        </div>
      )}
      {summary.files && summary.files.length > 0 && (
        <div className="mt-2 pt-2 border-t" style={{ borderColor: `${meta.color}30` }}>
          <div className="text-[10px] font-medium mb-1.5" style={{ color: meta.color }}>产出文件</div>
          <div className="flex flex-wrap gap-1.5">
            {summary.files.map(f => (
              <span
                key={f.relative_path}
                className="inline-flex items-center gap-1 rounded px-2 py-1 text-[10px]"
                style={{ background: '#fff', color: '#534ab7', border: '0.5px solid #e5e7eb' }}
                title={`工作空间 ${f.relative_path}`}
              >
                <FileText className="w-2.5 h-2.5" />
                {f.filename}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

interface ChatMessageListProps {
  messages: ChatMessage[];
  loading?: boolean;
  showReasoningToggle?: boolean;
  onReasoningToggle?: (messageId: string) => void;
  onStepToggle?: (messageId: string, stepIndex: number) => void;
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
  onStepToggle,
  onSourceClick,
  emptyState,
  className,
}: ChatMessageListProps) {
  const { t } = useI18n();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const prevMessagesLengthRef = useRef(0);

  // Auto-scroll to bottom - only when new messages are added
  useEffect(() => {
    // 只在消息数量增加时自动滚动（避免展开思考过程时滚动）
    if (messages.length > prevMessagesLengthRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
    prevMessagesLengthRef.current = messages.length;
  }, [messages.length]);

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
                {/* 线性时间线（首选）：思考 → 执行 → … → 总结，按事件到达顺序排列 */}
                {msg.role === 'assistant' && msg.steps && msg.steps.length > 0 ? (
                  <>
                    {msg.steps.map((s, si) => {
                      if (s.kind === 'reasoning') {
                        return (
                          <ThinkingBlock
                            key={si}
                            round={s.round}
                            rounds={msg.steps!.filter(x => x.kind === 'reasoning').length}
                            content={s.content}
                            show={s.show}
                            onToggle={() => onStepToggle?.(msg.id || `msg_${i}`, si)}
                          />
                        );
                      }
                      if (s.kind === 'tool') {
                        return (
                          <ToolStepCard key={si} tool={s.tool} status={s.status} input={s.input} result={s.result} files={s.files} sandbox={s.sandbox} />
                        );
                      }
                      return <MarkdownRenderer key={si} content={s.content} />;
                    })}
                    {msg.runSummary && <RunSummaryCard summary={msg.runSummary} />}
                  </>
                ) : (
                  <>
                    {/* 兼容：无 steps 的聚合渲染（历史消息/直接回答） */}
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
                    {msg.role === 'assistant' && msg.toolEvents && msg.toolEvents.length > 0 && (
                      <ToolCallChain tools={msg.toolEvents} />
                    )}
                    <MarkdownRenderer content={msg.content} />
                  </>
                )}
                {/* 来源引用（线性与聚合两种渲染共用） */}
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
              {/* Loading indicator - only show during initial retrieval/thinking phase */}
              {msg.isStreaming && !msg.content && !msg.steps?.some(s => s.kind === 'answer') && (
                <div className="flex items-center gap-1.5 mt-1.5 ml-0.5">
                  <Loader2 className="w-2.5 h-2.5 animate-spin" style={{ color: '#9b6bff' }} />
                  <span className="text-[11px] italic" style={{ color: '#9b6bff' }}>思考中...</span>
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
        {/* 移除重复的 loading 显示 - 只用 msg.isStreaming 即可 */}
        <div ref={messagesEndRef} />
      </div>
    </div>
  );
}
