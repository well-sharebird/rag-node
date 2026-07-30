import { useState, useEffect } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { Button, Card, CardHeader, CardBody, CardTitle, CardDescription, Badge, Input, Modal, Switch } from '@/src/components/enterprise';
import { Select } from '@/src/components/enterprise/Select';
import { Table, TableHeader, TableBody, TableRow, TableCell } from '@/src/components/enterprise/Table';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import {
  Database, Globe, MessageSquare, Cloud, HardDrive, FileText,
  Plus, Search, RefreshCw, Trash2, Settings, Loader2,
  CheckCircle2, XCircle, AlertCircle, Clock, ExternalLink
} from 'lucide-react';
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

const STATUS_BADGE: Record<string, { variant: 'success' | 'neutral' | 'primary' | 'error' | 'warning', label: string }> = {
  active: { variant: 'success', label: '正常' },
  inactive: { variant: 'neutral', label: '未激活' },
  syncing: { variant: 'primary', label: '同步中' },
  error: { variant: 'error', label: '错误' },
  pending: { variant: 'warning', label: '待同步' },
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

  const [formData, setFormData] = useState<Partial<DataSource>>({
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
      setDataSources(data.items || []);
    } catch (e: any) {
      console.error('Failed to load data sources:', e);
    } finally {
      setLoading(false);
    }
  };

  const loadPresets = async () => {
    try {
      const data = await fetchDataSourcesPresets();
      setPresets(data || []);
    } catch (e: any) {
      console.error('Failed to load presets:', e);
    }
  };

  const loadKnowledgeBases = async () => {
    try {
      const data = await fetchKnowledgeBases();
      setKnowledgeBases(data.items || []);
      if (data.items && data.items.length > 0 && !formData.kb_id) {
        setFormData((prev) => ({ ...prev, kb_id: data.items[0].id as unknown as number }));
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
      const pollInterval = setInterval(async () => {
        try {
          const status = await getSyncJobStatus(job.id);
          if (['completed', 'failed', 'cancelled'].includes(status.status)) {
            clearInterval(pollInterval);
            await loadDataSources();
            setSyncingId(null);
          }
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
      kb_id: '' as unknown as number,
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
      await createDataSource(formData);
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

  const resetForm = () => {
    setFormData({
      name: '',
      source_type: 'web_page',
      description: '',
      kb_id: '' as unknown as number,
      sync_mode: 'manual',
      auto_process: true,
      enabled: true,
      config_json: {},
    });
    setSelectedPreset(null);
  };

  const filteredSources = filterType === 'all'
    ? dataSources
    : dataSources.filter(ds => ds.source_type === filterType);

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-white">
      {/* Header */}
      <header className="h-[60px] px-6 bg-white flex items-center justify-between shrink-0 border-b border-[var(--gray-200)]">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-[var(--accent-light)] flex items-center justify-center">
            <Database className="w-5 h-5 text-[var(--accent)]" />
          </div>
          <div>
            <h1 className="text-[18px] font-semibold text-[var(--text-primary)]">数据源管理</h1>
            <p className="text-[12px] text-[var(--text-secondary)]">管理外部数据源和同步任务</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            onClick={() => setIsPresetOpen(true)}
            icon={<Plus className="w-4 h-4" />}
          >
            从预设创建
          </Button>
          <Button
            onClick={() => setIsCreateOpen(true)}
            className="bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white"
            icon={<Plus className="w-4 h-4" />}
          >
            新建数据源
          </Button>
        </div>
      </header>

      {/* Filters */}
      <div className="px-6 py-4 bg-white border-b border-[var(--gray-200)]">
        <div className="flex gap-3">
          <div className="flex-1 relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)]" />
            <Input placeholder="搜索数据源..." />
          </div>
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="enterprise-select w-[180px]"
          >
            <option value="all">所有类型</option>
            {Object.entries(SOURCE_TYPE_LABELS).map(([key, label]) => (
              <option key={key} value={key}>{label}</option>
            ))}
          </select>
          <Button variant="secondary" onClick={loadDataSources} icon={<RefreshCw className="w-4 h-4" />}>
            刷新
          </Button>
        </div>
      </div>

      {/* Data Sources Table */}
      <div className="flex-1 overflow-y-auto p-6">
        <Card>
          <CardBody className="p-0">
            {loading ? (
              <div className="flex justify-center py-12">
                <Loader2 className="w-8 h-8 animate-spin text-[var(--text-tertiary)]" />
              </div>
            ) : filteredSources.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-[var(--text-tertiary)]">
                <Database className="w-12 h-12 mb-4" />
                <p className="text-[14px]">暂无数据源</p>
              </div>
            ) : (
              <Table hover>
                <TableHeader>
                  <TableRow>
                    <TableCell className="font-medium">名称</TableCell>
                    <TableCell className="font-medium">类型</TableCell>
                    <TableCell className="font-medium">知识库</TableCell>
                    <TableCell className="font-medium">同步模式</TableCell>
                    <TableCell className="font-medium">状态</TableCell>
                    <TableCell className="font-medium text-right">操作</TableCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredSources.map((ds) => {
                    const Icon = SOURCE_TYPE_ICONS[ds.source_type] || Database;
                    const status = STATUS_BADGE[ds.status] || STATUS_BADGE.inactive;
                    return (
                      <TableRow key={ds.id}>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <div className="w-8 h-8 rounded-lg bg-[var(--gray-100)] flex items-center justify-center">
                              <Icon className="w-4 h-4 text-[var(--text-secondary)]" />
                            </div>
                            <div>
                              <div className="font-medium text-[var(--text-primary)]">{ds.name}</div>
                              {ds.description && (
                                <div className="text-[11px] text-[var(--text-tertiary)] truncate max-w-[200px]">{ds.description}</div>
                              )}
                            </div>
                          </div>
                        </TableCell>
                        <TableCell>
                          <Badge variant="neutral" size="sm">{SOURCE_TYPE_LABELS[ds.source_type] || ds.source_type}</Badge>
                        </TableCell>
                        <TableCell className="text-[var(--text-secondary)]">
                          {knowledgeBases.find(kb => kb.id === String(ds.kb_id))?.name || '-'}
                        </TableCell>
                        <TableCell>
                          <Badge variant={ds.sync_mode === 'auto' ? 'success' : 'neutral'} size="sm">
                            {ds.sync_mode === 'auto' ? '自动' : '手动'}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <Badge variant={status.variant} size="sm">{status.label}</Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex items-center justify-end gap-1">
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={() => handleSync(ds.id)}
                              disabled={syncingId === ds.id}
                              icon={syncingId === ds.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                            >
                              {syncingId === ds.id ? '同步中' : '同步'}
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              icon={<Settings className="w-3.5 h-3.5" />}
                            />
                            <Button
                              variant="danger"
                              size="sm"
                              onClick={() => handleDelete(ds.id)}
                              icon={<Trash2 className="w-3.5 h-3.5" />}
                            />
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
          </CardBody>
        </Card>
      </div>

      {/* Preset Modal */}
      <Modal
        open={isPresetOpen}
        onOpenChange={setIsPresetOpen}
        title="从预设创建数据源"
        className="max-w-4xl"
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 py-4">
          {presets.map((preset) => {
            const Icon = SOURCE_TYPE_ICONS[preset.source_type] || Database;
            return (
              <Card
                key={preset.id}
                className="cursor-pointer hover:border-[var(--accent)] hover:shadow-md transition-all"
                onClick={() => handleCreateFromPreset(preset)}
              >
                <CardBody>
                  <div className="flex items-center gap-3 mb-2">
                    <div className="w-10 h-10 rounded-xl bg-[var(--gray-100)] flex items-center justify-center">
                      <Icon className="w-5 h-5 text-[var(--text-secondary)]" />
                    </div>
                    <div>
                      <div className="font-medium text-[var(--text-primary)]">{preset.name}</div>
                      <div className="text-[11px] text-[var(--text-tertiary)]">{SOURCE_TYPE_LABELS[preset.source_type]}</div>
                    </div>
                  </div>
                  <p className="text-[12px] text-[var(--text-secondary)] line-clamp-2">{preset.description}</p>
                </CardBody>
              </Card>
            );
          })}
        </div>
      </Modal>

      {/* Create Modal */}
      <Modal
        open={isCreateOpen}
        onOpenChange={(open) => {
          setIsCreateOpen(open);
          if (!open) resetForm();
        }}
        title={selectedPreset ? `配置：${selectedPreset.name}` : '新建数据源'}
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsCreateOpen(false)}>取消</Button>
            <Button onClick={handleCreate} className="bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white">
              创建
            </Button>
          </>
        }
      >
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <label className="text-[12px] font-medium text-[var(--text-secondary)]">名称</label>
            <Input
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              placeholder="请输入名称"
            />
          </div>
          <div className="space-y-2">
            <label className="text-[12px] font-medium text-[var(--text-secondary)]">描述</label>
            <Input
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder="请输入描述"
            />
          </div>
          <div className="space-y-2">
            <label className="text-[12px] font-medium text-[var(--text-secondary)]">知识库</label>
            <Select
              value={String(formData.kb_id)}
              onChange={(e) => setFormData({ ...formData, kb_id: e.target.value as unknown as number })}
              className="w-full"
            >
              <option value="">选择知识库</option>
              {knowledgeBases.map(kb => (
                <option key={kb.id} value={kb.id}>{kb.name}</option>
              ))}
            </Select>
          </div>
          <div className="space-y-2">
            <label className="text-[12px] font-medium text-[var(--text-secondary)]">同步模式</label>
            <Select
              value={formData.sync_mode}
              onChange={(e) => setFormData({ ...formData, sync_mode: e.target.value as 'manual' | 'auto' })}
              className="w-full"
            >
              <option value="manual">手动同步</option>
              <option value="auto">自动同步</option>
            </Select>
          </div>
          <div className="flex items-center justify-between py-2">
            <label className="text-[14px] font-medium text-[var(--text-secondary)]">启用数据源</label>
            <Switch
              checked={formData.enabled}
              onCheckedChange={(checked) => setFormData({ ...formData, enabled: checked })}
            />
          </div>
        </div>
      </Modal>
    </div>
  );
}
