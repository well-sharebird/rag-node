import { useState, useEffect } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { useAuth } from '@/src/lib/auth-context';
import { Button, Card, CardHeader, CardBody, CardTitle, CardDescription, Input, Badge, Modal, Select, Table, TableHeader, TableBody, TableRow, TableCell } from '@/src/components/enterprise';
import { toast } from 'sonner';
import {
  Building2, Plus, Search, RefreshCw, Trash2, Edit2, Loader2, Users, User,
  ChevronRight, ChevronDown, FolderOpen, Building, Home
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  DepartmentData, fetchDepartments, createDepartment, updateDepartment, deleteDepartment,
  getDepartmentUsers, addUserToDepartment, removeUserFromDepartment, fetchUsers, UserData
} from '@/lib/api-client';

interface TreeNode extends DepartmentData {
  children?: TreeNode[];
  isExpanded?: boolean;
}

export function DepartmentManagement() {
  const { t } = useI18n();
  const { user, isAuthenticated } = useAuth();
  const [departments, setDepartments] = useState<DepartmentData[]>([]);
  const [treeData, setTreeData] = useState<TreeNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [isUsersOpen, setIsUsersOpen] = useState(false);
  const [selectedDept, setSelectedDept] = useState<DepartmentData | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
  const [deptUsers, setDeptUsers] = useState<UserData[]>([]);
  const [allUsers, setAllUsers] = useState<UserData[]>([]);
  const [addUserId, setAddUserId] = useState<string>('');

  // 部门表单数据
  const [formData, setFormData] = useState({
    name: '',
    code: '',
    description: '',
    parent_id: undefined as number | undefined,
  });

  // 检查是否为管理员
  const isAdmin = user?.roles?.some(r => r.name === 'Admin' || r.name === 'super_admin');

  // 构建树形结构
  const buildTree = (deptList: DepartmentData[]): TreeNode[] => {
    const deptMap = new Map<number, TreeNode>();
    deptList.forEach(dept => {
      deptMap.set(dept.id, { ...dept, children: [], isExpanded: false });
    });

    const roots: TreeNode[] = [];
    deptList.forEach(dept => {
      const node = deptMap.get(dept.id)!;
      if (!dept.parent_id || dept.parent_id === 0) {
        roots.push(node);
      } else {
        const parent = deptMap.get(dept.parent_id);
        if (parent) {
          if (!parent.children) parent.children = [];
          parent.children.push(node);
        } else {
          roots.push(node);
        }
      }
    });

    // 按排序排序
    roots.sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
    const sortChildren = (nodes: TreeNode[]) => {
      nodes.sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
      nodes.forEach(node => {
        if (node.children) sortChildren(node.children);
      });
    };
    sortChildren(roots);

    return roots;
  };

  useEffect(() => {
    const filtered = departments.filter(dept =>
      !searchQuery ||
      dept.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      dept.code.toLowerCase().includes(searchQuery.toLowerCase())
    );
    const tree = buildTree(filtered);
    // 恢复展开状态
    const restoreExpanded = (nodes: TreeNode[]) => {
      nodes.forEach(node => {
        node.isExpanded = expandedIds.has(node.id);
        if (node.children) restoreExpanded(node.children);
      });
    };
    restoreExpanded(tree);
    setTreeData(tree);
  }, [departments, searchQuery, expandedIds]);

  const loadDepartments = async () => {
    try {
      const data = await fetchDepartments();
      console.log('Departments loaded:', data);
      const items = Array.isArray(data.items) ? data.items : [];
      setDepartments(items);
    } catch (e: any) {
      console.error('Failed to load departments:', e);
      toast.error(`加载部门失败：${e.message}`);
      setDepartments([]);
    } finally {
      setLoading(false);
    }
  };

  const loadAllUsers = async () => {
    try {
      const data = await fetchUsers();
      setAllUsers(data.items || []);
    } catch (e: any) {
      console.error('Failed to load users:', e);
    }
  };

  const loadDepartmentUsers = async (deptId: number) => {
    try {
      const data = await getDepartmentUsers(deptId);
      const users = data.items?.map((ud: any) => ({
        ...ud.user || ud,
        dept_role: ud.dept_role,
        is_primary: ud.is_primary,
      })) || [];
      setDeptUsers(users);
    } catch (e: any) {
      console.error('Failed to load department users:', e);
      setDeptUsers([]);
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
    loadDepartments();
    loadAllUsers();
  }, [isAuthenticated, isAdmin]);

  const handleCreateDepartment = async () => {
    try {
      if (!formData.name || !formData.code) {
        toast.error('名称和编码不能为空');
        return;
      }
      await createDepartment({
        name: formData.name,
        code: formData.code,
        description: formData.description || undefined,
        parent_id: formData.parent_id,
        dept_type: formData.parent_id ? 'department' : 'company',
      });
      toast.success('部门创建成功');
      setIsCreateOpen(false);
      setFormData({ name: '', code: '', description: '', parent_id: undefined });
      loadDepartments();
    } catch (e: any) {
      console.error('Failed to create department:', e);
      toast.error(`创建部门失败：${e.message}`);
    }
  };

  const handleUpdateDepartment = async () => {
    if (!selectedDept) return;
    try {
      await updateDepartment(selectedDept.id, {
        name: formData.name,
        code: formData.code,
        description: formData.description || undefined,
      });
      toast.success('部门更新成功');
      setIsEditOpen(false);
      loadDepartments();
    } catch (e: any) {
      console.error('Failed to update department:', e);
      toast.error(`更新部门失败：${e.message}`);
    }
  };

  const handleDeleteDepartment = async (dept: DepartmentData) => {
    if (!confirm(`确定要删除部门 "${dept.name}" 吗？`)) return;
    try {
      await deleteDepartment(dept.id);
      toast.success('部门删除成功');
      loadDepartments();
    } catch (e: any) {
      console.error('Failed to delete department:', e);
      toast.error(`删除部门失败：${e.message}`);
    }
  };

  const openEditDialog = (dept: DepartmentData) => {
    setSelectedDept(dept);
    setFormData({
      name: dept.name,
      code: dept.code,
      description: dept.description || '',
      parent_id: dept.parent_id,
    });
    setIsEditOpen(true);
  };

  const openUsersDialog = async (dept: DepartmentData) => {
    setSelectedDept(dept);
    await loadDepartmentUsers(dept.id);
    setIsUsersOpen(true);
  };

  const handleAddUserToDepartment = async (userId: number) => {
    if (!selectedDept) return;
    try {
      await addUserToDepartment(selectedDept.id, userId, 'member', false);
      toast.success('用户已添加到部门');
      loadDepartmentUsers(selectedDept.id);
    } catch (e: any) {
      console.error('Failed to add user to department:', e);
      toast.error(`添加用户失败：${e.message}`);
    }
  };

  const handleRemoveUserFromDepartment = async (userId: number) => {
    if (!selectedDept) return;
    try {
      await removeUserFromDepartment(selectedDept.id, userId);
      toast.success('用户已从部门移除');
      loadDepartmentUsers(selectedDept.id);
    } catch (e: any) {
      console.error('Failed to remove user from department:', e);
      toast.error(`移除用户失败：${e.message}`);
    }
  };

  const toggleExpand = (deptId: number) => {
    const newExpanded = new Set(expandedIds);
    if (newExpanded.has(deptId)) {
      newExpanded.delete(deptId);
    } else {
      newExpanded.add(deptId);
    }
    setExpandedIds(newExpanded);
  };

  const getDeptTypeIcon = (deptType: string) => {
    switch (deptType) {
      case 'company':
        return <Building className="w-4 h-4" />;
      case 'department':
        return <FolderOpen className="w-4 h-4" />;
      case 'team':
        return <Home className="w-4 h-4" />;
      default:
        return <Building2 className="w-4 h-4" />;
    }
  };

  const getDeptTypeLabel = (deptType: string) => {
    switch (deptType) {
      case 'company':
        return '公司';
      case 'department':
        return '部门';
      case 'team':
        return '团队';
      default:
        return deptType;
    }
  };

  // 展平树为表格行（带层级信息）
  interface FlatNode extends DepartmentData {
    level: number;
    hasChildren: boolean;
  }
  const flattenTree = (nodes: TreeNode[], level = 0, result: FlatNode[] = []): FlatNode[] => {
    nodes.forEach((node) => {
      const { children, ...dept } = node;
      const hasChildren = children ? children.length > 0 : false;
      result.push({ ...dept, level, hasChildren });
      if (children && children.length > 0 && expandedIds.has(node.id)) {
        flattenTree(children, level + 1, result);
      }
    });
    return result;
  };
  const flatDepartments = flattenTree(treeData);

  if (!isAuthenticated) {
    return (
      <div className="p-6 space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Building2 className="w-5 h-5 text-[var(--warning)]" />
              需要登录
            </CardTitle>
            <CardDescription>
              请先登录以访问部门管理页面
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
              <Building2 className="w-5 h-5 text-[var(--error)]" />
              需要管理员权限
            </CardTitle>
            <CardDescription>
              此页面仅限管理员访问
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
            <Building2 className="w-5 h-5 text-[var(--accent)]" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-[var(--text-primary)]">部门管理</h1>
            <p className="text-sm text-[var(--text-secondary)] mt-0.5">
              共 {departments.length} 个部门 · 管理组织架构和部门人员
            </p>
          </div>
        </div>
        <Button
          onClick={() => setIsCreateOpen(true)}
          icon={<Plus className="w-4 h-4" />}
        >
          创建部门
        </Button>
      </div>

      {/* Filters */}
      <div className="flex gap-3 items-center">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text-tertiary)]" />
          <Input
            placeholder="搜索部门名称、编码..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>
        <Button variant="secondary" onClick={loadDepartments} icon={<RefreshCw className="w-4 h-4" />}>
          刷新
        </Button>
      </div>

      {/* Department Tree Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">组织架构</CardTitle>
        </CardHeader>
        <CardBody className="p-0">
          {loading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="w-8 h-8 animate-spin text-[var(--text-tertiary)]" />
            </div>
          ) : treeData.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-[var(--text-tertiary)]">
              <Building2 className="w-12 h-12 mb-4 opacity-30" />
              <p>暂无部门数据</p>
              <Button
                variant="secondary"
                className="mt-4"
                onClick={() => setIsCreateOpen(true)}
              >
                创建第一个部门
              </Button>
            </div>
          ) : (
            <Table hover>
              <TableHeader>
                <TableRow>
                  <TableCell variant="header" className="py-3 px-4 text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">部门名称</TableCell>
                  <TableCell variant="header" className="py-3 px-4 text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider w-24">编码</TableCell>
                  <TableCell variant="header" className="py-3 px-4 text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider w-20">类型</TableCell>
                  <TableCell variant="header" className="py-3 px-4 text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">描述</TableCell>
                  <TableCell variant="header" className="py-3 px-4 text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider w-16">状态</TableCell>
                  <TableCell variant="header" className="py-3 px-4 text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider text-right w-28">操作</TableCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {flatDepartments.map((dept) => {
                  const indentGap = dept.level * 24;
                  const isExpanded = expandedIds.has(dept.id);
                  return (
                    <TableRow key={dept.id} className="group">
                      <TableCell className="py-3 px-4">
                        <div className="flex items-center gap-2.5" style={{ paddingLeft: `${indentGap}px` }}>
                          {/* 展开/收起 */}
                          <button
                            onClick={() => dept.hasChildren && toggleExpand(dept.id)}
                            className={cn(
                              "w-5 h-5 flex items-center justify-center rounded hover:bg-[var(--bg-tertiary)] transition-colors flex-shrink-0",
                              !dept.hasChildren && "invisible"
                            )}
                          >
                            {isExpanded ? (
                              <ChevronDown className="w-4 h-4 text-[var(--text-tertiary)]" />
                            ) : (
                              <ChevronRight className="w-4 h-4 text-[var(--text-tertiary)]" />
                            )}
                          </button>
                          <div className={cn(
                            "w-7 h-7 rounded-md flex items-center justify-center flex-shrink-0",
                            dept.dept_type === 'company' ? "bg-[var(--accent-light)] text-[var(--accent)]" :
                            dept.dept_type === 'department' ? "bg-[var(--warning-bg)] text-[var(--warning)]" :
                            "bg-[var(--success-bg)] text-[var(--success)]"
                          )}>
                            {getDeptTypeIcon(dept.dept_type || 'department')}
                          </div>
                          <span className={cn(
                            "text-sm truncate",
                            dept.level === 0 ? "font-semibold text-[var(--text-primary)]" : "font-medium text-[var(--text-primary)]"
                          )}>{dept.name}</span>
                        </div>
                      </TableCell>
                      <TableCell className="py-3 px-4">
                        <span className="text-xs text-[var(--text-tertiary)] font-mono px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)]">{dept.code}</span>
                      </TableCell>
                      <TableCell className="py-3 px-4">
                        <Badge variant={
                          dept.dept_type === 'company' ? 'primary' :
                          dept.dept_type === 'department' ? 'secondary' : 'neutral'
                        } size="sm">
                          {getDeptTypeLabel(dept.dept_type || 'department')}
                        </Badge>
                      </TableCell>
                      <TableCell className="py-3 px-4">
                        <span className="text-sm text-[var(--text-secondary)] truncate max-w-[200px] block">
                          {dept.description || '-'}
                        </span>
                      </TableCell>
                      <TableCell className="py-3 px-4">
                        {dept.is_active !== false ? (
                          <span className="inline-flex items-center gap-1 text-xs text-[var(--success)]">
                            <span className="w-1.5 h-1.5 rounded-full bg-[var(--success)]" />
                            正常
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-xs text-[var(--text-tertiary)]">
                            <span className="w-1.5 h-1.5 rounded-full bg-[var(--text-tertiary)]" />
                            禁用
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="py-3 px-4">
                        <div className="flex gap-0.5 justify-end">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => openUsersDialog(dept)}
                            title="管理部门成员"
                            icon={<Users className="w-4 h-4" />}
                          />
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => openEditDialog(dept)}
                            title="编辑部门"
                            icon={<Edit2 className="w-4 h-4" />}
                          />
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDeleteDepartment(dept)}
                            title="删除部门"
                            icon={<Trash2 className="w-4 h-4" />}
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

      {/* Create Department Modal */}
      <Modal
        open={isCreateOpen}
        onOpenChange={setIsCreateOpen}
        title="创建部门"
        description="填写以下信息创建新部门"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsCreateOpen(false)}>取消</Button>
            <Button onClick={handleCreateDepartment}>创建</Button>
          </>
        }
      >
        <div className="py-4">
          {/* Section: 基本信息 */}
          <div className="mb-5">
            <div className="flex items-center gap-2 mb-3 pb-2 border-b border-[var(--border)]">
              <Building2 className="w-4 h-4 text-[var(--accent)]" />
              <span className="text-sm font-semibold text-[var(--text-primary)]">基本信息</span>
            </div>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-[var(--text-secondary)]">
                    部门名称 <span className="text-[var(--error)]">*</span>
                  </label>
                  <Input
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    placeholder="如：技术部"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-[var(--text-secondary)]">
                    部门编码 <span className="text-[var(--error)]">*</span>
                  </label>
                  <Input
                    value={formData.code}
                    onChange={(e) => setFormData({ ...formData, code: e.target.value })}
                    placeholder="如：tech"
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-[var(--text-secondary)]">描述</label>
                <Input
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="请输入部门描述（可选）"
                />
              </div>
            </div>
          </div>

          {/* Section: 组织关系 */}
          <div>
            <div className="flex items-center gap-2 mb-3 pb-2 border-b border-[var(--border)]">
              <FolderOpen className="w-4 h-4 text-[var(--accent)]" />
              <span className="text-sm font-semibold text-[var(--text-primary)]">组织关系</span>
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-[var(--text-secondary)]">父级部门</label>
              <Select
                value={formData.parent_id?.toString() || ''}
                onChange={(e) => setFormData({ ...formData, parent_id: e.target.value ? parseInt(e.target.value) : undefined })}
              >
                <option value="">无（作为根节点）</option>
                {departments.filter(d => !d.parent_id).map((dept) => (
                  <option key={dept.id} value={dept.id}>{dept.name}</option>
                ))}
              </Select>
              <p className="text-xs text-[var(--text-tertiary)]">不选择则创建为一级部门</p>
            </div>
          </div>
        </div>
      </Modal>

      {/* Edit Department Modal */}
      <Modal
        open={isEditOpen}
        onOpenChange={setIsEditOpen}
        title="编辑部门"
        description="修改部门信息"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsEditOpen(false)}>取消</Button>
            <Button onClick={handleUpdateDepartment}>保存</Button>
          </>
        }
      >
        <div className="py-4">
          {/* Section: 基本信息 */}
          <div>
            <div className="flex items-center gap-2 mb-3 pb-2 border-b border-[var(--border)]">
              <Building2 className="w-4 h-4 text-[var(--accent)]" />
              <span className="text-sm font-semibold text-[var(--text-primary)]">基本信息</span>
            </div>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-[var(--text-secondary)]">
                    部门名称 <span className="text-[var(--error)]">*</span>
                  </label>
                  <Input
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-[var(--text-secondary)]">部门编码</label>
                  <Input
                    value={formData.code}
                    onChange={(e) => setFormData({ ...formData, code: e.target.value })}
                    disabled
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-[var(--text-secondary)]">描述</label>
                <Input
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                />
              </div>
            </div>
          </div>
        </div>
      </Modal>

      {/* Department Users Modal */}
      <Modal
        open={isUsersOpen}
        onOpenChange={setIsUsersOpen}
        title="部门成员管理"
        description={
          <div className="flex items-center gap-2">
            <Building2 className="w-4 h-4 text-[var(--accent)]" />
            <span>{selectedDept?.name}</span>
            <Badge variant="neutral" size="sm">{deptUsers.length} 人</Badge>
          </div>
        }
        footer={
          <Button variant="secondary" onClick={() => setIsUsersOpen(false)}>关闭</Button>
        }
        width={580}
      >
        <div className="py-4">
          {/* Add User Section */}
          <div className="mb-5">
            <div className="flex items-center gap-2 mb-3 pb-2 border-b border-[var(--border)]">
              <Plus className="w-4 h-4 text-[var(--accent)]" />
              <span className="text-sm font-semibold text-[var(--text-primary)]">添加成员</span>
            </div>
            <div className="flex gap-2">
              <Select
                value={addUserId}
                onChange={(e) => setAddUserId(e.target.value)}
                className="flex-1"
              >
                <option value="">选择要添加的用户...</option>
                {allUsers
                  .filter(u => !deptUsers.find(du => du.id === u.id))
                  .map((user) => (
                    <option key={user.id} value={user.id}>
                      {user.username}{user.fullName ? ` (${user.fullName})` : ''} - {user.email}
                    </option>
                  ))
                }
              </Select>
              <Button
                onClick={() => {
                  if (addUserId) {
                    handleAddUserToDepartment(parseInt(addUserId));
                    setAddUserId('');
                  }
                }}
                disabled={!addUserId}
                icon={<Plus className="w-4 h-4" />}
              >
                添加
              </Button>
            </div>
            {allUsers.filter(u => !deptUsers.find(du => du.id === u.id)).length === 0 && (
              <p className="text-xs text-[var(--text-tertiary)] mt-2">所有用户已在此部门中</p>
            )}
          </div>

          {/* Current Users List */}
          <div>
            <div className="flex items-center gap-2 mb-3 pb-2 border-b border-[var(--border)]">
              <Users className="w-4 h-4 text-[var(--accent)]" />
              <span className="text-sm font-semibold text-[var(--text-primary)]">当前成员</span>
            </div>
            {deptUsers.length === 0 ? (
              <div className="text-center py-8 text-[var(--text-tertiary)]">
                <Users className="w-10 h-10 mx-auto mb-3 opacity-30" />
                <p className="text-sm">暂无成员</p>
              </div>
            ) : (
              <div className="space-y-1 max-h-[40vh] overflow-y-auto">
                {deptUsers.map((user) => (
                  <div
                    key={user.id}
                    className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-[var(--bg-primary)] transition-colors"
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <div className="w-8 h-8 rounded-full bg-[var(--accent-light)] flex items-center justify-center flex-shrink-0">
                        <User className="w-4 h-4 text-[var(--accent)]" />
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-[var(--text-primary)]">{user.username}</span>
                          {user.is_primary && (
                            <Badge variant="primary" size="sm">主部门</Badge>
                          )}
                        </div>
                        <p className="text-xs text-[var(--text-tertiary)] truncate">{user.email}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <Badge variant="neutral" size="sm">{user.dept_role || 'member'}</Badge>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleRemoveUserFromDepartment(user.id)}
                        title="移除成员"
                        icon={<Trash2 className="w-4 h-4" />}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </Modal>
    </div>
  );
}
