import { useState, useEffect } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { fetchApi } from '@/lib/api-client';
import { Button } from './enterprise/Button';
import { Input } from './enterprise/Input';
import { Select } from './enterprise/Select';
import { Badge } from './enterprise/Badge';
import { Card } from './enterprise/Card';
import { toast } from 'sonner';
import { Modal } from './enterprise/Modal';
import { Plus, Trash2, Edit, Search, RotateCcw } from 'lucide-react';

interface SynonymEntry {
  id: number;
  standard_term: string;
  synonyms: string[];
  category: string | null;
  kb_id: string | null;
  is_enabled: boolean;
}

interface KnowledgeBase {
  id: string;
  name: string;
}

const CATEGORIES = [
  { value: '', label: '全部' },
  { value: '技术术语', label: '技术术语' },
  { value: '品牌', label: '品牌' },
  { value: '职位', label: '职位' },
  { value: '自定义', label: '自定义' },
];

export function SynonymManagement() {
  const { t } = useI18n();
  const [synonyms, setSynonyms] = useState<SynonymEntry[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [filterCategory, setFilterCategory] = useState('');
  const [filterKbId, setFilterKbId] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  // 表单状态
  const [formData, setFormData] = useState({
    standard_term: '',
    synonyms: '',
    category: '',
    kb_id: '',
  });

  useEffect(() => {
    loadSynonyms();
    loadKnowledgeBases();
  }, []);

  const loadSynonyms = async () => {
    try {
      const params = new URLSearchParams();
      if (filterCategory) params.append('category', filterCategory);
      if (filterKbId) params.append('kb_id', filterKbId);

      const data = await fetchApi(`/api/v1/synonyms?${params}`);
      setSynonyms(data);
    } catch (error) {
      console.error('Failed to load synonyms:', error);
      toast.error('加载同义词失败');
    } finally {
      setLoading(false);
    }
  };

  const loadKnowledgeBases = async () => {
    try {
      const data = await fetchApi('/api/v1/knowledge-bases');
      setKnowledgeBases(data.items || data);
    } catch (error) {
      console.error('Failed to load knowledge bases:', error);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!formData.standard_term.trim()) {
      toast.error('请输入标准词');
      return;
    }

    const synonymsList = formData.synonyms
      .split(/[,,\n]/)
      .map(s => s.trim())
      .filter(s => s.length > 0);

    if (synonymsList.length === 0) {
      toast.error('请至少添加一个同义词');
      return;
    }

    try {
      const payload = {
        standard_term: formData.standard_term.trim(),
        synonyms: synonymsList,
        category: formData.category || null,
        kb_id: formData.kb_id || null,
      };

      const url = editingId
        ? `/api/v1/synonyms/${editingId}`
        : '/api/v1/synonyms';

      const method = editingId ? 'PUT' : 'POST';

      await fetchApi(url, {
        method,
        body: JSON.stringify(payload),
      });

      toast.success(editingId ? '同义词已更新' : '同义词已添加');
      setModalOpen(false);
      setEditingId(null);
      setFormData({ standard_term: '', synonyms: '', category: '', kb_id: '' });
      loadSynonyms();
    } catch (error) {
      console.error('Failed to save synonym:', error);
      toast.error('保存失败');
    }
  };

  const handleEdit = (synonym: SynonymEntry) => {
    setEditingId(synonym.id);
    setFormData({
      standard_term: synonym.standard_term,
      synonyms: synonym.synonyms.join(', '),
      category: synonym.category || '',
      kb_id: synonym.kb_id || '',
    });
    setModalOpen(true);
  };

  const handleDelete = async (id: number) => {
    if (!confirm('确定要删除这个同义词映射吗？')) return;

    try {
      await fetchApi(`/api/v1/synonyms/${id}`, {
        method: 'DELETE',
      });

      toast.success('同义词已删除');
      loadSynonyms();
    } catch (error) {
      console.error('Failed to delete synonym:', error);
      toast.error('删除失败');
    }
  };

  const handleInitDefault = async () => {
    try {
      await fetchApi('/api/v1/synonyms/init', {
        method: 'POST',
      });

      toast.success('默认同义词库已初始化');
      loadSynonyms();
    } catch (error) {
      console.error('Failed to init synonyms:', error);
      toast.error('初始化失败');
    }
  };

  const filteredSynonyms = synonyms.filter(s => {
    if (searchQuery && !s.standard_term.toLowerCase().includes(searchQuery.toLowerCase())) {
      return false;
    }
    if (filterCategory && s.category !== filterCategory) {
      return false;
    }
    if (filterKbId && s.kb_id !== filterKbId) {
      return false;
    }
    return true;
  });

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-[var(--gray-50)]">
      {/* Header */}
      <header className="h-[52px] px-5 bg-white flex items-center justify-between shrink-0"
              style={{ borderBottom: '0.5px solid var(--gray-200)' }}>
        <h1 className="text-[15px] font-medium text-[var(--text-primary)]">同义词管理</h1>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleInitDefault}>
            <RotateCcw className="w-4 h-4 mr-1" />
            初始化默认词库
          </Button>
          <Button size="sm" onClick={() => {
            setEditingId(null);
            setFormData({ standard_term: '', synonyms: '', category: '', kb_id: '' });
            setModalOpen(true);
          }}>
            <Plus className="w-4 h-4 mr-1" />
            添加同义词
          </Button>
        </div>
      </header>

      {/* Modal for Add/Edit */}
      <Modal
        open={modalOpen}
        onOpenChange={setModalOpen}
        title={editingId ? '编辑同义词' : '添加同义词'}
        width="500px"
        footer={
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setModalOpen(false)}>
              取消
            </Button>
            <Button type="button" onClick={handleSubmit}>
              {editingId ? '更新' : '添加'}
            </Button>
          </div>
        }
      >
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">标准词</label>
            <Input
              value={formData.standard_term}
              onChange={(e) => setFormData({ ...formData, standard_term: e.target.value })}
              placeholder="如：苹果、人工智能"
            />
            <p className="text-xs text-[var(--text-secondary)] mt-1">
              标准词是规范术语，同义词都会映射到它
            </p>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">同义词列表</label>
            <Input
              value={formData.synonyms}
              onChange={(e) => setFormData({ ...formData, synonyms: e.target.value })}
              placeholder="apple, 苹果手机，苹果公司"
            />
            <p className="text-xs text-[var(--text-secondary)] mt-1">
              用逗号或换行分隔，如：apple, 苹果手机，苹果公司
            </p>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">分类</label>
            <Select
              value={formData.category}
              onChange={(e) => setFormData({ ...formData, category: e.target.value })}
            >
              <option value="">选择分类</option>
              <option value="技术术语">技术术语</option>
              <option value="品牌">品牌</option>
              <option value="职位">职位</option>
              <option value="自定义">自定义</option>
            </Select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">所属知识库</label>
            <Select
              value={formData.kb_id}
              onChange={(e) => setFormData({ ...formData, kb_id: e.target.value })}
            >
              <option value="">全局（所有知识库）</option>
              {knowledgeBases.map(kb => (
                <option key={kb.id} value={kb.id}>{kb.name}</option>
              ))}
            </Select>
            <p className="text-xs text-[var(--text-secondary)] mt-1">
              留空表示全局同义词，适用于所有知识库
            </p>
          </div>
        </form>
      </Modal>

      {/* Filters */}
      <div className="p-4 bg-white" style={{ borderBottom: '0.5px solid var(--gray-200)' }}>
        <div className="flex gap-3">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text-secondary)]" />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="搜索标准词..."
              className="pl-9"
            />
          </div>
          <Select
            value={filterCategory}
            onChange={(e) => setFilterCategory(e.target.value)}
            className="w-[150px]"
          >
            {CATEGORIES.map(cat => (
              <option key={cat.value} value={cat.value}>{cat.label}</option>
            ))}
          </Select>
          <Select
            value={filterKbId}
            onChange={(e) => setFilterKbId(e.target.value)}
            className="w-[180px]"
          >
            <option value="">全部知识库</option>
            {knowledgeBases.map(kb => (
              <option key={kb.id} value={kb.id}>{kb.name}</option>
            ))}
          </Select>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4">
        {loading ? (
          <div className="flex items-center justify-center h-full text-[var(--text-secondary)]">
            加载中...
          </div>
        ) : filteredSynonyms.length === 0 ? (
          <Card className="p-8 text-center text-[var(--text-secondary)]">
            <p>暂无同义词数据</p>
            <p className="text-sm mt-2">点击"添加同义词"或"初始化默认词库"开始</p>
          </Card>
        ) : (
          <div className="space-y-3">
            {filteredSynonyms.map((synonym) => (
              <Card key={synonym.id} className="p-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-base font-medium text-[var(--text-primary)]">
                        {synonym.standard_term}
                      </span>
                      {synonym.category && (
                        <Badge variant="secondary">{synonym.category}</Badge>
                      )}
                      {!synonym.kb_id && (
                        <Badge variant="outline" className="text-xs">全局</Badge>
                      )}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {synonym.synonyms.map((syn, idx) => (
                        <Badge key={idx} variant="secondary" className="text-xs">
                          {syn}
                        </Badge>
                      ))}
                    </div>
                    {synonym.kb_id && (
                      <p className="text-xs text-[var(--text-secondary)] mt-2">
                        所属知识库：{knowledgeBases.find(kb => kb.id === synonym.kb_id)?.name || synonym.kb_id}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleEdit(synonym)}
                    >
                      <Edit className="w-4 h-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDelete(synonym.id)}
                    >
                      <Trash2 className="w-4 h-4 text-red-500" />
                    </Button>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
