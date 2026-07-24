/**
 * 提示词模板管理页面
 * Prompt Template Management View - Bird Design System
 */

import { useState, useEffect } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { toast } from 'sonner';
import { Button, Card, CardHeader, CardBody, CardTitle, Badge, Input } from '@/src/components/bird';
import { Select } from '@/src/components/bird/Select';
import {
  FileText, Plus, Search, MoreVertical, Trash2, Eye, Edit2,
  GitBranch, Tag, TrendingUp, Calendar, User, ChevronRight,
  Loader2, AlertCircle, CheckCircle2
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { promptsApi, type PromptTemplate } from '@/src/lib/api/prompts';

interface PromptTemplatesViewProps {
  onNavigateToDetail?: (templateName: string) => void;
}

export function PromptTemplatesViewBird({ onNavigateToDetail }: PromptTemplatesViewProps) {
  const { t, language } = useI18n();

  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterCategory, setFilterCategory] = useState<string>('all');
  const [filterStatus, setFilterStatus] = useState<string>('all');

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [newCategory, setNewCategory] = useState<'system' | 'user' | 'instruction'>('system');
  const [newOwner, setNewOwner] = useState('');
  const [creating, setCreating] = useState(false);

  const loadTemplates = async () => {
    try {
      setLoading(true);
      const data = await promptsApi.listTemplates();
      setTemplates((data as any).items || []);
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
      toast.error(error.message || (language === 'zh' ? '操作失败' : 'Failed'));
    }
  };

  const getCategoryBadge = (category: string) => {
    const map: Record<string, { variant: 'primary' | 'success' | 'warning', label: string }> = {
      system: { variant: 'primary', label: language === 'zh' ? '系统' : 'System' },
      user: { variant: 'success', label: language === 'zh' ? '用户' : 'User' },
      instruction: { variant: 'warning', label: language === 'zh' ? '指令' : 'Instruction' },
    };
    const badge = map[category] || { variant: 'primary' as const, label: category };
    return <Badge variant={badge.variant} size="sm">{badge.label}</Badge>;
  };

  const filteredTemplates = templates.filter(t => {
    const matchesSearch = t.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (t.description || '').toLowerCase().includes(searchTerm.toLowerCase());
    const matchesCategory = filterCategory === 'all' || t.category === filterCategory;
    const matchesStatus = filterStatus === 'all' || t.status === filterStatus;
    return matchesSearch && matchesCategory && matchesStatus;
  });

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-[#f9fafb]">
      {/* Header */}
      <header className="h-[60px] px-6 bg-white flex items-center justify-between shrink-0 border-b border-[#e5e7eb]">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-[#ede9fe] flex items-center justify-center">
            <FileText className="w-5 h-5 text-[#7c3aed]" />
          </div>
          <div>
            <h1 className="text-[18px] font-semibold text-[#111827]">
              {language === 'zh' ? '提示词模板' : 'Prompt Templates'}
            </h1>
            <p className="text-[12px] text-[#6b7280]">
              {language === 'zh' ? '管理和版本控制提示词模板' : 'Manage and version control prompt templates'}
            </p>
          </div>
        </div>
        <Button
          onClick={() => setIsCreateOpen(true)}
          className="bg-[#7c3aed] hover:bg-[#6d28d9] text-white"
          icon={<Plus className="w-4 h-4" />}
        >
          {language === 'zh' ? '新建模板' : 'New Template'}
        </Button>
      </header>

      {/* Filters */}
      <div className="px-6 py-4 bg-white border-b border-[#e5e7eb]">
        <div className="flex gap-3">
          <div className="flex-1 relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-[#9ca3af]" />
            <Input
              placeholder={language === 'zh' ? '搜索模板...' : 'Search templates...'}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10"
            />
          </div>
          <select
            value={filterCategory}
            onChange={(e) => setFilterCategory(e.target.value)}
            className="kimi-input w-[150px]"
          >
            <option value="all">{language === 'zh' ? '所有类别' : 'All Categories'}</option>
            <option value="system">{language === 'zh' ? '系统' : 'System'}</option>
            <option value="user">{language === 'zh' ? '用户' : 'User'}</option>
            <option value="instruction">{language === 'zh' ? '指令' : 'Instruction'}</option>
          </select>
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="kimi-input w-[120px]"
          >
            <option value="all">{language === 'zh' ? '所有状态' : 'All Status'}</option>
            <option value="active">{language === 'zh' ? '活跃' : 'Active'}</option>
            <option value="archived">{language === 'zh' ? '已归档' : 'Archived'}</option>
          </select>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {loading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="w-8 h-8 animate-spin text-[#9ca3af]" />
          </div>
        ) : filteredTemplates.length === 0 ? (
          <Card>
            <CardBody className="py-12 text-center">
              <FileText className="w-12 h-12 mx-auto mb-4 text-[#d1d5db]" />
              <p className="text-[14px] text-[#6b7280]">
                {language === 'zh' ? '暂无模板' : 'No templates'}
              </p>
            </CardBody>
          </Card>
        ) : (
          <div className="grid gap-4">
            {filteredTemplates.map((template) => (
              <Card key={template.name} className="hover:shadow-md transition-shadow">
                <CardBody>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="w-12 h-12 rounded-xl bg-[#ede9fe] flex items-center justify-center">
                        <FileText className="w-6 h-6 text-[#7c3aed]" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="text-[14px] font-semibold text-[#111827]">{template.name}</h3>
                          {getCategoryBadge(template.category)}
                          {template.status === 'active' ? (
                            <Badge variant="success" size="sm">{language === 'zh' ? '活跃' : 'Active'}</Badge>
                          ) : (
                            <Badge variant="neutral" size="sm">{language === 'zh' ? '已归档' : 'Archived'}</Badge>
                          )}
                        </div>
                        <p className="text-[13px] text-[#6b7280] mt-1">
                          {template.description || (language === 'zh' ? '无描述' : 'No description')}
                        </p>
                        <div className="flex items-center gap-4 mt-2 text-[12px] text-[#9ca3af]">
                          <span className="flex items-center gap-1">
                            <User className="w-3 h-3" />
                            {template.owner || (language === 'zh' ? '未知' : 'Unknown')}
                          </span>
                          {template.updated_at && (
                            <span className="flex items-center gap-1">
                              <Calendar className="w-3 h-3" />
                              {new Date(template.updated_at).toLocaleDateString('zh-CN')}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => onNavigateToDetail?.(template.name)}
                        icon={<ChevronRight className="w-4 h-4" />}
                      >
                        {language === 'zh' ? '详情' : 'Details'}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDelete(template)}
                        icon={<Trash2 className="w-4 h-4 text-[#ef4444]" />}
                      />
                    </div>
                  </div>
                </CardBody>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
