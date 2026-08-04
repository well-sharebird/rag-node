import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppContext } from '@/lib/app-context';
import { useAuth } from '@/src/lib/auth-context';
import { useI18n } from '@/src/lib/i18n';
import { toast } from 'sonner';
import { Button, Card, CardHeader, CardBody, CardTitle, Badge, Input, Modal } from '@/src/components/enterprise';
import { Select } from '@/src/components/enterprise/Select';
import { cn } from '@/lib/utils';
import {
  BarChart3,
  Plus,
  Trash2,
  Play,
  Clock,
  CheckCircle2,
  AlertCircle,
  FileText,
  BookOpen,
  ChevronRight,
} from 'lucide-react';
import {
  listGoldenSamples, createGoldenSample, deleteGoldenSample,
  createEvaluationRun, getEvaluationRun, executeEvaluationRun,
  type GoldenSampleResponse, type EvaluationRunResponse
} from '@/lib/api-client';

interface GoldenSample {
  id: string;
  question: string;
  expected_answer: string;
  difficulty?: string;
  category?: string;
}

interface EvaluationRun {
  id: string;
  name: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  avg_score?: number;
  total_samples?: number;
  completed_at?: string;
}

export function EvaluationPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const { knowledgeBases } = useAppContext();
  const { token } = useAuth();

  const [activeTab, setActiveTab] = useState<'samples' | 'runs'>('samples');
  const [samples, setSamples] = useState<GoldenSample[]>([]);
  const [runs, setRuns] = useState<EvaluationRun[]>([]);
  const [selectedKb, setSelectedKb] = useState('');
  const [loading, setLoading] = useState(false);

  const [showNewSample, setShowNewSample] = useState(false);
  const [newQuestion, setNewQuestion] = useState('');
  const [newAnswer, setNewAnswer] = useState('');
  const [newDifficulty, setNewDifficulty] = useState('medium');

  useEffect(() => {
    fetchSamples();
    fetchRuns();
  }, [selectedKb]);

  const fetchSamples = async () => {
    if (!selectedKb) return;
    setLoading(true);
    try {
      const data = await listGoldenSamples(selectedKb);
      setSamples(data);
    } catch (e: any) {
      console.error('Fetch samples failed:', e);
    } finally {
      setLoading(false);
    }
  };

  const fetchRuns = async () => {
    setLoading(true);
    try {
      setRuns([
        {
          id: 'run_1',
          name: 'RAG 质量评估 #1',
          status: 'completed',
          avg_score: 0.78,
          total_samples: 20,
          completed_at: new Date().toISOString(),
        },
        {
          id: 'run_2',
          name: 'RAG 质量评估 #2',
          status: 'running',
          total_samples: 15,
        },
      ]);
    } catch (e: any) {
      console.error('Fetch runs failed:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateSample = async () => {
    if (!newQuestion.trim() || !newAnswer.trim()) {
      toast.error('请填写问题和答案');
      return;
    }

    try {
      await createGoldenSample({
        kb_id: selectedKb,
        question: newQuestion,
        expected_answer: newAnswer,
      });
      toast.success('Golden Sample 创建成功');
      setShowNewSample(false);
      setNewQuestion('');
      setNewAnswer('');
      fetchSamples();
    } catch (e: any) {
      toast.error(e.message || '创建失败');
    }
  };

  const handleDeleteSample = async (id: string) => {
    if (!confirm('确定删除此 Golden Sample？')) return;

    try {
      await deleteGoldenSample(id);
      toast.success('删除成功');
      fetchSamples();
    } catch (e: any) {
      toast.error('删除失败');
    }
  };

  const handleRunEvaluation = async () => {
    if (!selectedKb) {
      toast.error('请先选择知识库');
      return;
    }

    try {
      const run = await createEvaluationRun({
        kb_id: selectedKb,
        name: `RAG 质量评估 #${runs.length + 1}`,
      });

      await executeEvaluationRun(run.id);

      toast.success('评估运行已开始');
      fetchRuns();
    } catch (e: any) {
      toast.error(e.message || '运行失败');
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return { variant: 'success' as const, icon: <CheckCircle2 className="w-3.5 h-3.5" /> };
      case 'running':
        return { variant: 'primary' as const, icon: <Clock className="w-3.5 h-3.5 animate-spin" /> };
      case 'failed':
        return { variant: 'error' as const, icon: <AlertCircle className="w-3.5 h-3.5" /> };
      default:
        return { variant: 'neutral' as const, icon: <Clock className="w-3.5 h-3.5" /> };
    }
  };

  const getDifficultyBadge = (difficulty?: string) => {
    switch (difficulty) {
      case 'easy':
        return { variant: 'success' as const, label: '简单' };
      case 'medium':
        return { variant: 'warning' as const, label: '中等' };
      case 'hard':
        return { variant: 'error' as const, label: '困难' };
      default:
        return { variant: 'neutral' as const, label: '未知' };
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-white">
      {/* Header */}
      <header className="h-[60px] px-6 bg-white flex items-center justify-between shrink-0 border-b border-[var(--gray-200)]">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-[var(--accent-light)] flex items-center justify-center">
            <BarChart3 className="w-5 h-5 text-[var(--accent)]" />
          </div>
          <div>
            <h1 className="text-[18px] font-semibold text-[var(--text-primary)]">RAG 评估</h1>
            <p className="text-[12px] text-[var(--text-secondary)]">评估检索增强生成质量</p>
          </div>
        </div>
        <Select
          value={selectedKb}
          onChange={(e) => setSelectedKb(e.target.value)}
          className="w-[200px]"
        >
          <option value="">选择知识库...</option>
          {knowledgeBases.map((kb) => (
            <option key={kb.id} value={kb.id}>{kb.name}</option>
          ))}
        </Select>
      </header>

      {/* Tabs */}
      <div className="px-6 py-3 bg-white border-b border-[var(--gray-200)] flex items-center gap-1">
        <button
          onClick={() => setActiveTab('samples')}
          className={cn(
            "px-4 py-2 text-[13px] font-medium rounded-lg transition-colors",
            activeTab === 'samples'
              ? "bg-[var(--accent-light)] text-[var(--accent)]"
              : "text-[var(--text-secondary)] hover:bg-[var(--bg-primary)]"
          )}
        >
          <FileText className="w-4 h-4 inline mr-1.5" />
          Golden Samples
        </button>
        <button
          onClick={() => setActiveTab('runs')}
          className={cn(
            "px-4 py-2 text-[13px] font-medium rounded-lg transition-colors",
            activeTab === 'runs'
              ? "bg-[var(--accent-light)] text-[var(--accent)]"
              : "text-[var(--text-secondary)] hover:bg-[var(--bg-primary)]"
          )}
        >
          <BarChart3 className="w-4 h-4 inline mr-1.5" />
          评估运行
        </button>

        <div className="ml-auto flex items-center gap-2">
          {activeTab === 'samples' && (
            <Button
              onClick={() => setShowNewSample(!showNewSample)}
              className="rounded-xl bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white"
              icon={<Plus className="w-4 h-4" />}
            >
              新建样本
            </Button>
          )}
          {activeTab === 'runs' && (
            <Button
              onClick={handleRunEvaluation}
              disabled={!selectedKb}
              className="rounded-xl bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white disabled:opacity-50"
              icon={<Play className="w-4 h-4" />}
            >
              运行评估
            </Button>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {!selectedKb ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-[var(--text-tertiary)]">
            <BookOpen className="w-12 h-12" />
            <p className="text-[14px]">请先选择知识库</p>
          </div>
        ) : activeTab === 'samples' ? (
          <div className="max-w-4xl mx-auto space-y-4">
            {/* New Sample Form */}
            {showNewSample && (
              <Card>
                <CardHeader>
                  <CardTitle>新建 Golden Sample</CardTitle>
                </CardHeader>
                <CardBody>
                  <div className="space-y-4">
                    <div className="space-y-2">
                      <label className="text-[12px] font-medium text-[var(--text-secondary)]">问题</label>
                      <textarea
                        value={newQuestion}
                        onChange={(e) => setNewQuestion(e.target.value)}
                        placeholder="输入测试问题..."
                        className="w-full px-3 py-2 text-[13px] rounded-xl border border-[var(--gray-200)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)] resize-none"
                        rows={3}
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="text-[12px] font-medium text-[var(--text-secondary)]">期望答案</label>
                      <textarea
                        value={newAnswer}
                        onChange={(e) => setNewAnswer(e.target.value)}
                        placeholder="输入期望的正确答案..."
                        className="w-full px-3 py-2 text-[13px] rounded-xl border border-[var(--gray-200)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)] resize-none"
                        rows={4}
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="text-[12px] font-medium text-[var(--text-secondary)]">难度</label>
                      <Select
                        value={newDifficulty}
                        onChange={(e) => setNewDifficulty(e.target.value)}
                        className="w-full"
                      >
                        <option value="easy">简单</option>
                        <option value="medium">中等</option>
                        <option value="hard">困难</option>
                      </Select>
                    </div>
                    <div className="flex justify-end gap-2 pt-2">
                      <Button variant="secondary" onClick={() => setShowNewSample(false)}>
                        取消
                      </Button>
                      <Button onClick={handleCreateSample} className="bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white">
                        创建
                      </Button>
                    </div>
                  </div>
                </CardBody>
              </Card>
            )}

            {/* Samples List */}
            {samples.length === 0 ? (
              <Card>
                <CardBody className="py-12 text-center">
                  <FileText className="w-12 h-12 mx-auto mb-4 text-[var(--gray-300)]" />
                  <p className="text-[14px] text-[var(--text-secondary)]">暂无 Golden Samples</p>
                  <p className="text-[12px] text-[var(--text-tertiary)] mt-1">创建测试样本来评估 RAG 质量</p>
                </CardBody>
              </Card>
            ) : (
              samples.map((sample) => {
                const diffBadge = getDifficultyBadge(sample.difficulty);
                return (
                  <Card key={sample.id}>
                    <CardBody>
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-2">
                            {diffBadge && (
                              <Badge variant={diffBadge.variant} size="sm">
                                {diffBadge.label}
                              </Badge>
                            )}
                            {sample.category && (
                              <Badge variant="neutral" size="sm">
                                {sample.category}
                              </Badge>
                            )}
                          </div>
                          <h4 className="text-[14px] font-medium text-[var(--text-primary)] mb-2">{sample.question}</h4>
                          <div className="text-[13px] text-[var(--text-secondary)] bg-[var(--bg-primary)] rounded-xl p-3">
                            <span className="text-[var(--text-tertiary)]">期望答案：</span>
                            {sample.expected_answer}
                          </div>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDeleteSample(sample.id)}
                          icon={<Trash2 className="w-4 h-4 text-[var(--error)]" />}
                        />
                      </div>
                    </CardBody>
                  </Card>
                );
              })
            )}
          </div>
        ) : (
          <div className="max-w-4xl mx-auto space-y-4">
            {/* Runs List */}
            {runs.length === 0 ? (
              <Card>
                <CardBody className="py-12 text-center">
                  <BarChart3 className="w-12 h-12 mx-auto mb-4 text-[var(--gray-300)]" />
                  <p className="text-[14px] text-[var(--text-secondary)]">暂无评估运行</p>
                  <p className="text-[12px] text-[var(--text-tertiary)] mt-1">点击"运行评估"开始质量评估</p>
                </CardBody>
              </Card>
            ) : (
              runs.map((run) => {
                const statusBadge = getStatusBadge(run.status);
                return (
                  <Card key={run.id}>
                    <CardBody>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <div className={cn(
                            "w-10 h-10 rounded-xl flex items-center justify-center",
                            run.status === 'completed' ? "bg-[var(--success-bg)] text-[var(--success)]" :
                            run.status === 'running' ? "bg-[var(--info-bg)] text-[var(--info)]" :
                            run.status === 'failed' ? "bg-[var(--error-bg)] text-[var(--error)]" :
                            "bg-[var(--gray-100)] text-[var(--text-tertiary)]"
                          )}>
                            {statusBadge.icon}
                          </div>
                          <div>
                            <h4 className="text-[14px] font-medium text-[var(--text-primary)]">{run.name}</h4>
                            <div className="flex items-center gap-3 mt-1">
                              <span className="text-[12px] text-[var(--text-secondary)] capitalize">{run.status}</span>
                              {run.total_samples && (
                                <span className="text-[12px] text-[var(--text-secondary)]">{run.total_samples} 样本</span>
                              )}
                              {run.avg_score && (
                                <span className="text-[12px] text-[var(--success)] font-medium">
                                  平均分 {(run.avg_score * 100).toFixed(0)}%
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                        <ChevronRight className="w-5 h-5 text-[var(--text-tertiary)]" />
                      </div>
                    </CardBody>
                  </Card>
                );
              })
            )}
          </div>
        )}
      </div>
    </div>
  );
}
