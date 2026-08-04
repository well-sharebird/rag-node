/**
 * Agent 调试面板
 * 显示执行轨迹和节点输出
 */
import React, { useState, useCallback } from 'react';

// ============================================================================
// 类型定义
// ============================================================================

interface DebugEvent {
  node: string;
  event: 'start' | 'node_output' | 'complete' | 'error';
  data: Record<string, unknown>;
  timestamp: number;
}

interface TraceMetrics {
  run_id: string;
  duration_ms: number;
  tokens: {
    input: number;
    output: number;
    total: number;
  };
  steps: Array<{
    step: string;
    timestamp: string;
    duration_ms?: number;
  }>;
}

interface AgentDebugPanelProps {
  isOpen: boolean;
  onClose: () => void;
  debugEvents: DebugEvent[];
  metrics: TraceMetrics | null;
}

// ============================================================================
// 调试面板组件
// ============================================================================

export const AgentDebugPanel: React.FC<AgentDebugPanelProps> = ({
  isOpen,
  onClose,
  debugEvents,
  metrics,
}) => {
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set(['system']));

  if (!isOpen) return null;

  // 按节点分组事件
  const eventsByNode = debugEvents.reduce((acc, event) => {
    const node = event.node;
    if (!acc[node]) {
      acc[node] = [];
    }
    acc[node].push(event);
    return acc;
  }, {} as Record<string, DebugEvent[]>);

  // 切换节点展开/收起
  const toggleNode = useCallback((node: string) => {
    setExpandedNodes((prev) => {
      const next = new Set(prev);
      if (next.has(node)) {
        next.delete(node);
      } else {
        next.add(node);
      }
      return next;
    });
  }, []);

  // 格式化时间
  const formatTime = (timestamp: number) => {
    return new Date(timestamp).toLocaleTimeString();
  };

  // 格式化持续时间
  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
  };

  return (
    <div className="fixed right-0 top-0 h-full w-96 bg-white border-l border-gray-200 shadow-lg overflow-y-auto z-50">
      {/* Header */}
      <div className="sticky top-0 bg-white border-b border-gray-200 p-4 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-800">执行轨迹</h3>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600 transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Metrics Summary */}
      {metrics && (
        <div className="p-4 bg-gray-50 border-b border-gray-200">
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-white rounded-lg p-3 shadow-sm">
              <div className="text-xs text-gray-500">执行时长</div>
              <div className="text-lg font-semibold text-gray-800">
                {formatDuration(metrics.duration_ms)}
              </div>
            </div>
            <div className="bg-white rounded-lg p-3 shadow-sm">
              <div className="text-xs text-gray-500">Token 消耗</div>
              <div className="text-lg font-semibold text-gray-800">
                {metrics.tokens.total}
              </div>
            </div>
            <div className="bg-white rounded-lg p-3 shadow-sm">
              <div className="text-xs text-gray-500">输入 Token</div>
              <div className="text-sm font-medium text-blue-600">
                {metrics.tokens.input}
              </div>
            </div>
            <div className="bg-white rounded-lg p-3 shadow-sm">
              <div className="text-xs text-gray-500">输出 Token</div>
              <div className="text-sm font-medium text-green-600">
                {metrics.tokens.output}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Node List */}
      <div className="p-4 space-y-3">
        <h4 className="text-sm font-medium text-gray-600">节点执行</h4>

        {Object.entries(eventsByNode).map(([node, events]) => (
          <NodeTimeline
            key={node}
            node={node}
            events={events}
            isExpanded={expandedNodes.has(node)}
            onToggle={() => toggleNode(node)}
            formatTime={formatTime}
          />
        ))}

        {debugEvents.length === 0 && (
          <div className="text-center py-8 text-gray-400 text-sm">
            暂无调试信息
            <br />
            启用调试模式后查看执行轨迹
          </div>
        )}
      </div>
    </div>
  );
};

// ============================================================================
// 节点时间线组件
// ============================================================================

interface NodeTimelineProps {
  node: string;
  events: DebugEvent[];
  isExpanded: boolean;
  onToggle: () => void;
  formatTime: (timestamp: number) => string;
}

const NodeTimeline: React.FC<NodeTimelineProps> = ({
  node,
  events,
  isExpanded,
  onToggle,
  formatTime,
}) => {
  const getNodeColor = (node: string) => {
    const colors: Record<string, string> = {
      system: 'bg-blue-500',
      agent: 'bg-green-500',
      tool: 'bg-amber-500',
      router: 'bg-purple-500',
      default: 'bg-gray-500',
    };
    return colors[node] || colors.default;
  };

  const getEventIcon = (event: string) => {
    switch (event) {
      case 'start':
        return (
          <svg className="w-4 h-4 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        );
      case 'complete':
        return (
          <svg className="w-4 h-4 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        );
      case 'error':
        return (
          <svg className="w-4 h-4 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        );
      default:
        return (
          <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        );
    }
  };

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      {/* Node Header */}
      <div
        className="flex items-center gap-2 p-3 bg-gray-50 cursor-pointer hover:bg-gray-100 transition-colors"
        onClick={onToggle}
      >
        <svg
          className={`w-4 h-4 text-gray-400 transition-transform ${isExpanded ? 'rotate-90' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
        <div className={`w-2 h-2 rounded-full ${getNodeColor(node)}`} />
        <span className="text-sm font-medium text-gray-700 flex-1 capitalize">{node}</span>
        <span className="text-xs text-gray-500">{events.length} 事件</span>
      </div>

      {/* Events */}
      {isExpanded && (
        <div className="divide-y divide-gray-100">
          {events.map((event, index) => (
            <div key={index} className="p-3 flex items-start gap-2">
              <div className="flex-shrink-0 mt-0.5">
                {getEventIcon(event.event)}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-medium text-gray-600 capitalize">
                    {event.event}
                  </span>
                  <span className="text-xs text-gray-400">
                    {formatTime(event.timestamp)}
                  </span>
                </div>
                {Object.keys(event.data).length > 0 && (
                  <pre className="mt-1 text-xs text-gray-500 bg-gray-50 rounded p-2 overflow-x-auto">
                    {JSON.stringify(event.data, null, 2)}
                  </pre>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default AgentDebugPanel;
