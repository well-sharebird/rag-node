/**
 * 文档处理进度列表组件
 * 展示多个文档的实时处理进度
 */
import { useEffect } from 'react';
import { useDocumentProgress, DocumentProgress } from '@/src/hooks/useDocumentProgress';
import { Loader2, CheckCircle2, XCircle, Clock, FileText } from 'lucide-react';
import { cn } from '@/lib/utils';

interface DocumentProgressListProps {
  docIds: string[];
  onAllComplete?: () => void;
}

const STAGE_LABELS: Record<string, string> = {
  pending: '等待处理',
  parsing: '解析文档',
  cleaning: '文本清洗',
  desensitization: '数据脱敏',
  chunking: '分块处理',
  embedding: '向量化',
  validation: '质量验证',
  indexing: '索引构建',
  completed: '处理完成',
  failed: '处理失败',
  processing: '处理中',
};

export function DocumentProgressList({ docIds, onAllComplete }: DocumentProgressListProps) {
  // 为每个文档创建进度追踪
  const progressStates = docIds.map(docId => useDocumentProgress(docId, true));

  // 检查是否所有文档都已完成
  useEffect(() => {
    const allComplete = progressStates.every(state =>
      state.progress?.status === 'completed' || state.progress?.status === 'failed'
    );

    if (allComplete && docIds.length > 0 && onAllComplete) {
      onAllComplete();
    }
  }, [progressStates, docIds.length, onAllComplete]);

  if (docIds.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      {progressStates.map((state, index) => (
        <DocumentProgressItem
          key={docIds[index]}
          progress={state.progress}
          loading={state.loading}
          error={state.error}
        />
      ))}
    </div>
  );
}

interface DocumentProgressItemProps {
  progress: DocumentProgress | null;
  loading: boolean;
  error: string | null;
}

function DocumentProgressItem({ progress, loading, error }: DocumentProgressItemProps) {
  if (loading || !progress) {
    return (
      <div className="flex items-center gap-3 p-3 bg-[var(--gray-50)] rounded-lg">
        <Loader2 className="w-4 h-4 animate-spin text-[var(--primary)]" />
        <span className="text-sm text-[var(--text-secondary)]">加载进度...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center gap-3 p-3 bg-red-50 rounded-lg border border-red-200">
        <XCircle className="w-4 h-4 text-red-500" />
        <span className="text-sm text-red-700">{error}</span>
      </div>
    );
  }

  const isCompleted = progress.status === 'completed';
  const isFailed = progress.status === 'failed';
  const isProcessing = progress.status === 'processing' || progress.status === 'pending';

  return (
    <div className={cn(
      "p-3 rounded-lg border",
      isCompleted && "bg-green-50 border-green-200",
      isFailed && "bg-red-50 border-red-200",
      isProcessing && "bg-[var(--gray-50)] border-[var(--gray-200)]"
    )}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <FileText className={cn(
            "w-4 h-4 shrink-0",
            isCompleted && "text-green-600",
            isFailed && "text-red-600",
            isProcessing && "text-[var(--primary)]"
          )} />
          <span className="text-sm font-medium text-[var(--text-primary)] truncate">
            文档 {progress.doc_id.slice(0, 8)}...
          </span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {isCompleted && <CheckCircle2 className="w-4 h-4 text-green-600" />}
          {isFailed && <XCircle className="w-4 h-4 text-red-600" />}
          {isProcessing && <Clock className="w-4 h-4 text-[var(--primary)]" />}
          <span className={cn(
            "text-xs font-medium",
            isCompleted && "text-green-700",
            isFailed && "text-red-700",
            isProcessing && "text-[var(--primary)]"
          )}>
            {STAGE_LABELS[progress.current_stage || progress.status] || progress.status}
          </span>
        </div>
      </div>

      {/* 进度条 */}
      <div className="relative h-2 bg-[var(--gray-200)] rounded-full overflow-hidden">
        <div
          className={cn(
            "absolute left-0 top-0 h-full transition-all duration-300",
            isCompleted && "bg-green-500",
            isFailed && "bg-red-500",
            isProcessing && "bg-[var(--primary)]"
          )}
          style={{ width: `${progress.progress}%` }}
        />
      </div>

      <div className="flex items-center justify-between mt-2">
        <span className="text-xs text-[var(--text-tertiary)]">
          {progress.progress}%
        </span>
        {isFailed && progress.error_message && (
          <span className="text-xs text-red-600 truncate max-w-[200px]" title={progress.error_message}>
            {progress.error_message}
          </span>
        )}
        {isCompleted && progress.chunk_count && (
          <span className="text-xs text-green-600">
            分块数：{progress.chunk_count}
          </span>
        )}
      </div>
    </div>
  );
}
