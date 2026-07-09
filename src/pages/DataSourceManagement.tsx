import { useState, useEffect } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { toast } from 'sonner';
import {
  Database, Globe, MessageSquare, Cloud, HardDrive, FileText,
  Plus, Search, RefreshCw, Trash2, Settings, Loader2,
  CheckCircle2, XCircle, AlertCircle, Clock, ExternalLink
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  DataSourceSnake as DataSource,
  DataSourcePresetSnake as DataSourcePreset,
  SyncJobSnake as SyncJob,
  fetchDataSources, fetchDataSourcesPresets, syncDataSource, getSyncJobStatus,
  deleteDataSource, updateDataSource, createDataSource, getSyncHistory,
  fetchKnowledgeBases
} from '@/lib/api-client';

const SOURCE_TYPE_LABELS: Record<string, string> = {
  local_file: '本地文件',
  web_page: '网页抓取',
  wechat_official: '微信公众号',
  database: '数据库',
  api: 'REST API',
  object_storage: '对象存储',
  sharepoint: 'SharePoint',
  confluence: 'Confluence',
  notion: 'Notion',
};

const SOURCE_TYPE_ICONS: Record<string, any> = {
  local_file: FileText,
  web_page: Globe,
  wechat_official: MessageSquare,
  database: Database,
  api: Cloud,
  object_storage: HardDrive,
  sharepoint: Cloud,
  confluence: FileText,
  notion: FileText,
};

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-green-50 text-green-600',
  inactive: 'bg-slate-100 text-slate-500',
  syncing: 'bg-blue-50 text-blue-600',
  error: 'bg-red-50 text-red-600',
  pending: 'bg-amber-50 text-amber-600',
};

const STATUS_LABELS: Record<string, string> = {
  active: '正常',
  inactive: '未激活',
  syncing: '同步中',
  error: '错误',
  pending: '待同步',
};

export function DataSourceManagement() {
  const { t } = useI18n();
  const [dataSources, setDataSources] = useState<DataSource[]>([]);
  const [presets, setPresets] = useState<DataSourcePreset[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncingId, setSyncingId] = useState<number | null>(null);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isPresetOpen, setIsPresetOpen] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState<DataSourcePreset | null>(null);
  const [filterType, setFilterType] = useState<string>('all');
  const [syncHistory, setSyncHistory] = useState<SyncJob[]>([]);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [viewingHistory, setViewingHistory] = useState<DataSource | null>(null);
  const [knowledgeBases, setKnowledgeBases] = useState<{ id: string; name: string }[]>([]);

  // Form state - using snake_case for API compatibility
  const [formData, setFormData] = useState<Partial<DataSourceSnake>>({
    name: '',
    source_type: 'web_page',
    description: '',
    kb_id: '' as unknown as number,
    sync_mode: 'manual',
    auto_process: true,
    enabled: true,
    config_json: {},
  });

  const loadDataSources = async () => {
    try {
      const data = await fetchDataSources();
      // Map camelCase API response to snake_case for component
      const snakeItems = data.items.map((item: any) => ({
        ...item,
        source_type: item.sourceType,
        kb_id: item.kbId,
        sync_mode: item.syncMode,
        auto_process: item.autoProcess,
        config_json: item.configJson,
        last_sync_at: item.lastSyncAt,
        last_sync_status: item.lastSyncStatus,
        sync_message: item.syncMessage,
        items_synced: item.itemsSynced,
        items_failed: item.itemsFailed,
        created_at: item.createdAt,
        updated_at: item.updatedAt,
      }));
      setDataSources(snakeItems);
    } catch (e: any) {
      console.error('Failed to load data sources:', e);
    } finally {
      setLoading(false);
    }
  };

  const loadPresets = async () => {
    try {
      const data = await fetchDataSourcesPresets();
      // Map camelCase API response to snake_case for component
      const snakePresets = data.map((item: any) => ({
        ...item,
        source_type: item.sourceType,
        config_template: item.configTemplate,
        use_cases: item.useCases,
      }));
      setPresets(snakePresets);
    } catch (e: any) {
      console.error('Failed to load presets:', e);
    }
  };

  const loadKnowledgeBases = async () => {
    try {
      const data = await fetchKnowledgeBases();
      setKnowledgeBases(data.items || []);
      // Set default KB if available
      if (data.items && data.items.length > 0 && !formData.kb_id) {
        setFormData((prev: Partial<DataSourceSnake>) => ({ ...prev, kb_id: data.items[0].id as unknown as number }));
      }
    } catch (e: any) {
      console.error('Failed to load knowledge bases:', e);
    }
  };

  useEffect(() => {
    loadDataSources();
    loadPresets();
    loadKnowledgeBases();
  }, []);

  const handleSync = async (sourceId: number) => {
    setSyncingId(sourceId);
    try {
      const job = await syncDataSource(sourceId, true);
      console.log('Sync job started:', job);

      // Poll for status with proper cleanup
      const pollInterval = setInterval(async () => {
        try {
          const status = await getSyncJobStatus(job.id);
          if (status.status === 'completed' || status.status === 'failed' || status.status === 'cancelled') {
            clearInterval(pollInterval);
            await loadDataSources();
            setSyncingId(null);
          }
          // Only clear syncing state when done, not on every poll
        } catch (err) {
          console.error('Polling error:', err);
          clearInterval(pollInterval);
          setSyncingId(null);
        }
      }, 2000);
    } catch (e: any) {
      console.error('Sync failed:', e);
      setSyncingId(null);
    }
  };

  const handleCreateFromPreset = (preset: DataSourcePreset) => {
    setSelectedPreset(preset);
    setFormData({
      name: preset.name,
      source_type: preset.source_type,
      description: preset.description,
      kb_id: '',
      sync_mode: 'manual',
      auto_process: true,
      enabled: true,
      config_json: preset.config_template,
    });
    setIsPresetOpen(false);
    setIsCreateOpen(true);
  };

  const handleCreate = async () => {
    try {
      await createDataSource({
        ...formData,
        configJson: formData.config_json || {},
      });
      setIsCreateOpen(false);
      loadDataSources();
      resetForm();
      toast.success('数据源创建成功');
    } catch (e: any) {
      toast.error(`创建失败：${e.message}`);
    }
  };

  const handleDelete = async (sourceId: number) => {
    if (!window.confirm('确定要删除此数据源吗？')) return;
    try {
      await deleteDataSource(sourceId);
      loadDataSources();
      toast.success('数据源已删除');
    } catch (e: any) {
      toast.error(`删除失败：${e.message}`);
    }
  };

  const handleToggleEnabled = async (sourceId: number, current: boolean) => {
    try {
      await updateDataSource(sourceId, { enabled: !current });
      loadDataSources();
      toast.success(current ? '已禁用' : '已启用');
    } catch (e: any) {
      toast.error(`设置失败：${e.message}`);
    }
  };

  const handleViewHistory = async (source: DataSource) => {
    setViewingHistory(source);
    try {
      const history = await getSyncHistory(source.id);
      setSyncHistory(history);
      setIsHistoryOpen(true);
    } catch (e: any) {
      toast.error(`加载历史失败：${e.message}`);
    }
  };

  const resetForm = () => {
    setFormData({
      name: '',
      source_type: 'web_page',
      description: '',
      kb_id: '',
      sync_mode: 'manual',
      auto_process: true,
      enabled: true,
      config_json: {},
    });
    setSelectedPreset(null);
  };

  const filteredDataSources = filterType === 'all'
    ? dataSources
    : dataSources.filter(ds => ds.source_type === filterType);

  const renderConfigFields = () => {
    const config = formData.config_json || {};

    if (formData.source_type === 'web_page') {
      return (
        <div className="space-y-4">
          <div className="space-y-2">
            <Label className="text-sm font-semibold">起始 URL</Label>
            <Input
              value={config.urls?.[0] || ''}
              onChange={(e) => setFormData({
                ...formData,
                config_json: { ...config, urls: [e.target.value] },
              })}
              placeholder="https://example.com"
              className="rounded-xl h-10"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label className="text-sm font-semibold">最大深度</Label>
              <Input
                type="number"
                value={config.max_depth || 1}
                onChange={(e) => setFormData({
                  ...formData,
                  config_json: { ...config, max_depth: parseInt(e.target.value) },
                })}
                className="rounded-xl h-10"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-sm font-semibold">内容选择器</Label>
              <Input
                value={config.content_selector || 'article'}
                onChange={(e) => setFormData({
                  ...formData,
                  config_json: { ...config, content_selector: e.target.value },
                })}
                placeholder="article, .content"
                className="rounded-xl h-10"
              />
            </div>
          </div>
        </div>
      );
    }

    if (formData.source_type === 'database') {
      return (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label className="text-sm font-semibold">数据库类型</Label>
              <Select
                value={config.db_type || 'mysql'}
                onValueChange={(v) => setFormData({
                  ...formData,
                  config_json: { ...config, db_type: v },
                })}
              >
                <SelectTrigger className="rounded-xl h-10">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="rounded-xl">
                  <SelectItem value="mysql">MySQL</SelectItem>
                  <SelectItem value="postgresql">PostgreSQL</SelectItem>
                  <SelectItem value="sqlserver">SQL Server</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="text-sm font-semibold">表名</Label>
              <Input
                value={config.table_name || ''}
                onChange={(e) => setFormData({
                  ...formData,
                  config_json: { ...config, table_name: e.target.value },
                })}
                placeholder="table_name"
                className="rounded-xl h-10"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label className="text-sm font-semibold">主机</Label>
              <Input
                value={config.host || 'localhost'}
                onChange={(e) => setFormData({
                  ...formData,
                  config_json: { ...config, host: e.target.value },
                })}
                placeholder="localhost"
                className="rounded-xl h-10"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-sm font-semibold">端口</Label>
              <Input
                type="number"
                value={config.port || ''}
                onChange={(e) => setFormData({
                  ...formData,
                  config_json: { ...config, port: parseInt(e.target.value) },
                })}
                placeholder="3306"
                className="rounded-xl h-10"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label className="text-sm font-semibold">数据库名</Label>
              <Input
                value={config.database || ''}
                onChange={(e) => setFormData({
                  ...formData,
                  config_json: { ...config, database: e.target.value },
                })}
                placeholder="database"
                className="rounded-xl h-10"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-sm font-semibold">用户名</Label>
              <Input
                value={config.username || ''}
                onChange={(e) => setFormData({
                  ...formData,
                  config_json: { ...config, username: e.target.value },
                })}
                placeholder="root"
                className="rounded-xl h-10"
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label className="text-sm font-semibold">密码</Label>
            <Input
              type="password"
              value={config.password || ''}
              onChange={(e) => setFormData({
                ...formData,
                config_json: { ...config, password: e.target.value },
              })}
              placeholder="password"
              className="rounded-xl h-10"
            />
          </div>
        </div>
      );
    }

    if (formData.source_type === 'wechat_official') {
      return (
        <div className="space-y-4">
          <div className="space-y-2">
            <Label className="text-sm font-semibold">公众号名称</Label>
            <Input
              value={config.account_name || ''}
              onChange={(e) => setFormData({
                ...formData,
                config_json: { ...config, account_name: e.target.value },
              })}
              placeholder="公众号名称"
              className="rounded-xl h-10"
            />
          </div>
          <div className="space-y-2">
            <Label className="text-sm font-semibold">Cookie (可选)</Label>
            <Input
              value={config.cookie || ''}
              onChange={(e) => setFormData({
                ...formData,
                config_json: { ...config, cookie: e.target.value },
              })}
              type="password"
              placeholder="用于认证"
              className="rounded-xl h-10"
            />
          </div>
          <div className="space-y-2">
            <Label className="text-sm font-semibold">最大文章数</Label>
            <Input
              type="number"
              value={config.max_articles || 100}
              onChange={(e) => setFormData({
                ...formData,
                config_json: { ...config, max_articles: parseInt(e.target.value) },
              })}
              className="rounded-xl h-10"
            />
          </div>
        </div>
      );
    }

    if (formData.source_type === 'api') {
      return (
        <div className="space-y-4">
          <div className="space-y-2">
            <Label className="text-sm font-semibold">Base URL</Label>
            <Input
              value={config.base_url || ''}
              onChange={(e) => setFormData({
                ...formData,
                config_json: { ...config, base_url: e.target.value },
              })}
              placeholder="https://api.example.com"
              className="rounded-xl h-10"
            />
          </div>
          <div className="space-y-2">
            <Label className="text-sm font-semibold">API 端点</Label>
            <Input
              value={config.endpoint || ''}
              onChange={(e) => setFormData({
                ...formData,
                config_json: { ...config, endpoint: e.target.value },
              })}
              placeholder="/v1/items"
              className="rounded-xl h-10"
            />
          </div>
          <div className="space-y-2">
            <Label className="text-sm font-semibold">数据路径</Label>
            <Input
              value={config.data_path || 'data'}
              onChange={(e) => setFormData({
                ...formData,
                config_json: { ...config, data_path: e.target.value },
              })}
              placeholder="data"
              className="rounded-xl h-10"
            />
          </div>
        </div>
      );
    }

    // Default / local_file
    return (
      <p className="text-sm text-slate-500">
        本地文件可通过知识库的文档上传功能直接添加
      </p>
    );
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-[#F8FAFC]">
      {/* Header */}
      <header className="h-20 px-8 bg-white/80 backdrop-blur-md border-b border-slate-200/60 flex items-center justify-between shrink-0 z-10">
        <div className="space-y-1">
          <h1 className="text-xl font-bold tracking-tight text-slate-900">多源知识接入</h1>
          <p className="text-[13px] text-slate-500">支持网页、公众号、数据库、API 等多种数据源，打破企业数据孤岛</p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setIsPresetOpen(true)}
            className="rounded-xl shadow-sm border-slate-200 hover:bg-slate-50 font-medium"
          >
            <Plus className="w-4 h-4 mr-2" />
            从预设创建
          </Button>
          <Button
            size="sm"
            onClick={() => setIsCreateOpen(true)}
            className="bg-[#1677ff] hover:bg-[#0958d9] rounded-xl shadow-sm font-medium transition-colors"
          >
            <Plus className="w-4 h-4 mr-2" />
            新建数据源
          </Button>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto p-8">
        {/* Filters */}
        <div className="mb-6 flex items-center gap-2">
          <Select value={filterType} onValueChange={setFilterType}>
            <SelectTrigger className="w-[200px] rounded-xl h-10 border-slate-200">
              <SelectValue placeholder="筛选类型" />
            </SelectTrigger>
            <SelectContent className="rounded-xl">
              <SelectItem value="all">全部类型</SelectItem>
              {Object.entries(SOURCE_TYPE_LABELS).map(([key, label]) => (
                <SelectItem key={key} value={key}>{label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Data Sources Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {loading ? (
            <div className="col-span-full flex items-center justify-center py-20">
              <Loader2 className="w-8 h-8 animate-spin text-[#1677ff]" />
            </div>
          ) : filteredDataSources.length === 0 ? (
            <div className="col-span-full flex flex-col items-center justify-center py-20 text-center">
              <Database className="w-16 h-16 text-slate-300 mb-4" />
              <h3 className="text-lg font-semibold text-slate-700">暂无数据源</h3>
              <p className="text-slate-500 text-sm mt-1">从预设创建或手动配置第一个数据源</p>
            </div>
          ) : (
            filteredDataSources.map((source) => {
              const SourceIcon = SOURCE_TYPE_ICONS[source.source_type] || Database;
              return (
                <Card key={source.id} className="relative overflow-hidden rounded-2xl border-slate-200/60 hover:shadow-lg transition-shadow">
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-3">
                        <div className={cn(
                          "w-10 h-10 rounded-xl flex items-center justify-center",
                          source.status === 'active' ? 'bg-green-50 text-green-600' :
                          source.status === 'error' ? 'bg-red-50 text-red-600' :
                          source.status === 'syncing' ? 'bg-blue-50 text-blue-600' :
                          'bg-slate-100 text-slate-500'
                        )}>
                          <SourceIcon className="w-5 h-5" />
                        </div>
                        <div>
                          <CardTitle className="text-base font-semibold">{source.name}</CardTitle>
                          <CardDescription className="text-xs">
                            {SOURCE_TYPE_LABELS[source.source_type]}
                          </CardDescription>
                        </div>
                      </div>
                      <Badge
                        className={cn("text-xs rounded-lg", STATUS_COLORS[source.status])}
                      >
                        {STATUS_LABELS[source.status]}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {source.description && (
                      <p className="text-xs text-slate-500 line-clamp-2">{source.description}</p>
                    )}

                    <div className="flex items-center justify-between text-xs text-slate-500">
                      <span>已同步：{source.items_synced} 条</span>
                      {source.items_failed > 0 && (
                        <span className="text-red-500">失败：{source.items_failed}</span>
                      )}
                    </div>

                    {source.last_sync_at && (
                      <p className="text-xs text-slate-400">
                        上次同步：{new Date(source.last_sync_at).toLocaleString('zh-CN')}
                      </p>
                    )}

                    <div className="flex items-center gap-2 pt-2 border-t border-slate-100">
                      <Button
                        size="sm"
                        variant="outline"
                        className="flex-1 h-8 text-xs rounded-lg"
                        onClick={() => handleSync(source.id)}
                        disabled={syncingId === source.id || !source.enabled}
                      >
                        {syncingId === source.id ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" />
                        ) : (
                          <RefreshCw className="w-3.5 h-3.5 mr-1" />
                        )}
                        同步
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-8 w-8 p-0 rounded-lg"
                        onClick={() => handleViewHistory(source)}
                      >
                        <Clock className="w-4 h-4 text-slate-600" />
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-8 w-8 p-0 rounded-lg"
                        onClick={() => handleDelete(source.id)}
                      >
                        <Trash2 className="w-4 h-4 text-red-500" />
                      </Button>
                    </div>

                    <div className="flex items-center justify-between pt-2 border-t border-slate-100">
                      <div className="flex items-center gap-2">
                        <Switch
                          checked={source.enabled}
                          onCheckedChange={() => handleToggleEnabled(source.id, source.enabled)}
                          className="scale-75"
                        />
                        <span className="text-xs text-slate-600">启用</span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              );
            })
          )}
        </div>
      </div>

      {/* Preset Selection Dialog */}
      <Dialog open={isPresetOpen} onOpenChange={setIsPresetOpen}>
        <DialogContent className="max-w-7xl max-h-[85vh] overflow-y-auto rounded-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl font-bold">选择数据源类型</DialogTitle>
            <DialogDescription className="pt-2 text-slate-600">
              选择预配置的数据源模板快速开始
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 py-4">
            {presets.map((preset) => {
              const PresetIcon = SOURCE_TYPE_ICONS[preset.source_type] || Database;
              return (
                <Card
                  key={preset.id}
                  className="cursor-pointer hover:border-[#1677ff] hover:shadow-md transition-all rounded-xl"
                  onClick={() => handleCreateFromPreset(preset)}
                >
                  <CardHeader className="pb-2">
                    <div className="flex items-center gap-2 mb-2">
                      <div className="w-8 h-8 rounded-lg bg-[#1677ff]/10 text-[#1677ff] flex items-center justify-center">
                        <PresetIcon className="w-4 h-4" />
                      </div>
                      <CardTitle className="text-base">{preset.name}</CardTitle>
                    </div>
                    <CardDescription className="text-xs line-clamp-2">
                      {preset.description}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="flex flex-wrap gap-1">
                      {preset.use_cases.slice(0, 3).map((use) => (
                        <Badge key={use} variant="secondary" className="text-xs rounded-lg">
                          {use}
                        </Badge>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </DialogContent>
      </Dialog>

      {/* Create Data Source Dialog */}
      <Dialog open={isCreateOpen} onOpenChange={(open) => {
        setIsCreateOpen(open);
        if (!open) resetForm();
      }}>
        <DialogContent className="max-w-5xl max-h-[85vh] overflow-y-auto rounded-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl font-bold">
              {selectedPreset ? `配置：${selectedPreset.name}` : '新建数据源'}
            </DialogTitle>
            <DialogDescription className="pt-2 text-slate-600">
              填写数据源连接和采集配置
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label className="text-sm font-semibold">数据源名称</Label>
                <Input
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="如：公司产品文档"
                  className="rounded-xl h-10"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-sm font-semibold">目标知识库</Label>
                <Select
                  value={formData.kb_id}
                  onValueChange={(v) => setFormData({ ...formData, kb_id: v })}
                >
                  <SelectTrigger className="rounded-xl h-10">
                    <SelectValue placeholder="选择知识库" />
                  </SelectTrigger>
                  <SelectContent className="rounded-xl">
                    {knowledgeBases.map((kb) => (
                      <SelectItem key={kb.id} value={kb.id}>{kb.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label className="text-sm font-semibold">数据类型</Label>
                <Select
                  value={formData.source_type}
                  onValueChange={(v) => setFormData({ ...formData, source_type: v })}
                >
                  <SelectTrigger className="rounded-xl h-10">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="rounded-xl">
                    {Object.entries(SOURCE_TYPE_LABELS).map(([key, label]) => (
                      <SelectItem key={key} value={key}>{label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label className="text-sm font-semibold">描述</Label>
              <Input
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="可选描述"
                className="rounded-xl h-10"
              />
            </div>

            {/* Type-specific config */}
            {renderConfigFields()}

            {/* Sync Settings */}
            <div className="pt-4 border-t border-slate-100 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-sm font-semibold">自动处理</Label>
                  <p className="text-xs text-slate-500">同步后自动进行向量化处理</p>
                </div>
                <Switch
                  checked={formData.auto_process}
                  onCheckedChange={(v) => setFormData({ ...formData, auto_process: v })}
                />
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-sm font-semibold">启用</Label>
                  <p className="text-xs text-slate-500">禁用后将不会执行同步</p>
                </div>
                <Switch
                  checked={formData.enabled}
                  onCheckedChange={(v) => setFormData({ ...formData, enabled: v })}
                />
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="ghost" onClick={() => setIsCreateOpen(false)} className="rounded-xl">取消</Button>
            <Button className="bg-[#1677ff] hover:bg-[#0958d9] rounded-xl" onClick={handleCreate}>
              创建
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Sync History Dialog */}
      <Dialog open={isHistoryOpen} onOpenChange={setIsHistoryOpen}>
        <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto rounded-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl font-bold">同步历史</DialogTitle>
            <DialogDescription className="pt-2 text-slate-600">
              {viewingHistory?.name} - 最近同步记录
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-4">
            {syncHistory.length === 0 ? (
              <p className="text-center text-slate-500 py-8">暂无同步记录</p>
            ) : (
              syncHistory.map((job) => (
                <Card key={job.id} className="rounded-xl">
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        {job.status === 'completed' ? (
                          <CheckCircle2 className="w-5 h-5 text-green-600" />
                        ) : job.status === 'failed' ? (
                          <XCircle className="w-5 h-5 text-red-600" />
                        ) : job.status === 'running' ? (
                          <RefreshCw className="w-5 h-5 text-blue-600 animate-spin" />
                        ) : (
                          <Clock className="w-5 h-5 text-slate-400" />
                        )}
                        <div>
                          <p className="text-sm font-medium">
                            {job.status === 'completed' ? '同步完成' :
                             job.status === 'failed' ? '同步失败' :
                             job.status === 'running' ? '同步中...' :
                             job.status}
                          </p>
                          <p className="text-xs text-slate-500">
                            {new Date(job.created_at).toLocaleString('zh-CN')}
                          </p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="text-sm font-medium">
                          成功：{job.items_synced} | 失败：{job.items_failed}
                        </p>
                        {job.progress_percent > 0 && job.progress_percent < 100 && (
                          <p className="text-xs text-slate-500">进度：{job.progress_percent}%</p>
                        )}
                      </div>
                    </div>
                    {job.error_message && (
                      <p className="text-xs text-red-500 mt-2">{job.error_message}</p>
                    )}
                  </CardContent>
                </Card>
              ))
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
