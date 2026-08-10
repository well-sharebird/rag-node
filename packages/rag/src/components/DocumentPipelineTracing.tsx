/**
 * 文档处理流水线追踪组件
 * 展示文档处理的完整流程和各阶段详情
 */
import { useEffect, useState } from 'react';
import { PipelineStageCard } from './PipelineStageCard';
import { Activity, RefreshCw, FileText, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { fetchApi } from '@/lib/api-client';

export interface PipelineStage {
  stage: string;
  label: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  duration_ms: number | null;
  input_summary: {
    preview: string;
    count?: number | null;
    size?: number | null;
  } | null;
  output_summary: {
    preview: string;
    count?: number | null;
    size?: number | null;
  } | null;
  error: {
    message: string;
    details: Record<string, unknown>;
  } | null;
  span_id: string;
}

export interface DocumentPipelineTracingProps {
  docId: string;
  onClose?: () => void;
}

export function DocumentPipelineTracing({ docId, onClose }: DocumentPipelineTracingProps) {
  const [loading, setLoading] = useState(true);
  const [stages, setStages] = useState<PipelineStage[]>([]);
  const [totalDuration, setTotalDuration] = useState(0);
  const [status, setStatus] = useState<string>('');
  const [docName, setDocName] = useState<string>('');

  const loadPipeline = async () => {
    setLoading(true);
    try {
      const data = await fetchApi(`/api/v1/documents/${docId}/pipeline`);
      setStages(data.stages || []);
      setTotalDuration(data.total_duration_ms || 0);
      setStatus(data.status || '');
    } catch (error) {
      console.error('Failed to load pipeline:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadDocumentName = async () => {
    try {
      const data = await fetchApi(`/api/v1/documents/${docId}`);
      setDocName(data.name || '未知文档');
    } catch (error) {
      console.error('Failed to load document:', error);
    }
  };

  useEffect(() => {
    loadPipeline();
    loadDocumentName();
  }, [docId]);

  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${(ms / 60000).toFixed(1)}m`;
  };

  const getStatusColor = () => {
    if (status === 'completed') return 'text-emerald-600';
    if (status === 'failed') return 'text-red-600';
    if (status === 'running') return 'text-blue-600';
    return 'text-gray-600';
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-gray-50">
      {/* Header */}
      <header className="h-[60px] px-6 bg-white flex items-center justify-between shrink-0 border-b border-gray-200">
        <div className="flex items-center gap-3">
          <Activity className="w-5 h-5 text-blue-600" />
          <div>
            <h1 className="text-base font-medium text-gray-900">文档处理流水线</h1>
            <div className="flex items-center gap-2 text-xs text-gray-500">
              <FileText className="w-3 h-3" />
              <span className="truncate max-w-[300px]">{docName}</span>
              {status && (
                <span className={cn("font-medium", getStatusColor())}>
                  · {status === 'completed' ? '处理完成' : status === 'failed' ? '处理失败' : '处理中'}
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadPipeline}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
            title="刷新"
          >
            <RefreshCw className="w-4 h-4 text-gray-600" />
          </button>
          {onClose && (
            <button
              onClick={onClose}
              className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
              title="关闭"
            >
              <X className="w-4 h-4 text-gray-600" />
            </button>
          )}
        </div>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="text-center">
              <RefreshCw className="w-8 h-8 animate-spin text-blue-600 mx-auto mb-3" />
              <p className="text-sm text-gray-500">加载处理流程...</p>
            </div>
          </div>
        ) : stages.length === 0 ? (
          <div className="flex items-center justify-center py-12">
            <div className="text-center">
              <Activity className="w-12 h-12 text-gray-300 mx-auto mb-3" />
              <p className="text-sm text-gray-500">暂无处理流程数据</p>
              <p className="text-xs text-gray-400 mt-1">文档可能还未开始处理或没有追踪数据</p>
            </div>
          </div>
        ) : (
          <div className="space-y-4 max-w-4xl mx-auto">
            {/* Summary */}
            <div className="bg-white border border-gray-200 rounded-lg p-4">
              <div className="flex items-center justify-between">
                <div className="text-sm text-gray-600">
                  共 <span className="font-medium text-gray-900">{stages.length}</span> 个处理阶段
                </div>
                <div className="text-sm text-gray-600">
                  总耗时：<span className="font-medium text-gray-900">{formatDuration(totalDuration)}</span>
                </div>
              </div>
            </div>

            {/* Stages */}
            {stages.map((stage, index) => (
              <div key={stage.span_id || index}>
                <PipelineStageCard
                  stage={stage.stage}
                  label={stage.label}
                  status={stage.status}
                  durationMs={stage.duration_ms}
                  inputSummary={stage.input_summary}
                  outputSummary={stage.output_summary}
                  error={stage.error}
                  spanId={stage.span_id}
                />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
