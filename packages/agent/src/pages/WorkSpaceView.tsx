import { useState, useEffect, useRef } from 'react';
import { toast } from 'sonner';
import { FolderOpen, FileText, Upload, Trash2, History, HardDrive, Download } from 'lucide-react';
import { Button } from '@/src/components/enterprise/Button';
import { Card, CardHeader, CardTitle, CardBody } from '@/src/components/enterprise/Card';
import { Badge } from '@/src/components/enterprise/Badge';
import { Modal } from '@/src/components/enterprise/Modal';
import { Table, TableBody, TableCell, TableHeader, TableRow } from '@/src/components/enterprise/Table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/src/components/enterprise/Tabs';
import { getApiUrl } from '@/src/lib/env';
import { useAuth } from '@/src/lib/auth-context';
import { fetchApi } from '@/lib/api-client';

interface Workspace {
  id: string;
  user_id: number;
  root_path: string;
  storage_quota_bytes: number;
  storage_used_bytes: number;
  storage_used_percent: number;
  status: string;
  is_isolated?: boolean;
  created_at: string;
}

interface WorkspaceFile {
  id: string;
  filename: string;
  relative_path: string;
  file_size: number;
  mime_type: string | null;
  source_type: string;
  is_sandbox_generated: boolean;
  scan_status: string;
  created_at: string;
}

interface AuditLog {
  id: number;
  action: string;
  file_path: string;
  file_size: number | null;
  success: boolean;
  user_id: number | null;
  created_at: string;
}

const fmtBytes = (n: number): string => {
  if (!n) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(1)} ${units[i]}`;
};

const fmtTime = (s?: string): string => (s ? new Date(s).toLocaleString() : '-');

export function WorkSpaceView() {
  const { token } = useAuth();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [files, setFiles] = useState<WorkspaceFile[]>([]);
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [preview, setPreview] = useState<{ file: WorkspaceFile; content: string } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<WorkspaceFile | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    try {
      const ws = await fetchApi<Workspace>('/api/v1/workspaces/me');
      setWorkspace(ws);
      const [fl, lg] = await Promise.all([
        fetchApi<{ files: WorkspaceFile[] }>(`/api/v1/workspaces/${ws.id}/files`),
        fetchApi<{ logs: AuditLog[] }>(`/api/v1/workspaces/${ws.id}/audit-logs`).catch(() => ({ logs: [] })),
      ]);
      setFiles(fl.files || []);
      setLogs(lg.logs || []);
    } catch (e: any) {
      toast.error(`加载工作空间失败：${e?.message || ''}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [token]);

  const openFilePicker = () => fileInputRef.current?.click();

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file || !workspace) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      await fetchApi(`/api/v1/workspaces/${workspace.id}/files`, { method: 'POST', body: formData });
      toast.success('上传成功');
      await load();
    } catch (err: any) {
      toast.error(err?.message || '上传失败');
    } finally {
      setUploading(false);
    }
  };

  const previewFile = async (f: WorkspaceFile) => {
    try {
      const res = await fetch(getApiUrl(`/api/v1/workspaces/${workspace?.id}/files/${f.id}`), {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) { toast.error('获取文件失败'); return; }
      const blob = await res.blob();
      const text = await blob.text();
      setPreview({ file: f, content: text.length > 50000 ? text.slice(0, 50000) + '\n…(截断)' : text });
    } catch (e: any) {
      toast.error(`预览失败：${e?.message || ''}`);
    }
  };

  const downloadFile = async (f: WorkspaceFile) => {
    try {
      const res = await fetch(getApiUrl(`/api/v1/workspaces/${workspace?.id}/files/${f.id}`), {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) { toast.error('下载失败'); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = f.filename; a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      toast.error(`下载失败：${e?.message || ''}`);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget || !workspace) return;
    try {
      await fetchApi(`/api/v1/workspaces/${workspace.id}/files/${deleteTarget.id}`, { method: 'DELETE' });
      toast.success('已删除');
      setDeleteTarget(null);
      await load();
    } catch (e: any) {
      toast.error(`删除失败：${e?.message || ''}`);
    }
  };

  if (loading) return <div className="p-8 text-sm text-[#9b9b9b]">加载中…</div>;

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      <div className="p-5 flex-1 overflow-y-auto">
        <div className="flex items-center gap-2 mb-4">
          <FolderOpen className="w-5 h-5 text-[#534ab7]" />
          <h1 className="text-[15px] font-medium text-[var(--text-primary)]">工作空间</h1>
        </div>

        {workspace && (
          <Card className="mb-5">
            <CardHeader className="flex items-center justify-between">
              <CardTitle className="text-sm">空间信息</CardTitle>
              <Badge variant={workspace.status === 'active' ? 'success' : 'neutral'}>{workspace.status}</Badge>
            </CardHeader>
            <CardBody className="space-y-2 text-xs">
              <div className="flex justify-between"><span className="text-[#9b9b9b]">根路径</span><span className="font-mono">{workspace.root_path}</span></div>
              <div className="flex justify-between items-center">
                <span className="text-[#9b9b9b]">存储用量</span>
                <span>{fmtBytes(workspace.storage_used_bytes)} / {fmtBytes(workspace.storage_quota_bytes)} ({workspace.storage_used_percent.toFixed(1)}%)</span>
              </div>
              <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
                <div className="h-full" style={{ width: `${Math.min(workspace.storage_used_percent, 100)}%`, background: '#534ab7' }} />
              </div>
              <div className="flex justify-between"><span className="text-[#9b9b9b]">创建时间</span><span>{fmtTime(workspace.created_at)}</span></div>
            </CardBody>
          </Card>
        )}

        <Tabs defaultValue="files">
          <TabsList>
            <TabsTrigger value="files"><FileText className="w-3.5 h-3.5 mr-1" />文件</TabsTrigger>
            <TabsTrigger value="logs"><History className="w-3.5 h-3.5 mr-1" />审计日志</TabsTrigger>
          </TabsList>

          <TabsContent value="files" className="pt-4">
            <div className="mb-3">
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                onChange={handleFileSelect}
              />
              <Button variant="primary" size="sm" icon={<Upload className="w-3.5 h-3.5" />} onClick={openFilePicker} loading={uploading}>
                上传文件
              </Button>
            </div>
            <Card padding="none">
              <Table hover size="sm">
                <TableHeader>
                  <TableRow>
                    <TableCell variant="header">文件名</TableCell>
                    <TableCell variant="header">路径</TableCell>
                    <TableCell variant="header">大小</TableCell>
                    <TableCell variant="header">类型</TableCell>
                    <TableCell variant="header">来源</TableCell>
                    <TableCell variant="header">时间</TableCell>
                    <TableCell variant="header" className="text-right">操作</TableCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {files.length === 0 && (
                    <TableRow><TableCell colSpan={7} className="text-center text-xs text-[#9b9b9b] py-8">暂无文件</TableCell></TableRow>
                  )}
                  {files.map((f) => (
                    <TableRow key={f.id}>
                      <TableCell className="font-medium">{f.filename}</TableCell>
                      <TableCell className="font-mono text-xs">{f.relative_path}</TableCell>
                      <TableCell>{fmtBytes(f.file_size)}</TableCell>
                      <TableCell>{f.mime_type || '-'}</TableCell>
                      <TableCell><Badge variant="neutral" size="sm">{f.source_type}</Badge></TableCell>
                      <TableCell className="text-xs">{fmtTime(f.created_at)}</TableCell>
                      <TableCell className="text-right space-x-1">
                        <Button variant="ghost" size="sm" onClick={() => previewFile(f)}>查看</Button>
                        <Button variant="ghost" size="sm" onClick={() => downloadFile(f)}><Download className="w-3.5 h-3.5" /></Button>
                        <Button variant="ghost" size="sm" onClick={() => setDeleteTarget(f)}>
                          <Trash2 className="w-3.5 h-3.5 text-red-500" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Card>
          </TabsContent>

          <TabsContent value="logs" className="pt-4">
            <Card padding="none">
              <Table hover size="sm">
                <TableHeader>
                  <TableRow>
                    <TableCell variant="header">操作</TableCell>
                    <TableCell variant="header">文件路径</TableCell>
                    <TableCell variant="header">大小</TableCell>
                    <TableCell variant="header">状态</TableCell>
                    <TableCell variant="header">时间</TableCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {logs.length === 0 && (
                    <TableRow><TableCell colSpan={5} className="text-center text-xs text-[#9b9b9b] py-8">暂无审计日志</TableCell></TableRow>
                  )}
                  {logs.map((l) => (
                    <TableRow key={l.id}>
                      <TableCell><Badge variant="secondary" size="sm">{l.action}</Badge></TableCell>
                      <TableCell className="font-mono text-xs">{l.file_path}</TableCell>
                      <TableCell>{l.file_size != null ? fmtBytes(l.file_size) : '-'}</TableCell>
                      <TableCell><Badge variant={l.success ? 'success' : 'error'} size="sm">{l.success ? '成功' : '失败'}</Badge></TableCell>
                      <TableCell className="text-xs">{fmtTime(l.created_at)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Card>
          </TabsContent>
        </Tabs>
      </div>

      {/* 文件内容预览 */}
      <Modal
        open={!!preview}
        onOpenChange={(o) => { if (!o) setPreview(null); }}
        title={preview?.file.filename || '文件预览'}
        description={`${preview?.file.mime_type || 'text/plain'} · ${preview ? fmtBytes(preview.file.file_size) : ''}`}
      >
        <pre className="max-h-80 overflow-auto text-xs bg-gray-50 p-3 rounded whitespace-pre-wrap break-all">
          {preview?.content}
        </pre>
      </Modal>

      {/* 删除确认 */}
      <Modal
        open={!!deleteTarget}
        onOpenChange={(o) => { if (!o) setDeleteTarget(null); }}
        title="删除文件"
        description={`确定删除「${deleteTarget?.filename}」吗？此操作不可恢复。`}
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={() => setDeleteTarget(null)}>取消</Button>
            <Button variant="danger" size="sm" onClick={confirmDelete}>删除</Button>
          </div>
        }
      />
    </div>
  );
}

export default WorkSpaceView;
