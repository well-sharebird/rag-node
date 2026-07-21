import { useState, useEffect } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';
import { Switch } from '../../components/ui/switch';
import { Checkbox } from '../../components/ui/checkbox';
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
  Admin: 'bg-red-50 text-red-700 border-red-200',
  Editor: 'bg-blue-50 text-blue-700 border-blue-200',
  Viewer: 'bg-green-50 text-green-700 border-green-200',
  Developer: 'bg-purple-50 text-purple-700 border-purple-200',
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

export function UserManagement() {
  const { t } = useI18n();
  const [users, setUsers] = useState<UserData[]>([]);
  const [roles, setRoles] = useState<RoleData[]>([]);
  const [loading, setLoading] = useState(true);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [isRolesOpen, setIsRolesOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState<UserData | null>(null);
  const [filterRole, setFilterRole] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');

  // Form state
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
      // Fallback to demo data for testing
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
    loadUsers();
    loadRoles();
  }, []);

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

  const getRoleBadgeClass = (roleName: string) => {
    return ROLE_BADGE_COLORS[roleName] || 'bg-gray-50 text-gray-700 border-gray-200';
  };

  const getRoleIcon = (roleName: string) => {
    const Icon = ROLE_ICONS[roleName] || Users;
    return <Icon className="w-3 h-3" />;
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold">用户管理</h1>
          <p className="text-muted-foreground mt-1">管理系统用户和角色权限</p>
        </div>
        <Button onClick={() => setIsCreateOpen(true)}>
          <UserPlus className="w-4 h-4 mr-2" />
          创建用户
        </Button>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex gap-4">
            <div className="flex-1">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  placeholder="搜索用户名、邮箱或姓名..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10"
                />
              </div>
            </div>
            <Select value={filterRole} onValueChange={setFilterRole}>
              <SelectTrigger className="w-[200px]">
                <SelectValue placeholder="按角色筛选" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">所有角色</SelectItem>
                {roles.map((role) => (
                  <SelectItem key={role.id} value={role.name}>
                    {role.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button variant="outline" onClick={loadUsers}>
              <RefreshCw className="w-4 h-4 mr-2" />
              刷新
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Users List */}
      <div className="grid gap-4">
        {loading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
          </div>
        ) : users.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center text-muted-foreground">
              <Users className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p>暂无用户</p>
            </CardContent>
          </Card>
        ) : (
          users.map((user) => (
            <Card key={user.id} className="hover:shadow-md transition-shadow">
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center">
                      <User className="w-6 h-6 text-primary" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold">{user.username}</h3>
                        {false && (
                          <Badge variant="destructive" className="text-xs">超级管理员</Badge>
                        )}
                        {!user.isActive && (
                          <Badge variant="secondary" className="text-xs">已禁用</Badge>
                        )}
                      </div>
                      <div className="flex items-center gap-3 mt-1 text-sm text-muted-foreground">
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
                          variant="outline"
                          className={getRoleBadgeClass(role.name)}
                        >
                          {getRoleIcon(role.name)}
                          <span className="ml-1">{role.name}</span>
                        </Badge>
                      ))}
                    </div>
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => openRolesDialog(user)}
                      >
                        <Shield className="w-4 h-4" />
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => openEditDialog(user)}
                      >
                        <Settings className="w-4 h-4" />
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleDeleteUser(user)}
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {/* Create User Dialog */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>创建用户</DialogTitle>
            <DialogDescription>
              填写以下信息创建新用户
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label htmlFor="username">用户名</Label>
              <Input
                id="username"
                value={formData.username}
                onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                placeholder="请输入用户名"
              />
            </div>
            <div>
              <Label htmlFor="email">邮箱</Label>
              <Input
                id="email"
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                placeholder="请输入邮箱"
              />
            </div>
            <div>
              <Label htmlFor="password">密码</Label>
              <Input
                id="password"
                type="password"
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                placeholder="请输入密码（至少 8 位）"
              />
            </div>
            <div>
              <Label htmlFor="fullName">姓名</Label>
              <Input
                id="fullName"
                value={formData.fullName}
                onChange={(e) => setFormData({ ...formData, fullName: e.target.value })}
                placeholder="请输入姓名"
              />
            </div>
            <div>
              <Label>初始角色</Label>
              <div className="grid gap-2 mt-2">
                {roles.map((role) => (
                  <div key={role.id} className="flex items-center space-x-2">
                    <Checkbox
                      id={`create-role-${role.id}`}
                      checked={formData.roleIds?.includes(role.id)}
                      onCheckedChange={(checked) => {
                        const current = formData.roleIds || [];
                        if (checked) {
                          setFormData({ ...formData, roleIds: [...current, role.id] });
                        } else {
                          setFormData({ ...formData, roleIds: current.filter(id => id !== role.id) });
                        }
                      }}
                    />
                    <label
                      htmlFor={`create-role-${role.id}`}
                      className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                    >
                      {role.name}
                    </label>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsCreateOpen(false)}>
              取消
            </Button>
            <Button onClick={handleCreateUser}>
              创建
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit User Dialog */}
      <Dialog open={isEditOpen} onOpenChange={setIsEditOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>编辑用户</DialogTitle>
            <DialogDescription>
              修改用户信息
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label htmlFor="edit-username">用户名</Label>
              <Input
                id="edit-username"
                value={formData.username}
                onChange={(e) => setFormData({ ...formData, username: e.target.value })}
              />
            </div>
            <div>
              <Label htmlFor="edit-email">邮箱</Label>
              <Input
                id="edit-email"
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              />
            </div>
            <div>
              <Label htmlFor="edit-fullName">姓名</Label>
              <Input
                id="edit-fullName"
                value={formData.fullName}
                onChange={(e) => setFormData({ ...formData, fullName: e.target.value })}
              />
            </div>
            <div className="flex items-center space-x-2">
              <Switch
                id="edit-active"
                checked={formData.isActive}
                onCheckedChange={(checked) => setFormData({ ...formData, isActive: checked })}
              />
              <Label htmlFor="edit-active">启用账号</Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsEditOpen(false)}>
              取消
            </Button>
            <Button onClick={handleUpdateUser}>
              保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Assign Roles Dialog */}
      <Dialog open={isRolesOpen} onOpenChange={setIsRolesOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>分配角色</DialogTitle>
            <DialogDescription>
              为用户 <strong>{selectedUser?.username}</strong> 分配角色
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-3">
              {roles.map((role) => (
                <Card
                  key={role.id}
                  className={cn(
                    "cursor-pointer transition-all",
                    selectedRoleIds.includes(role.id)
                      ? "border-primary bg-primary/5"
                      : "hover:bg-muted/50"
                  )}
                  onClick={() => {
                    setSelectedRoleIds(
                      selectedRoleIds.includes(role.id)
                        ? selectedRoleIds.filter(id => id !== role.id)
                        : [...selectedRoleIds, role.id]
                    );
                  }}
                >
                  <CardContent className="pt-4">
                    <div className="flex items-start gap-3">
                      <Checkbox
                        checked={selectedRoleIds.includes(role.id)}
                        onCheckedChange={() => {
                          setSelectedRoleIds(
                            selectedRoleIds.includes(role.id)
                              ? selectedRoleIds.filter(id => id !== role.id)
                              : [...selectedRoleIds, role.id]
                          );
                        }}
                        className="mt-1"
                      />
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <Badge className={getRoleBadgeClass(role.name)}>
                            {getRoleIcon(role.name)}
                            <span className="ml-1">{role.name}</span>
                          </Badge>
                          {role.isSystem && (
                            <Badge variant="outline" className="text-xs">系统角色</Badge>
                          )}
                        </div>
                        <p className="text-sm text-muted-foreground mt-1">
                          {ROLE_DESCRIPTIONS[role.name] || role.description}
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsRolesOpen(false)}>
              取消
            </Button>
            <Button onClick={handleAssignRoles}>
              保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
