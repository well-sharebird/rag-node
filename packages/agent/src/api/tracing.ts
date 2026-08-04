/**
 * 执行追踪 API 客户端
 */
import { fetchWithBaseUrl } from '@/src/lib/env';

export interface TraceSpan {
  trace_id: string;
  span_id: string;
  parent_span_id: string | null;
  execution_type: string;
  execution_id: string;
  node_type: string;
  node_name: string;
  status: string;
  duration_ms: number | null;
  started_at: string;
  completed_at: string | null;
  input_data: Record<string, unknown> | null;
  output_data: Record<string, unknown> | null;
  error_info: Record<string, unknown> | null;
}

export interface TraceTree {
  trace_id: string;
  execution_type: string;
  execution_id: string;
  total_spans: number;
  total_duration_ms: number;
  final_status: string;
  started_at: string;
  completed_at: string;
  spans: TraceSpan[];
}

export interface TraceListItem {
  trace_id: string;
  execution_type: string;
  execution_id: string;
  total_spans: number;
  total_duration_ms: number;
  final_status: string;
  started_at: string;
  completed_at: string;
}

export interface TraceListResponse {
  traces: TraceListItem[];
  next_search_after: unknown[] | null;
  has_more: boolean;
}

export interface TraceStats {
  span_count: number;
  avg_duration: number | null;
  total_duration: number;
  status_breakdown: Record<string, number>;
  final_status: string;
}

export interface TraceDurationBreakdown {
  node_type: string;
  node_name: string;
  duration_ms: number | null;
  status: string;
}

export interface TraceListRequest {
  execution_type?: string;
  execution_id?: string;
  status?: string;
  start_time?: string;
  end_time?: string;
  user_id?: number;
  search_after?: unknown[];
  size?: number;
}

/**
 * 获取追踪树详情
 */
export async function getTraceTree(traceId: string): Promise<TraceTree> {
  return fetchWithBaseUrl<TraceTree>(`/api/v1/tracing/${traceId}`);
}

/**
 * 列出追踪记录
 */
export async function listTraces(request?: TraceListRequest): Promise<TraceListResponse> {
  return fetchWithBaseUrl<TraceListResponse>('/api/v1/tracing/list', {
    method: 'POST',
    body: JSON.stringify(request || {}),
  });
}

/**
 * 获取追踪统计
 */
export async function getTraceStats(traceId: string): Promise<TraceStats> {
  return fetchWithBaseUrl<TraceStats>(`/api/v1/tracing/${traceId}/stats`);
}

/**
 * 获取耗时分析
 */
export async function getTraceDurationBreakdown(traceId: string): Promise<TraceDurationBreakdown[]> {
  return fetchWithBaseUrl<TraceDurationBreakdown[]>(`/api/v1/tracing/${traceId}/duration-breakdown`);
}

/**
 * 清理旧的追踪数据
 */
export async function cleanupOldTraces(days: number): Promise<{ message: string }> {
  return fetchWithBaseUrl<{ message: string }>(`/api/v1/tracing/cleanup?days=${days}`, {
    method: 'DELETE',
  });
}
