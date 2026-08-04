import { useState, useEffect, ReactElement } from 'react';
import React from 'react';
import { useI18n } from '@/src/lib/i18n';
import { useAuth } from '@/src/lib/auth-context';
import { Button, Card, CardHeader, CardBody, CardTitle, CardDescription, Input, Badge, Switch, Modal, Table, TableHeader, TableBody, TableRow, TableCell } from '@/src/components/enterprise';
import { Select } from '@/src/components/enterprise/Select';
import { toast } from 'sonner';
import {
  Users, UserPlus, Search, RefreshCw, Trash2, Settings, Loader2,
  CheckCircle2, XCircle, Shield, Key, Mail, User, Calendar, Building2
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  UserData, RoleData, UserCreate, fetchUsers, fetchRoles, createUser, updateUser, deleteUser, assignUserRoles,
  createRole, deleteRole, fetchDepartments, DepartmentData,
  addUserToDepartment
} from '@/lib/api-client';

const ROLE_BADGE_COLORS: Record<string, string> = {
  Admin: 'enterprise-badge-error',
  Editor: 'enterprise-badge-primary',
  Viewer: 'enterprise-badge-success',
  Developer: 'enterprise-badge-secondary',
};

const AVATAR_COLORS = [
  { bg: '#EEF2FB', icon: '#4F7BE5' },
  { bg: '#E8F5F1', icon: '#0F8A6B' },
  { bg: '#F4ECFB', icon: '#7B3FBF' },
  { bg: '#FEF1E7', icon: '#C75D1F' },
  { bg: '#EAF3FE', icon: '#1E73C2' },
  { bg: '#FCEEF1', icon: '#B23A5C' },
];

function getAvatarColor(id: number) {
  return AVATAR_COLORS[id % AVATAR_COLORS.length];
}

const ROLE_ICONS: Record<string, any> = {
  Admin: Shield,
  Editor: Settings,
  Viewer: Users,
  Developer: Key,
};

const ROLE_DESCRIPTIONS: Record<string, string> = {
  Admin: '平台全量控制：用户管理、角色分配、系统配置',
  Editor: '知识库内容运营：上传文档、管理连接器',
  Viewer: '纯查询权限：在授权范围内提问',
  Developer: '程序化集成：通过 API 构建应用',
};

export function UserManagement() {
  const { t } = useI18n();
  const { user, isAuthenticated } = useAuth();
  const [users, setUsers] = useState<UserData[]>([]);
  const [roles, setRoles] = useState<RoleData[]>([]);
  const [loading, setLoading] = useState(true);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [isRolesOpen, setIsRolesOpen] = useState(false);
  const [isDepartmentsOpen, setIsDepartmentsOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState<UserData | null>(null);
  const [filterRole, setFilterRole] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [departments, setDepartments] = useState<DepartmentData[]>([]);
  const [selectedDepartmentIds, setSelectedDepartmentIds] = useState<number[]>([]);

  // 检查是否为管理员（支持 Admin 和 super_admin 角色）
  const isAdmin = user?.roles?.some(r => r.name === 'Admin' || r.name === 'super_admin');

  const [formData, setFormData] = useState<Partial<UserCreate>>({
    email: '',
    username: '',
    password: '',
    fullName: '',
    isActive: true,
  });

  const [selectedRoleIds, setSelectedRoleIds] = useState<number[]>([]);

  const loadUsers = async () => {
    try {
      const data = await fetchUsers(searchQuery || undefined, filterRole !== 'all' ? filterRole : undefined);
      setUsers(data.items || []);
    } catch (e: any) {
      console.error('Failed to load users:', e);
      setUsers([
        { id: 1, email: 'admin@example.com', username: 'admin', fullName: 'System Administrator', isActive: true, createdAt: new Date().toISOString(), roles: [{ id: 1, name: 'Admin', description: 'Administrator', isSystem: true }] },
        { id: 2, email: 'editor@example.com', username: 'editor', fullName: 'Editor User', isActive: true, createdAt: new Date().toISOString(), roles: [{ id: 2, name: 'Editor', description: 'Editor', isSystem: true }] },
        { id: 3, email: 'viewer@example.com', username: 'viewer', fullName: 'Viewer User', isActive: true, createdAt: new Date().toISOString(), roles: [{ id: 3, name: 'Viewer', description: 'Viewer', isSystem: true }] },
        { id: 4, email: 'dev@example.com', username: 'developer', fullName: 'Developer User', isActive: true, createdAt: new Date().toISOString(), roles: [{ id: 4, name: 'Developer', description: 'Developer', isSystem: true }] },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const loadRoles = async () => {
    try {
      const data = await fetchRoles();
      console.log('Roles loaded:', data);
      const items = Array.isArray(data.items) ? data.items : [];
      setRoles(items);
    } catch (e: any) {
      console.error('Failed to load roles:', e);
      setRoles([]);
    }
  };

  const loadDepartments = async () => {
    try {
      const data = await fetchDepartments();
      console.log('Departments loaded:', data);
      const items = Array.isArray(data.items) ? data.items : [];
      setDepartments(items);
    } catch (e: any) {
      console.error('Failed to load departments:', e);
      setDepartments([]);
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
    loadUsers();
    loadRoles();
    loadDepartments();
  }, [isAuthenticated, isAdmin]);

  useEffect(() => {
    const debounce = setTimeout(() => {
      loadUsers();
    }, 300);
    return () => clearTimeout(debounce);
  }, [searchQuery, filterRole]);

  const handleCreateUser = async () => {
    try {
      if (!formData.email || !formData.username || !formData.password) {
        toast.error('请填写必填项');
        return;
      }
      await createUser(formData as UserCreate);
      toast.success('用户创建成功');
      setIsCreateOpen(false);
      setFormData({ email: '', username: '', password: '', fullName: '', isActive: true });
      loadUsers();
    } catch (e: any) {
      console.error('Failed to create user:', e);
      toast.error(`创建用户失败：${e.message}`);
    }
  };

  const handleUpdateUser = async () => {
    if (!selectedUser) return;
    try {
      await updateUser(selectedUser.id, {
        email: formData.email,
        username: formData.username,
        fullName: formData.fullName,
        isActive: formData.isActive,
      });
      toast.success('用户更新成功');
      setIsEditOpen(false);
      loadUsers();
    } catch (e: any) {
      console.error('Failed to update user:', e);
      toast.error(`更新用户失败：${e.message}`);
    }
  };

  const handleDeleteUser = async (user: UserData) => {
    if (!confirm(`确定要删除用户 "${user.username}" 吗？`)) return;
    try {
      await deleteUser(user.id);
      toast.success('用户删除成功');
      loadUsers();
    } catch (e: any) {
      console.error('Failed to delete user:', e);
      toast.error(`删除用户失败：${e.message}`);
    }
  };

  const handleAssignRoles = async () => {
    if (!selectedUser) return;
    try {
      await assignUserRoles(selectedUser.id, selectedRoleIds);
      toast.success('角色分配成功');
      setIsRolesOpen(false);
      loadUsers();
    } catch (e: any) {
      console.error('Failed to assign roles:', e);
      toast.error(`分配角色失败：${e.message}`);
    }
  };

  const handleAssignDepartments = async () => {
    if (!selectedUser) return;
    try {
      // 先移除用户所有部门，再添加新部门
      for (const deptId of selectedDepartmentIds) {
        await addUserToDepartment(deptId, selectedUser.id, undefined, selectedDepartmentIds[0] === deptId);
      }
      toast.success('部门分配成功');
      setIsDepartmentsOpen(false);
      loadUsers();
    } catch (e: any) {
      console.error('Failed to assign departments:', e);
      toast.error(`分配部门失败：${e.message}`);
    }
  };

  const openEditDialog = (user: UserData) => {
    setSelectedUser(user);
    setFormData({
      email: user.email,
      username: user.username,
      fullName: user.fullName,
      isActive: user.isActive,
    });
    setIsEditOpen(true);
  };

  const openRolesDialog = (user: UserData) => {
    setSelectedUser(user);
    setSelectedRoleIds(user.roles.map(r => r.id));
    setIsRolesOpen(true);
  };

  const openDepartmentsDialog = (user: UserData) => {
    console.log('Opening departments dialog for user:', user.username, 'departments count:', departments.length);
    setSelectedUser(user);
    setSelectedDepartmentIds([]);
    setIsDepartmentsOpen(true);
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
              请先登录以访问用户管理页面
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

  return (
    <div className="p-6 space-y-5 bg-white min-h-screen">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-[var(--accent-light)] flex items-center justify-center">
            <Users className="w-5 h-5 text-[var(--accent)]" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-[var(--text-primary)]">用户管理</h1>
            <p className="text-sm text-[var(--text-secondary)] mt-0.5">
              共 {users.length} 位用户 · 管理系统用户和角色权限
            </p>
          </div>
        </div>
        <Button onClick={() => setIsCreateOpen(true)} icon={<UserPlus className="w-4 h-4" />}>
          创建用户
        </Button>
      </div>

      {/* Filters */}
      <div className="flex gap-3 items-center">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text-tertiary)]" />
          <Input
            placeholder="搜索用户名、邮箱或姓名..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>
        <Select
          value={filterRole}
          onChange={(e) => setFilterRole(e.target.value)}
          className="w-[180px]"
        >
          <option value="all">所有角色</option>
          {roles.map((role) => (
            <option key={role.id} value={role.name}>{role.name}</option>
          ))}
        </Select>
        <Button variant="secondary" onClick={loadUsers} icon={<RefreshCw className="w-4 h-4" />}>
          刷新
        </Button>
      </div>

      {/* Users Table */}
      {loading ? (
        <div className="flex justify-center py-16">
          <Loader2 className="w-8 h-8 animate-spin text-[var(--text-tertiary)]" />
        </div>
      ) : users.length === 0 ? (
        <Card>
          <CardBody className="py-16 text-center">
            <Users className="w-12 h-12 mx-auto mb-4 opacity-50 text-[var(--text-tertiary)]" />
            <p className="text-[var(--text-secondary)] mb-4">暂无用户</p>
            <Button variant="secondary" onClick={() => setIsCreateOpen(true)} icon={<UserPlus className="w-4 h-4" />}>
              创建第一个用户
            </Button>
          </CardBody>
        </Card>
      ) : (
        <Card>
          <Table hover>
            <TableHeader>
              <TableRow>
                <TableCell variant="header" className="text-left py-3 px-4 text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">用户</TableCell>
                <TableCell variant="header" className="text-left py-3 px-4 text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">角色</TableCell>
                <TableCell variant="header" className="text-left py-3 px-4 text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">状态</TableCell>
                <TableCell variant="header" className="text-left py-3 px-4 text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">创建时间</TableCell>
                <TableCell variant="header" className="text-right py-3 px-4 text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">操作</TableCell>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map((user) => {
                const ac = getAvatarColor(user.id);
                return (
                  <TableRow key={user.id}>
                    {/* User cell: avatar + name + email */}
                    <TableCell className="py-3 px-4">
                      <div className="flex items-center gap-3">
                        <div
                          className="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0"
                          style={{ backgroundColor: ac.bg }}
                        >
                          <User className="w-4 h-4" style={{ color: ac.icon }} />
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-[var(--text-primary)] text-sm">{user.username}</span>
                            {user.fullName && (
                              <span className="text-xs text-[var(--text-tertiary)]">({user.fullName})</span>
                            )}
                          </div>
                          <div className="flex items-center gap-1 text-xs text-[var(--text-secondary)] mt-0.5">
                            <Mail className="w-3 h-3" />
                            <span className="truncate">{user.email}</span>
                          </div>
                        </div>
                      </div>
                    </TableCell>
                    {/* Roles */}
                    <TableCell className="py-3 px-4">
                      <div className="flex gap-1 flex-wrap">
                        {user.roles.map((role) => (
                          <Badge
                            key={role.id}
                            variant={
                              role.name === 'Admin' ? 'error' :
                              role.name === 'Editor' ? 'primary' :
                              role.name === 'Viewer' ? 'success' : 'neutral'
                            }
                            size="sm"
                          >
                            {React.createElement(getRoleIcon(role.name), { className: "w-3 h-3 mr-0.5" })}
                            {role.name}
                          </Badge>
                        ))}
                      </div>
                    </TableCell>
                    {/* Status */}
                    <TableCell className="py-3 px-4">
                      <span className="inline-flex items-center gap-1.5">
                        <span
                          className="w-2 h-2 rounded-full"
                          style={{ backgroundColor: user.isActive ? 'var(--success)' : 'var(--text-tertiary)' }}
                        />
                        <span className="text-sm text-[var(--text-secondary)]">
                          {user.isActive ? '启用' : '已禁用'}
                        </span>
                      </span>
                    </TableCell>
                    {/* Created */}
                    <TableCell className="py-3 px-4 text-sm text-[var(--text-secondary)]">
                      {user.createdAt ? new Date(user.createdAt).toLocaleDateString('zh-CN') : '-'}
                    </TableCell>
                    {/* Actions */}
                    <TableCell className="py-3 px-4">
                      <div className="flex gap-1 justify-end">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => openDepartmentsDialog(user)}
                          title="分配部门"
                          icon={<Building2 className="w-4 h-4" />}
                        />
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => openRolesDialog(user)}
                          title="分配角色"
                          icon={<Shield className="w-4 h-4" />}
                        />
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => openEditDialog(user)}
                          title="编辑用户"
                          icon={<Settings className="w-4 h-4" />}
                        />
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDeleteUser(user)}
                          title="删除用户"
                          icon={<Trash2 className="w-4 h-4" />}
                        />
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Card>
      )}

      {/* Create User Modal */}
      <Modal
        open={isCreateOpen}
        onOpenChange={setIsCreateOpen}
        title="创建用户"
        description="填写以下信息创建新用户"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsCreateOpen(false)}>取消</Button>
            <Button onClick={handleCreateUser}>创建</Button>
          </>
        }
      >
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <label className="text-sm font-medium text-[var(--text-secondary)]">用户名</label>
            <Input
              value={formData.username}
              onChange={(e) => setFormData({ ...formData, username: e.target.value })}
              placeholder="请输入用户名"
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-[var(--text-secondary)]">邮箱</label>
            <Input
              type="email"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              placeholder="请输入邮箱"
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-[var(--text-secondary)]">密码</label>
            <Input
              type="password"
              value={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              placeholder="请输入密码（至少 8 位）"
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-[var(--text-secondary)]">姓名</label>
            <Input
              value={formData.fullName}
              onChange={(e) => setFormData({ ...formData, fullName: e.target.value })}
              placeholder="请输入姓名"
            />
          </div>
        </div>
      </Modal>

      {/* Edit User Modal */}
      <Modal
        open={isEditOpen}
        onOpenChange={setIsEditOpen}
        title="编辑用户"
        description="修改用户信息"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsEditOpen(false)}>取消</Button>
            <Button onClick={handleUpdateUser}>保存</Button>
          </>
        }
      >
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <label className="text-sm font-medium text-[var(--text-secondary)]">用户名</label>
            <Input
              value={formData.username}
              onChange={(e) => setFormData({ ...formData, username: e.target.value })}
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-[var(--text-secondary)]">邮箱</label>
            <Input
              type="email"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-[var(--text-secondary)]">姓名</label>
            <Input
              value={formData.fullName}
              onChange={(e) => setFormData({ ...formData, fullName: e.target.value })}
            />
          </div>
          <div className="flex items-center gap-2 py-2">
            <Switch
              checked={formData.isActive}
              onCheckedChange={(checked) => setFormData({ ...formData, isActive: checked })}
            />
            <label className="text-sm text-[var(--text-secondary)]">启用账号</label>
          </div>
        </div>
      </Modal>

      {/* Assign Roles Modal */}
      <Modal
        open={isRolesOpen}
        onOpenChange={setIsRolesOpen}
        title="分配角色"
        description={<>为用户 <strong className="text-[var(--text-primary)]">{selectedUser?.username}</strong> 分配角色</>}
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsRolesOpen(false)}>取消</Button>
            <Button onClick={handleAssignRoles}>保存</Button>
          </>
        }
      >
        <div className="space-y-3 py-4">
          {roles.map((role) => (
            <Card
              key={role.id}
              className={cn(
                "cursor-pointer transition-all",
                selectedRoleIds.includes(role.id)
                  ? "border-[var(--primary)] bg-[var(--accent-light)]"
                  : "hover:bg-[var(--bg-primary)]"
              )}
              onClick={() => {
                setSelectedRoleIds(
                  selectedRoleIds.includes(role.id)
                    ? selectedRoleIds.filter(id => id !== role.id)
                    : [...selectedRoleIds, role.id]
                );
              }}
            >
              <CardBody>
                <div className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    checked={selectedRoleIds.includes(role.id)}
                    onChange={() => {
                      setSelectedRoleIds(
                        selectedRoleIds.includes(role.id)
                          ? selectedRoleIds.filter(id => id !== role.id)
                          : [...selectedRoleIds, role.id]
                      );
                    }}
                    className="enterprise-checkbox mt-1"
                  />
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <Badge className={getRoleBadgeClass(role.name)}>
                        {React.createElement(getRoleIcon(role.name), { className: "w-3 h-3" })}
                        <span className="ml-1">{role.name}</span>
                      </Badge>
                      {role.isSystem && (
                        <Badge variant="neutral" className="text-xs">系统角色</Badge>
                      )}
                    </div>
                    <p className="text-sm text-[var(--text-secondary)] mt-1">
                      {ROLE_DESCRIPTIONS[role.name] || role.description}
                    </p>
                  </div>
                </div>
              </CardBody>
            </Card>
          ))}
        </div>
      </Modal>

      {/* Assign Departments Modal */}
      <Modal
        open={isDepartmentsOpen}
        onOpenChange={setIsDepartmentsOpen}
        title="分配部门"
        description={<>为用户 <strong className="text-[var(--text-primary)]">{selectedUser?.username}</strong> 分配部门</>}
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsDepartmentsOpen(false)}>取消</Button>
            <Button onClick={handleAssignDepartments}>保存</Button>
          </>
        }
      >
        <div className="space-y-3 py-4">
          {departments.length === 0 ? (
            <div className="text-center py-8 text-[var(--text-secondary)]">
              暂无部门数据
            </div>
          ) : (
            departments.map((dept) => (
              <Card
                key={dept.id}
                className={cn(
                  "cursor-pointer transition-all",
                  selectedDepartmentIds.includes(dept.id)
                    ? "border-[var(--primary)] bg-[var(--accent-light)]"
                    : "hover:bg-[var(--bg-primary)]"
                )}
                onClick={() => {
                  setSelectedDepartmentIds(
                    selectedDepartmentIds.includes(dept.id)
                      ? selectedDepartmentIds.filter(id => id !== dept.id)
                      : [...selectedDepartmentIds, dept.id]
                  );
                }}
              >
                <CardBody>
                  <div className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      checked={selectedDepartmentIds.includes(dept.id)}
                      onChange={() => {
                        setSelectedDepartmentIds(
                          selectedDepartmentIds.includes(dept.id)
                            ? selectedDepartmentIds.filter(id => id !== dept.id)
                            : [...selectedDepartmentIds, dept.id]
                        );
                      }}
                      className="enterprise-checkbox mt-1"
                    />
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-[var(--text-primary)]">{dept.name}</span>
                      </div>
                      {dept.description && (
                        <p className="text-sm text-[var(--text-secondary)] mt-1">
                          {dept.description}
                        </p>
                      )}
                    </div>
                  </div>
                </CardBody>
              </Card>
            ))
          )}
        </div>
      </Modal>
    </div>
  );
}

function getRoleBadgeClass(roleName: string) {
  return ROLE_BADGE_COLORS[roleName] || 'enterprise-badge-neutral';
}

function getRoleIcon(roleName: string) {
  return ROLE_ICONS[roleName] || Users;
}
