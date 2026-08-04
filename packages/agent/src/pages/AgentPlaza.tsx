import { useState, useEffect } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { useAuth } from '@/src/lib/auth-context';
import { toast } from 'sonner';
import { fetchApi } from '@/lib/api-client';
import {
  Bot, Plus, Search, Trash2, Loader2, Play,
  Eye, Copy, Share2, Sparkles, Zap,
  MessageSquare, Settings, TrendingUp, Filter, RefreshCw
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/src/components/enterprise/Button';
import { Modal } from '@/src/components/enterprise/Modal';
import { Badge } from '@/src/components/enterprise/Badge';
import { Input } from '@/src/components/enterprise/Input';
import { Label } from '@/src/components/enterprise/Label';
import { Switch } from '@/src/components/enterprise/Switch';
import { Select } from '@/src/components/enterprise/Select';
import { Card, CardHeader, CardTitle, CardBody, CardDescription } from '@/src/components/enterprise/Card';

// ========== Types ==========

interface AgentConfig {
  id: string;
  user_id: number;
  name: string;
  description: string | null;
  icon: string | null;
  agent_type: 'single' | 'multi';
  default_model_config: Record<string, any> | null;
  system_prompt: string;
  enabled_skills: string[];
  mcp_servers: string[];
  memory_type: string;
  memory_ttl_hours: number;
  max_memory_turns: number;
  kb_ids: string[];
  retrieval_top_k: number;
  retrieval_enabled: boolean;
  multi_agent_config: Record<string, any> | null;
  status: 'draft' | 'active' | 'archived' | 'disabled';
  is_public: boolean;
  current_version: string;
  total_runs: number;
  total_tokens: number;
  created_at: string;
  updated_at: string;
  published_at: string | null;
}

interface AgentFormData {
  name: string;
  description: string;
  icon: string;
  agent_type: 'single' | 'multi';
  system_prompt: string;
  memory_type: string;
  memory_ttl_hours: number;
  is_public: boolean;
  enabled_skills?: string[];
  mcp_servers?: string[];
  kb_ids?: string[];
  retrieval_enabled?: boolean;
  retrieval_top_k?: number;
  default_model_config?: {
    provider: string;
    model: string;
    temperature?: number;
    max_tokens?: number;
  };
}

interface AgentPlazaProps {
  onNavigate?: (tab: string, agentId?: string) => void;
}

// ========== Constants ==========

const AGENT_TYPES = [
  { value: 'single', label: '单智能体' },
  { value: 'multi', label: '多智能体编排' },
];

const MEMORY_TYPES = [
  { value: 'conversation', label: '对话历史' },
  { value: 'vector', label: '向量记忆' },
  { value: 'hybrid', label: '混合记忆' },
];

const STATUS_LABELS: Record<string, string> = {
  draft: '草稿',
  active: '已发布',
  archived: '已归档',
  disabled: '已禁用',
};

// 头像调色板 — 6 套柔和色，按 agent id 哈希分配，保证同一 agent 颜色稳定
const AVATAR_PALETTE = [
  { bg: '#EEF2FB', icon: '#4F7BE5' }, // 蓝
  { bg: '#E8F5F1', icon: '#0F8A6B' }, // 薄荷
  { bg: '#F4ECFB', icon: '#7B3FBF' }, // 紫
  { bg: '#FEF1E7', icon: '#C75D1F' }, // 暖橙
  { bg: '#EAF3FE', icon: '#1E73C2' }, // 天蓝
  { bg: '#FCEEF1', icon: '#B23A5C' }, // 玫红
];

function getAvatarPalette(agent: { id: string; name?: string }) {
  const seed = (agent.id || agent.name || '0').split('').reduce((acc, c) => acc + c.charCodeAt(0), 0);
  return AVATAR_PALETTE[seed % AVATAR_PALETTE.length];
}

// ========== Main Component ==========

export function AgentPlaza({ onNavigate }: AgentPlazaProps) {
  const { t } = useI18n();
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [publicAgents, setPublicAgents] = useState<AgentConfig[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<AgentConfig | null>(null);
  const [activeTab, setActiveTab] = useState<'my' | 'plaza'>('my');

  // Form state
  const [formData, setFormData] = useState<AgentFormData>({
    name: '',
    description: '',
    icon: '🤖',
    agent_type: 'single',
    system_prompt: '',
    memory_type: 'conversation',
    memory_ttl_hours: 24,
    is_public: false,
    enabled_skills: [],
    mcp_servers: [],
    kb_ids: [],
    retrieval_enabled: false,
    retrieval_top_k: 5,
    default_model_config: undefined,
  });

  // Model options for default model selection
  const [modelProviders, setModelProviders] = useState<ModelProviderData[]>([]);
  const [modelConfigs, setModelConfigs] = useState<ModelConfigData[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);

  // Fetch model options on mount
  useEffect(() => {
    const fetchModelOptions = async () => {
      try {
        setLoadingModels(true);
        const [providersData, modelsData] = await Promise.all([
          fetchApi<{items: ModelProviderData[]}>('/api/v1/model-gateway/providers'),
          fetchApi<{items: ModelConfigData[]}>('/api/v1/models'),
        ]);
        setModelProviders((providersData?.items || []).filter(p => p.is_enabled));
        setModelConfigs((modelsData?.items || []).filter(m => m.is_enabled && m.model_type === 'llm'));
      } catch (error: any) {
        console.error('Failed to fetch model options:', error);
      } finally {
        setLoadingModels(false);
      }
    };
    fetchModelOptions();
  }, []);

  useEffect(() => {
    fetchAgents();
    if (activeTab === 'plaza') {
      fetchPublicAgents();
    }
  }, [activeTab, filterStatus]);

  const fetchAgents = async () => {
    try {
      setLoading(true);
      const params = filterStatus !== 'all' ? `?status=${filterStatus}` : '';
      const data = await fetchApi(`/api/v1/agents${params}`);
      setAgents(Array.isArray(data) ? data : []);
    } catch (error: any) {
      toast.error(`获取 Agent 列表失败：${error.message}`);
      setAgents([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchPublicAgents = async () => {
    try {
      setLoading(true);
      const data = await fetchApi('/api/v1/agents/public');
      setPublicAgents(Array.isArray(data) ? data : []);
    } catch (error: any) {
      toast.error(`获取广场 Agent 失败：${error.message}`);
      setPublicAgents([]);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!formData.name || !formData.system_prompt) {
      toast.error('请填写必填项');
      return;
    }

    try {
      const submitData: any = {
        name: formData.name,
        description: formData.description,
        icon: formData.icon,
        agent_type: formData.agent_type,
        system_prompt: formData.system_prompt,
        memory_type: formData.memory_type,
        memory_ttl_hours: formData.memory_ttl_hours,
        is_public: formData.is_public,
        enabled_skills: formData.enabled_skills || [],
        mcp_servers: formData.mcp_servers || [],
        kb_ids: formData.kb_ids || [],
        retrieval_enabled: formData.retrieval_enabled || false,
        retrieval_top_k: formData.retrieval_top_k || 5,
      };

      // 只提交设置了供应商和模型的情况
      if (formData.default_model_config?.provider && formData.default_model_config?.model) {
        submitData.default_model_config = formData.default_model_config;
      }

      await fetchApi('/api/v1/agents', {
        method: 'POST',
        body: JSON.stringify(submitData),
      });
      toast.success('Agent 创建成功');
      setShowCreateModal(false);
      fetchAgents();
      resetForm();
    } catch (error: any) {
      toast.error(`创建失败：${error.message}`);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('确定要删除这个 Agent 吗？')) return;

    try {
      await fetchApi(`/api/v1/agents/${id}`, { method: 'DELETE' });
      toast.success('删除成功');
      fetchAgents();
    } catch (error: any) {
      toast.error(`删除失败：${error.message}`);
    }
  };

  const handlePublish = async (id: string) => {
    try {
      await fetchApi(`/api/v1/agents/${id}/publish`, { method: 'POST' });
      toast.success('发布成功');
      fetchAgents();
    } catch (error: any) {
      toast.error(`发布失败：${error.message}`);
    }
  };

  const handleDuplicate = async (agent: AgentConfig) => {
    try {
      await fetchApi(`/api/v1/agents/${agent.id}/duplicate`, { method: 'POST' });
      toast.success('复制成功');
      if (activeTab === 'my') {
        fetchAgents();
      }
    } catch (error: any) {
      toast.error(`复制失败：${error.message}`);
    }
  };

  const handleChat = (agent: AgentConfig) => {
    if (onNavigate) {
      // 存储 agentId 到 sessionStorage，供 AgentChat 读取
      sessionStorage.setItem('agent_chat_id', agent.id);
      onNavigate('agent-chat', agent.id);
    } else {
      // 降级处理：直接跳转
      window.location.href = `/?tab=agent-chat&agent_id=${agent.id}`;
    }
  };

  const resetForm = () => {
    setFormData({
      name: '',
      description: '',
      icon: '🤖',
      agent_type: 'single',
      system_prompt: '',
      memory_type: 'conversation',
      memory_ttl_hours: 24,
      is_public: false,
      enabled_skills: [],
      mcp_servers: [],
      kb_ids: [],
      retrieval_enabled: false,
      retrieval_top_k: 5,
      default_model_config: undefined,
    });
  };

  const filteredAgents = agents.filter(agent => {
    const matchesSearch = agent.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.description?.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesSearch;
  });

  const displayAgents = activeTab === 'my' ? filteredAgents : publicAgents;

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-white">
      {/* Header */}
      <header className="h-[52px] px-5 bg-white flex items-center justify-between shrink-0 border-b border-[var(--gray-200)]">
        <h1 className="text-[15px] font-medium text-[var(--text-primary)]">智能体广场</h1>
        <Button onClick={() => setShowCreateModal(true)} className="flex items-center gap-2">
          <Plus className="w-4 h-4" />
          创建 Agent
        </Button>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-7xl mx-auto">
          {/* Page Title */}
          <div className="mb-6">
            <h2 className="text-2xl font-semibold text-[var(--text-primary)] mb-1 flex items-center gap-2">
              <Bot className="w-6 h-6 text-blue-500" />
              智能体广场
            </h2>
            <p className="text-[var(--text-secondary)] text-sm">
              {activeTab === 'my'
                ? '创建和管理你的 AI 智能体'
                : '探索其他人分享的智能体'}
            </p>
          </div>

          {/* Tabs — 轻量分段控件，选中态用淡蓝底+蓝字 */}
          <div className="flex gap-1 mb-6 bg-[var(--bg-primary)] rounded-lg p-1 w-fit">
            <button
              className={cn(
                "px-4 py-2 rounded-md text-sm font-medium transition-all",
                activeTab === 'my'
                  ? "bg-[var(--accent-light)] text-[var(--accent)] shadow-sm"
                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              )}
              onClick={() => setActiveTab('my')}
            >
              我的智能体
            </button>
            <button
              className={cn(
                "px-4 py-2 rounded-md text-sm font-medium transition-all",
                activeTab === 'plaza'
                  ? "bg-[var(--accent-light)] text-[var(--accent)] shadow-sm"
                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              )}
              onClick={() => setActiveTab('plaza')}
            >
              广场探索
            </button>
          </div>

          {/* Filters */}
          {activeTab === 'my' && (
            <div className="flex gap-3 mb-6">
              <div className="flex-1 relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text-tertiary)]" />
                <Input
                  placeholder="搜索智能体名称或描述..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10 w-full"
                />
              </div>
              <div className="flex items-center gap-2">
                <Filter className="w-4 h-4 text-[var(--text-tertiary)]" />
                <Select
                  value={filterStatus}
                  onChange={(e) => setFilterStatus(e.target.value)}
                  className="w-36"
                >
                  <option value="all">全部状态</option>
                  <option value="draft">草稿</option>
                  <option value="active">已发布</option>
                  <option value="archived">已归档</option>
                  <option value="disabled">已禁用</option>
                </Select>
              </div>
              <Button variant="outline" size="sm" onClick={fetchAgents}>
                <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
              </Button>
            </div>
          )}

          {/* Agent Grid */}
          {loading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
            </div>
          ) : displayAgents.length === 0 ? (
            <Card className="py-12">
              <div className="text-center">
                <Bot className="w-16 h-16 mx-auto mb-4 text-[var(--gray-200)]" />
                <h3 className="text-lg font-medium text-[var(--text-primary)] mb-1">
                  {activeTab === 'my' ? '暂无智能体' : '广场暂无内容'}
                </h3>
                <p className="text-[var(--text-secondary)] text-sm mb-4">
                  {activeTab === 'my'
                    ? '创建一个智能体开始使用吧'
                    : '还没有人分享智能体'}
                </p>
                {activeTab === 'my' && (
                  <Button onClick={() => setShowCreateModal(true)}>
                    <Plus className="w-4 h-4 mr-2" />
                    创建智能体
                  </Button>
                )}
              </div>
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {displayAgents.map((agent) => (
                <Card key={agent.id} hover className="cursor-pointer" onClick={() => handleChat(agent)}>
                  <CardHeader className="pb-3">
                    <div className="flex justify-between items-start">
                      <div className="flex items-center gap-3">
                        <div
                          className="w-12 h-12 rounded-lg flex items-center justify-center flex-shrink-0"
                          style={{
                            backgroundColor: getAvatarPalette(agent).bg,
                            color: getAvatarPalette(agent).icon,
                          }}
                        >
                          <Bot className="w-6 h-6" strokeWidth={1.75} />
                        </div>
                        <div className="min-w-0 flex-1">
                          <CardTitle className="text-base truncate">{agent.name}</CardTitle>
                          <div className="flex items-center gap-2 mt-1 flex-wrap">
                            <Badge variant={agent.status === 'active' ? 'success' : 'secondary'} size="sm">
                              {STATUS_LABELS[agent.status] || agent.status}
                            </Badge>
                            {agent.is_public && (
                              <Badge variant="info" size="sm" className="flex items-center gap-1">
                                <Share2 className="w-2.5 h-2.5" />
                                公开
                              </Badge>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  </CardHeader>
                  <CardBody>
                    <CardDescription className="text-sm text-[var(--text-secondary)] line-clamp-2 mb-3 min-h-[2.5rem]">
                      {agent.description || '暂无描述'}
                    </CardDescription>

                    <div className="flex items-center gap-4 text-xs text-[var(--text-tertiary)] mb-4">
                      <span className="flex items-center gap-1">
                        <MessageSquare className="w-3 h-3" />
                        {agent.total_runs}
                      </span>
                      <span className="flex items-center gap-1">
                        <Zap className="w-3 h-3" />
                        {(agent.total_tokens / 1000).toFixed(1)}k
                      </span>
                      <span className="flex items-center gap-1">
                        <Settings className="w-3 h-3" />
                        {agent.agent_type === 'single' ? '单体' : '多体'}
                      </span>
                    </div>

                    <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => handleChat(agent)}
                        className="flex-1 flex items-center justify-center gap-1"
                      >
                        <Play className="w-3 h-3" />
                        对话
                      </Button>
                      {activeTab === 'my' ? (
                        <>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => {
                              setSelectedAgent(agent);
                              setShowDetailModal(true);
                            }}
                          >
                            <Eye className="w-3 h-3" />
                          </Button>
                          {agent.status !== 'active' && (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => handlePublish(agent.id)}
                            >
                              发布
                            </Button>
                          )}
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleDuplicate(agent)}
                          >
                            <Copy className="w-3 h-3" />
                          </Button>
                          <Button
                            size="sm"
                            variant="danger"
                            onClick={() => handleDelete(agent.id)}
                          >
                            <Trash2 className="w-3 h-3" />
                          </Button>
                        </>
                      ) : (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleDuplicate(agent)}
                          className="flex-1"
                        >
                          复制到我的
                        </Button>
                      )}
                    </div>
                  </CardBody>
                </Card>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Create Modal */}
      <Modal
        open={showCreateModal}
        onOpenChange={(open) => {
          setShowCreateModal(open);
          if (!open) resetForm();
        }}
        title="创建智能体"
        description="配置智能体的基本信息和核心能力"
        width="700px"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowCreateModal(false)}>取消</Button>
            <Button variant="primary" onClick={handleCreate}>创建</Button>
          </>
        }
      >
        <div className="space-y-4 py-2">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>名称 *</Label>
              <Input
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="客服助手"
              />
            </div>
            <div>
              <Label>图标</Label>
              <Input
                value={formData.icon}
                onChange={(e) => setFormData({ ...formData, icon: e.target.value })}
                placeholder="🤖"
              />
            </div>
          </div>

          <div>
            <Label>描述</Label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder="这个智能体的用途..."
              rows={2}
              className="w-full enterprise-input"
            />
          </div>

          <div>
            <Label>类型</Label>
            <Select
              value={formData.agent_type}
              onChange={(e) => setFormData({ ...formData, agent_type: e.target.value as 'single' | 'multi' })}
              options={AGENT_TYPES}
            />
          </div>

          <div>
            <Label>系统提示词 *</Label>
            <textarea
              value={formData.system_prompt}
              onChange={(e) => setFormData({ ...formData, system_prompt: e.target.value })}
              placeholder="你是专业的客服助手，负责回答用户问题..."
              rows={4}
              className="w-full enterprise-input"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>记忆类型</Label>
              <Select
                value={formData.memory_type}
                onChange={(e) => setFormData({ ...formData, memory_type: e.target.value })}
                options={MEMORY_TYPES}
              />
            </div>
            <div>
              <Label>记忆时长 (小时)</Label>
              <Input
                type="number"
                value={formData.memory_ttl_hours}
                onChange={(e) => setFormData({ ...formData, memory_ttl_hours: parseInt(e.target.value) || 24 })}
              />
            </div>
          </div>

          <div>
            <Label>启用的 Skills</Label>
            <div className="text-xs text-gray-500 mb-2">选择智能体可调用的工具</div>
            <div className="flex flex-wrap gap-2">
              {['web_search', 'code_interpreter', 'file_processor', 'data_analysis'].map((skill) => (
                <label key={skill} className="flex items-center gap-2 text-sm cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.enabled_skills?.includes(skill)}
                    onChange={(e) => {
                      const newSkills = e.target.checked
                        ? [...(formData.enabled_skills || []), skill]
                        : (formData.enabled_skills || []).filter(s => s !== skill);
                      setFormData({ ...formData, enabled_skills: newSkills });
                    }}
                  />
                  {skill}
                </label>
              ))}
            </div>
          </div>

          <div>
            <Label>MCP Servers</Label>
            <Input
              value={formData.mcp_servers?.join(',') || ''}
              onChange={(e) => setFormData({
                ...formData,
                mcp_servers: e.target.value.split(',').filter(s => s.trim())
              })}
              placeholder="输入 MCP 服务器地址，用逗号分隔"
            />
            <div className="text-xs text-gray-500 mt-1">例如：http://localhost:8080,http://localhost:8081</div>
          </div>

          <div>
            <Label>默认模型配置</Label>
            <div className="text-xs text-gray-500 mb-2">设置智能体默认使用的模型（可选，不设置则在运行时选择）</div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label className="text-xs">供应商</Label>
                <Select
                  value={formData.default_model_config?.provider || ''}
                  onChange={(e) => {
                    const provider = e.target.value;
                    setFormData({
                      ...formData,
                      default_model_config: {
                        ...formData.default_model_config,
                        provider,
                        model: '',
                      },
                    });
                  }}
                  options={[
                    { value: '', label: '不设置（运行时选择）' },
                    ...modelProviders.map(p => ({ value: p.code, label: p.name })),
                  ]}
                />
              </div>
              <div>
                <Label className="text-xs">模型</Label>
                <Select
                  value={formData.default_model_config?.model || ''}
                  onChange={(e) => setFormData({
                    ...formData,
                    default_model_config: {
                      ...formData.default_model_config,
                      model: e.target.value,
                    },
                  })}
                  options={[
                    { value: '', label: '选择模型' },
                    ...modelConfigs
                      .filter(m => !formData.default_model_config?.provider || m.provider === formData.default_model_config?.provider)
                      .map(m => ({ value: m.model_id, label: m.name || m.model_id })),
                  ]}
                  disabled={!formData.default_model_config?.provider}
                />
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 pt-2">
            <Switch
              checked={formData.is_public}
              onCheckedChange={(checked) => setFormData({ ...formData, is_public: checked })}
            />
            <Label className="cursor-pointer">公开到广场（其他人可以查看和复制）</Label>
          </div>
        </div>
      </Modal>

      {/* Detail Modal */}
      {selectedAgent && (
        <Modal
          open={showDetailModal}
          onOpenChange={setShowDetailModal}
          title={selectedAgent.name}
          size="lg"
        >
          <div className="space-y-4">
            <div className="flex items-center gap-3 pb-3 border-b border-[var(--gray-200)]">
              <div className="w-16 h-16 rounded-xl bg-gradient-to-br from-[var(--primary)] to-[var(--accent)] flex items-center justify-center text-3xl flex-shrink-0">
                {selectedAgent.icon || '🤖'}
              </div>
              <div>
                <h3 className="text-xl font-bold text-[var(--text-primary)]">{selectedAgent.name}</h3>
                <p className="text-sm text-[var(--text-secondary)]">{selectedAgent.description}</p>
              </div>
            </div>

            <div>
              <Label className="text-sm font-semibold text-[var(--text-primary)]">系统提示词</Label>
              <div className="mt-2 p-3 bg-[var(--bg-primary)] rounded-lg text-sm whitespace-pre-wrap text-[var(--text-secondary)]">
                {selectedAgent.system_prompt}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="p-3 bg-[var(--bg-primary)] rounded-lg">
                <Label className="text-xs text-[var(--text-tertiary)]">运行次数</Label>
                <p className="text-2xl font-bold text-[var(--text-primary)] mt-1">{selectedAgent.total_runs}</p>
              </div>
              <div className="p-3 bg-[var(--bg-primary)] rounded-lg">
                <Label className="text-xs text-[var(--text-tertiary)]">Token 消耗</Label>
                <p className="text-2xl font-bold text-[var(--text-primary)] mt-1">{(selectedAgent.total_tokens / 1000).toFixed(1)}k</p>
              </div>
            </div>

            <div>
              <Label className="text-sm font-semibold text-[var(--text-primary)]">配置信息</Label>
              <div className="mt-2 space-y-2 text-sm">
                <div className="flex justify-between py-1.5 border-b border-[var(--gray-200)]">
                  <span className="text-[var(--text-tertiary)]">类型</span>
                  <span className="text-[var(--text-primary)]">{selectedAgent.agent_type === 'single' ? '单智能体' : '多智能体'}</span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-[var(--gray-200)]">
                  <span className="text-[var(--text-tertiary)]">记忆类型</span>
                  <span className="text-[var(--text-primary)]">{selectedAgent.memory_type}</span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-[var(--gray-200)]">
                  <span className="text-[var(--text-tertiary)]">记忆时长</span>
                  <span className="text-[var(--text-primary)]">{selectedAgent.memory_ttl_hours} 小时</span>
                </div>
                <div className="flex justify-between py-1.5">
                  <span className="text-[var(--text-tertiary)]">状态</span>
                  <Badge variant={selectedAgent.status === 'active' ? 'success' : 'secondary'}>
                    {STATUS_LABELS[selectedAgent.status] || selectedAgent.status}
                  </Badge>
                </div>
              </div>
            </div>
          </div>

          <div className="flex justify-end gap-2 mt-6 pt-4 border-t border-[var(--gray-200)]">
            <Button variant="outline" onClick={() => setShowDetailModal(false)}>
              关闭
            </Button>
            <Button onClick={() => {
              setShowDetailModal(false);
              handleChat(selectedAgent);
            }}>
              开始对话
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
}
