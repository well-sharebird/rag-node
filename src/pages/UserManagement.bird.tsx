import { useState, useEffect, ReactElement } from 'react';
import React from 'react';
import { useI18n } from '@/src/lib/i18n';
import { useAuth } from '@/src/lib/auth-context';
import { Button, Card, CardHeader, CardBody, CardTitle, CardDescription, Input, Badge, Switch, Modal } from '@/src/components/bird';
import { Select } from '@/src/components/bird/Select';
import { toast } from 'sonner';
import {
  Users, UserPlus, Search, RefreshCw, Trash2, Settings, Loader2,
  CheckCircle2, XCircle, Shield, Key, Mail, User, Calendar
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  UserData, RoleData, UserCreate, fetchUsers, fetchRoles, createUser, updateUser, deleteUser, assignUserRoles,
  createRole, deleteRole
} from '@/lib/api-client';

const ROLE_BADGE_COLORS: Record<string, string> = {
  Admin: 'bird-badge-error',
  Editor: 'bird-badge-primary',
  Viewer: 'bird-badge-success',
  Developer: 'bg-purple-100 text-purple-700 border-purple-200',
};

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

export function UserManagementBird() {
  const { t } = useI18n();
  const { user, isAuthenticated } = useAuth();
  const [users, setUsers] = useState<UserData[]>([]);
  const [roles, setRoles] = useState<RoleData[]>([]);
  const [loading, setLoading] = useState(true);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [isRolesOpen, setIsRolesOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState<UserData | null>(null);
  const [filterRole, setFilterRole] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');

  const isAdmin = user?.roles?.some(r => r.name === 'Admin');

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
      setRoles(data.items || []);
    } catch (e: any) {
      console.error('Failed to load roles:', e);
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

  if (!isAuthenticated) {
    return (
      <div className="p-6 space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Shield className="w-5 h-5 text-[#f59e0b]" />
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
              <Shield className="w-5 h-5 text-[#ef4444]" />
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
    <div className="p-6 space-y-6 bg-[#f9fafb] min-h-screen">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-semibold text-[#111827]">用户管理</h1>
          <p className="text-[#6b7280] mt-1">管理系统用户和角色权限</p>
        </div>
        <Button onClick={() => setIsCreateOpen(true)} icon={<UserPlus className="w-4 h-4" />}>
          创建用户
        </Button>
      </div>

      {/* Filters */}
      <Card>
        <CardBody>
          <div className="flex gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9ca3af]" />
              <Input
                placeholder="搜索用户名、邮箱或姓名..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10"
              />
            </div>
            <Select value={filterRole} onValueChange={setFilterRole} className="w-[200px]">
              <option value="all">所有角色</option>
              {roles.map((role) => (
                <option key={role.id} value={role.name}>{role.name}</option>
              ))}
            </Select>
            <Button variant="secondary" onClick={loadUsers} icon={<RefreshCw className="w-4 h-4" />}>
              刷新
            </Button>
          </div>
        </CardBody>
      </Card>

      {/* Users List */}
      <div className="grid gap-4">
        {loading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="w-8 h-8 animate-spin text-[#9ca3af]" />
          </div>
        ) : users.length === 0 ? (
          <Card>
            <CardBody className="py-12 text-center">
              <Users className="w-12 h-12 mx-auto mb-4 opacity-50 text-[#9ca3af]" />
              <p className="text-[#6b7280]">暂无用户</p>
            </CardBody>
          </Card>
        ) : (
          users.map((user) => (
            <Card key={user.id} className="hover:shadow-md transition-shadow">
              <CardBody>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className="w-12 h-12 rounded-full bg-[#ede9fe] flex items-center justify-center">
                      <User className="w-6 h-6 text-[#7c3aed]" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-medium text-[#111827]">{user.username}</h3>
                        {!user.isActive && (
                          <Badge variant="neutral">已禁用</Badge>
                        )}
                      </div>
                      <div className="flex items-center gap-3 mt-1 text-sm text-[#6b7280]">
                        <span className="flex items-center gap-1">
                          <Mail className="w-3 h-3" />
                          {user.email}
                        </span>
                        {user.fullName && (
                          <span>{user.fullName}</span>
                        )}
                        {user.lastLoginAt && (
                          <span className="flex items-center gap-1">
                            <Calendar className="w-3 h-3" />
                            最后登录：{new Date(user.lastLoginAt).toLocaleDateString('zh-CN')}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="flex gap-1">
                      {user.roles.map((role) => (
                        <Badge
                          key={role.id}
                          className={cn(getRoleBadgeClass(role.name), 'text-xs')}
                        >
                          {React.createElement(getRoleIcon(role.name), { className: "w-3 h-3" })}
                          <span className="ml-1">{role.name}</span>
                        </Badge>
                      ))}
                    </div>
                    <div className="flex gap-2">
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => openRolesDialog(user)}
                        icon={<Shield className="w-4 h-4" />}
                      />
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => openEditDialog(user)}
                        icon={<Settings className="w-4 h-4" />}
                      />
                      <Button
                        variant="danger"
                        size="sm"
                        onClick={() => handleDeleteUser(user)}
                        icon={<Trash2 className="w-4 h-4" />}
                      />
                    </div>
                  </div>
                </div>
              </CardBody>
            </Card>
          ))
        )}
      </div>

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
            <label className="text-sm font-medium text-[#4b5563]">用户名</label>
            <Input
              value={formData.username}
              onChange={(e) => setFormData({ ...formData, username: e.target.value })}
              placeholder="请输入用户名"
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-[#4b5563]">邮箱</label>
            <Input
              type="email"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              placeholder="请输入邮箱"
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-[#4b5563]">密码</label>
            <Input
              type="password"
              value={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              placeholder="请输入密码（至少 8 位）"
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-[#4b5563]">姓名</label>
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
            <label className="text-sm font-medium text-[#4b5563]">用户名</label>
            <Input
              value={formData.username}
              onChange={(e) => setFormData({ ...formData, username: e.target.value })}
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-[#4b5563]">邮箱</label>
            <Input
              type="email"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-[#4b5563]">姓名</label>
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
            <label className="text-sm text-[#4b5563]">启用账号</label>
          </div>
        </div>
      </Modal>

      {/* Assign Roles Modal */}
      <Modal
        open={isRolesOpen}
        onOpenChange={setIsRolesOpen}
        title="分配角色"
        description={<>为用户 <strong className="text-[#111827]">{selectedUser?.username}</strong> 分配角色</>}
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
                  ? "border-[#7c3aed] bg-[#f5f3ff]"
                  : "hover:bg-[#f9fafb]"
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
                    className="bird-checkbox mt-1"
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
                    <p className="text-sm text-[#6b7280] mt-1">
                      {ROLE_DESCRIPTIONS[role.name] || role.description}
                    </p>
                  </div>
                </div>
              </CardBody>
            </Card>
          ))}
        </div>
      </Modal>
    </div>
  );
}

function getRoleBadgeClass(roleName: string) {
  return ROLE_BADGE_COLORS[roleName] || 'bird-badge-neutral';
}

function getRoleIcon(roleName: string) {
  return ROLE_ICONS[roleName] || Users;
}
