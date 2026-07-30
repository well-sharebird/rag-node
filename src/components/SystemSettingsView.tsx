import { useState, useEffect } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { toast } from 'sonner';
import { Button } from '@/src/components/enterprise/Button';
import { Input } from '@/src/components/enterprise/Input';
import { Select } from '@/src/components/enterprise/Select';
import { Modal } from '@/src/components/enterprise/Modal';
import { Card, CardHeader, CardTitle, CardBody } from '@/src/components/enterprise/Card';
import { Badge } from '@/src/components/enterprise/Badge';
import { Switch } from '@/src/components/enterprise/Switch';
import { Save, History, AlertCircle, Scissors, Search, ShieldCheck, CheckCircle, FileText, Code, List, Layers, Type, Link } from 'lucide-react';
import { cn } from '@/lib/utils';
import { fetchSettings, updateSettings } from '@/lib/api-client';

// 分块策略说明数据
const CHUNK_STRATEGIES: Record<string, {
  icon: React.ElementType;
  title: string;
  description: string;
  pros: string[];
  cons: string[];
  recommended: string[];
}> = {
  recursive: {
    icon: Layers,
    title: '递归字符拆分',
    description: '按优先级尝试多种分隔符（段落→行→句子→词），尽量保持语义完整性。最常用的通用拆分策略。',
    pros: ['保持语义完整', '适应性强', '效果稳定'],
    cons: ['块大小不均匀'],
    recommended: ['文档文章', '技术文档', '通用场景'],
  },
  fixed: {
    icon: Type,
    title: '固定长度拆分',
    description: '按固定字符数切分，简单快速但可能切断句子。适合对速度要求高的场景。',
    pros: ['简单快速', '块大小均匀', '易于预测'],
    cons: ['可能切断语义', '上下文不连贯'],
    recommended: ['日志文件', '结构化数据', '快速原型'],
  },
  semantic: {
    icon: FileText,
    title: '语义拆分',
    description: '基于文本语义相似度检测边界，块内语义最连贯。计算开销较大，适合高质量问答。',
    pros: ['语义连贯性最好', '检索质量高'],
    cons: ['计算开销大', '需要多次嵌入'],
    recommended: ['问答系统', '复杂文档', '高质量场景'],
  },
  markdown: {
    icon: List,
    title: 'Markdown 结构拆分',
    description: '按 Markdown 标题层级拆分，保留文档结构。适合技术文档和 API 文档。',
    pros: ['保留文档结构', '层级清晰'],
    cons: ['仅适用于 Markdown'],
    recommended: ['API 文档', '技术手册', 'Wiki 文档'],
  },
  code: {
    icon: Code,
    title: '代码结构拆分',
    description: '按代码函数/类结构拆分，保留导入语句和上下文。适合代码库检索。',
    pros: ['保持代码完整性', '保留上下文'],
    cons: ['仅适用于代码'],
    recommended: ['代码库', '脚本文件', '编程文档'],
  },
  parent_child: {
    icon: Link,
    title: '父子块分块',
    description: '创建小块用于索引，同时关联大块提供完整上下文。兼顾检索精度和生成质量，是高级 RAG 系统的理想选择。',
    pros: ['检索精准', '上下文完整', '平衡性好'],
    cons: ['实现复杂', '存储开销大'],
    recommended: ['复杂问答', '高精度场景', '企业知识库'],
  },
};

function StrategyDescription({ strategy }: { strategy: string }) {
  const config = CHUNK_STRATEGIES[strategy] || CHUNK_STRATEGIES.recursive;
  const Icon = config.icon;

  return (
    <div className="p-4 bg-[var(--gray-50)] border border-[var(--gray-200)] rounded-xl space-y-3">
      <div className="flex items-center gap-2">
        <Icon className="w-4 h-4 text-[var(--primary)]" />
        <span className="text-[14px] font-medium text-[var(--text-primary)]">{config.title}</span>
      </div>
      <p className="text-[13px] text-[var(--text-secondary)]">{config.description}</p>
      <div className="grid grid-cols-3 gap-3">
        <div>
          <div className="text-[11px] font-medium text-green-600 mb-1">优点</div>
          <ul className="space-y-0.5">
            {config.pros.map((p, i) => (
              <li key={i} className="text-[11px] text-[var(--text-secondary)]">• {p}</li>
            ))}
          </ul>
        </div>
        <div>
          <div className="text-[11px] font-medium text-yellow-600 mb-1">缺点</div>
          <ul className="space-y-0.5">
            {config.cons.map((c, i) => (
              <li key={i} className="text-[11px] text-[var(--text-secondary)]">• {c}</li>
            ))}
          </ul>
        </div>
        <div>
          <div className="text-[11px] font-medium text-blue-600 mb-1">推荐场景</div>
          <ul className="space-y-0.5">
            {config.recommended.map((r, i) => (
              <li key={i} className="text-[11px] text-[var(--text-secondary)]">• {r}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

function apiToDraft(settings: Record<string, any>) {
  const c = settings.chunking || {};
  const r = settings.retrieval || {};
  const s = settings.security || {};
  return {
    chunkStrategy: c.strategy || 'recursive',
    chunkSize: String(c.chunk_size || 512),
    chunkOverlap: String(c.chunk_overlap || 50),
    parentChunkSize: String(c.parent_chunk_size || 1024),
    separators: (c.separators || ['\n\n', '\n', '.']).join(', '),
    // 文件类型路由配置
    fileTypeRoutes: JSON.stringify(c.file_type_routes || {}, null, 2),
    topK: String(r.default_top_k || 10),
    minScore: String(r.default_min_score ?? 0.6),
    enableRerank: r.enable_rerank ?? true,
    rerankTopN: String(r.rerank_top_n || 3),
    maxSize: `${s.max_upload_size_mb || 50}MB`,
    formats: (s.allowed_formats || ['pdf', 'docx', 'txt', 'md', 'html']).join(','),
    rateLimit: `${s.rate_limit_per_minute || 100}/min`,
    timeout: String(s.search_timeout_ms || 5000),
    logs: String(s.log_retention_days || 30),
  };
}

function draftToApi(d: Record<string, any>) {
  // Parse file type routes from JSON
  let fileTypeRoutes = {};
  try {
    fileTypeRoutes = JSON.parse(d.fileTypeRoutes || '{}');
  } catch (e) {
    console.warn('Invalid file type routes JSON, using empty object');
  }

  return {
    chunking: {
      strategy: d.chunkStrategy,
      chunk_size: parseInt(String(d.chunkSize), 10) || 512,
      chunk_overlap: parseInt(String(d.chunkOverlap), 10) || 50,
      parent_chunk_size: d.chunkStrategy === 'parent_child' ? parseInt(String(d.parentChunkSize), 10) || 1024 : undefined,
      separators: d.separators.split(',').map((s: string) => s.trim()).filter(Boolean),
      file_type_routes: fileTypeRoutes,
    },
    retrieval: {
      default_top_k: parseInt(String(d.topK), 10) || 10,
      default_min_score: parseFloat(String(d.minScore)) || 0.6,
      enable_rerank: d.enableRerank,
      rerank_top_n: parseInt(String(d.rerankTopN), 10) || 3,
    },
    security: {
      max_upload_size_mb: parseInt(String(d.maxSize), 10) || 50,
      allowed_formats: d.formats.split(',').map((s: string) => s.trim()).filter(Boolean),
      rate_limit_per_minute: parseInt(String(d.rateLimit), 10) || 100,
      search_timeout_ms: parseInt(String(d.timeout), 10) || 5000,
      log_retention_days: parseInt(String(d.logs), 10) || 30,
    },
  };
}

export function SystemSettingsView() {
  const { t } = useI18n();
  const [hasChanges, setHasChanges] = useState(false);
  const [isPublishOpen, setIsPublishOpen] = useState(false);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('chunk');
  const [settingsVersion, setSettingsVersion] = useState('v--');
  const [publishedAt, setPublishedAt] = useState('--');
  const [saving, setSaving] = useState(false);

  const [draft, setDraft] = useState({
    chunkStrategy: 'recursive',
    chunkSize: '512',
    chunkOverlap: '50',
    parentChunkSize: '1024',
    separators: '\\n\\n, \\n, .',
    fileTypeRoutes: JSON.stringify({
      'pdf': { strategy: 'semantic', chunk_size: 512, chunk_overlap: 0.2 },
      'docx': { strategy: 'semantic', chunk_size: 512, chunk_overlap: 0.2 },
      'md': { strategy: 'hierarchical', chunk_size: 512, chunk_overlap: 0.15 },
      'py': { strategy: 'ast', chunk_size: 512, chunk_overlap: 0.1 },
      'xlsx': { strategy: 'table', chunk_size: 1024, chunk_overlap: 0.1 },
    }, null, 2),
    topK: '10',
    minScore: '0.6',
    enableRerank: true,
    rerankTopN: '3',
    maxSize: '50MB',
    formats: 'pdf,docx,txt,md,html',
    rateLimit: '100/min',
    timeout: '5000',
    logs: '30',
  });

  useEffect(() => {
    fetchSettings()
      .then((data) => {
        setDraft(apiToDraft(data.settings));
        setSettingsVersion(`v${data.version}`);
        if (data.publishedAt) {
          setPublishedAt(new Date(data.publishedAt).toLocaleString());
        }
      })
      .catch(() => {});
  }, []);

  const handleChange = (key: keyof typeof draft, value: any) => {
    setDraft(prev => ({ ...prev, [key]: value }));
    setHasChanges(true);
  };

  const handleSaveDraft = async () => {
    setSaving(true);
    try {
      await updateSettings(draftToApi(draft));
      setHasChanges(false);
      toast.success('草稿已保存');
    } catch (err: any) {
      toast.error(err.message || '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const handlePublish = async () => {
    setSaving(true);
    try {
      await updateSettings(draftToApi(draft));
      setHasChanges(false);
      setIsPublishOpen(false);
      toast.success('配置已发布');
      fetchSettings().then((data) => {
        setSettingsVersion(`v${data.version}`);
        if (data.publishedAt) {
          setPublishedAt(new Date(data.publishedAt).toLocaleString());
        }
      });
    } catch (err: any) {
      toast.error(err.message || '发布失败');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    fetchSettings().then((data) => {
      setDraft(apiToDraft(data.settings));
      setHasChanges(false);
      toast.success('已重置为线上配置');
    });
  };

  const tabs = [
    { id: 'chunk', label: '分块策略', icon: Scissors },
    { id: 'retrieval', label: '检索参数', icon: Search },
    { id: 'security', label: '系统安全', icon: ShieldCheck },
  ];

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-white">
      {/* Header */}
      <header className="h-[60px] px-6 bg-white flex items-center justify-between shrink-0 border-b border-[var(--sidebar-border)]">
        <div className="flex items-baseline gap-3">
          <h1 className="text-[18px] font-semibold text-[var(--text-primary)]">{t('settings.title')}</h1>
          <span className="text-[13px] text-[var(--text-tertiary)]">{t('settings.desc')}</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-[var(--gray-100)] rounded-lg">
            <span className="text-[12px] text-[var(--text-secondary)]">版本</span>
            <Badge variant="primary">{settingsVersion}</Badge>
            <span className="text-[12px] text-[var(--text-tertiary)] ml-2">发布于 {publishedAt}</span>
          </div>
          <Button variant="secondary" size="md" onClick={() => setIsHistoryOpen(true)}>
            <History className="w-4 h-4 mr-2" />
            历史版本
          </Button>
          {hasChanges && (
            <Button variant="primary" size="md" onClick={handleSaveDraft} disabled={saving}>
              <Save className="w-4 h-4 mr-2" />
              {saving ? '保存中...' : '保存草稿'}
            </Button>
          )}
          <Button
            variant="primary"
            size="md"
            onClick={() => setIsPublishOpen(true)}
            disabled={!hasChanges && saving}
          >
            发布变更
          </Button>
        </div>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-4xl mx-auto">
          {/* Tabs */}
          <div className="flex gap-2 mb-6 p-1 bg-[var(--gray-100)] rounded-lg w-fit">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  "flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md transition-colors",
                  activeTab === tab.id
                    ? "bg-[var(--card-bg)] text-[var(--text-primary)] shadow-sm"
                    : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                )}
              >
                <tab.icon className="w-4 h-4" />
                {tab.label}
              </button>
            ))}
          </div>

          {/* Chunk Settings */}
          {activeTab === 'chunk' && (
            <Card>
              <CardHeader>
                <CardTitle>分块策略</CardTitle>
              </CardHeader>
              <CardBody>
                <div className="space-y-5">
                  <div className="space-y-3">
                    <label className="text-[14px] font-medium text-[var(--text-secondary)]">
                      分块策略
                    </label>
                    <Select
                      value={draft.chunkStrategy}
                      onChange={(e) => handleChange('chunkStrategy', e.target.value)}
                      className="w-full"
                    >
                      <option value="recursive">递归字符拆分（推荐）</option>
                      <option value="fixed">固定长度拆分</option>
                      <option value="semantic">语义拆分</option>
                      <option value="markdown">Markdown 结构拆分</option>
                      <option value="code">代码结构拆分</option>
                      <option value="parent_child">父子块分块</option>
                    </Select>
                    <StrategyDescription strategy={draft.chunkStrategy} />
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <label className="text-[14px] font-medium text-[var(--text-secondary)]">
                        块大小 (chunk_size)
                      </label>
                      <Input
                        type="number"
                        value={draft.chunkSize}
                        onChange={(e) => handleChange('chunkSize', e.target.value)}
                      />
                      <p className="text-[12px] text-[var(--text-tertiary)]">每个文本块的最大 tokens 数</p>
                    </div>

                    <div className="space-y-2">
                      <label className="text-[14px] font-medium text-[var(--text-secondary)]">
                        重叠度 (overlap)
                      </label>
                      <Input
                        type="number"
                        value={draft.chunkOverlap}
                        onChange={(e) => handleChange('chunkOverlap', e.target.value)}
                      />
                      <p className="text-[12px] text-[var(--text-tertiary)]">相邻块之间的重叠 tokens 数</p>
                    </div>
                  </div>

                  {draft.chunkStrategy === 'parent_child' && (
                    <div className="space-y-2">
                      <label className="text-[14px] font-medium text-[var(--text-secondary)]">
                        父块大小 (parent_chunk_size)
                      </label>
                      <Input
                        type="number"
                        value={draft.parentChunkSize}
                        onChange={(e) => handleChange('parentChunkSize', e.target.value)}
                      />
                      <p className="text-[12px] text-[var(--text-tertiary)]">父块用于提供完整上下文，建议设置为块大小的 2 倍</p>
                    </div>
                  )}

                  <div className="space-y-2">
                    <label className="text-[14px] font-medium text-[var(--text-secondary)]">
                      分隔符列表
                    </label>
                    <Input
                      value={draft.separators}
                      onChange={(e) => handleChange('separators', e.target.value)}
                      placeholder="\\n\\n, \\n, ."
                    />
                    <p className="text-[12px] text-[var(--text-tertiary)]">逗号分隔，用于语义分块时的切分依据</p>
                  </div>

                  {/* 文件类型路由配置 */}
                  <div className="space-y-2">
                    <label className="text-[14px] font-medium text-[var(--text-secondary)]">
                      文件类型路由映射表
                    </label>
                    <textarea
                      value={draft.fileTypeRoutes}
                      onChange={(e) => handleChange('fileTypeRoutes', e.target.value)}
                      className="w-full min-h-[200px] p-3 font-mono text-[12px] bg-[var(--gray-50)] border border-[var(--gray-200)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
                      placeholder='{"pdf": {"strategy": "semantic", "chunk_size": 512, "chunk_overlap": 0.2}}'
                    />
                    <p className="text-[12px] text-[var(--text-tertiary)]">
                      JSON 格式，定义文件扩展名到分块策略的映射。系统将根据文件类型自动选择最优分块策略。
                      <br />
                      支持策略：fixed, recursive, semantic, ast, hierarchical, table
                    </p>
                  </div>
                </div>
              </CardBody>
            </Card>
          )}

          {/* Retrieval Settings */}
          {activeTab === 'retrieval' && (
            <Card>
              <CardHeader>
                <CardTitle>检索参数</CardTitle>
              </CardHeader>
              <CardBody>
                <div className="space-y-5">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <label className="text-[14px] font-medium text-[var(--text-secondary)]">
                        默认 Top-K
                      </label>
                      <Input
                        type="number"
                        value={draft.topK}
                        onChange={(e) => handleChange('topK', e.target.value)}
                      />
                      <p className="text-[12px] text-[var(--text-tertiary)]">每次检索返回的 chunk 数量</p>
                    </div>

                    <div className="space-y-2">
                      <label className="text-[14px] font-medium text-[var(--text-secondary)]">
                        默认相似度阈值
                      </label>
                      <Input
                        type="number"
                        step="0.01"
                        value={draft.minScore}
                        onChange={(e) => handleChange('minScore', e.target.value)}
                      />
                      <p className="text-[12px] text-[var(--text-tertiary)]">低于此分数的结果不返回，0 表示不过滤</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-3 p-4 bg-[var(--gray-50)] rounded-xl">
                    <Switch
                      checked={draft.enableRerank}
                      onCheckedChange={(v) => handleChange('enableRerank', v)}
                    />
                    <div className="flex-1">
                      <label className="text-[14px] font-medium text-[var(--text-primary)]">
                        启用重排序
                      </label>
                      <p className="text-[12px] text-[var(--text-tertiary)]">是否对检索结果进行二次精排</p>
                    </div>
                  </div>

                  {draft.enableRerank && (
                    <div className="space-y-2">
                      <label className="text-[14px] font-medium text-[var(--text-secondary)]">
                        重排后 Top-N
                      </label>
                      <Input
                        type="number"
                        value={draft.rerankTopN}
                        onChange={(e) => handleChange('rerankTopN', e.target.value)}
                      />
                      <p className="text-[12px] text-[var(--text-tertiary)]">重排后最终返回的数量，通常≤Top-K</p>
                    </div>
                  )}
                </div>
              </CardBody>
            </Card>
          )}

          {/* Security Settings */}
          {activeTab === 'security' && (
            <Card>
              <CardHeader>
                <CardTitle>系统安全</CardTitle>
              </CardHeader>
              <CardBody>
                <div className="space-y-5">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <label className="text-[14px] font-medium text-[var(--text-secondary)]">
                        最大上传文件大小
                      </label>
                      <Input
                        value={draft.maxSize}
                        onChange={(e) => handleChange('maxSize', e.target.value)}
                        placeholder="50MB"
                      />
                      <p className="text-[12px] text-[var(--text-tertiary)]">单文件大小上限</p>
                    </div>

                    <div className="space-y-2">
                      <label className="text-[14px] font-medium text-[var(--text-secondary)]">
                        支持的文件格式
                      </label>
                      <Input
                        value={draft.formats}
                        onChange={(e) => handleChange('formats', e.target.value)}
                        placeholder="pdf,docx,txt,md,html"
                      />
                      <p className="text-[12px] text-[var(--text-tertiary)]">逗号分隔的 MIME 类型列表</p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <label className="text-[14px] font-medium text-[var(--text-secondary)]">
                        API 限流配置
                      </label>
                      <Input
                        value={draft.rateLimit}
                        onChange={(e) => handleChange('rateLimit', e.target.value)}
                        placeholder="100/min"
                      />
                      <p className="text-[12px] text-[var(--text-tertiary)]">每用户/每 API Key 的 QPS 上限</p>
                    </div>

                    <div className="space-y-2">
                      <label className="text-[14px] font-medium text-[var(--text-secondary)]">
                        检索超时时间
                      </label>
                      <Input
                        type="number"
                        value={draft.timeout}
                        onChange={(e) => handleChange('timeout', e.target.value)}
                        placeholder="5000"
                      />
                      <p className="text-[12px] text-[var(--text-tertiary)]">单次检索的最大等待时间 (ms)</p>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <label className="text-[14px] font-medium text-[var(--text-secondary)]">
                      日志保留天数
                    </label>
                    <Input
                      type="number"
                      value={draft.logs}
                      onChange={(e) => handleChange('logs', e.target.value)}
                      placeholder="30"
                    />
                    <p className="text-[12px] text-[var(--text-tertiary)]">检索日志的保存周期</p>
                  </div>
                </div>
              </CardBody>
            </Card>
          )}

          {/* Reset Button */}
          <div className="mt-6 flex justify-end">
            <Button variant="ghost" onClick={handleReset}>
              重置为线上配置
            </Button>
          </div>
        </div>
      </div>

      {/* Publish Modal */}
      <Modal
        open={isPublishOpen}
        onOpenChange={setIsPublishOpen}
        title="发布变更"
        description="此配置将影响所有知识库。部分关键配置（如嵌入模型）可能需重新向量化才能生效。"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsPublishOpen(false)} disabled={saving}>取消</Button>
            <Button variant="primary" onClick={handlePublish} disabled={saving}>
              {saving ? '发布中...' : '确认发布'}
            </Button>
          </>
        }
      >
        <div className="py-4 space-y-4">
          <div className="flex items-start gap-3 p-4 bg-[var(--warning-bg)] border border-[var(--warning)] rounded-xl">
            <AlertCircle className="w-5 h-5 text-[var(--warning)] mt-0.5" />
            <div>
              <h4 className="text-[14px] font-medium text-[var(--text-primary)] mb-1">
                发布前请确认
              </h4>
              <ul className="text-[13px] text-[var(--text-secondary)] space-y-1">
                <li>• 当前配置将应用到所有知识库</li>
                <li>• 嵌入模型等关键配置可能需要重新向量化</li>
                <li>• 发布后无法快速回滚，请谨慎操作</li>
              </ul>
            </div>
          </div>
        </div>
      </Modal>

      {/* History Modal */}
      <Modal
        open={isHistoryOpen}
        onOpenChange={setIsHistoryOpen}
        title="配置历史版本"
        description="查看和恢复历史配置版本"
        footer={
          <Button variant="secondary" onClick={() => setIsHistoryOpen(false)}>关闭</Button>
        }
      >
        <div className="py-4 space-y-3">
          {[
            { version: 'v3', date: '2024-01-15 10:30:00', author: 'Admin' },
            { version: 'v2', date: '2024-01-10 14:20:00', author: 'Admin' },
            { version: 'v1', date: '2024-01-01 09:00:00', author: 'System' },
          ].map((item) => (
            <div
              key={item.version}
              className={cn(
                "flex items-center justify-between p-4 rounded-xl border",
                item.version === settingsVersion
                  ? "bg-[var(--accent-light)] border-[var(--primary-light)]"
                  : "bg-[var(--card-bg)] border-[var(--card-border)]"
              )}
            >
              <div className="flex items-center gap-3">
                <div className={cn(
                  "w-8 h-8 rounded-lg flex items-center justify-center",
                  item.version === settingsVersion
                    ? "bg-[var(--primary)] text-white"
                    : "bg-[var(--gray-100)] text-[var(--text-secondary)]"
                )}>
                  <CheckCircle className="w-4 h-4" />
                </div>
                <div>
                  <div className="text-[14px] font-medium text-[var(--text-primary)]">
                    {item.version}
                  </div>
                  <div className="text-[12px] text-[var(--text-tertiary)]">
                    {item.date} · {item.author}
                  </div>
                </div>
              </div>
              {item.version !== settingsVersion && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    toast.info('恢复功能开发中');
                  }}
                >
                  恢复此版本
                </Button>
              )}
            </div>
          ))}
        </div>
      </Modal>
    </div>
  );
}
