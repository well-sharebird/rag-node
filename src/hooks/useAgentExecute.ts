/**
 * Agent 执行 Hook - 支持调试模式
 */
import { useState, useCallback, useRef } from 'react';

// ============================================================================
// 类型定义
// ============================================================================

export interface DebugEvent {
  node: string;
  event: 'start' | 'node_output' | 'complete' | 'error' | 'debug_enabled';
  data: Record<string, unknown>;
  timestamp: number;
}

export interface TraceMetrics {
  run_id: string;
  agent_id: string;
  user_id: number;
  start_time: string;
  end_time: string | null;
  duration_ms: number;
  steps: Array<{
    step: string;
    timestamp: string;
    data?: Record<string, unknown>;
    duration_ms?: number;
  }>;
  tokens: {
    input: number;
    output: number;
    total: number;
  };
  errors: string[];
  status: string;
}

export interface UseAgentExecuteOptions {
  agentId: string;
  debugMode?: boolean;
  onToken?: (token: string) => void;
  onComplete?: (response: string, metrics: TraceMetrics | null) => void;
  onError?: (error: string) => void;
  onDebugEvent?: (event: DebugEvent) => void;
}

export interface UseAgentExecuteReturn {
  isLoading: boolean;
  error: string | null;
  response: string;
  debugEvents: DebugEvent[];
  metrics: TraceMetrics | null;
  execute: (query: string, options?: Partial<UseAgentExecuteOptions>) => Promise<void>;
  stop: () => void;
}

// ============================================================================
// Hook 实现
// ============================================================================

export function useAgentExecute(options: UseAgentExecuteOptions): UseAgentExecuteReturn {
  const {
    agentId,
    debugMode = false,
    onToken,
    onComplete,
    onError,
    onDebugEvent,
  } = options;

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState('');
  const [debugEvents, setDebugEvents] = useState<DebugEvent[]>([]);
  const [metrics, setMetrics] = useState<TraceMetrics | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);

  // 执行 Agent
  const execute = useCallback(async (
    query: string,
    execOptions?: Partial<UseAgentExecuteOptions>
  ) => {
    const finalDebugMode = execOptions?.debugMode ?? debugMode;
    const finalOnToken = execOptions?.onToken ?? onToken;
    const finalOnComplete = execOptions?.onComplete ?? onComplete;
    const finalOnError = execOptions?.onError ?? onError;
    const finalOnDebugEvent = execOptions?.onDebugEvent ?? onDebugEvent;

    setIsLoading(true);
    setError(null);
    setResponse('');
    setDebugEvents([]);
    setMetrics(null);

    abortControllerRef.current = new AbortController();

    try {
      const res = await fetch(`/api/v1/agents/${agentId}/execute/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query,
          debug_mode: finalDebugMode,
        }),
        signal: abortControllerRef.current.signal,
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }

      const reader = res.body?.getReader();
      if (!reader) {
        throw new Error('No response body');
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // 解析 SSE 事件
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('event:')) {
            const eventType = line.slice(6).trim();
            const nextLine = lines.shift();
            if (!nextLine || !nextLine.startsWith('data:')) continue;

            const dataStr = nextLine.slice(5).trim();
            try {
              const data = JSON.parse(dataStr);

              switch (eventType) {
                case 'token':
                  if (data.type === 'token' && data.content) {
                    setResponse((prev) => prev + data.content);
                    finalOnToken?.(data.content);
                  }
                  break;

                case 'debug':
                  const debugEvent: DebugEvent = {
                    node: data.node || 'unknown',
                    event: data.type as DebugEvent['event'],
                    data: data.data || {},
                    timestamp: Date.now(),
                  };
                  setDebugEvents((prev) => [...prev, debugEvent]);
                  finalOnDebugEvent?.(debugEvent);
                  break;

                case 'done':
                  if (data.type === 'done' && data.metrics) {
                    setMetrics(data.metrics as TraceMetrics);
                  }
                  finalOnComplete?.(response, data.metrics as TraceMetrics);
                  break;

                case 'error':
                  if (data.type === 'error' && data.error) {
                    throw new Error(data.error);
                  }
                  break;
              }
            } catch (parseError) {
              console.warn('Failed to parse SSE data:', parseError);
            }
          }
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') {
        console.log('Execution aborted');
        return;
      }

      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
      finalOnError?.(errorMessage);
    } finally {
      setIsLoading(false);
      abortControllerRef.current = null;
    }
  }, [agentId, debugMode, onToken, onComplete, onError, onDebugEvent, response]);

  // 停止执行
  const stop = useCallback(() => {
    abortControllerRef.current?.abort();
  }, []);

  return {
    isLoading,
    error,
    response,
    debugEvents,
    metrics,
    execute,
    stop,
  };
}

export default useAgentExecute;
