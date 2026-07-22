/**
 * 提示词模板管理页面
 * Prompt Template Management View
 */

import { useState, useEffect } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import {
  FileText, Plus, Search, MoreVertical, Trash2, Eye, Edit2,
  GitBranch, Tag, TrendingUp, Calendar, User, ChevronRight,
  Loader2, AlertCircle, CheckCircle2, XCircle
} from 'lucide-react';
import { promptsApi, type PromptTemplate } from '@/src/lib/api/prompts';
import { cn } from '@/lib/utils';

interface PromptTemplatesViewProps {
  onNavigateToDetail?: (templateName: string) => void;
}

export function PromptTemplatesView({ onNavigateToDetail }: PromptTemplatesViewProps) {
  const { t, language } = useI18n();

  // State
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterCategory, setFilterCategory] = useState<string>('all');
  const [filterStatus, setFilterStatus] = useState<string>('all');

  // Create dialog
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [newCategory, setNewCategory] = useState<'system' | 'user' | 'instruction'>('system');
  const [newOwner, setNewOwner] = useState('');
  const [creating, setCreating] = useState(false);

  // Load templates
  const loadTemplates = async () => {
    try {
      setLoading(true);
      const data = await promptsApi.listTemplates();
      setTemplates(data.items || []);
    } catch (error) {
      console.error('Failed to load templates:', error);
      toast.error(language === 'zh' ? '加载模板列表失败' : 'Failed to load templates');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTemplates();
  }, []);

  // Create template
  const handleCreate = async () => {
    if (!newName.trim()) {
      toast.error(language === 'zh' ? '请输入模板名称' : 'Please enter template name');
      return;
    }

    try {
      setCreating(true);
      await promptsApi.createTemplate({
        name: newName.trim(),
        description: newDescription.trim() || undefined,
        category: newCategory,
        owner: newOwner.trim() || undefined,
      });
      toast.success(language === 'zh' ? '模板创建成功' : 'Template created');
      setIsCreateOpen(false);
      setNewName('');
      setNewDescription('');
      setNewCategory('system');
      setNewOwner('');
      loadTemplates();
    } catch (error: any) {
      toast.error(error.message || (language === 'zh' ? '创建失败' : 'Failed to create'));
    } finally {
      setCreating(false);
    }
  };

  // Delete template
  const handleDelete = async (template: PromptTemplate) => {
    if (!confirm(language === 'zh'
      ? `确定要归档模板 "${template.name}" 吗？`
      : `Are you sure to archive template "${template.name}"?`)) {
      return;
    }

    try {
      await promptsApi.archiveTemplate(template.name);
      toast.success(language === 'zh' ? '模板已归档' : 'Template archived');
      loadTemplates();
    } catch (error: any) {
      toast.error(error.message || (language === 'zh' ? '删除失败' : 'Failed to delete'));
    }
  };

  // Navigate to detail
  const handleNavigate = (template: PromptTemplate) => {
    if (onNavigateToDetail) {
      onNavigateToDetail(template.name);
    }
  };

  // Filter templates
  const filteredTemplates = templates.filter((t) => {
    const matchSearch = t.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (t.description?.toLowerCase().includes(searchTerm.toLowerCase()) ?? false);
    const matchCategory = filterCategory === 'all' || t.category === filterCategory;
    const matchStatus = filterStatus === 'all' || t.status === filterStatus;
    return matchSearch && matchCategory && matchStatus;
  });

  // Category badge colors
  const getCategoryColor = (category: string) => {
    switch (category) {
      case 'system': return 'bg-blue-100 text-blue-700';
      case 'user': return 'bg-green-100 text-green-700';
      case 'instruction': return 'bg-purple-100 text-purple-700';
      default: return 'bg-gray-100 text-gray-700';
    }
  };

  const getStatusColor = (status: string) => {
    return status === 'active'
      ? 'bg-green-100 text-green-700'
      : 'bg-gray-100 text-gray-700';
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-[#f7f7f7]">
      {/* Header */}
      <header className="h-[52px] px-5 bg-white flex items-center justify-between shrink-0 border-b border-[#e5e5e5]">
        <div className="flex items-center gap-3">
          <FileText className="w-5 h-5 text-[#534ab7]" />
          <h1 className="text-[15px] font-medium text-[#1a1a1a]">
            {language === 'zh' ? '提示词模板管理' : 'Prompt Templates'}
          </h1>
        </div>
        <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
          <DialogTrigger asChild>
            <Button className="bg-[#1a1a1a] hover:bg-[#333] text-white text-sm">
              <Plus className="w-4 h-4 mr-1" />
              {language === 'zh' ? '新建模板' : 'New Template'}
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-[500px]">
            <DialogHeader>
              <DialogTitle>{language === 'zh' ? '创建提示词模板' : 'Create Prompt Template'}</DialogTitle>
              <DialogDescription>
                {language === 'zh'
                  ? '创建一个新的提示词模板，后续可以添加版本和标签'
                  : 'Create a new prompt template, then add versions and tags'}
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div>
                <label className="text-sm font-medium mb-1 block">
                  {language === 'zh' ? '模板名称' : 'Template Name'} *
                </label>
                <Input
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="e.g., safety_system_prompt"
                  className="font-mono text-sm"
                />
                <p className="text-xs text-gray-500 mt-1">
                  {language === 'zh' ? '唯一标识符，使用小写字母和下划线' : 'Unique identifier, use lowercase and underscores'}
                </p>
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">
                  {language === 'zh' ? '描述' : 'Description'}
                </label>
                <Textarea
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  placeholder={language === 'zh' ? '描述模板用途...' : 'Describe the template purpose...'}
                  rows={3}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium mb-1 block">
                    {language === 'zh' ? '分类' : 'Category'}
                  </label>
                  <Select value={newCategory} onValueChange={(v) => setNewCategory(v as any)}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="system">System</SelectItem>
                      <SelectItem value="user">User</SelectItem>
                      <SelectItem value="instruction">Instruction</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <label className="text-sm font-medium mb-1 block">
                    {language === 'zh' ? '负责人' : 'Owner'}
                  </label>
                  <Input
                    value={newOwner}
                    onChange={(e) => setNewOwner(e.target.value)}
                    placeholder="username"
                  />
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setIsCreateOpen(false)}>
                {language === 'zh' ? '取消' : 'Cancel'}
              </Button>
              <Button
                onClick={handleCreate}
                disabled={creating || !newName.trim()}
                className="bg-[#1a1a1a] hover:bg-[#333]"
              >
                {creating && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
                {language === 'zh' ? '创建' : 'Create'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </header>

      {/* Filters */}
      <div className="px-5 py-4 bg-white border-b border-[#e5e5e5]">
        <div className="flex items-center gap-3">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <Input
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder={language === 'zh' ? '搜索模板...' : 'Search templates...'}
              className="pl-9"
            />
          </div>
          <Select value={filterCategory} onValueChange={setFilterCategory}>
            <SelectTrigger className="w-[150px]">
              <SelectValue placeholder={language === 'zh' ? '全部分类' : 'All Categories'} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{language === 'zh' ? '全部分类' : 'All Categories'}</SelectItem>
              <SelectItem value="system">System</SelectItem>
              <SelectItem value="user">User</SelectItem>
              <SelectItem value="instruction">Instruction</SelectItem>
            </SelectContent>
          </Select>
          <Select value={filterStatus} onValueChange={setFilterStatus}>
            <SelectTrigger className="w-[120px]">
              <SelectValue placeholder={language === 'zh' ? '全部状态' : 'All Status'} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{language === 'zh' ? '全部状态' : 'All Status'}</SelectItem>
              <SelectItem value="active">{language === 'zh' ? '启用中' : 'Active'}</SelectItem>
              <SelectItem value="archived">{language === 'zh' ? '已归档' : 'Archived'}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-5">
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="w-8 h-8 animate-spin text-[#534ab7]" />
          </div>
        ) : filteredTemplates.length === 0 ? (
          <Card className="border-dashed">
            <CardContent className="flex flex-col items-center justify-center py-16">
              <FileText className="w-12 h-12 text-gray-300 mb-4" />
              <p className="text-gray-500 text-sm">
                {searchTerm || filterCategory !== 'all' || filterStatus !== 'all'
                  ? (language === 'zh' ? '没有找到匹配的模板' : 'No matching templates found')
                  : (language === 'zh' ? '暂无模板，点击右上角创建第一个' : 'No templates yet, create one to get started')}
              </p>
            </CardContent>
          </Card>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{language === 'zh' ? '模板名称' : 'Template Name'}</TableHead>
                <TableHead>{language === 'zh' ? '描述' : 'Description'}</TableHead>
                <TableHead>{language === 'zh' ? '分类' : 'Category'}</TableHead>
                <TableHead>{language === 'zh' ? '标签' : 'Tags'}</TableHead>
                <TableHead>{language === 'zh' ? '负责人' : 'Owner'}</TableHead>
                <TableHead>{language === 'zh' ? '状态' : 'Status'}</TableHead>
                <TableHead className="w-[80px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredTemplates.map((template) => (
                <TableRow
                  key={template.id}
                  className="cursor-pointer hover:bg-gray-50"
                  onClick={() => handleNavigate(template)}
                >
                  <TableCell className="font-medium">
                    <div className="flex items-center gap-2">
                      <FileText className="w-4 h-4 text-gray-400" />
                      <span className="font-mono text-sm">{template.name}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <span className="text-sm text-gray-500 line-clamp-1 max-w-[300px]">
                      {template.description || '-'}
                    </span>
                  </TableCell>
                  <TableCell>
                    <Badge className={getCategoryColor(template.category)} variant="secondary">
                      {template.category}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1">
                      {template.current_tags && Object.entries(template.current_tags).map(([tag, version]) => (
                        <Badge key={tag} variant="outline" className="text-xs">
                          <Tag className="w-3 h-3 mr-0.5" />
                          {tag}={version}
                        </Badge>
                      ))}
                      {(!template.current_tags || Object.keys(template.current_tags).length === 0) && (
                        <span className="text-gray-400 text-xs">-</span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    {template.owner ? (
                      <div className="flex items-center gap-1.5 text-sm text-gray-600">
                        <User className="w-3.5 h-3.5" />
                        {template.owner}
                      </div>
                    ) : (
                      <span className="text-gray-400 text-sm">-</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge className={getStatusColor(template.status)} variant="secondary">
                      {template.status === 'active'
                        ? (language === 'zh' ? '启用中' : 'Active')
                        : (language === 'zh' ? '已归档' : 'Archived')}
                    </Badge>
                  </TableCell>
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                          <MoreVertical className="w-4 h-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => handleNavigate(template)}>
                          <Eye className="w-4 h-4 mr-2" />
                          {language === 'zh' ? '查看详情' : 'View Detail'}
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onClick={() => handleDelete(template)}
                          className="text-red-600"
                        >
                          <Trash2 className="w-4 h-4 mr-2" />
                          {language === 'zh' ? '归档' : 'Archive'}
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      {/* Footer stats */}
      <div className="h-[40px] px-5 bg-white border-t border-[#e5e5e5] flex items-center justify-between text-xs text-gray-500">
        <span>
          {language === 'zh'
            ? `共 ${filteredTemplates.length} 个模板`
            : `${filteredTemplates.length} templates`}
        </span>
        <span className="flex items-center gap-1">
          <CheckCircle2 className="w-3 h-3 text-green-500" />
          {templates.filter(t => t.status === 'active').length} active
          <span className="mx-1">|</span>
          <XCircle className="w-3 h-3 text-gray-400" />
          {templates.filter(t => t.status === 'archived').length} archived
        </span>
      </div>
    </div>
  );
}
