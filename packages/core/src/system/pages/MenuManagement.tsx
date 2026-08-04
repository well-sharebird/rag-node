import { useState, useEffect } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { useAuth } from '@/src/lib/auth-context';
import { Button, Card, CardHeader, CardBody, CardTitle, CardDescription, Input, Badge, Modal, Switch, Select, Table, TableHeader, TableBody, TableRow, TableCell } from '@/src/components/enterprise';
import { toast } from 'sonner';
import {
  Plus, Search, RefreshCw, Trash2, Edit2, Loader2, Folder, FileText, Square,
  ChevronRight, ChevronDown, FolderOpen, Settings, Eye, EyeOff, Link as LinkIcon,
  LayoutGrid, Type, Hash
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  MenuData, fetchMenus, createMenu, updateMenu, deleteMenu
} from '@/lib/api-client';

interface TreeNode extends MenuData {
  children?: TreeNode[];
  isExpanded?: boolean;
}

export function MenuManagement() {
  const { t } = useI18n();
  const { user, isAuthenticated } = useAuth();
  const [menus, setMenus] = useState<MenuData[]>([]);
  const [treeData, setTreeData] = useState<TreeNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [selectedMenu, setSelectedMenu] = useState<MenuData | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  // 菜单表单数据
  const [formData, setFormData] = useState({
    name: '',
    name_i18n: '',
    menu_type: 'menu' as 'menu' | 'sub_menu' | 'button',
    path: '',
    component: '',
    icon: '',
    order: 0,
    parent_id: undefined as number | undefined,
    permission: '',
    is_visible: true,
    is_active: true,
  });

  // 检查是否为管理员
  const isAdmin = user?.roles?.some(r => r.name === 'Admin' || r.name === 'super_admin');

  // 递归展平菜单树为列表（用于搜索过滤）
  const flattenTree = (tree: MenuData[]): MenuData[] => {
    const result: MenuData[] = [];
    const traverse = (nodes: MenuData[]) => {
      for (const node of nodes) {
        result.push(node);
        if (node.children && node.children.length > 0) {
          traverse(node.children);
        }
      }
    };
    traverse(tree);
    return result;
  };

  // 递归处理树形结构，保持层级关系
  const buildTree = (menuList: MenuData[]): TreeNode[] => {
    return menuList.map(menu => ({
      ...menu,
      children: menu.children && menu.children.length > 0 ? buildTree(menu.children) : [],
      isExpanded: expandedIds.has(menu.id) // 根据展开状态设置
    }));
  };

  useEffect(() => {
    // 搜索时，先展平所有菜单，过滤后再重建树形结构
    const allMenus = flattenTree(menus);
    const filteredMenus = allMenus.filter(m =>
      !searchQuery ||
      m.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      m.path.toLowerCase().includes(searchQuery.toLowerCase())
    );
    // 搜索结果显示为平铺列表（重建树形会丢失上下文）
    if (searchQuery) {
      setTreeData(filteredMenus.map(m => ({
        ...m,
        children: [],
        isExpanded: true
      })));
    } else {
      setTreeData(buildTree(menus));
    }
  }, [menus, searchQuery]);

  const loadMenus = async () => {
    try {
      const data = await fetchMenus();
      console.log('Menus loaded:', data);
      const items = Array.isArray(data.items) ? data.items : [];
      setMenus(items);
    } catch (e: any) {
      console.error('Failed to load menus:', e);
      toast.error(`加载菜单失败：${e.message}`);
      setMenus([]);
    } finally {
      setLoading(false);
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
    loadMenus();
  }, [isAuthenticated, isAdmin]);

  // 菜单加载后，初始化展开状态 - 默认展开所有一级菜单
  useEffect(() => {
    if (menus.length > 0) {
      const rootIds = new Set<number>();
      menus.forEach(menu => {
        rootIds.add(menu.id);
      });
      setExpandedIds(rootIds);
    }
  }, [menus]);

  const handleCreateMenu = async () => {
    try {
      if (!formData.name || !formData.path) {
        toast.error('名称和路径不能为空');
        return;
      }
      await createMenu({
        name: formData.name,
        name_i18n: formData.name_i18n || undefined,
        menu_type: formData.menu_type,
        path: formData.path,
        component: formData.component || undefined,
        icon: formData.icon || undefined,
        order: formData.order,
        parent_id: formData.parent_id,
        permission: formData.permission || undefined,
        is_visible: formData.is_visible,
        is_active: formData.is_active,
      });
      toast.success('菜单创建成功');
      setIsCreateOpen(false);
      resetForm();
      loadMenus();
    } catch (e: any) {
      console.error('Failed to create menu:', e);
      toast.error(`创建菜单失败：${e.message}`);
    }
  };

  const handleUpdateMenu = async () => {
    if (!selectedMenu) return;
    try {
      await updateMenu(selectedMenu.id, {
        name: formData.name,
        name_i18n: formData.name_i18n || undefined,
        path: formData.path,
        component: formData.component || undefined,
        icon: formData.icon || undefined,
        order: formData.order,
        permission: formData.permission || undefined,
        is_visible: formData.is_visible,
        is_active: formData.is_active,
      });
      toast.success('菜单更新成功');
      setIsEditOpen(false);
      loadMenus();
    } catch (e: any) {
      console.error('Failed to update menu:', e);
      toast.error(`更新菜单失败：${e.message}`);
    }
  };

  const handleDeleteMenu = async (menu: MenuData) => {
    if (!confirm(`确定要删除菜单 "${menu.name}" 吗？`)) return;
    try {
      await deleteMenu(menu.id);
      toast.success('菜单删除成功');
      loadMenus();
    } catch (e: any) {
      console.error('Failed to delete menu:', e);
      toast.error(`删除菜单失败：${e.message}`);
    }
  };

  const openEditDialog = (menu: MenuData) => {
    setSelectedMenu(menu);
    setFormData({
      name: menu.name,
      name_i18n: menu.name_i18n || '',
      menu_type: menu.menu_type as 'menu' | 'sub_menu' | 'button',
      path: menu.path,
      component: menu.component || '',
      icon: menu.icon || '',
      order: menu.order,
      parent_id: menu.parent_id,
      permission: menu.permission || '',
      is_visible: menu.is_visible,
      is_active: menu.is_active,
    });
    setIsEditOpen(true);
  };

  const resetForm = () => {
    setFormData({
      name: '',
      name_i18n: '',
      menu_type: 'menu',
      path: '',
      component: '',
      icon: '',
      order: 0,
      parent_id: undefined,
      permission: '',
      is_visible: true,
      is_active: true,
    });
  };

  const toggleExpand = (menuId: number) => {
    const newExpanded = new Set(expandedIds);
    if (newExpanded.has(menuId)) {
      newExpanded.delete(menuId);
    } else {
      newExpanded.add(menuId);
    }
    setExpandedIds(newExpanded);
  };

  const getMenuIcon = (menuType: string, icon?: string) => {
    if (icon) {
      return <Settings className="w-4 h-4" />;
    }
    switch (menuType) {
      case 'menu':
        return <Folder className="w-4 h-4" />;
      case 'sub_menu':
        return <FileText className="w-4 h-4" />;
      case 'button':
        return <Square className="w-4 h-4" />;
      default:
        return <Folder className="w-4 h-4" />;
    }
  };

  const getMenuTypeLabel = (menuType: string) => {
    switch (menuType) {
      case 'menu':
        return '目录';
      case 'sub_menu':
        return '菜单';
      case 'button':
        return '按钮';
      default:
        return menuType;
    }
  };

  // 展平菜单树为表格行（用于表格展示）- 根据展开状态控制子菜单显示
  interface FlatMenuNode extends MenuData {
    level: number;
    hasChildren: boolean;
  }
  const flattenMenuTree = (nodes: TreeNode[], level = 0, result: FlatMenuNode[] = []): FlatMenuNode[] => {
    nodes.forEach((node) => {
      const { children, ...menu } = node;
      const hasChildren = children ? children.length > 0 : false;
      result.push({ ...menu, level, hasChildren });
      // 根据展开状态决定是否显示子菜单
      const isExpanded = expandedIds.has(node.id);
      if (children && children.length > 0 && isExpanded) {
        flattenMenuTree(children, level + 1, result);
      }
    });
    return result;
  };
  const flatMenus = flattenMenuTree(treeData);

  // 展平菜单树为列表（用于父级菜单选择器）
  const flattenMenusForSelect = (nodes: TreeNode[], result: TreeNode[] = []): TreeNode[] => {
    nodes.forEach((node) => {
      result.push(node);
      if (node.children && node.children.length > 0) {
        flattenMenusForSelect(node.children, result);
      }
    });
    return result;
  };
  const allMenusForSelect = flattenMenusForSelect(treeData);

  if (!isAuthenticated) {
    return (
      <div className="p-6 space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <LayoutGrid className="w-5 h-5 text-[var(--warning)]" />
              需要登录
            </CardTitle>
            <CardDescription>
              请先登录以访问菜单管理页面
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
              <LayoutGrid className="w-5 h-5 text-[var(--error)]" />
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
            <LayoutGrid className="w-5 h-5 text-[var(--accent)]" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-[var(--text-primary)]">菜单管理</h1>
            <p className="text-sm text-[var(--text-secondary)] mt-0.5">
              共 {menus.length} 个菜单项 · 管理系统菜单树和路由配置
            </p>
          </div>
        </div>
        <Button
          onClick={() => setIsCreateOpen(true)}
          icon={<Plus className="w-4 h-4" />}
        >
          创建菜单
        </Button>
      </div>

      {/* Filters */}
      <div className="flex gap-3 items-center">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text-tertiary)]" />
          <Input
            placeholder="搜索菜单名称、路径..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
              />
            </div>
            <Button variant="secondary" onClick={loadMenus} icon={<RefreshCw className="w-4 h-4" />}>
              刷新
            </Button>
          </div>

      {/* Menu Tree Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">菜单树</CardTitle>
        </CardHeader>
        <CardBody className="p-0">
          {loading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="w-8 h-8 animate-spin text-[var(--text-tertiary)]" />
            </div>
          ) : treeData.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-[var(--text-tertiary)]">
              <LayoutGrid className="w-12 h-12 mb-4 opacity-30" />
              <p>暂无菜单数据</p>
              <Button
                variant="secondary"
                className="mt-4"
                onClick={() => setIsCreateOpen(true)}
              >
                创建第一个菜单
              </Button>
            </div>
          ) : (
            <Table hover>
              <TableHeader>
                <TableRow>
                  <TableCell variant="header" className="py-3 px-4 text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">菜单名称</TableCell>
                  <TableCell variant="header" className="py-3 px-4 text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider w-16">类型</TableCell>
                  <TableCell variant="header" className="py-3 px-4 text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">路径</TableCell>
                  <TableCell variant="header" className="py-3 px-4 text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider w-36">组件</TableCell>
                  <TableCell variant="header" className="py-3 px-4 text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider w-16">排序</TableCell>
                  <TableCell variant="header" className="py-3 px-4 text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider w-20">状态</TableCell>
                  <TableCell variant="header" className="py-3 px-4 text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider text-right w-20">操作</TableCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {flatMenus.map((menu) => {
                  const indentGap = menu.level * 24;
                  // 由于始终显示所有菜单，展开状态只用于图标显示
                  const isExpanded = expandedIds.has(menu.id);
                  return (
                    <TableRow key={menu.id} className="group">
                      <TableCell className="py-3 px-4">
                        <div className="flex items-center gap-2.5" style={{ paddingLeft: `${indentGap}px` }}>
                          {/* 展开/收起按钮 - 仅用于视觉指示层级关系 */}
                          <button
                            onClick={() => menu.hasChildren && toggleExpand(menu.id)}
                            className={cn(
                              "w-5 h-5 flex items-center justify-center rounded hover:bg-[var(--bg-tertiary)] transition-colors flex-shrink-0",
                              !menu.hasChildren && "invisible"
                            )}
                            title={isExpanded ? "收起子菜单" : "展开子菜单"}
                          >
                            {isExpanded ? (
                              <ChevronDown className="w-4 h-4 text-[var(--text-tertiary)]" />
                            ) : (
                              <ChevronRight className="w-4 h-4 text-[var(--text-tertiary)]" />
                            )}
                          </button>
                          <div className={cn(
                            "w-7 h-7 rounded-md flex items-center justify-center flex-shrink-0",
                            menu.menu_type === 'menu' ? "bg-[var(--warning-bg)] text-[var(--warning)]" :
                            menu.menu_type === 'sub_menu' ? "bg-[var(--accent-light)] text-[var(--accent)]" :
                            "bg-[var(--bg-tertiary)] text-[var(--text-secondary)]"
                          )}>
                            {menu.menu_type === 'menu' ? (
                              isExpanded ? <FolderOpen className="w-3.5 h-3.5" /> : <Folder className="w-3.5 h-3.5" />
                            ) : menu.menu_type === 'sub_menu' ? (
                              <FileText className="w-3.5 h-3.5" />
                            ) : (
                              <Square className="w-3.5 h-3.5" />
                            )}
                          </div>
                          <span className={cn(
                            "text-sm truncate",
                            menu.level === 0 ? "font-semibold text-[var(--text-primary)]" : "font-medium text-[var(--text-primary)]"
                          )}>{menu.name}</span>
                        </div>
                      </TableCell>
                      <TableCell className="py-3 px-4">
                        <Badge variant={
                          menu.menu_type === 'menu' ? 'primary' :
                          menu.menu_type === 'sub_menu' ? 'secondary' : 'neutral'
                        } size="sm">
                          {getMenuTypeLabel(menu.menu_type)}
                        </Badge>
                      </TableCell>
                      <TableCell className="py-3 px-4">
                        <span className="text-xs text-[var(--text-tertiary)] font-mono truncate max-w-[180px] block">{menu.path}</span>
                      </TableCell>
                      <TableCell className="py-3 px-4">
                        <span className="text-xs text-[var(--text-secondary)] truncate max-w-[140px] block">{menu.component || '-'}</span>
                      </TableCell>
                      <TableCell className="py-3 px-4">
                        <span className="text-xs text-[var(--text-secondary)] font-mono">{menu.order}</span>
                      </TableCell>
                      <TableCell className="py-3 px-4">
                        <div className="flex items-center gap-1.5">
                          {menu.is_visible ? (
                            <span className="inline-flex items-center gap-1 text-xs text-[var(--success)]">
                              <Eye className="w-3 h-3" />
                              可见
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-xs text-[var(--text-tertiary)]">
                              <EyeOff className="w-3 h-3" />
                              隐藏
                            </span>
                          )}
                          {!menu.is_active && (
                            <span className="text-xs text-[var(--text-tertiary)]">· 禁用</span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="py-3 px-4">
                        <div className="flex gap-0.5 justify-end">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => openEditDialog(menu)}
                            title="编辑菜单"
                            icon={<Edit2 className="w-4 h-4" />}
                          />
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDeleteMenu(menu)}
                            title="删除菜单"
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

      {/* Create Menu Modal */}
      <Modal
        open={isCreateOpen}
        onOpenChange={setIsCreateOpen}
        title="创建菜单"
        description="填写以下信息创建新菜单"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsCreateOpen(false)}>取消</Button>
            <Button onClick={handleCreateMenu}>创建</Button>
          </>
        }
        width={580}
      >
        <div className="py-4 max-h-[65vh] overflow-y-auto">
          {/* Section: 基本信息 */}
          <div className="mb-5">
            <div className="flex items-center gap-2 mb-3 pb-2 border-b border-[var(--border)]">
              <LayoutGrid className="w-4 h-4 text-[var(--accent)]" />
              <span className="text-sm font-semibold text-[var(--text-primary)]">基本信息</span>
            </div>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-[var(--text-secondary)]">
                    菜单名称 <span className="text-[var(--error)]">*</span>
                  </label>
                  <Input
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    placeholder="如：用户管理"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-[var(--text-secondary)]">国际化键</label>
                  <Input
                    value={formData.name_i18n}
                    onChange={(e) => setFormData({ ...formData, name_i18n: e.target.value })}
                    placeholder="如：nav.user-management"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-[var(--text-secondary)]">
                    菜单类型 <span className="text-[var(--error)]">*</span>
                  </label>
                  <Select
                    value={formData.menu_type}
                    onChange={(e) => setFormData({ ...formData, menu_type: e.target.value as 'menu' | 'sub_menu' | 'button' })}
                  >
                    <option value="menu">目录</option>
                    <option value="sub_menu">菜单</option>
                    <option value="button">按钮</option>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-[var(--text-secondary)]">父级菜单</label>
                  <Select
                    value={formData.parent_id?.toString() || ''}
                    onChange={(e) => setFormData({ ...formData, parent_id: e.target.value ? parseInt(e.target.value) : undefined })}
                  >
                    <option value="">无（作为根节点）</option>
                    {allMenusForSelect.filter(m => m.menu_type === 'menu').map((menu) => (
                      <option key={menu.id} value={menu.id}>{menu.name}</option>
                    ))}
                  </Select>
                </div>
              </div>
            </div>
          </div>

          {/* Section: 路由配置 */}
          <div className="mb-5">
            <div className="flex items-center gap-2 mb-3 pb-2 border-b border-[var(--border)]">
              <LinkIcon className="w-4 h-4 text-[var(--accent)]" />
              <span className="text-sm font-semibold text-[var(--text-primary)]">路由配置</span>
            </div>
            <div className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-[var(--text-secondary)]">
                  路径 <span className="text-[var(--error)]">*</span>
                </label>
                <Input
                  value={formData.path}
                  onChange={(e) => setFormData({ ...formData, path: e.target.value })}
                  placeholder="如：/admin/users"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-[var(--text-secondary)]">组件</label>
                  <Input
                    value={formData.component}
                    onChange={(e) => setFormData({ ...formData, component: e.target.value })}
                    placeholder="如：UserManagement"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-[var(--text-secondary)]">图标</label>
                  <Input
                    value={formData.icon}
                    onChange={(e) => setFormData({ ...formData, icon: e.target.value })}
                    placeholder="如：Users"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Section: 权限与排序 */}
          <div className="mb-5">
            <div className="flex items-center gap-2 mb-3 pb-2 border-b border-[var(--border)]">
              <Hash className="w-4 h-4 text-[var(--accent)]" />
              <span className="text-sm font-semibold text-[var(--text-primary)]">权限与排序</span>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-[var(--text-secondary)]">排序</label>
                <Input
                  type="number"
                  value={formData.order}
                  onChange={(e) => setFormData({ ...formData, order: parseInt(e.target.value) || 0 })}
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-[var(--text-secondary)]">权限标识</label>
                <Input
                  value={formData.permission}
                  onChange={(e) => setFormData({ ...formData, permission: e.target.value })}
                  placeholder="如：user:manage"
                />
              </div>
            </div>
          </div>

          {/* Section: 显示设置 */}
          <div>
            <div className="flex items-center gap-2 mb-3 pb-2 border-b border-[var(--border)]">
              <Eye className="w-4 h-4 text-[var(--accent)]" />
              <span className="text-sm font-semibold text-[var(--text-primary)]">显示设置</span>
            </div>
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2">
                <Switch
                  checked={formData.is_visible}
                  onCheckedChange={(checked) => setFormData({ ...formData, is_visible: checked })}
                />
                <label className="text-sm text-[var(--text-secondary)] flex items-center gap-1">
                  {formData.is_visible ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
                  可见
                </label>
              </div>
              <div className="flex items-center gap-2">
                <Switch
                  checked={formData.is_active}
                  onCheckedChange={(checked) => setFormData({ ...formData, is_active: checked })}
                />
                <label className="text-sm text-[var(--text-secondary)]">启用</label>
              </div>
            </div>
          </div>
        </div>
      </Modal>

      {/* Edit Menu Modal */}
      <Modal
        open={isEditOpen}
        onOpenChange={setIsEditOpen}
        title="编辑菜单"
        description="修改菜单配置"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsEditOpen(false)}>取消</Button>
            <Button onClick={handleUpdateMenu}>保存</Button>
          </>
        }
        width={580}
      >
        <div className="py-4 max-h-[65vh] overflow-y-auto">
          {/* Section: 基本信息 */}
          <div className="mb-5">
            <div className="flex items-center gap-2 mb-3 pb-2 border-b border-[var(--border)]">
              <LayoutGrid className="w-4 h-4 text-[var(--accent)]" />
              <span className="text-sm font-semibold text-[var(--text-primary)]">基本信息</span>
            </div>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-[var(--text-secondary)]">
                    菜单名称 <span className="text-[var(--error)]">*</span>
                  </label>
                  <Input
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-[var(--text-secondary)]">国际化键</label>
                  <Input
                    value={formData.name_i18n}
                    onChange={(e) => setFormData({ ...formData, name_i18n: e.target.value })}
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-[var(--text-secondary)]">菜单类型</label>
                  <Select
                    value={formData.menu_type}
                    onChange={(e) => setFormData({ ...formData, menu_type: e.target.value as 'menu' | 'sub_menu' | 'button' })}
                    disabled
                  >
                    <option value="menu">目录</option>
                    <option value="sub_menu">菜单</option>
                    <option value="button">按钮</option>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-[var(--text-secondary)]">父级菜单</label>
                  <Select
                    value={formData.parent_id?.toString() || ''}
                    onChange={(e) => setFormData({ ...formData, parent_id: e.target.value ? parseInt(e.target.value) : undefined })}
                  >
                    <option value="">无（作为根节点）</option>
                    {allMenusForSelect.filter(m => m.id !== selectedMenu?.id && m.menu_type === 'menu').map((menu) => (
                      <option key={menu.id} value={menu.id}>{menu.name}</option>
                    ))}
                  </Select>
                </div>
              </div>
            </div>
          </div>

          {/* Section: 路由配置 */}
          <div className="mb-5">
            <div className="flex items-center gap-2 mb-3 pb-2 border-b border-[var(--border)]">
              <LinkIcon className="w-4 h-4 text-[var(--accent)]" />
              <span className="text-sm font-semibold text-[var(--text-primary)]">路由配置</span>
            </div>
            <div className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-[var(--text-secondary)]">
                  路径 <span className="text-[var(--error)]">*</span>
                </label>
                <Input
                  value={formData.path}
                  onChange={(e) => setFormData({ ...formData, path: e.target.value })}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-[var(--text-secondary)]">组件</label>
                  <Input
                    value={formData.component}
                    onChange={(e) => setFormData({ ...formData, component: e.target.value })}
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-[var(--text-secondary)]">图标</label>
                  <Input
                    value={formData.icon}
                    onChange={(e) => setFormData({ ...formData, icon: e.target.value })}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Section: 权限与排序 */}
          <div className="mb-5">
            <div className="flex items-center gap-2 mb-3 pb-2 border-b border-[var(--border)]">
              <Hash className="w-4 h-4 text-[var(--accent)]" />
              <span className="text-sm font-semibold text-[var(--text-primary)]">权限与排序</span>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-[var(--text-secondary)]">排序</label>
                <Input
                  type="number"
                  value={formData.order}
                  onChange={(e) => setFormData({ ...formData, order: parseInt(e.target.value) || 0 })}
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-[var(--text-secondary)]">权限标识</label>
                <Input
                  value={formData.permission}
                  onChange={(e) => setFormData({ ...formData, permission: e.target.value })}
                />
              </div>
            </div>
          </div>

          {/* Section: 显示设置 */}
          <div>
            <div className="flex items-center gap-2 mb-3 pb-2 border-b border-[var(--border)]">
              <Eye className="w-4 h-4 text-[var(--accent)]" />
              <span className="text-sm font-semibold text-[var(--text-primary)]">显示设置</span>
            </div>
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2">
                <Switch
                  checked={formData.is_visible}
                  onCheckedChange={(checked) => setFormData({ ...formData, is_visible: checked })}
                />
                <label className="text-sm text-[var(--text-secondary)] flex items-center gap-1">
                  {formData.is_visible ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
                  可见
                </label>
              </div>
              <div className="flex items-center gap-2">
                <Switch
                  checked={formData.is_active}
                  onCheckedChange={(checked) => setFormData({ ...formData, is_active: checked })}
                />
                <label className="text-sm text-[var(--text-secondary)]">启用</label>
              </div>
            </div>
          </div>
        </div>
      </Modal>
    </div>
  );
}
