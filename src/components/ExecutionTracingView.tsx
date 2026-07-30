/**
 * 执行追踪查看组件
 * 显示文档处理和 Agent 执行的追踪详情
 */
import { useEffect, useState } from 'react';
import { useI18n } from '@/src/lib/i18n';
import {
  listTraces,
  getTraceTree,
  getTraceStats,
  getTraceDurationBreakdown,
  TraceListItem,
  TraceTree,
  TraceDurationBreakdown,
  TraceSpan
} from '@/src/lib/api/tracing';
import { Card, CardHeader, CardBody, CardTitle } from '@/src/components/enterprise';
import { Activity, Clock, CheckCircle, XCircle, AlertCircle, ChevronRight, ChevronDown, RefreshCw } from 'lucide-react';

type ExecutionType = 'all' | 'document_pipeline' | 'agent_execution';

export function ExecutionTracingView() {
  const { t } = useI18n();
  const [traces, setTraces] = useState<TraceListItem[]>([]);
  const [selectedTrace, setSelectedTrace] = useState<TraceTree | null>(null);
  const [selectedType, setSelectedType] = useState<ExecutionType>('all');
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [nextSearchAfter, setNextSearchAfter] = useState<unknown[] | null>(null);
  const [durationBreakdown, setDurationBreakdown] = useState<TraceDurationBreakdown[]>([]);
  const [stats, setStats] = useState<{ span_count: number; total_duration: number; final_status: string } | null>(null);

  const getTypeLabel = (type: string) => {
    if (type === 'document_pipeline') return t('execution-tracing.documentPipeline');
    if (type === 'agent_execution') return t('execution-tracing.agentExecution');
    return type;
  };

  const getStatusLabel = (status: string) => {
    if (status === 'success') return t('execution-tracing.success');
    if (status === 'failed') return t('execution-tracing.failed');
    if (status === 'running') return t('execution-tracing.running');
    return status;
  };

  // 加载追踪列表
  const loadTraces = async (append = false) => {
    setLoading(true);
    try {
      const request: { execution_type?: string; search_after?: unknown[]; size: number } = {
        size: 20,
      };

      if (selectedType !== 'all') {
        request.execution_type = selectedType;
      }

      if (append && nextSearchAfter) {
        request.search_after = nextSearchAfter;
      }

      const result = await listTraces(request);

      if (append) {
        setTraces(prev => [...prev, ...result.traces]);
      } else {
        setTraces(result.traces);
      }

      setHasMore(result.has_more);
      setNextSearchAfter(result.next_search_after);
    } catch (error) {
      console.error('Failed to load traces:', error);
    } finally {
      setLoading(false);
    }
  };

  // 加载追踪详情
  const loadTraceDetail = async (traceId: string) => {
    try {
      const [tree, breakdown, traceStats] = await Promise.all([
        getTraceTree(traceId),
        getTraceDurationBreakdown(traceId),
        getTraceStats(traceId),
      ]);
      setSelectedTrace(tree);
      setDurationBreakdown(breakdown);
      setStats({
        span_count: traceStats.span_count,
        total_duration: traceStats.total_duration,
        final_status: traceStats.final_status,
      });
    } catch (error) {
      console.error('Failed to load trace detail:', error);
    }
  };

  useEffect(() => {
    loadTraces();
  }, [selectedType]);

  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${(ms / 60000).toFixed(1)}m`;
  };

  const formatTime = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'success':
        return <CheckCircle className="w-4 h-4 text-emerald-500" />;
      case 'failed':
        return <XCircle className="w-4 h-4 text-red-500" />;
      case 'running':
        return <Activity className="w-4 h-4 text-blue-500" />;
      default:
        return <AlertCircle className="w-4 h-4 text-gray-400" />;
    }
  };


  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-gray-50">
      {/* Header */}
      <header className="h-[60px] px-6 bg-white flex items-center justify-between shrink-0 border-b border-gray-200">
        <div className="flex items-center gap-3">
          <Activity className="w-5 h-5 text-blue-600" />
          <h1 className="text-base font-medium text-gray-900">{t('execution-tracing.title')}</h1>
          <span className="text-xs text-gray-500">{t('execution-tracing.desc')}</span>
        </div>
        <button
          onClick={() => loadTraces()}
          className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          title={t('refresh') || '刷新'}
        >
          <RefreshCw className="w-4 h-4 text-gray-600" />
        </button>
      </header>

      {/* Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Trace List */}
        <div className="w-[400px] border-r border-gray-200 bg-white overflow-y-auto">
          {/* Filter Tabs */}
          <div className="flex border-b border-gray-200">
            {(['all', 'document_pipeline', 'agent_execution'] as ExecutionType[]).map(type => (
              <button
                key={type}
                onClick={() => setSelectedType(type)}
                className={`flex-1 px-3 py-2 text-sm font-medium transition-colors ${
                  selectedType === type
                    ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                {type === 'all' ? t('execution-tracing.all') : getTypeLabel(type)}
              </button>
            ))}
          </div>

          {/* Trace List */}
          <div className="divide-y divide-gray-100">
            {traces.map(trace => (
              <div
                key={trace.trace_id}
                onClick={() => loadTraceDetail(trace.trace_id)}
                className={`p-4 cursor-pointer transition-colors hover:bg-gray-50 ${
                  selectedTrace?.trace_id === trace.trace_id ? 'bg-blue-50' : ''
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-medium text-gray-500">
                    {getTypeLabel(trace.execution_type)}
                  </span>
                  <div className="flex items-center gap-1">
                    {getStatusIcon(trace.final_status)}
                    <span className={`text-xs ${
                      trace.final_status === 'success' ? 'text-emerald-600' :
                      trace.final_status === 'failed' ? 'text-red-600' : 'text-gray-500'
                    }`}>
                      {getStatusLabel(trace.final_status)}
                    </span>
                  </div>
                </div>
                <div className="text-sm font-medium text-gray-900 truncate mb-1">
                  {trace.execution_id}
                </div>
                <div className="flex items-center justify-between text-xs text-gray-500">
                  <span>{formatTime(trace.started_at)}</span>
                  <span className="flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {formatDuration(trace.total_duration_ms)}
                  </span>
                </div>
              </div>
            ))}

            {loading && (
              <div className="p-4 text-center text-sm text-gray-500">{t('execution-tracing.loading')}</div>
            )}

            {!loading && traces.length === 0 && (
              <div className="p-8 text-center text-gray-500">
                <Activity className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                <p>{t('execution-tracing.noTraces')}</p>
              </div>
            )}

            {hasMore && (
              <button
                onClick={() => loadTraces(true)}
                className="w-full p-3 text-sm text-blue-600 hover:bg-gray-50 transition-colors"
              >
                {t('execution-tracing.loadMore')}
              </button>
            )}
          </div>
        </div>

        {/* Right: Trace Detail */}
        <div className="flex-1 overflow-y-auto bg-gray-50 p-6">
          {selectedTrace ? (
            <div className="max-w-4xl mx-auto space-y-6">
              {/* Summary Card */}
              <Card>
                <CardHeader>
                  <CardTitle>{t('execution-tracing.overview')}</CardTitle>
                </CardHeader>
                <CardBody>
                  <div className="grid grid-cols-4 gap-4">
                    <div>
                      <div className="text-sm text-gray-500 mb-1">{t('execution-tracing.executionType')}</div>
                      <div className="font-medium text-gray-900">
                        {getTypeLabel(selectedTrace.execution_type)}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-500 mb-1">{t('execution-tracing.status')}</div>
                      <div className="flex items-center gap-2">
                        {getStatusIcon(selectedTrace.final_status)}
                        <span className="font-medium text-gray-900">
                          {getStatusLabel(selectedTrace.final_status)}
                        </span>
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-500 mb-1">{t('execution-tracing.duration')}</div>
                      <div className="font-medium text-gray-900">
                        {formatDuration(selectedTrace.total_duration_ms)}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-500 mb-1">{t('execution-tracing.spanCount')}</div>
                      <div className="font-medium text-gray-900">
                        {selectedTrace.total_spans}
                      </div>
                    </div>
                  </div>
                  <div className="mt-4 pt-4 border-t border-gray-200">
                    <div className="text-sm text-gray-500">ID: {selectedTrace.execution_id}</div>
                    <div className="text-sm text-gray-500">{t('execution-tracing.startTime')}: {formatTime(selectedTrace.started_at)}</div>
                    <div className="text-sm text-gray-500">{t('execution-tracing.endTime')}: {formatTime(selectedTrace.completed_at)}</div>
                  </div>
                </CardBody>
              </Card>

              {/* Duration Breakdown */}
              {durationBreakdown.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle>{t('execution-tracing.durationAnalysis')}</CardTitle>
                  </CardHeader>
                  <CardBody>
                    <div className="space-y-3">
                      {durationBreakdown.map((item, index) => (
                        <div key={index} className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
                          <div className="flex items-center gap-3">
                            <span className="text-sm text-gray-500">{item.node_type}</span>
                            <span className="text-sm font-medium text-gray-900">{item.node_name}</span>
                          </div>
                          <div className="flex items-center gap-4">
                            <span className={`text-xs px-2 py-1 rounded ${
                              item.status === 'success' ? 'bg-emerald-100 text-emerald-700' :
                              item.status === 'failed' ? 'bg-red-100 text-red-700' :
                              'bg-gray-100 text-gray-700'
                            }`}>
                              {getStatusLabel(item.status)}
                            </span>
                            <span className="text-sm font-medium text-gray-900 w-20 text-right">
                              {formatDuration(item.duration_ms || 0)}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardBody>
                </Card>
              )}

              {/* Span Tree */}
              <Card>
                <CardHeader>
                  <CardTitle>{t('execution-tracing.executionChain')}</CardTitle>
                </CardHeader>
                <CardBody>
                  <div className="space-y-2">
                    {selectedTrace.spans.map((span) => (
                      <TraceSpanRow
                        key={span.span_id}
                        span={span}
                        allSpans={selectedTrace.spans}
                        depth={0}
                        formatDuration={formatDuration}
                        formatTime={formatTime}
                      />
                    ))}
                  </div>
                </CardBody>
              </Card>
            </div>
          ) : (
            <div className="flex items-center justify-center h-full">
              <div className="text-center text-gray-500">
                <Activity className="w-16 h-16 text-gray-300 mx-auto mb-4" />
                <p className="text-lg font-medium mb-2">{t('execution-tracing.selectTrace')}</p>
                <p className="text-sm">{t('execution-tracing.desc')}</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// 递归渲染 Span 树
function TraceSpanRow({
  span,
  allSpans,
  depth,
  formatDuration,
  formatTime
}: {
  span: TraceSpan;
  allSpans: TraceSpan[];
  depth: number;
  formatDuration: (ms: number) => string;
  formatTime: (iso: string) => string;
}) {
  const [expanded, setExpanded] = useState(true);
  const hasChildren = allSpans.some(s => s.parent_span_id === span.span_id);

  // 查找所有子 span
  const childSpans = allSpans.filter(s => s.parent_span_id === span.span_id);

  return (
    <>
      <div
        className={`flex items-center gap-2 p-3 rounded-lg transition-colors ${
          span.status === 'failed' ? 'bg-red-50' : 'bg-gray-50'
        }`}
        style={{ marginLeft: depth * 24 }}
      >
        {hasChildren && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="p-1 hover:bg-gray-200 rounded"
          >
            {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          </button>
        )}
        {!hasChildren && <div className="w-6" />}

        <span className={`w-2 h-2 rounded-full ${
          span.status === 'success' ? 'bg-emerald-500' :
          span.status === 'failed' ? 'bg-red-500' :
          span.status === 'running' ? 'bg-blue-500' : 'bg-gray-400'
        }`} />

        <span className="flex-1 text-sm font-medium text-gray-900">
          {span.node_name}
        </span>

        <span className="text-xs text-gray-500">
          {span.node_type}
        </span>

        {span.duration_ms !== null && (
          <span className="text-xs font-medium text-gray-700 w-20 text-right">
            {formatDuration(span.duration_ms)}
          </span>
        )}

        <span className="text-xs text-gray-500 w-24 text-right">
          {formatTime(span.started_at)}
        </span>
      </div>

      {expanded && childSpans.map(child => (
        <TraceSpanRow
          key={child.span_id}
          span={child}
          allSpans={allSpans}
          depth={depth + 1}
          formatDuration={formatDuration}
          formatTime={formatTime}
        />
      ))}
    </>
  );
}
