import { useState, useEffect } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { useAuth } from '@/src/lib/auth-context';
import { Button, Card, CardHeader, CardBody, CardTitle, CardDescription, Input, Badge, Modal, Switch, Table, TableHeader, TableBody, TableRow, TableCell } from '@/src/components/enterprise';
import { Select } from '@/src/components/enterprise/Select';
import { toast } from 'sonner';
import {
  Shield, Plus, Search, RefreshCw, Trash2, Settings, Loader2, Edit2,
  CheckCircle2, XCircle, Menu as MenuIcon, Key, Users
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  RoleData, fetchRoles, createRole, updateRole, deleteRole,
  fetchMenus, assignMenusToRole, MenuData
} from '@/lib/api-client';

const ROLE_ICONS: Record<string, any> = {
  Admin: Shield,
  Editor: Settings,
  Viewer: Users,
  Developer: Key,
};

export function RoleManagement() {
  const { t } = useI18n();
  const { user, isAuthenticated } = useAuth();
  const [roles, setRoles] = useState<RoleData[]>([]);
  const [menus, setMenus] = useState<MenuData[]>([]);
  const [loading, setLoading] = useState(true);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [isMenusOpen, setIsMenusOpen] = useState(false);
  const [selectedRole, setSelectedRole] = useState<RoleData | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedMenuIds, setSelectedMenuIds] = useState<number[]>([]);

  // 角色表单数据
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    isSystem: false,
  });

  // 检查是否为管理员
  const isAdmin = user?.roles?.some(r => r.name === 'Admin' || r.name === 'super_admin');

  const loadRoles = async () => {
    try {
      const data = await fetchRoles();
      console.log('Roles loaded:', data);
      const items = Array.isArray(data.items) ? data.items : [];
      setRoles(items);
    } catch (e: any) {
      console.error('Failed to load roles:', e);
      toast.error(`加载角色失败：${e.message}`);
      setRoles([]);
    } finally {
      setLoading(false);
    }
  };

  const loadMenus = async () => {
    try {
      const data = await fetchMenus();
      console.log('Menus loaded:', data);
      const items = Array.isArray(data.items) ? data.items : [];
      setMenus(items);
    } catch (e: any) {
      console.error('Failed to load menus:', e);
      setMenus([]);
    }
  };

  useEffect(() => {
    if (!isAuthenticated) {
      toast.error('请先登录');
      setLoading(false);
      return;
    }
    if (!isAdmin) {
      toast.error('需要管理员权限才能访问此页面');
      setLoading(false);
      return;
    }
    loadRoles();
    loadMenus();
  }, [isAuthenticated, isAdmin]);

  const handleCreateRole = async () => {
    try {
      if (!formData.name) {
        toast.error('角色名称不能为空');
        return;
      }
      await createRole(formData.name, formData.description || undefined);
      toast.success('角色创建成功');
      setIsCreateOpen(false);
      setFormData({ name: '', description: '', isSystem: false });
      loadRoles();
    } catch (e: any) {
      console.error('Failed to create role:', e);
      toast.error(`创建角色失败：${e.message}`);
    }
  };

  const handleUpdateRole = async () => {
    if (!selectedRole) return;
    try {
      await updateRole(selectedRole.id, {
        name: formData.name,
        description: formData.description,
      });
      toast.success('角色更新成功');
      setIsEditOpen(false);
      loadRoles();
    } catch (e: any) {
      console.error('Failed to update role:', e);
      toast.error(`更新角色失败：${e.message}`);
    }
  };

  const handleDeleteRole = async (role: RoleData) => {
    if (role.isSystem) {
      toast.error('系统角色不能删除');
      return;
    }
    if (!confirm(`确定要删除角色 "${role.name}" 吗？`)) return;
    try {
      await deleteRole(role.id);
      toast.success('角色删除成功');
      loadRoles();
    } catch (e: any) {
      console.error('Failed to delete role:', e);
      toast.error(`删除角色失败：${e.message}`);
    }
  };

  const openEditDialog = (role: RoleData) => {
    setSelectedRole(role);
    setFormData({
      name: role.name,
      description: role.description || '',
      isSystem: role.isSystem || false,
    });
    setIsEditOpen(true);
  };

  const openMenusDialog = (role: RoleData) => {
    setSelectedRole(role);
    // TODO: 加载角色已有的菜单 ID
    setSelectedMenuIds([]);
    setIsMenusOpen(true);
  };

  const handleAssignMenus = async () => {
    if (!selectedRole) return;
    try {
      await assignMenusToRole(selectedRole.id, selectedMenuIds);
      toast.success('菜单权限分配成功');
      setIsMenusOpen(false);
      loadRoles();
    } catch (e: any) {
      console.error('Failed to assign menus:', e);
      toast.error(`分配菜单失败：${e.message}`);
    }
  };

  // 递归渲染菜单树
  const renderMenuTree = (menuList: MenuData[], level = 0) => {
    return menuList.map((menu) => (
      <div key={menu.id}>
        <div
          className={cn(
            "flex items-center gap-2.5 py-2 px-3 rounded-md cursor-pointer transition-colors",
            selectedMenuIds.includes(menu.id)
              ? "bg-[var(--accent-light)]"
              : "hover:bg-[var(--bg-primary)]"
          )}
          style={{ marginLeft: `${level * 20}px` }}
          onClick={() => {
            if (selectedMenuIds.includes(menu.id)) {
              setSelectedMenuIds(selectedMenuIds.filter(id => id !== menu.id));
            } else {
              setSelectedMenuIds([...selectedMenuIds, menu.id]);
            }
          }}
        >
          <input
            type="checkbox"
            checked={selectedMenuIds.includes(menu.id)}
            onChange={(e) => {
              e.stopPropagation();
              if (selectedMenuIds.includes(menu.id)) {
                setSelectedMenuIds(selectedMenuIds.filter(id => id !== menu.id));
              } else {
                setSelectedMenuIds([...selectedMenuIds, menu.id]);
              }
            }}
            onClick={(e) => e.stopPropagation()}
            className="enterprise-checkbox flex-shrink-0"
          />
          <span className={cn(
            "text-sm flex-shrink-0",
            level === 0 ? "font-medium text-[var(--text-primary)]" : "text-[var(--text-secondary)]"
          )}>{menu.name}</span>
          {menu.menu_type === 'menu' && (
            <Badge variant="secondary" className="text-xs flex-shrink-0">目录</Badge>
          )}
          {menu.menu_type === 'sub_menu' && (
            <Badge variant="outline" className="text-xs flex-shrink-0">菜单</Badge>
          )}
          {menu.menu_type === 'button' && (
            <Badge variant="neutral" className="text-xs flex-shrink-0">按钮</Badge>
          )}
          {!menu.is_visible && (
            <Badge variant="neutral" className="text-xs flex-shrink-0">隐藏</Badge>
          )}
          {menu.path && (
            <span className="text-xs text-[var(--text-tertiary)] ml-auto truncate">{menu.path}</span>
          )}
        </div>
        {menu.children && menu.children.length > 0 && renderMenuTree(menu.children, level + 1)}
      </div>
    ));
  };

  if (!isAuthenticated) {
    return (
      <div className="p-6 space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Shield className="w-5 h-5 text-[var(--warning)]" />
              需要登录
            </CardTitle>
            <CardDescription>
              请先登录以访问角色管理页面
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <div className="p-6 space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Shield className="w-5 h-5 text-[var(--error)]" />
              需要管理员权限
            </CardTitle>
            <CardDescription>
              此页面仅限管理员访问。当前用户角色：{user?.roles?.map(r => r.name).join(', ') || '无'}
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  const filteredRoles = roles.filter(role =>
    role.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (role.description && role.description.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  return (
    <div className="p-6 space-y-5 bg-white min-h-screen">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-[var(--accent-light)] flex items-center justify-center">
            <Shield className="w-5 h-5 text-[var(--accent)]" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-[var(--text-primary)]">角色管理</h1>
            <p className="text-sm text-[var(--text-secondary)] mt-0.5">
              共 {filteredRoles.length} 个角色 · 管理系统角色和权限配置
            </p>
          </div>
        </div>
        <Button
          onClick={() => setIsCreateOpen(true)}
          icon={<Plus className="w-4 h-4" />}
        >
          创建角色
        </Button>
      </div>

      {/* Filters */}
      <div className="flex gap-3 items-center">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text-tertiary)]" />
          <Input
            placeholder="搜索角色名称或描述..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>
        <Button variant="secondary" onClick={loadRoles} icon={<RefreshCw className="w-4 h-4" />}>
          刷新
        </Button>
      </div>

      {/* Roles Table */}
      {loading ? (
        <div className="flex justify-center py-16">
          <Loader2 className="w-8 h-8 animate-spin text-[var(--text-tertiary)]" />
        </div>
      ) : filteredRoles.length === 0 ? (
        <Card>
          <CardBody className="py-16 text-center">
            <Shield className="w-12 h-12 mx-auto mb-4 opacity-50 text-[var(--text-tertiary)]" />
            <p className="text-[var(--text-secondary)] mb-4">暂无角色</p>
            <Button variant="secondary" onClick={() => setIsCreateOpen(true)} icon={<Plus className="w-4 h-4" />}>
              创建第一个角色
            </Button>
          </CardBody>
        </Card>
      ) : (
        <Card>
          <Table hover>
            <TableHeader>
              <TableRow>
                <TableCell variant="header" className="text-left py-3 px-4 text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">角色</TableCell>
                <TableCell variant="header" className="text-left py-3 px-4 text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">类型</TableCell>
                <TableCell variant="header" className="text-left py-3 px-4 text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">描述</TableCell>
                <TableCell variant="header" className="text-right py-3 px-4 text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">操作</TableCell>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredRoles.map((role) => {
                const isSystem = role.isSystem;
                const RoleIcon = ROLE_ICONS[role.name] || Shield;
                return (
                  <TableRow key={role.id}>
                    {/* Role cell: icon + name */}
                    <TableCell className="py-3 px-4">
                      <div className="flex items-center gap-3">
                        <div className={cn(
                          "w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0",
                          isSystem ? "bg-[var(--accent-light)]" : "bg-[var(--bg-tertiary)]"
                        )}>
                          <RoleIcon className={cn("w-4 h-4", isSystem ? "text-[var(--accent)]" : "text-[var(--text-secondary)]")} />
                        </div>
                        <span className="font-medium text-[var(--text-primary)] text-sm">{role.name}</span>
                      </div>
                    </TableCell>
                    {/* Type */}
                    <TableCell className="py-3 px-4">
                      {isSystem ? (
                        <Badge variant="primary" size="sm">系统</Badge>
                      ) : (
                        <Badge variant="neutral" size="sm">自定义</Badge>
                      )}
                    </TableCell>
                    {/* Description */}
                    <TableCell className="py-3 px-4">
                      <span className="text-sm text-[var(--text-secondary)]">
                        {role.description || '-'}
                      </span>
                    </TableCell>
                    {/* Actions */}
                    <TableCell className="py-3 px-4">
                      <div className="flex gap-1 justify-end">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => openMenusDialog(role)}
                          title="分配菜单权限"
                          icon={<MenuIcon className="w-4 h-4" />}
                        />
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => openEditDialog(role)}
                          title="编辑角色"
                          icon={<Edit2 className="w-4 h-4" />}
                        />
                        {!role.isSystem && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDeleteRole(role)}
                            title="删除角色"
                            icon={<Trash2 className="w-4 h-4" />}
                          />
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Card>
      )}

      {/* Create Role Modal */}
      <Modal
        open={isCreateOpen}
        onOpenChange={setIsCreateOpen}
        title="创建角色"
        description="填写以下信息创建新角色"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsCreateOpen(false)}>取消</Button>
            <Button onClick={handleCreateRole}>创建</Button>
          </>
        }
      >
        <div className="py-4">
          {/* Section: 基本信息 */}
          <div className="mb-5">
            <div className="flex items-center gap-2 mb-3 pb-2 border-b border-[var(--border)]">
              <Shield className="w-4 h-4 text-[var(--accent)]" />
              <span className="text-sm font-semibold text-[var(--text-primary)]">基本信息</span>
            </div>
            <div className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-[var(--text-secondary)]">
                  角色名称 <span className="text-[var(--error)]">*</span>
                </label>
                <Input
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="请输入角色名称（如：Admin、Editor）"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-[var(--text-secondary)]">描述</label>
                <Input
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="请输入角色描述（可选）"
                />
              </div>
            </div>
          </div>
        </div>
      </Modal>

      {/* Edit Role Modal */}
      <Modal
        open={isEditOpen}
        onOpenChange={setIsEditOpen}
        title="编辑角色"
        description="修改角色信息"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsEditOpen(false)}>取消</Button>
            <Button onClick={handleUpdateRole}>保存</Button>
          </>
        }
      >
        <div className="py-4">
          {/* Section: 基本信息 */}
          <div className="mb-5">
            <div className="flex items-center gap-2 mb-3 pb-2 border-b border-[var(--border)]">
              <Shield className="w-4 h-4 text-[var(--accent)]" />
              <span className="text-sm font-semibold text-[var(--text-primary)]">基本信息</span>
            </div>
            <div className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-[var(--text-secondary)]">
                  角色名称 <span className="text-[var(--error)]">*</span>
                </label>
                <Input
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  disabled={formData.isSystem}
                  placeholder="请输入角色名称"
                />
                {formData.isSystem && (
                  <p className="text-xs text-[var(--text-tertiary)] flex items-center gap-1">
                    <Shield className="w-3 h-3" />
                    系统角色不可修改名称
                  </p>
                )}
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-[var(--text-secondary)]">描述</label>
                <Input
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="请输入角色描述"
                />
              </div>
            </div>
          </div>
        </div>
      </Modal>

      {/* Assign Menus Modal */}
      <Modal
        open={isMenusOpen}
        onOpenChange={setIsMenusOpen}
        title="分配菜单权限"
        description={
          <div>
            为角色 <strong className="text-[var(--text-primary)]">{selectedRole?.name}</strong> 分配菜单权限
            <p className="text-xs text-[var(--text-tertiary)] mt-1">
              勾选菜单将自动包含其子菜单
            </p>
          </div>
        }
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsMenusOpen(false)}>取消</Button>
            <Button onClick={handleAssignMenus}>保存</Button>
          </>
        }
        width={600}
      >
        <div className="py-4 max-h-[60vh] overflow-y-auto">
          {menus.length === 0 ? (
            <div className="text-center py-8 text-[var(--text-secondary)]">
              暂无菜单数据
            </div>
          ) : (
            <div className="space-y-0.5">
              {renderMenuTree(menus.filter(m => !m.parent_id))}
            </div>
          )}
        </div>
      </Modal>
    </div>
  );
}
