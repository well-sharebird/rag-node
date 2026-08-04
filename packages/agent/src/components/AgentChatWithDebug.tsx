/**
 * Agent 聊天组件（带调试面板）
 *
 * 使用示例：
 *
 * ```tsx
 * import AgentChatWithDebug from '@/src/components/components/AgentChatWithDebug';
 *
 * function App() {
 *   return (
 *     <AgentChatWithDebug agentId="xxx-xxx-xxx" />
 *   );
 * }
 * ```
 */
import React, { useState, useRef, useEffect } from 'react';
import { useAgentExecute, DebugEvent, TraceMetrics } from '@/src/hooks/useAgentExecute';
import AgentDebugPanel from '@/src/components/AgentDebugPanel';

// ============================================================================
// 组件
// ============================================================================

interface AgentChatWithDebugProps {
  agentId: string;
}

export const AgentChatWithDebug: React.FC<AgentChatWithDebugProps> = ({ agentId }) => {
  const [query, setQuery] = useState('');
  const [debugMode, setDebugMode] = useState(false);
  const [showDebugPanel, setShowDebugPanel] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const {
    isLoading,
    error,
    response,
    debugEvents,
    metrics,
    execute,
    stop,
  } = useAgentExecute({
    agentId,
    debugMode,
    onToken: (token) => {
      // 实时滚动到底部
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    },
    onComplete: () => {
      console.log('执行完成', metrics);
    },
    onError: (err) => {
      console.error('执行错误:', err);
    },
    onDebugEvent: (event) => {
      console.log('调试事件:', event);
      // 自动打开调试面板
      if (!showDebugPanel) {
        setShowDebugPanel(true);
      }
    },
  });

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [response, debugEvents]);

  // 提交处理
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || isLoading) return;

    const currentQuery = query;
    setQuery('');
    await execute(currentQuery);
  };

  // 清除调试数据
  const clearDebugData = () => {
    setShowDebugPanel(false);
  };

  return (
    <div className="flex h-screen bg-gray-100">
      {/* 主聊天区域 */}
      <div className={`flex-1 flex flex-col transition-all duration-300 ${showDebugPanel ? 'mr-96' : ''}`}>

        {/* Header */}
        <div className="bg-white border-b border-gray-200 p-4 flex items-center justify-between">
          <h1 className="text-xl font-semibold text-gray-800">Agent 聊天</h1>
          <div className="flex items-center gap-3">
            {/* 调试模式开关 */}
            <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
              <input
                type="checkbox"
                checked={debugMode}
                onChange={(e) => setDebugMode(e.target.checked)}
                className="w-4 h-4 text-blue-600 rounded focus:ring-blue-500"
              />
              调试模式
            </label>

            {/* 调试面板按钮 */}
            <button
              onClick={() => setShowDebugPanel(!showDebugPanel)}
              disabled={!debugMode}
              className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                showDebugPanel
                  ? 'bg-blue-100 text-blue-700'
                  : debugMode
                  ? 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  : 'bg-gray-50 text-gray-300 cursor-not-allowed'
              }`}
            >
              <div className="flex items-center gap-1.5">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"
                  />
                </svg>
                执行轨迹
              </div>
            </button>
          </div>
        </div>

        {/* 消息区域 */}
        <div className="flex-1 overflow-y-auto p-4">
          {/* 用户输入 */}
          {query && (
            <div className="mb-4 flex justify-end">
              <div className="bg-blue-600 text-white rounded-lg p-3 max-w-lg">
                {query}
              </div>
            </div>
          )}

          {/* AI 响应 */}
          {response && (
            <div className="mb-4 flex justify-start">
              <div className="bg-white border border-gray-200 rounded-lg p-3 max-w-lg shadow-sm">
                <div className="text-gray-800 whitespace-pre-wrap">{response}</div>
              </div>
            </div>
          )}

          {/* 加载中 */}
          {isLoading && (
            <div className="mb-4 flex justify-start">
              <div className="bg-white border border-gray-200 rounded-lg p-3 max-w-lg shadow-sm">
                <div className="flex items-center gap-2 text-gray-500">
                  <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            </div>
          )}

          {/* 错误 */}
          {error && (
            <div className="mb-4 flex justify-start">
              <div className="bg-red-50 border border-red-200 rounded-lg p-3 max-w-lg">
                <div className="flex items-center gap-2 text-red-600">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span>{error}</span>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* 输入区域 */}
        <div className="bg-white border-t border-gray-200 p-4">
          <form onSubmit={handleSubmit} className="flex gap-3">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="输入消息..."
              disabled={isLoading}
              className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100"
            />
            {isLoading ? (
              <button
                type="button"
                onClick={stop}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
              >
                停止
              </button>
            ) : (
              <button
                type="submit"
                disabled={!query.trim()}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed"
              >
                发送
              </button>
            )}
          </form>
        </div>
      </div>

      {/* 调试面板 */}
      <AgentDebugPanel
        isOpen={showDebugPanel}
        onClose={() => setShowDebugPanel(false)}
        debugEvents={debugEvents}
        metrics={metrics}
      />
    </div>
  );
};

export default AgentChatWithDebug;
