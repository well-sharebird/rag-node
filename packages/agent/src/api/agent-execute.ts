/**
 * Agent 执行 API 客户端 - Harness 架构统一入口
 *
 * Harness 架构采用统一执行入口，用户只需表达需求，Harness 自主决策使用哪个 Agent
 */
import { fetchWithBaseUrl, getApiUrl } from '@/src/lib/env';

export interface AgentExecuteUnifiedRequest {
  query: string;
  agent_id?: string;           // 可选：指定 Agent ID (不传时由 Harness 自主决策)
  model_name?: string;
  kb_ids?: string[];
  top_k?: number;
  enable_rerank?: boolean;
  session_id?: string;
}

export interface AgentExecuteUnifiedResponse {
  run_id: string;
  response: string;
  messages: Array<{
    role: string;
    content: string;
  }>;
  agent_id?: string;           // 实际使用的 Agent ID
  agent_type?: string;         // single/multi/meta
  agents_used?: string[];      // 被调用的子 Agent ID 列表 (多 Agent 场景)
}

export interface AgentExecuteStreamRequest {
  query: string;
  agent_id?: string;
  model_name?: string;
  kb_ids?: string[];
  top_k?: number;
  enable_rerank?: boolean;
  session_id?: string;
}

/** 工具执行事件（tool_event）——前端实时工具调用链渲染 */
export interface ToolEventFile {
  filename: string;
  relative_path: string;
}

export interface ToolEventData {
  phase: 'start' | 'done';
  tool: string;
  input?: Record<string, unknown>;
  status?: 'running' | 'success' | 'error' | 'denied' | 'limited' | 'circuit' | 'blocked';
  result?: string;
  files?: ToolEventFile[];
  sandbox?: string;
}

/**
 * 执行 Agent - Harness 统一入口 (非流式)
 *
 * @param data - 执行请求 (agent_id 可选)
 */
export async function executeAgent(
  data: AgentExecuteUnifiedRequest
): Promise<AgentExecuteUnifiedResponse> {
  return fetchWithBaseUrl<AgentExecuteUnifiedResponse>('/api/v1/agents/execute', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * 执行 Agent - Harness 统一入口 (流式)
 * 使用 fetch + ReadableStream 实现 SSE
 *
 * @param data - 执行请求 (agent_id 可选)
 * @param callbacks - 回调函数
 */
export async function executeAgentStream(
  data: AgentExecuteStreamRequest,
  callbacks: {
    onToken?: (content: string) => void;
    onReasoning?: (content: string) => void;
    onToolEvent?: (event: ToolEventData) => void;
    onDone?: () => void;
    onError?: (error: string) => void;
  }
): Promise<AbortController> {
  const controller = new AbortController();
  const token = localStorage.getItem('auth_token');

  (async () => {
    try {
      const response = await fetch(getApiUrl('/api/v1/agents/execute/stream'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(data),
        signal: controller.signal,
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: '请求失败' }));
        throw new Error(error.detail || `HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('ReadableStream not supported');
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // 解析 SSE 格式
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const eventData = line.slice(6);
            try {
              const parsed = JSON.parse(eventData);
              if (parsed.type === 'reasoning' && parsed.content) {
                callbacks.onReasoning?.(parsed.content);
              } else if (parsed.type === 'token' || parsed.content) {
                callbacks.onToken?.(parsed.content || parsed.data);
              } else if (parsed.type === 'tool_event' && parsed.data) {
                callbacks.onToolEvent?.(parsed.data as ToolEventData);
              } else if (parsed.type === 'done') {
                callbacks.onDone?.();
              } else if (parsed.type === 'error') {
                callbacks.onError?.(parsed.error || 'Unknown error');
              }
            } catch (e) {
              // 忽略解析错误
            }
          }
        }
      }

      callbacks.onDone?.();
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        return; // 忽略中止错误
      }
      callbacks.onError?.(error instanceof Error ? error.message : 'Unknown error');
    }
  })();

  return controller;
}

/**
 * 获取可用的 Agent 列表 (用于用户选择)
 */
export async function getAgentList(): Promise<Array<{
  id: string;
  name: string;
  description: string;
  agent_type: string;
}>> {
  return fetchWithBaseUrl('/api/v1/agents');
}
