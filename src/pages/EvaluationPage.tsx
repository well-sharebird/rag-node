import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppContext } from '@/lib/app-context';
import { useAuth } from '@/src/lib/auth-context';
import { useI18n } from '@/src/lib/i18n';
import { toast } from 'sonner';
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
  ChevronDown,
} from 'lucide-react';

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

  // New sample form
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
      const res = await fetch(`/api/v1/evaluation/golden-samples?kb_id=${selectedKb}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
      if (res.ok) {
        const data = await res.json();
        setSamples(data);
      }
    } catch (e: any) {
      console.error('Fetch samples failed:', e);
    } finally {
      setLoading(false);
    }
  };

  const fetchRuns = async () => {
    setLoading(true);
    try {
      // Mock data for now
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
      const res = await fetch('/api/v1/evaluation/golden-samples', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          kb_id: selectedKb,
          question: newQuestion,
          expected_answer: newAnswer,
          difficulty: newDifficulty,
        }),
      });

      if (res.ok) {
        toast.success('Golden Sample 创建成功');
        setShowNewSample(false);
        setNewQuestion('');
        setNewAnswer('');
        fetchSamples();
      } else {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || '创建失败');
      }
    } catch (e: any) {
      toast.error(e.message || '创建失败');
    }
  };

  const handleDeleteSample = async (id: string) => {
    if (!confirm('确定删除此 Golden Sample？')) return;

    try {
      const res = await fetch(`/api/v1/evaluation/golden-samples/${id}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
      if (res.ok) {
        toast.success('删除成功');
        fetchSamples();
      }
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
      // Create run
      const res = await fetch('/api/v1/evaluation/runs', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          kb_id: selectedKb,
          name: `RAG 质量评估 #${runs.length + 1}`,
          evaluation_type: 'golden_dataset',
          metrics: ['answer_relevancy', 'faithfulness', 'context_precision', 'context_recall'],
        }),
      });

      if (!res.ok) throw new Error('创建运行失败');

      const run = await res.json();

      // Execute run
      const execRes = await fetch(`/api/v1/evaluation/runs/${run.id}/execute`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (!execRes.ok) throw new Error('执行失败');

      toast.success('评估运行已开始');
      fetchRuns();
    } catch (e: any) {
      toast.error(e.message || '运行失败');
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="w-4 h-4 text-green-600" />;
      case 'running':
        return <Clock className="w-4 h-4 text-blue-600 animate-spin" />;
      case 'failed':
        return <AlertCircle className="w-4 h-4 text-red-600" />;
      default:
        return <Clock className="w-4 h-4 text-gray-400" />;
    }
  };

  const getDifficultyColor = (difficulty?: string) => {
    switch (difficulty) {
      case 'easy':
        return 'bg-green-100 text-green-700';
      case 'medium':
        return 'bg-yellow-100 text-yellow-700';
      case 'hard':
        return 'bg-red-100 text-red-700';
      default:
        return 'bg-gray-100 text-gray-700';
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-[#f7f7f5]">
      {/* Header */}
      <header className="h-[52px] px-5 bg-white flex items-center justify-between shrink-0" style={{ borderBottom: '0.5px solid #e2e1dd' }}>
        <div className="flex items-center gap-3">
          <h1 className="text-[15px] font-medium text-[#1a1a1a]">RAG 评估</h1>
          <span className="text-[11px] text-[#9b9b9b]">评估检索增强生成质量</span>
        </div>
        <select
          value={selectedKb}
          onChange={(e) => setSelectedKb(e.target.value)}
          className="px-3 py-1.5 text-[13px] rounded-md border outline-none"
          style={{ borderColor: '#e2e1dd' }}
        >
          <option value="">选择知识库...</option>
          {knowledgeBases.map((kb) => (
            <option key={kb.id} value={kb.id}>{kb.name}</option>
          ))}
        </select>
      </header>

      {/* Tabs */}
      <div className="px-5 py-3 bg-white border-b border-gray-200 flex items-center gap-4">
        <button
          onClick={() => setActiveTab('samples')}
          className={`text-[13px] font-medium pb-1 border-b-2 transition-colors ${
            activeTab === 'samples'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          <FileText className="w-3.5 h-3.5 inline mr-1.5" />
          Golden Samples
        </button>
        <button
          onClick={() => setActiveTab('runs')}
          className={`text-[13px] font-medium pb-1 border-b-2 transition-colors ${
            activeTab === 'runs'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          <BarChart3 className="w-3.5 h-3.5 inline mr-1.5" />
          评估运行
        </button>

        <div className="ml-auto flex items-center gap-2">
          {activeTab === 'samples' && (
            <button
              onClick={() => setShowNewSample(!showNewSample)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-white text-[13px]"
              style={{ background: '#534ab7' }}
            >
              <Plus className="w-3.5 h-3.5" />
              新建样本
            </button>
          )}
          {activeTab === 'runs' && (
            <button
              onClick={handleRunEvaluation}
              disabled={!selectedKb}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-white text-[13px] disabled:opacity-50"
              style={{ background: '#534ab7' }}
            >
              <Play className="w-3.5 h-3.5" />
              运行评估
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-5">
        {!selectedKb ? (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <BookOpen className="w-10 h-10 text-gray-300" />
            <p className="text-sm text-gray-500">请先选择知识库</p>
          </div>
        ) : activeTab === 'samples' ? (
          <div className="max-w-4xl mx-auto">
            {/* New Sample Form */}
            {showNewSample && (
              <div className="mb-4 p-4 bg-white rounded-lg border border-gray-200">
                <h3 className="text-sm font-medium mb-3">新建 Golden Sample</h3>
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs text-gray-600 mb-1">问题</label>
                    <textarea
                      value={newQuestion}
                      onChange={(e) => setNewQuestion(e.target.value)}
                      placeholder="输入测试问题..."
                      className="w-full px-3 py-2 text-[13px] rounded-md border outline-none resize-none"
                      style={{ borderColor: '#e2e1dd' }}
                      rows={3}
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-600 mb-1">期望答案</label>
                    <textarea
                      value={newAnswer}
                      onChange={(e) => setNewAnswer(e.target.value)}
                      placeholder="输入期望的正确答案..."
                      className="w-full px-3 py-2 text-[13px] rounded-md border outline-none resize-none"
                      style={{ borderColor: '#e2e1dd' }}
                      rows={4}
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-600 mb-1">难度</label>
                    <select
                      value={newDifficulty}
                      onChange={(e) => setNewDifficulty(e.target.value)}
                      className="px-3 py-1.5 text-[13px] rounded-md border outline-none"
                      style={{ borderColor: '#e2e1dd' }}
                    >
                      <option value="easy">简单</option>
                      <option value="medium">中等</option>
                      <option value="hard">困难</option>
                    </select>
                  </div>
                  <div className="flex justify-end gap-2">
                    <button
                      onClick={() => setShowNewSample(false)}
                      className="px-3 py-1.5 text-[13px] rounded-md border hover:bg-gray-50"
                      style={{ borderColor: '#e2e1dd' }}
                    >
                      取消
                    </button>
                    <button
                      onClick={handleCreateSample}
                      className="px-3 py-1.5 text-[13px] rounded-lg text-white"
                      style={{ background: '#534ab7' }}
                    >
                      创建
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Samples List */}
            <div className="space-y-3">
              {samples.length === 0 ? (
                <div className="text-center py-12 bg-white rounded-lg border border-gray-200">
                  <FileText className="w-10 h-10 text-gray-300 mx-auto mb-3" />
                  <p className="text-sm text-gray-500">暂无 Golden Samples</p>
                  <p className="text-xs text-gray-400 mt-1">创建测试样本来评估 RAG 质量</p>
                </div>
              ) : (
                samples.map((sample) => (
                  <div
                    key={sample.id}
                    className="bg-white rounded-lg border border-gray-200 p-4"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          {sample.difficulty && (
                            <span className={`text-[11px] px-1.5 py-0.5 rounded ${getDifficultyColor(sample.difficulty)}`}>
                              {sample.difficulty}
                            </span>
                          )}
                          {sample.category && (
                            <span className="text-[11px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">
                              {sample.category}
                            </span>
                          )}
                        </div>
                        <h4 className="text-sm font-medium text-gray-900 mb-2">{sample.question}</h4>
                        <div className="text-xs text-gray-600 bg-gray-50 rounded p-2">
                          <span className="text-gray-500">期望答案：</span>
                          {sample.expected_answer}
                        </div>
                      </div>
                      <button
                        onClick={() => handleDeleteSample(sample.id)}
                        className="p-2 hover:bg-red-50 rounded transition-colors"
                      >
                        <Trash2 className="w-4 h-4 text-gray-400 hover:text-red-600" />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        ) : (
          <div className="max-w-4xl mx-auto">
            {/* Runs List */}
            <div className="space-y-3">
              {runs.length === 0 ? (
                <div className="text-center py-12 bg-white rounded-lg border border-gray-200">
                  <BarChart3 className="w-10 h-10 text-gray-300 mx-auto mb-3" />
                  <p className="text-sm text-gray-500">暂无评估运行</p>
                  <p className="text-xs text-gray-400 mt-1">点击"运行评估"开始质量评估</p>
                </div>
              ) : (
                runs.map((run) => (
                  <div
                    key={run.id}
                    className="bg-white rounded-lg border border-gray-200 p-4"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        {getStatusIcon(run.status)}
                        <div>
                          <h4 className="text-sm font-medium text-gray-900">{run.name}</h4>
                          <div className="flex items-center gap-3 mt-1">
                            <span className="text-xs text-gray-500 capitalize">{run.status}</span>
                            {run.total_samples && (
                              <span className="text-xs text-gray-500">{run.total_samples} 样本</span>
                            )}
                            {run.avg_score && (
                              <span className="text-xs text-green-600 font-medium">
                                平均分 {(run.avg_score * 100).toFixed(0)}%
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                      <ChevronRight className="w-4 h-4 text-gray-400" />
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
