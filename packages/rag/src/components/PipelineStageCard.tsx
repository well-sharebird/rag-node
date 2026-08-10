/**
 * 流水线处理阶段卡片组件
 * 展示单个处理阶段的输入输出数据对比
 */
import { useState } from 'react';
import { cn } from '@/lib/utils';
import {
  CheckCircle, XCircle, AlertCircle, Clock,
  ChevronDown, ChevronRight, ArrowDown,
  FileText, Table, Image, Code
} from 'lucide-react';
import { DataPreviewPanel } from '@/packages/core/src/components/DataPreviewPanel';

export interface PipelineStageCardProps {
  stage: string;
  label: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  durationMs?: number | null;
  inputSummary?: {
    preview: string;
    count?: number | null;
    size?: number | null;
  } | null;
  outputSummary?: {
    preview: string;
    count?: number | null;
    size?: number | null;
  } | null;
  error?: {
    message: string;
    details: Record<string, unknown>;
  } | null;
  spanId?: string;
}

const STAGE_ICONS: Record<string, React.ElementType> = {
  parsing: FileText,
  cleaning: FileText,
  desensitization: FileText,
  chunking: Table,
  embedding: Code,
  indexing: Table,
};

const STAGE_LABELS: Record<string, string> = {
  parsing: '解析',
  cleaning: '清洗',
  desensitization: '脱敏',
  chunking: '分块',
  embedding: '向量化',
  indexing: '索引',
};

export function PipelineStageCard({
  stage,
  label,
  status,
  durationMs,
  inputSummary,
  outputSummary,
  error,
  spanId,
}: PipelineStageCardProps) {
  const [expanded, setExpanded] = useState(false);

  const getStatusIcon = () => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="w-5 h-5 text-emerald-500" />;
      case 'failed':
        return <XCircle className="w-5 h-5 text-red-500" />;
      case 'running':
        return <Clock className="w-5 h-5 text-blue-500 animate-pulse" />;
      default:
        return <AlertCircle className="w-5 h-5 text-gray-400" />;
    }
  };

  const getStatusText = () => {
    switch (status) {
      case 'completed':
        return '完成';
      case 'failed':
        return '失败';
      case 'running':
        return '进行中';
      default:
        return '等待中';
    }
  };

  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${(ms / 60000).toFixed(1)}m`;
  };

  const Icon = STAGE_ICONS[stage] || FileText;
  const displayLabel = STAGE_LABELS[stage] || label;

  return (
    <div className="border border-gray-200 rounded-lg bg-white overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 bg-gray-50 cursor-pointer hover:bg-gray-100 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3">
          {expanded ? (
            <ChevronDown className="w-4 h-4 text-gray-500" />
          ) : (
            <ChevronRight className="w-4 h-4 text-gray-500" />
          )}

          <div className="flex items-center gap-3">
            <Icon className="w-5 h-5 text-gray-600" />
            <span className="font-medium text-gray-800">
              [{displayLabel}]
            </span>
            {getStatusIcon()}
            <span className={cn(
              "text-sm",
              status === 'completed' ? 'text-emerald-600' :
              status === 'failed' ? 'text-red-600' :
              status === 'running' ? 'text-blue-600' :
              'text-gray-500'
            )}>
              {getStatusText()}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-4 text-sm text-gray-500">
          {durationMs && (
            <span>耗时：{formatDuration(durationMs)}</span>
          )}
          {inputSummary?.count !== undefined && inputSummary?.count !== null && (
            <span>输入：{inputSummary.count}</span>
          )}
          {outputSummary?.count !== undefined && outputSummary?.count !== null && (
            <span>输出：{outputSummary.count}</span>
          )}
        </div>
      </div>

      {/* Content */}
      {expanded && (
        <div className="p-4 space-y-4">
          {/* Input */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <ArrowDown className="w-4 h-4 text-gray-400 rotate-90" />
              <span className="text-sm font-medium text-gray-700">输入数据</span>
              {inputSummary?.count !== undefined && inputSummary?.count !== null && (
                <span className="text-xs text-gray-500">({inputSummary.count} 项)</span>
              )}
            </div>
            <DataPreviewPanel
              data={inputSummary?.preview || {}}
              title="输入预览"
              maxHeight="200px"
            />
          </div>

          {/* Output */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <ArrowDown className="w-4 h-4 text-gray-400 rotate-90" />
              <span className="text-sm font-medium text-gray-700">输出数据</span>
              {outputSummary?.count !== undefined && outputSummary?.count !== null && (
                <span className="text-xs text-gray-500">({outputSummary.count} 项)</span>
              )}
            </div>
            <DataPreviewPanel
              data={outputSummary?.preview || {}}
              title="输出预览"
              maxHeight="200px"
            />
          </div>

          {/* Error */}
          {error && (
            <div className="border border-red-200 rounded-lg bg-red-50 p-4">
              <div className="flex items-center gap-2 mb-2">
                <XCircle className="w-4 h-4 text-red-600" />
                <span className="text-sm font-medium text-red-700">错误信息</span>
              </div>
              <div className="text-sm text-red-600">{error.message}</div>
              {Object.keys(error.details).length > 0 && (
                <DataPreviewPanel
                  data={error.details}
                  title="错误详情"
                  maxHeight="150px"
                  className="mt-2"
                />
              )}
            </div>
          )}

          {/* Span ID */}
          {spanId && (
            <div className="text-xs text-gray-400 text-center">
              Span ID: {spanId}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
