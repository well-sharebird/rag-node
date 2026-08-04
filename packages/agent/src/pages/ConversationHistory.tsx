/**
 * 会话历史页面
 * 支持查看、搜索和管理会话历史
 */
import { useState, useEffect, useRef } from 'react';
import { useAuth } from '@/src/lib/auth-context';
import {
  listConversations,
  getConversation,
  deleteConversation,
  type ChatMessageDetail,
} from '@/lib/api-client';
import { useI18n } from '@/src/lib/i18n';
import { toast } from 'sonner';
import { getApiUrl } from '@/src/lib/env';
import { ChatMessageList, type ChatMessage } from '@/src/components/ChatMessageList';
import {
  Clock,
  MessageSquare,
  Trash2,
  Search,
  ChevronRight,
  Loader2,
  RefreshCw,
  X,
  Send,
} from 'lucide-react';

// 会话项类型
interface SessionItem {
  id: string;
  title: string;
  message_count: number;
  last_message_at: string;
  created_at: string;
}

export function ConversationHistory() {
  const { t } = useI18n();
  const { token } = useAuth();
  const [loading, setLoading] = useState(true);

  // 会话列表
  const [sessions, setSessions] = useState<SessionItem[]>([]);

  // 会话详情
  const [selectedSession, setSelectedSession] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessageDetail[]>([]);
  const [messageLoading, setMessageLoading] = useState(false);

  // 继续对话状态
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);

  // 搜索和过滤
  const [searchQuery, setSearchQuery] = useState('');

  // 加载会话列表
  const loadSessions = async () => {
    try {
      setLoading(true);
      const res = await listConversations({ limit: 100 });
      const sessionItems: SessionItem[] = res.items
        .filter((c: any) => c.message_count > 0)
        .map((c: any) => ({
          id: c.id,
          title: c.title || '新对话',
          message_count: c.message_count,
          last_message_at: c.last_message_at,
          created_at: c.created_at,
        }))
        .sort((a, b) => new Date(b.last_message_at).getTime() - new Date(a.last_message_at).getTime());
      setSessions(sessionItems);
    } catch (error: any) {
      toast.error(error.message || '加载会话列表失败');
    } finally {
      setLoading(false);
    }
  };

  // 加载会话消息
  const loadSessionMessages = async (sessionId: string) => {
    try {
      setMessageLoading(true);
      const res = await getConversation(sessionId);
      const messagesData = (res as any).messages || [];
      setMessages(messagesData.map((m: any) => ({
        id: m.id,
        role: m.role,
        content: m.content,
        timestamp: m.created_at,
      })));
      setSelectedSession(sessionId);
    } catch (error: any) {
      toast.error(error.message || '加载消息失败');
    } finally {
      setMessageLoading(false);
    }
  };

  // 转换消息格式为 ChatMessage
  const convertToChatMessages = (msgs: ChatMessageDetail[]): ChatMessage[] => {
    return msgs.map(m => ({
      id: m.id ? String(m.id) : undefined,
      role: m.role as 'user' | 'assistant',
      content: m.content,
      timestamp: m.timestamp,
    }));
  };

  // 继续对话 - 发送消息到当前会话
  const handleContinueChat = async () => {
    if (!input.trim() || sending || !selectedSession) return;

    const query = input.trim();
    setInput('');
    setSending(true);

    // 添加用户消息
    const userMsg: ChatMessageDetail = {
      role: 'user',
      content: query,
      timestamp: new Date().toISOString(),
    };
    setMessages(prev => [...prev, userMsg]);

    try {
      // 调用 Meta Agent 接口
      const res = await fetch(getApiUrl('/api/v1/agents/meta/execute/stream'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ query, session_id: selectedSession }),
      });

      if (!res.ok) {
        throw new Error('Request failed');
      }

      // 读取流式响应
      const reader = res.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let accumulatedContent = '';

      // 添加 AI 消息占位符
      const aiMsgId = `ai_${Date.now()}`;
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: '',
        timestamp: new Date().toISOString(),
        id: aiMsgId,
      }]);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data === '[DONE]') continue;

            try {
              const parsed = JSON.parse(data);
              if (parsed.type === 'token' && parsed.content) {
                accumulatedContent += parsed.content;
                setMessages(prev => prev.map(msg =>
                  msg.id === aiMsgId
                    ? { ...msg, content: accumulatedContent }
                    : msg
                ));
              }
            } catch (e) {
              console.warn('Failed to parse SSE line:', e);
            }
          }
        }
      }

      // 完成后移除占位符 ID
      setMessages(prev => prev.map(msg =>
        msg.id === aiMsgId
          ? { ...msg, id: undefined }
          : msg
      ));

      // 重新加载会话列表以更新标题和消息数
      loadSessions();

    } catch (e: any) {
      toast.error(e.message || '发送失败');
      // 移除失败的消息
      setMessages(prev => prev.slice(0, -1));
    } finally {
      setSending(false);
    }
  };

  // 删除会话
  const handleDelete = async (sessionId: string) => {
    if (!confirm('确定要删除这个会话吗？此操作不可逆。')) return;

    try {
      await deleteConversation(sessionId);
      toast.success('会话已删除');
      loadSessions();
      if (selectedSession === sessionId) {
        setSelectedSession(null);
        setMessages([]);
      }
    } catch (error: any) {
      toast.error(error.message || '删除失败');
    }
  };

  // 格式化时间
  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const days = Math.floor(diff / 86400000);

    if (days === 0) return '今天';
    if (days === 1) return '昨天';
    if (days < 7) return `${days}天前`;
    return date.toLocaleDateString('zh-CN');
  };

  // 初始化加载
  useEffect(() => {
    loadSessions();
  }, []);

  // 过滤后的会话数据
  const filteredSessions = sessions.filter(item => {
    if (!searchQuery) return true;
    return item.title.toLowerCase().includes(searchQuery.toLowerCase());
  });

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-gray-50">
      {/* 头部 */}
      <header className="h-[52px] px-5 bg-white flex items-center justify-between shrink-0 border-b border-gray-200">
        <div className="flex items-center gap-3">
          <h1 className="text-[15px] font-medium text-gray-900">会话历史</h1>
          <span className="text-xs text-gray-500">共 {sessions.length} 个会话</span>
        </div>
        <button
          onClick={loadSessions}
          className="p-1.5 rounded-md hover:bg-gray-100"
        >
          <RefreshCw className="w-4 h-4 text-gray-600" />
        </button>
      </header>

      {/* 主体内容 */}
      <div className="flex-1 flex overflow-hidden">
        {/* 左侧：会话列表 */}
        <div className="w-96 bg-white border-r border-gray-200 flex flex-col">
          {/* 搜索 */}
          <div className="p-3 border-b border-gray-200">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder="搜索会话..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 hover:bg-gray-100 rounded"
                >
                  <X className="w-3.5 h-3.5 text-gray-500" />
                </button>
              )}
            </div>
          </div>

          {/* 会话列表 */}
          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
              </div>
            ) : filteredSessions.length === 0 ? (
              <div className="flex items-center justify-center py-12">
                <p className="text-sm text-gray-400">暂无会话</p>
              </div>
            ) : (
              <ul className="divide-y divide-gray-50">
                {filteredSessions.map((item) => (
                  <li key={item.id}>
                    <button
                      onClick={() => loadSessionMessages(item.id)}
                      className={`w-full px-4 py-3 text-left hover:bg-gray-50 transition-colors ${
                        selectedSession === item.id ? 'bg-blue-50' : ''
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-sm font-medium text-gray-900 truncate">
                              {item.title || '新对话'}
                            </span>
                          </div>
                          <div className="flex items-center gap-3 text-xs text-gray-400">
                            <span className="flex items-center gap-1">
                              <MessageSquare className="w-3 h-3" />
                              {item.message_count}
                            </span>
                            <span className="flex items-center gap-1">
                              <Clock className="w-3 h-3" />
                              {formatTime(item.last_message_at)}
                            </span>
                          </div>
                        </div>
                        <ChevronRight
                          className={`w-4 h-4 text-gray-400 transition-transform ${
                            selectedSession === item.id ? 'rotate-90' : ''
                          }`}
                        />
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* 右侧：消息详情 */}
        <div className="flex-1 flex flex-col bg-white">
          {selectedSession === null ? (
            <div className="flex-1 flex flex-col items-center justify-center text-gray-500">
              <MessageSquare className="w-16 h-16 mb-4 opacity-20" />
              <p className="text-sm">选择一个会话查看详情</p>
            </div>
          ) : messageLoading ? (
            <div className="flex-1 flex flex-col items-center justify-center">
              <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
              <p className="text-sm text-gray-500 mt-2">加载消息中...</p>
            </div>
          ) : (
            <>
              {/* 消息头部 */}
              <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">消息详情</span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleDelete(selectedSession)}
                    className="p-1 hover:bg-red-50 rounded"
                    title="删除会话"
                  >
                    <Trash2 className="w-4 h-4 text-red-500" />
                  </button>
                  <button
                    onClick={() => setSelectedSession(null)}
                    className="p-1 hover:bg-gray-100 rounded"
                  >
                    <X className="w-4 h-4 text-gray-500" />
                  </button>
                </div>
              </div>

              {/* 消息列表 - 使用公共组件 */}
              <ChatMessageList
                messages={convertToChatMessages(messages)}
                loading={sending}
                showReasoningToggle={false}
                className="bg-gray-50"
                emptyState={{
                  title: '暂无消息',
                  description: '开始提问吧',
                }}
              />

              {/* 输入框 */}
              <div className="p-4 border-t border-gray-200 bg-white">
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        handleContinueChat();
                      }
                    }}
                    placeholder="继续提问..."
                    disabled={sending}
                    className="flex-1 px-4 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-1 focus:ring-[#534ab7]"
                  />
                  <button
                    onClick={handleContinueChat}
                    disabled={sending || !input.trim()}
                    className="px-4 py-2 bg-[#534ab7] text-white rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center gap-1.5"
                  >
                    {sending ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Send className="w-4 h-4" />
                    )}
                    发送
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default ConversationHistory;
