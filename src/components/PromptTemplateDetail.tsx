/**
 * 提示词模板详情页面
 * Prompt Template Detail View
 */

import { useState, useEffect, useRef } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  ArrowLeft, FileText, GitBranch, Tag, TrendingUp, Calendar, User, Plus,
  Loader2, CheckCircle2, XCircle, AlertCircle, Play, Copy, Eye, Trash2,
  ChevronRight, GitMerge, Clock, BarChart3
} from 'lucide-react';
import { promptsApi, type PromptTemplate, type PromptVersion, type PromptTag, type TestCase, type EvalReport } from '@/src/lib/api/prompts';
import { cn } from '@/lib/utils';

interface PromptTemplateDetailProps {
  templateName: string;
  onBack?: () => void;
}

export function PromptTemplateDetail({ templateName, onBack }: PromptTemplateDetailProps) {
  const { t, language } = useI18n();

  // State
  const [template, setTemplate] = useState<PromptTemplate | null>(null);
  const [versions, setVersions] = useState<PromptVersion[]>([]);
  const [tags, setTags] = useState<PromptTag[]>([]);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedVersion, setSelectedVersion] = useState<PromptVersion | null>(null);
  const [activeTab, setActiveTab] = useState<'versions' | 'test-cases' | 'eval' | 'audit'>('versions');

  // Create version dialog
  const [isCreateVersionOpen, setIsCreateVersionOpen] = useState(false);
  const [newVersion, setNewVersion] = useState('');
  const [newContent, setNewContent] = useState('');
  const [newChangelog, setNewChangelog] = useState('');
  const [creating, setCreating] = useState(false);

  // Tag dialog
  const [isTagOpen, setIsTagOpen] = useState(false);
  const [selectedTag, setSelectedTag] = useState<string>('stable');
  const [selectedVersionForTag, setSelectedVersionForTag] = useState<number | null>(null);
  const [grayPercent, setGrayPercent] = useState<number>(0);

  // Eval dialog
  const [isEvalOpen, setIsEvalOpen] = useState(false);
  const [candidateVersion, setCandidateVersion] = useState<number | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [evalReport, setEvalReport] = useState<EvalReport | null>(null);

  // Render preview
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [renderVariables, setRenderVariables] = useState<Record<string, string>>({});
  const [renderedContent, setRenderedContent] = useState('');

  // Load data
  const loadData = async () => {
    try {
      setLoading(true);
      const [templateData, versionsData, tagsData, testCasesData] = await Promise.all([
        promptsApi.getTemplate(templateName),
        promptsApi.listVersions(templateName, { limit: 50 }),
        promptsApi.listTags(templateName),
        promptsApi.listTestCases(templateName),
      ]);
      setTemplate(templateData);
      setVersions(versionsData.items || []);
      setTags(tagsData.items || []);
      setTestCases(testCasesData.items || []);

      // Select first version by default
      if (versionsData.items?.length > 0) {
        setSelectedVersion(versionsData.items[0]);
      }
    } catch (error: any) {
      console.error('Failed to load template detail:', error);
      toast.error(error.message || (language === 'zh' ? '加载失败' : 'Failed to load'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [templateName]);

  // Create version
  const handleCreateVersion = async () => {
    if (!newVersion.trim() || !newContent.trim()) {
      toast.error(language === 'zh' ? '请填写版本号和内容' : 'Please fill version and content');
      return;
    }

    try {
      setCreating(true);
      await promptsApi.createVersion(templateName, {
        version: newVersion,
        content: newContent,
        changelog: newChangelog || undefined,
      });
      toast.success(language === 'zh' ? '版本创建成功' : 'Version created');
      setIsCreateVersionOpen(false);
      setNewVersion('');
      setNewContent('');
      setNewChangelog('');
      loadData();
    } catch (error: any) {
      toast.error(error.message || (language === 'zh' ? '创建失败' : 'Failed to create'));
    } finally {
      setCreating(false);
    }
  };

  // Release version
  const handleReleaseVersion = async (versionId: number) => {
    try {
      await promptsApi.releaseVersion(templateName, versionId);
      toast.success(language === 'zh' ? '版本已发布' : 'Version released');
      loadData();
    } catch (error: any) {
      toast.error(error.message || (language === 'zh' ? '发布失败' : 'Failed to release'));
    }
  };

  // Set tag
  const handleSetTag = async () => {
    if (!selectedVersionForTag) {
      toast.error(language === 'zh' ? '请选择版本' : 'Please select a version');
      return;
    }

    try {
      await promptsApi.setTag(templateName, {
        tag_name: selectedTag,
        version_id: selectedVersionForTag,
        meta_config: selectedTag === 'canary' ? { gray_percent: grayPercent } : {},
      });
      toast.success(language === 'zh' ? `标签 ${selectedTag} 已设置` : `Tag ${selectedTag} set`);
      setIsTagOpen(false);
      loadData();
    } catch (error: any) {
      toast.error(error.message || (language === 'zh' ? '设置失败' : 'Failed to set'));
    }
  };

  // Run evaluation
  const handleRunEval = async () => {
    if (!candidateVersion) {
      toast.error(language === 'zh' ? '请选择候选版本' : 'Please select candidate version');
      return;
    }

    try {
      setEvaluating(true);
      const report = await promptsApi.runEvaluation(templateName, {
        candidate_version_id: candidateVersion,
        triggered_by: 'web',
      });
      setEvalReport(report);
      toast.success(language === 'zh' ? '评估完成' : 'Evaluation completed');
    } catch (error: any) {
      toast.error(error.message || (language === 'zh' ? '评估失败' : 'Evaluation failed'));
    } finally {
      setEvaluating(false);
    }
  };

  // Open preview
  const handlePreview = (version: PromptVersion) => {
    setSelectedVersion(version);
    // Extract variables from schema
    const vars: Record<string, string> = {};
    version.variables_schema?.forEach((v) => {
      vars[v.name] = v.default || '';
    });
    setRenderVariables(vars);
    setRenderedContent(version.content);
    setIsPreviewOpen(true);
  };

  // Render preview content
  useEffect(() => {
    if (isPreviewOpen && selectedVersion) {
      let content = selectedVersion.content;
      Object.entries(renderVariables).forEach(([key, value]) => {
        content = content.replace(new RegExp(`\\{\\{${key}\\}\\}`, 'g'), value || `__${key}__`);
      });
      setRenderedContent(content);
    }
  }, [renderVariables, isPreviewOpen, selectedVersion]);

  // Get tag color
  const getTagColor = (tagName: string) => {
    switch (tagName) {
      case 'stable': return 'bg-green-100 text-green-700 border-green-300';
      case 'beta': return 'bg-yellow-100 text-yellow-700 border-yellow-300';
      case 'dev': return 'bg-blue-100 text-blue-700 border-blue-300';
      case 'canary': return 'bg-purple-100 text-purple-700 border-purple-300';
      default: return 'bg-gray-100 text-gray-700 border-gray-300';
    }
  };

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-[#534ab7]" />
      </div>
    );
  }

  if (!template) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center">
        <AlertCircle className="w-12 h-12 text-red-400 mb-4" />
        <h2 className="text-lg font-medium text-gray-700">
          {language === 'zh' ? '模板不存在' : 'Template not found'}
        </h2>
        <Button onClick={onBack} className="mt-4" variant="outline">
          <ArrowLeft className="w-4 h-4 mr-1" />
          {language === 'zh' ? '返回列表' : 'Back to List'}
        </Button>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-[#f7f7f7]">
      {/* Header */}
      <header className="h-[52px] px-5 bg-white flex items-center justify-between shrink-0 border-b border-[#e5e5e5]">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={onBack} className="h-8 w-8 p-0">
            <ArrowLeft className="w-4 h-4" />
          </Button>
          <div className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-[#534ab7]" />
            <h1 className="text-[15px] font-medium text-[#1a1a1a] font-mono">{template.name}</h1>
            <Badge variant="secondary" className={template.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-700'}>
              {template.status}
            </Badge>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setIsTagOpen(true)}
            className="text-xs"
          >
            <Tag className="w-3.5 h-3.5 mr-1" />
            {language === 'zh' ? '设置标签' : 'Set Tag'}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setIsCreateVersionOpen(true)}
            className="text-xs"
          >
            <Plus className="w-3.5 h-3.5 mr-1" />
            {language === 'zh' ? '新建版本' : 'New Version'}
          </Button>
        </div>
      </header>

      {/* Template Info */}
      <div className="px-5 py-3 bg-white border-b border-[#e5e5e5]">
        <div className="grid grid-cols-4 gap-4 text-sm">
          <div>
            <span className="text-gray-500">{language === 'zh' ? '描述' : 'Description'}</span>
            <p className="text-gray-700 mt-0.5">{template.description || '-'}</p>
          </div>
          <div>
            <span className="text-gray-500">{language === 'zh' ? '分类' : 'Category'}</span>
            <p className="text-gray-700 mt-0.5">
              <Badge variant="secondary" className="text-xs">{template.category}</Badge>
            </p>
          </div>
          <div>
            <span className="text-gray-500">{language === 'zh' ? '负责人' : 'Owner'}</span>
            <p className="text-gray-700 mt-0.5">{template.owner || '-'}</p>
          </div>
          <div>
            <span className="text-gray-500">{language === 'zh' ? '标签' : 'Tags'}</span>
            <div className="flex items-center gap-1 mt-0.5">
              {tags.map((tag) => (
                <Badge key={tag.id} variant="outline" className={cn('text-xs border', getTagColor(tag.tag_name))}>
                  {tag.tag_name}={tag.version}
                </Badge>
              ))}
              {tags.length === 0 && <span className="text-gray-400">-</span>}
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as any)} className="flex-1 flex flex-col overflow-hidden">
        <div className="px-5 bg-white border-b border-[#e5e5e5]">
          <TabsList className="h-10 bg-transparent">
            <TabsTrigger value="versions" className="data-[state=active]:bg-gray-100">
              <GitBranch className="w-4 h-4 mr-1.5" />
              {language === 'zh' ? '版本历史' : 'Versions'}
            </TabsTrigger>
            <TabsTrigger value="test-cases" className="data-[state=active]:bg-gray-100">
              <CheckCircle2 className="w-4 h-4 mr-1.5" />
              {language === 'zh' ? '测试用例' : 'Test Cases'}
            </TabsTrigger>
            <TabsTrigger value="eval" className="data-[state=active]:bg-gray-100">
              <BarChart3 className="w-4 h-4 mr-1.5" />
              {language === 'zh' ? '评估报告' : 'Evaluation'}
            </TabsTrigger>
          </TabsList>
        </div>

        {/* Versions Tab */}
        <TabsContent value="versions" className="flex-1 overflow-auto p-5">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{language === 'zh' ? '版本' : 'Version'}</TableHead>
                <TableHead>{language === 'zh' ? '状态' : 'Status'}</TableHead>
                <TableHead>{language === 'zh' ? '变更说明' : 'Changelog'}</TableHead>
                <TableHead>{language === 'zh' ? '评估分数' : 'Score'}</TableHead>
                <TableHead>{language === 'zh' ? '发布时间' : 'Released'}</TableHead>
                <TableHead className="w-[200px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {versions.map((v) => (
                <TableRow key={v.id}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-medium">{v.version}</span>
                      {tags.filter(t => t.version_id === v.id).map(t => (
                        <Badge key={t.id} variant="outline" className={cn('text-xs', getTagColor(t.tag_name))}>
                          {t.tag_name}
                        </Badge>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant="secondary"
                      className={
                        v.status === 'released' ? 'bg-green-100 text-green-700' :
                        v.status === 'draft' ? 'bg-blue-100 text-blue-700' :
                        'bg-gray-100 text-gray-700'
                      }
                    >
                      {v.status}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <span className="text-sm text-gray-600">{v.changelog || '-'}</span>
                  </TableCell>
                  <TableCell>
                    {v.latest_eval_score !== null && v.latest_eval_score !== undefined ? (
                      <div className="flex items-center gap-1">
                        <TrendingUp className="w-4 h-4 text-green-600" />
                        <span className={cn(
                          'font-medium',
                          v.latest_eval_score >= 80 ? 'text-green-600' :
                          v.latest_eval_score >= 60 ? 'text-yellow-600' : 'text-red-600'
                        )}>
                          {v.latest_eval_score.toFixed(1)}
                        </span>
                      </div>
                    ) : (
                      <span className="text-gray-400">-</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {v.released_at ? (
                      <div className="flex items-center gap-1.5 text-sm text-gray-600">
                        <Calendar className="w-3.5 h-3.5" />
                        {new Date(v.released_at).toLocaleDateString()}
                      </div>
                    ) : (
                      <span className="text-gray-400">-</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-xs"
                        onClick={() => handlePreview(v)}
                      >
                        <Eye className="w-3.5 h-3.5" />
                      </Button>
                      {v.status === 'draft' && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 text-xs text-green-600"
                          onClick={() => handleReleaseVersion(v.id)}
                        >
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          {language === 'zh' ? '发布' : 'Release'}
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-xs"
                        onClick={() => {
                          setSelectedVersionForTag(v.id);
                          setIsTagOpen(true);
                        }}
                      >
                        <Tag className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {versions.length === 0 && (
            <Card className="border-dashed mt-4">
              <CardContent className="flex flex-col items-center justify-center py-12">
                <GitBranch className="w-10 h-10 text-gray-300 mb-3" />
                <p className="text-gray-500 text-sm">
                  {language === 'zh' ? '暂无版本，点击"新建版本"创建第一个' : 'No versions yet'}
                </p>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Test Cases Tab */}
        <TabsContent value="test-cases" className="flex-1 overflow-auto p-5">
          <div className="flex justify-end mb-3">
            <Button size="sm" className="text-xs">
              <Plus className="w-3.5 h-3.5 mr-1" />
              {language === 'zh' ? '新建用例' : 'New Case'}
            </Button>
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>{language === 'zh' ? '输入上下文' : 'Input Context'}</TableHead>
                <TableHead>{language === 'zh' ? '期望输出' : 'Expected Output'}</TableHead>
                <TableHead>{language === 'zh' ? '标签' : 'Tags'}</TableHead>
                <TableHead>{language === 'zh' ? '优先级' : 'Priority'}</TableHead>
                <TableHead>{language === 'zh' ? '状态' : 'Status'}</TableHead>
                <TableHead className="w-[80px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {testCases.map((tc) => (
                <TableRow key={tc.id}>
                  <TableCell className="font-mono text-sm">{tc.id}</TableCell>
                  <TableCell>
                    <pre className="text-xs bg-gray-50 p-2 rounded max-w-xs overflow-auto">
                      {JSON.stringify(tc.input_context, null, 2)}
                    </pre>
                  </TableCell>
                  <TableCell>
                    <span className="text-sm text-gray-600 line-clamp-2 max-w-xs block">
                      {tc.expected_output || tc.expected_behavior || '-'}
                    </span>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {tc.tags.map((tag, i) => (
                        <Badge key={i} variant="outline" className="text-xs">
                          {tag}
                        </Badge>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex">
                      {Array.from({ length: 5 }).map((_, i) => (
                        <div
                          key={i}
                          className={cn(
                            'w-2 h-4 border-r',
                            i < tc.priority ? 'bg-yellow-400 border-yellow-400' : 'bg-gray-200 border-gray-200'
                          )}
                        />
                      ))}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary" className={tc.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-700'}>
                      {tc.is_active ? (language === 'zh' ? '启用' : 'Active') : (language === 'zh' ? '禁用' : 'Inactive')}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Button variant="ghost" size="sm" className="h-7 w-7 p-0">
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {testCases.length === 0 && (
            <Card className="border-dashed mt-4">
              <CardContent className="flex flex-col items-center justify-center py-12">
                <CheckCircle2 className="w-10 h-10 text-gray-300 mb-3" />
                <p className="text-gray-500 text-sm">
                  {language === 'zh' ? '暂无测试用例' : 'No test cases yet'}
                </p>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Evaluation Tab */}
        <TabsContent value="eval" className="flex-1 overflow-auto p-5">
          <div className="flex justify-between items-center mb-4">
            <div className="flex items-center gap-3">
              <Select value={candidateVersion?.toString()} onValueChange={(v) => setCandidateVersion(Number(v))}>
                <SelectTrigger className="w-[200px]">
                  <SelectValue placeholder={language === 'zh' ? '选择候选版本' : 'Select candidate'} />
                </SelectTrigger>
                <SelectContent>
                  {versions.filter(v => v.status === 'released').map((v) => (
                    <SelectItem key={v.id} value={v.id.toString()}>
                      {v.version} {v.latest_eval_score ? `(${v.latest_eval_score.toFixed(1)})` : ''}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button onClick={handleRunEval} disabled={!candidateVersion || evaluating}>
                {evaluating && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
                <Play className="w-3.5 h-3.5 mr-1" />
                {language === 'zh' ? '运行评估' : 'Run Evaluation'}
              </Button>
            </div>
          </div>

          {evalReport && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center justify-between">
                  <span>{language === 'zh' ? '评估结果' : 'Evaluation Result'}</span>
                  <Badge className={evalReport.passed ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}>
                    {evalReport.passed ? (language === 'zh' ? '通过' : 'Passed') : (language === 'zh' ? '未通过' : 'Failed')}
                  </Badge>
                </CardTitle>
                <CardDescription>
                  {language === 'zh' ? `平均分：${evalReport.avg_score?.toFixed(1)} | 相对提升：${evalReport.delta?.toFixed(1)}` : `Avg: ${evalReport.avg_score?.toFixed(1)} | Delta: ${evalReport.delta?.toFixed(1)}`}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-4 gap-4 mb-4">
                  <div className="text-center p-3 bg-gray-50 rounded-lg">
                    <div className="text-2xl font-bold text-gray-700">{evalReport.avg_score?.toFixed(1)}</div>
                    <div className="text-xs text-gray-500 mt-1">{language === 'zh' ? '平均分' : 'Avg Score'}</div>
                  </div>
                  <div className="text-center p-3 bg-green-50 rounded-lg">
                    <div className="text-2xl font-bold text-green-700">{evalReport.pass_count}</div>
                    <div className="text-xs text-green-600 mt-1">{language === 'zh' ? '通过' : 'Passed'}</div>
                  </div>
                  <div className="text-center p-3 bg-red-50 rounded-lg">
                    <div className="text-2xl font-bold text-red-700">{evalReport.fail_count}</div>
                    <div className="text-xs text-red-600 mt-1">{language === 'zh' ? '失败' : 'Failed'}</div>
                  </div>
                  <div className="text-center p-3 bg-blue-50 rounded-lg">
                    <div className="text-2xl font-bold text-blue-700">{evalReport.total_count}</div>
                    <div className="text-xs text-blue-600 mt-1">{language === 'zh' ? '总计' : 'Total'}</div>
                  </div>
                </div>

                <div className="border rounded-lg">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{language === 'zh' ? '用例 ID' : 'Case ID'}</TableHead>
                        <TableHead>{language === 'zh' ? '分数' : 'Score'}</TableHead>
                        <TableHead>{language === 'zh' ? '结果' : 'Result'}</TableHead>
                        <TableHead>{language === 'zh' ? '评估理由' : 'Reasoning'}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {evalReport.detailed_results.map((r) => (
                        <TableRow key={r.case_id}>
                          <TableCell className="font-mono">{r.case_id}</TableCell>
                          <TableCell>
                            <span className={cn(
                              'font-medium',
                              r.score >= 80 ? 'text-green-600' : r.score >= 60 ? 'text-yellow-600' : 'text-red-600'
                            )}>
                              {r.score.toFixed(1)}
                            </span>
                          </TableCell>
                          <TableCell>
                            {r.passed ? (
                              <CheckCircle2 className="w-4 h-4 text-green-600" />
                            ) : (
                              <XCircle className="w-4 h-4 text-red-600" />
                            )}
                          </TableCell>
                          <TableCell className="max-w-md truncate text-gray-600">
                            {r.reasoning || '-'}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          )}

          {!evalReport && (
            <Card className="border-dashed">
              <CardContent className="flex flex-col items-center justify-center py-16">
                <BarChart3 className="w-12 h-12 text-gray-300 mb-4" />
                <p className="text-gray-500 text-sm">
                  {language === 'zh' ? '选择版本并点击"运行评估"开始测试' : 'Select a version and click "Run Evaluation"'}
                </p>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>

      {/* Create Version Dialog */}
      <Dialog open={isCreateVersionOpen} onOpenChange={setIsCreateVersionOpen}>
        <DialogContent className="sm:max-w-[600px]">
          <DialogHeader>
            <DialogTitle>{language === 'zh' ? '创建新版本' : 'Create New Version'}</DialogTitle>
            <DialogDescription>
              {language === 'zh' ? '添加一个新的提示词版本（语义化版本号）' : 'Add a new version (semantic versioning)'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <label className="text-sm font-medium mb-1 block">{language === 'zh' ? '版本号' : 'Version'} *</label>
              <Input
                value={newVersion}
                onChange={(e) => setNewVersion(e.target.value)}
                placeholder="1.0.0"
                className="font-mono"
              />
              <p className="text-xs text-gray-500 mt-1">
                {language === 'zh' ? '格式：major.minor.patch (如 1.0.0, 1.1.0-beta)' : 'Format: major.minor.patch (e.g., 1.0.0, 1.1.0-beta)'}
              </p>
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">{language === 'zh' ? '提示词内容' : 'Content'} *</label>
              <Textarea
                value={newContent}
                onChange={(e) => setNewContent(e.target.value)}
                placeholder={language === 'zh' ? '输入提示词模板内容，使用 {{variable}} 语法...' : 'Enter prompt content, use {{variable}} syntax...'}
                rows={10}
                className="font-mono text-sm"
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">{language === 'zh' ? '变更说明' : 'Changelog'}</label>
              <Textarea
                value={newChangelog}
                onChange={(e) => setNewChangelog(e.target.value)}
                placeholder={language === 'zh' ? '描述本次版本的变更...' : 'Describe changes in this version...'}
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsCreateVersionOpen(false)}>
              {language === 'zh' ? '取消' : 'Cancel'}
            </Button>
            <Button
              onClick={handleCreateVersion}
              disabled={creating || !newVersion.trim() || !newContent.trim()}
              className="bg-[#1a1a1a] hover:bg-[#333]"
            >
              {creating && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
              {language === 'zh' ? '创建' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Tag Dialog */}
      <Dialog open={isTagOpen} onOpenChange={setIsTagOpen}>
        <DialogContent className="sm:max-w-[450px]">
          <DialogHeader>
            <DialogTitle>{language === 'zh' ? '设置标签' : 'Set Tag'}</DialogTitle>
            <DialogDescription>
              {language === 'zh' ? '将标签指向指定版本' : 'Point tag to a specific version'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <label className="text-sm font-medium mb-1 block">{language === 'zh' ? '标签' : 'Tag'}</label>
              <Select value={selectedTag} onValueChange={setSelectedTag}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="stable">stable - {language === 'zh' ? '稳定版' : 'Stable'}</SelectItem>
                  <SelectItem value="beta">beta - {language === 'zh' ? '测试版' : 'Beta'}</SelectItem>
                  <SelectItem value="dev">dev - {language === 'zh' ? '开发版' : 'Dev'}</SelectItem>
                  <SelectItem value="canary">canary - {language === 'zh' ? '金丝雀' : 'Canary'}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">{language === 'zh' ? '版本' : 'Version'}</label>
              <Select
                value={selectedVersionForTag?.toString()}
                onValueChange={(v) => setSelectedVersionForTag(Number(v))}
              >
                <SelectTrigger>
                  <SelectValue placeholder={language === 'zh' ? '选择版本' : 'Select version'} />
                </SelectTrigger>
                <SelectContent>
                  {versions.map((v) => (
                    <SelectItem key={v.id} value={v.id.toString()}>
                      {v.version}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {selectedTag === 'canary' && (
              <div>
                <label className="text-sm font-medium mb-1 block">
                  {language === 'zh' ? '灰度百分比' : 'Gray Percent'} (%)
                </label>
                <Input
                  type="number"
                  min="0"
                  max="100"
                  value={grayPercent}
                  onChange={(e) => setGrayPercent(Number(e.target.value))}
                />
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsTagOpen(false)}>
              {language === 'zh' ? '取消' : 'Cancel'}
            </Button>
            <Button
              onClick={handleSetTag}
              disabled={!selectedVersionForTag}
              className="bg-[#1a1a1a] hover:bg-[#333]"
            >
              {language === 'zh' ? '确认' : 'Confirm'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Preview Dialog */}
      <Dialog open={isPreviewOpen} onOpenChange={setIsPreviewOpen}>
        <DialogContent className="sm:max-w-[700px]">
          <DialogHeader>
            <DialogTitle>
              {language === 'zh' ? '预览：' : 'Preview: '} {selectedVersion?.version}
            </DialogTitle>
            <DialogDescription>
              {language === 'zh' ? '填写变量值查看渲染结果' : 'Fill variable values to see rendered result'}
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-4 max-h-[60vh] overflow-auto">
            <div>
              <label className="text-sm font-medium mb-2 block">{language === 'zh' ? '变量' : 'Variables'}</label>
              <div className="space-y-2">
                {selectedVersion?.variables_schema?.map((v) => (
                  <div key={v.name}>
                    <label className="text-xs text-gray-500">{v.name}</label>
                    <Input
                      value={renderVariables[v.name] || ''}
                      onChange={(e) => setRenderVariables({ ...renderVariables, [v.name]: e.target.value })}
                      placeholder={v.default || ''}
                      className="text-sm"
                    />
                  </div>
                ))}
                {(!selectedVersion?.variables_schema || selectedVersion.variables_schema.length === 0) && (
                  <p className="text-sm text-gray-500">{language === 'zh' ? '无变量' : 'No variables'}</p>
                )}
              </div>
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">{language === 'zh' ? '渲染结果' : 'Rendered'}</label>
              <pre className="text-xs bg-gray-50 p-3 rounded-lg h-[200px] overflow-auto whitespace-pre-wrap">
                {renderedContent}
              </pre>
            </div>
          </div>
          <DialogFooter>
            <Button onClick={() => setIsPreviewOpen(false)}>
              {language === 'zh' ? '关闭' : 'Close'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
