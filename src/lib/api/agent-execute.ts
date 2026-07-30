/**
 * Agent 执行 API 客户端
 * 连接到后端的工厂模式 Agent 执行接口
 */
import { fetchWithBaseUrl, getApiUrl } from '../env';

export interface AgentExecuteRequest {
  query: string;
  model_name?: string;
  plan_mode?: boolean;
  skills?: string[];
  mcp_servers?: string[];
  session_id?: string;
}

export interface AgentExecuteResponse {
  run_id: string;
  response: string;
  messages: Array<{
    role: string;
    content: string;
  }>;
  factory_mode: boolean;
  agent_type: string;
}

export interface AgentExecuteStreamRequest {
  query: string;
  model_name?: string;
  plan_mode?: boolean;
  session_id?: string;
}

/**
 * 执行 Agent（非流式）
 */
export async function executeAgent(
  agentId: string,
  data: AgentExecuteRequest
): Promise<AgentExecuteResponse> {
  return fetchWithBaseUrl<AgentExecuteResponse>(`/api/v1/agents/${agentId}/execute`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * 执行 Agent（流式）
 * 使用 EventSource 接收 SSE 事件
 */
export function executeAgentStream(
  agentId: string,
  data: AgentExecuteStreamRequest,
  callbacks: {
    onToken?: (content: string) => void;
    onDone?: () => void;
    onError?: (error: string) => void;
  }
): { abort: () => void } {
  const url = getApiUrl(`/api/v1/agents/${agentId}/execute/stream`);
  const token = localStorage.getItem('auth_token');

  const eventSource = new EventSource(url, {
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
  });

  let aborted = false;

  eventSource.addEventListener('token', (event) => {
    if (aborted) return;
    const data = JSON.parse(event.data);
    callbacks.onToken?.(data.content);
  });

  eventSource.addEventListener('done', () => {
    if (aborted) return;
    eventSource.close();
    callbacks.onDone?.();
  });

  eventSource.addEventListener('error', (event) => {
    if (aborted) return;
    eventSource.close();
    const data = JSON.parse(event.data);
    callbacks.onError?.(data.error || 'Stream error');
  });

  // 处理连接建立
  eventSource.onopen = () => {
    console.log('SSE connection opened');
    // 发送请求体（POST 数据）
    // 注意：EventSource 默认只支持 GET，需要使用其他方式发送 POST
  };

  return {
    abort: () => {
      aborted = true;
      eventSource.close();
    },
  };
}

/**
 * 执行 Agent（流式）- Fetch 版本
 * 使用 fetch + ReadableStream 实现
 */
export async function executeAgentStreamFetch(
  agentId: string,
  data: AgentExecuteStreamRequest,
  callbacks: {
    onToken?: (content: string) => void;
    onDone?: () => void;
    onError?: (error: string) => void;
  }
): Promise<AbortController> {
  const controller = new AbortController();
  const token = localStorage.getItem('auth_token');

  (async () => {
    try {
      const response = await fetch(getApiUrl(`/api/v1/agents/${agentId}/execute/stream`), {
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
              if (parsed.content) {
                callbacks.onToken?.(parsed.content);
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
 * 获取可用的子智能体列表
 */
export async function getAvailableSubagents(): Promise<Array<{
  type: string;
  name: string;
  description: string;
  default_skills: string[];
}>> {
  return fetchWithBaseUrl('/api/v1/agents/subagents');
}

/**
 * 注册自定义子智能体
 */
export async function registerCustomSubagent(data: {
  name: string;
  system_prompt: string;
  skills: string[];
  model_config: {
    provider: string;
    model: string;
  };
}): Promise<{
  id: string;
  name: string;
  type: string;
}> {
  return fetchWithBaseUrl('/api/v1/agents/subagents', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}
