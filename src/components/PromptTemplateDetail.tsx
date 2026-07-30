/**
 * 提示词模板详情页面
 * Prompt Template Detail View - Bird Design System
 */

import { useState, useEffect, useRef } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { toast } from 'sonner';
import { Button, Card, CardHeader, CardBody, CardTitle, Badge, Input, Modal } from '@/src/components/enterprise';
import { Select } from '@/src/components/enterprise/Select';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/src/components/enterprise/Tabs';
import {
  ArrowLeft, FileText, GitBranch, Tag, TrendingUp, Calendar, User, Plus,
  Loader2, CheckCircle2, AlertCircle, Play, Copy, Eye, Trash2,
  ChevronRight, GitMerge, Clock, BarChart3
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { promptsApi, type PromptTemplate, type PromptVersion, type PromptTag, type TestCase, type EvalReport } from '@/src/lib/api/prompts';

interface PromptTemplateDetailProps {
  templateName: string;
  onBack?: () => void;
}

export function PromptTemplateDetail({ templateName, onBack }: PromptTemplateDetailProps) {
  const { t, language } = useI18n();

  const [template, setTemplate] = useState<PromptTemplate | null>(null);
  const [versions, setVersions] = useState<PromptVersion[]>([]);
  const [tags, setTags] = useState<PromptTag[]>([]);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedVersion, setSelectedVersion] = useState<PromptVersion | null>(null);
  const [activeTab, setActiveTab] = useState<'versions' | 'test-cases' | 'eval'>('versions');

  const [isCreateVersionOpen, setIsCreateVersionOpen] = useState(false);
  const [newVersion, setNewVersion] = useState('');
  const [newContent, setNewContent] = useState('');
  const [newChangelog, setNewChangelog] = useState('');
  const [creating, setCreating] = useState(false);

  const [isTagOpen, setIsTagOpen] = useState(false);
  const [selectedTag, setSelectedTag] = useState<string>('stable');
  const [selectedVersionForTag, setSelectedVersionForTag] = useState<number | null>(null);

  const [isEvalOpen, setIsEvalOpen] = useState(false);
  const [candidateVersion, setCandidateVersion] = useState<number | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [evalReport, setEvalReport] = useState<EvalReport | null>(null);

  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [renderVariables, setRenderVariables] = useState<Record<string, string>>({});
  const [renderedContent, setRenderedContent] = useState('');

  const loadData = async () => {
    try {
      setLoading(true);
      const [templateData, versionsData, tagsData, testCasesData] = await Promise.all([
        promptsApi.getTemplate(templateName),
        promptsApi.listVersions(templateName, { limit: 50 }),
        promptsApi.listTags(templateName),
        promptsApi.listTestCases(templateName),
      ]);
      setTemplate(templateData as PromptTemplate);
      setVersions((versionsData as any).items || []);
      setTags((tagsData as any).items || []);
      setTestCases((testCasesData as any).items || []);
      if ((versionsData as any).items?.length > 0) {
        setSelectedVersion((versionsData as any).items[0]);
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

  const handleCreateVersion = async () => {
    if (!newVersion.trim() || !newContent.trim()) {
      toast.error(language === 'zh' ? '请填写版本号和提示词内容' : 'Please fill in version and content');
      return;
    }
    try {
      setCreating(true);
      const versionData = await promptsApi.createVersion(templateName, {
        version: newVersion.trim(),
        content: newContent.trim(),
        changelog: newChangelog.trim() || undefined,
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

  const handleSetTag = async () => {
    if (!selectedVersionForTag) {
      toast.error(language === 'zh' ? '请选择版本' : 'Please select a version');
      return;
    }
    try {
      await promptsApi.setTag(templateName, {
        tag_name: selectedTag,
        version_id: selectedVersionForTag,
        meta_config: selectedTag === 'canary' ? { gray_percent: 10 } : {},
      });
      toast.success(language === 'zh' ? `标签 ${selectedTag} 设置成功` : `Tag ${selectedTag} set`);
      setIsTagOpen(false);
      loadData();
    } catch (error: any) {
      toast.error(error.message || (language === 'zh' ? '设置失败' : 'Failed to set'));
    }
  };

  const handleEval = async () => {
    if (!candidateVersion) return;
    try {
      setEvaluating(true);
      const report = await promptsApi.runEvaluation(templateName, {
        candidate_version_id: candidateVersion,
        triggered_by: 'web',
      });
      setEvalReport(report as EvalReport);
      toast.success(language === 'zh' ? '评估完成' : 'Evaluation completed');
    } catch (error: any) {
      toast.error(error.message || (language === 'zh' ? '评估失败' : 'Evaluation failed'));
    } finally {
      setEvaluating(false);
      setIsEvalOpen(false);
    }
  };

  const handlePreview = (version: PromptVersion) => {
    setSelectedVersion(version);
    // 从 schema 初始化变量
    const vars: Record<string, string> = {};
    version.variables_schema?.forEach((v) => {
      vars[v.name] = v.default || '';
    });
    setRenderVariables(vars);
    setRenderedContent(version.content);
    setIsPreviewOpen(true);
  };

  const handleRender = async () => {
    if (!selectedVersion) return;
    try {
      const rendered = await promptsApi.render(templateName, {
        version_id: selectedVersion.id,
        variables: renderVariables,
      });
      setRenderedContent(rendered.rendered_content);
    } catch (error: any) {
      toast.error(error.message || (language === 'zh' ? '渲染失败' : 'Failed to render'));
    }
  };

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    toast.success(language === 'zh' ? '已复制' : 'Copied');
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

  const getStatusBadge = (status: string) => {
    if (status === 'active') return <Badge variant="success" size="sm">{language === 'zh' ? '活跃' : 'Active'}</Badge>;
    return <Badge variant="neutral" size="sm">{language === 'zh' ? '已归档' : 'Archived'}</Badge>;
  };

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-[var(--accent)]" />
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-white">
      {/* Header */}
      <header className="h-[60px] px-6 bg-white flex items-center justify-between shrink-0 border-b border-[var(--gray-200)]">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={onBack} icon={<ArrowLeft className="w-4 h-4" />} />
          <div className="w-9 h-9 rounded-xl bg-[var(--accent-light)] flex items-center justify-center">
            <FileText className="w-5 h-5 text-[var(--accent)]" />
          </div>
          <div>
            <h1 className="text-[18px] font-semibold text-[var(--text-primary)]">{template?.name}</h1>
            <div className="flex items-center gap-2 mt-0.5">
              {getCategoryBadge(template?.category || '')}
              {getStatusBadge(template?.status || '')}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            onClick={() => setIsTagOpen(true)}
            icon={<Tag className="w-4 h-4" />}
          >
            {language === 'zh' ? '设置标签' : 'Set Tag'}
          </Button>
          <Button
            onClick={() => setIsCreateVersionOpen(true)}
            className="bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white"
            icon={<Plus className="w-4 h-4" />}
          >
            {language === 'zh' ? '新建版本' : 'New Version'}
          </Button>
        </div>
      </header>

      {/* Tabs */}
      <div className="px-6 py-3 bg-white border-b border-[var(--gray-200)]">
        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as any)} className="w-full">
          <TabsList>
            <TabsTrigger value="versions">{language === 'zh' ? '版本列表' : 'Versions'}</TabsTrigger>
            <TabsTrigger value="test-cases">{language === 'zh' ? '测试用例' : 'Test Cases'}</TabsTrigger>
            <TabsTrigger value="eval">{language === 'zh' ? '评估报告' : 'Evaluation'}</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {activeTab === 'versions' && (
          <div className="space-y-4">
            {versions.length === 0 ? (
              <Card>
                <CardBody className="py-12 text-center">
                  <GitBranch className="w-12 h-12 mx-auto mb-4 text-[var(--gray-300)]" />
                  <p className="text-[14px] text-[var(--text-secondary)]">{language === 'zh' ? '暂无版本' : 'No versions'}</p>
                </CardBody>
              </Card>
            ) : (
              versions.map((v) => (
                <Card key={v.id}>
                  <CardBody>
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <Badge variant="primary" size="sm">v{v.version}</Badge>
                          {tags.find(t => t.version_id === v.id) && (
                            <Badge variant="success" size="sm">
                              <Tag className="w-3 h-3 mr-1" />
                              {tags.find(t => t.version_id === v.id)?.tag_name}
                            </Badge>
                          )}
                        </div>
                        <div className="text-[13px] text-[var(--text-secondary)] mb-3 font-mono bg-[var(--bg-primary)] p-3 rounded-lg max-h-32 overflow-y-auto">
                          {v.content?.slice(0, 500)}{v.content?.length > 500 ? '...' : ''}
                        </div>
                        {v.changelog && (
                          <p className="text-[12px] text-[var(--text-tertiary)]">
                            <GitMerge className="w-3 h-3 inline mr-1" />
                            {v.changelog}
                          </p>
                        )}
                      </div>
                      <div className="flex flex-col gap-2">
                        <Button variant="secondary" size="sm" onClick={() => handlePreview(v)} icon={<Eye className="w-3.5 h-3.5" />}>
                          {language === 'zh' ? '预览' : 'Preview'}
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => handleCopy(v.content)} icon={<Copy className="w-3.5 h-3.5" />} />
                      </div>
                    </div>
                  </CardBody>
                </Card>
              ))
            )}
          </div>
        )}

        {activeTab === 'test-cases' && (
          <div className="space-y-4">
            {testCases.length === 0 ? (
              <Card>
                <CardBody className="py-12 text-center">
                  <AlertCircle className="w-12 h-12 mx-auto mb-4 text-[var(--gray-300)]" />
                  <p className="text-[14px] text-[var(--text-secondary)]">{language === 'zh' ? '暂无测试用例' : 'No test cases'}</p>
                </CardBody>
              </Card>
            ) : (
              testCases.map((tc) => (
                <Card key={tc.id}>
                  <CardBody>
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <Badge variant={tc.is_active ? 'success' : 'neutral'} size="sm">
                            {tc.is_active ? (language === 'zh' ? '启用' : 'Active') : (language === 'zh' ? '禁用' : 'Inactive')}
                          </Badge>
                          <span className="text-[12px] text-[var(--text-tertiary)]">ID: {tc.id}</span>
                        </div>
                        <div className="text-[13px] text-[var(--text-secondary)] mt-2">
                          <span className="text-[var(--text-tertiary)] block mb-1">{language === 'zh' ? '输入上下文：' : 'Input Context: '}</span>
                          <pre className="text-[12px] bg-[var(--bg-primary)] p-2 rounded-lg overflow-auto max-w-md">
                            {JSON.stringify(tc.input_context, null, 2)}
                          </pre>
                        </div>
                        {tc.expected_output && (
                          <div className="text-[13px] text-[var(--text-secondary)] mt-2">
                            <span className="text-[var(--text-tertiary)] block mb-1">{language === 'zh' ? '期望输出：' : 'Expected Output: '}</span>
                            <p className="text-[12px] bg-[var(--bg-primary)] p-2 rounded-lg max-w-md">{tc.expected_output}</p>
                          </div>
                        )}
                        {tc.expected_behavior && (
                          <div className="text-[13px] text-[var(--text-secondary)] mt-2">
                            <span className="text-[var(--text-tertiary)] block mb-1">{language === 'zh' ? '期望行为：' : 'Expected Behavior: '}</span>
                            <p className="text-[12px] bg-[var(--bg-primary)] p-2 rounded-lg max-w-md">{tc.expected_behavior}</p>
                          </div>
                        )}
                        <div className="flex items-center gap-2 mt-2">
                          <span className="text-[12px] text-[var(--text-tertiary)]">{language === 'zh' ? '优先级：' : 'Priority: '}</span>
                          <div className="flex">
                            {Array.from({ length: 5 }).map((_, i) => (
                              <div
                                key={i}
                                className={cn(
                                  'w-3 h-4 border-r',
                                  i < tc.priority ? 'bg-yellow-400 border-yellow-400' : 'bg-gray-200 border-gray-200'
                                )}
                              />
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  </CardBody>
                </Card>
              ))
            )}
          </div>
        )}

        {activeTab === 'eval' && (
          <div className="space-y-4">
            <Card>
              <CardBody>
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <BarChart3 className="w-5 h-5 text-[var(--accent)]" />
                    <h3 className="text-[15px] font-semibold text-[var(--text-primary)]">{language === 'zh' ? '评估报告' : 'Evaluation Report'}</h3>
                  </div>
                  <Button
                    onClick={() => setIsEvalOpen(true)}
                    className="bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white"
                    icon={<Play className="w-4 h-4" />}
                  >
                    {language === 'zh' ? '运行评估' : 'Run Evaluation'}
                  </Button>
                </div>
                {evalReport ? (
                  <div className="space-y-4">
                    <div className="grid grid-cols-4 gap-4">
                      <div className="p-4 bg-[var(--bg-primary)] rounded-xl text-center">
                        <div className="text-[12px] text-[var(--text-tertiary)] mb-1">{language === 'zh' ? '平均分' : 'Avg Score'}</div>
                        <div className="text-[24px] font-semibold text-[var(--text-primary)]">{evalReport.avg_score?.toFixed(1) || '0'}</div>
                      </div>
                      <div className="p-4 bg-[var(--success-bg)] rounded-xl text-center">
                        <div className="text-[12px] text-[#059669] mb-1">{language === 'zh' ? '通过' : 'Passed'}</div>
                        <div className="text-[24px] font-semibold text-[#059669]">{evalReport.pass_count || 0}</div>
                      </div>
                      <div className="p-4 bg-[var(--error-bg)] rounded-xl text-center">
                        <div className="text-[12px] text-[#dc2626] mb-1">{language === 'zh' ? '失败' : 'Failed'}</div>
                        <div className="text-[24px] font-semibold text-[#dc2626]">{evalReport.fail_count || 0}</div>
                      </div>
                      <div className="p-4 bg-[var(--info-bg)] rounded-xl text-center">
                        <div className="text-[12px] text-[#2563eb] mb-1">{language === 'zh' ? '总计' : 'Total'}</div>
                        <div className="text-[24px] font-semibold text-[#2563eb]">{evalReport.total_count || 0}</div>
                      </div>
                    </div>
                    {evalReport.detailed_results && evalReport.detailed_results.length > 0 && (
                      <div className="border border-[var(--gray-200)] rounded-xl">
                        <div className="p-3 border-b border-[var(--gray-200)]">
                          <h4 className="text-[14px] font-semibold text-[var(--text-primary)]">{language === 'zh' ? '详细结果' : 'Detailed Results'}</h4>
                        </div>
                        <div className="divide-y divide-[var(--gray-200)]">
                          {evalReport.detailed_results.map((result, index) => (
                            <div key={index} className="p-3">
                              <div className="flex items-center justify-between mb-2">
                                <span className="text-[12px] text-[var(--text-tertiary)]">{language === 'zh' ? '用例' : 'Case'} #{result.case_id}</span>
                                <Badge variant={result.passed ? 'success' : 'error'} size="sm">
                                  {result.passed ? (language === 'zh' ? '通过' : 'Passed') : (language === 'zh' ? '失败' : 'Failed')}
                                </Badge>
                              </div>
                              <div className="flex items-center justify-between">
                                <span className="text-[13px] text-[var(--text-secondary)]">
                                  {language === 'zh' ? '分数：' : 'Score: '}
                                  <span className={cn(
                                    'font-medium',
                                    result.score >= 80 ? 'text-green-600' :
                                    result.score >= 60 ? 'text-yellow-600' : 'text-red-600'
                                  )}>
                                    {result.score.toFixed(1)}
                                  </span>
                                </span>
                              </div>
                              {result.reasoning && (
                                <p className="text-[12px] text-[var(--text-secondary)] mt-2 line-clamp-2">{result.reasoning}</p>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-[14px] text-[var(--text-tertiary)] text-center py-8">
                    {language === 'zh' ? '暂无评估报告，点击运行评估开始测试' : 'No evaluation report yet. Click Run Evaluation to start testing.'}
                  </p>
                )}
              </CardBody>
            </Card>
          </div>
        )}
      </div>

      {/* Create Version Modal */}
      <Modal
        open={isCreateVersionOpen}
        onOpenChange={setIsCreateVersionOpen}
        title={language === 'zh' ? '创建新版本' : 'Create New Version'}
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsCreateVersionOpen(false)}>{language === 'zh' ? '取消' : 'Cancel'}</Button>
            <Button onClick={handleCreateVersion} disabled={creating} className="bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white">
              {creating ? (language === 'zh' ? '创建中...' : 'Creating...') : (language === 'zh' ? '创建' : 'Create')}
            </Button>
          </>
        }
      >
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <label className="text-[12px] font-medium text-[var(--text-secondary)]">{language === 'zh' ? '版本号' : 'Version'}</label>
            <Input
              value={newVersion}
              onChange={(e) => setNewVersion(e.target.value)}
              placeholder="1.0.0"
            />
          </div>
          <div className="space-y-2">
            <label className="text-[12px] font-medium text-[var(--text-secondary)]">{language === 'zh' ? '提示词内容' : 'Prompt Content'}</label>
            <textarea
              value={newContent}
              onChange={(e) => setNewContent(e.target.value)}
              className="w-full min-h-[200px] p-3 text-[13px] border border-[var(--gray-200)] rounded-xl focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
              placeholder={language === 'zh' ? '输入提示词内容...' : 'Enter prompt content...'}
            />
          </div>
          <div className="space-y-2">
            <label className="text-[12px] font-medium text-[var(--text-secondary)]">{language === 'zh' ? '更新说明' : 'Changelog'}</label>
            <Input
              value={newChangelog}
              onChange={(e) => setNewChangelog(e.target.value)}
              placeholder={language === 'zh' ? '可选' : 'Optional'}
            />
          </div>
        </div>
      </Modal>

      {/* Set Tag Modal */}
      <Modal
        open={isTagOpen}
        onOpenChange={setIsTagOpen}
        title={language === 'zh' ? '设置标签' : 'Set Tag'}
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsTagOpen(false)}>{language === 'zh' ? '取消' : 'Cancel'}</Button>
            <Button onClick={handleSetTag} className="bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white">{language === 'zh' ? '设置' : 'Set'}</Button>
          </>
        }
      >
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <label className="text-[12px] font-medium text-[var(--text-secondary)]">{language === 'zh' ? '标签名称' : 'Tag Name'}</label>
            <Select
              value={selectedTag}
              onChange={(e) => setSelectedTag(e.target.value)}
              className="w-full"
            >
              <option value="stable">stable</option>
              <option value="production">production</option>
              <option value="development">development</option>
            </Select>
          </div>
          <div className="space-y-2">
            <label className="text-[12px] font-medium text-[var(--text-secondary)]">{language === 'zh' ? '关联版本' : 'Select Version'}</label>
            <Select
              value={selectedVersionForTag?.toString() || ''}
              onChange={(e) => setSelectedVersionForTag(parseInt(e.target.value))}
              className="w-full"
            >
              {versions.map((v) => (
                <option key={v.id} value={v.id}>v{v.version}</option>
              ))}
            </Select>
          </div>
        </div>
      </Modal>

      {/* Preview Modal */}
      <Modal
        open={isPreviewOpen}
        onOpenChange={setIsPreviewOpen}
        title={language === 'zh' ? '预览渲染结果' : 'Preview Rendered Result'}
        className="max-w-3xl"
      >
        <div className="space-y-4 py-4">
          <div className="grid grid-cols-2 gap-4 max-h-[60vh] overflow-auto">
            <div className="space-y-3">
              <label className="text-[12px] font-medium text-[var(--text-secondary)]">{language === 'zh' ? '变量' : 'Variables'}</label>
              {selectedVersion?.variables_schema && selectedVersion.variables_schema.length > 0 ? (
                selectedVersion.variables_schema.map((v) => (
                  <div key={v.name}>
                    <label className="text-[11px] text-[var(--text-tertiary)] block mb-1">{v.name}</label>
                    <Input
                      value={renderVariables[v.name] || ''}
                      onChange={(e) => setRenderVariables({ ...renderVariables, [v.name]: e.target.value })}
                      placeholder={v.default || ''}
                      className="text-sm"
                    />
                  </div>
                ))
              ) : (
                <p className="text-[12px] text-[var(--text-tertiary)]">{language === 'zh' ? '无变量' : 'No variables'}</p>
              )}
            </div>
            <div>
              <label className="text-[12px] font-medium text-[var(--text-secondary)] mb-2 block">{language === 'zh' ? '渲染结果' : 'Rendered Result'}</label>
              <pre className="text-[12px] bg-[var(--bg-primary)] p-3 rounded-xl h-[200px] overflow-auto whitespace-pre-wrap text-[#374151]">
                {renderedContent || (language === 'zh' ? '点击渲染查看结果' : 'Click Render to see result')}
              </pre>
            </div>
          </div>
          <Button onClick={handleRender} className="w-full bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white">
            {language === 'zh' ? '渲染' : 'Render'}
          </Button>
        </div>
      </Modal>

      {/* Eval Modal */}
      <Modal
        open={isEvalOpen}
        onOpenChange={(open) => {
          setIsEvalOpen(open);
          if (!open) {
            setCandidateVersion(null);
            setEvalReport(null);
          }
        }}
        title={language === 'zh' ? '运行评估' : 'Run Evaluation'}
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsEvalOpen(false)}>{language === 'zh' ? '取消' : 'Cancel'}</Button>
            <Button onClick={handleEval} disabled={evaluating || !candidateVersion} className="bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white">
              {evaluating ? (language === 'zh' ? '评估中...' : 'Evaluating...') : (language === 'zh' ? '开始评估' : 'Start Evaluation')}
            </Button>
          </>
        }
      >
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <label className="text-[12px] font-medium text-[var(--text-secondary)]">{language === 'zh' ? '选择候选版本' : 'Select Candidate Version'}</label>
            <Select
              value={candidateVersion?.toString() || ''}
              onChange={(e) => setCandidateVersion(parseInt(e.target.value))}
              className="w-full"
            >
              {versions.map((v) => (
                <option key={v.id} value={v.id}>v{v.version}</option>
              ))}
            </Select>
          </div>
        </div>
      </Modal>
    </div>
  );
}
