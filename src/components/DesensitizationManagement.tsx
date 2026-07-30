import { useState, useEffect } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { fetchApi } from '@/lib/api-client';
import { Button } from './enterprise/Button';
import { Input } from './enterprise/Input';
import { Select } from './enterprise/Select';
import { Switch } from './enterprise/Switch';
import { Badge } from './enterprise/Badge';
import { Card } from './enterprise/Card';
import { toast } from 'sonner';
import { Modal } from './enterprise/Modal';
import { Plus, Trash2, Edit, TestTube, Save } from 'lucide-react';

interface DesensitizationConfig {
  kb_id: string | null;
  level: string;
  enable_email_mask: boolean;
  enable_phone_mask: boolean;
  enable_id_card_mask: boolean;
  enable_bank_card_mask: boolean;
  enable_address_mask: boolean;
  enable_name_mask: boolean;
}

interface KnowledgeBase {
  id: string;
  name: string;
}

interface CustomRule {
  from: string;
  to: string;
  is_enabled: boolean;
}

export function DesensitizationManagement() {
  const { t } = useI18n();
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedKbId, setSelectedKbId] = useState<string>('');
  const [config, setConfig] = useState<DesensitizationConfig>({
    kb_id: null,
    level: 'medium',
    enable_email_mask: true,
    enable_phone_mask: true,
    enable_id_card_mask: true,
    enable_bank_card_mask: true,
    enable_address_mask: false,
    enable_name_mask: false,
  });
  const [customRules, setCustomRules] = useState<CustomRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [testText, setTestText] = useState('');
  const [testResult, setTestResult] = useState<any>(null);
  const [ruleModalOpen, setRuleModalOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<number | null>(null);
  const [ruleForm, setRuleForm] = useState({ from: '', to: '' });

  useEffect(() => {
    loadKnowledgeBases();
  }, []);

  useEffect(() => {
    if (selectedKbId || selectedKbId === '') {
      loadConfig(selectedKbId || null);
    }
  }, [selectedKbId]);

  const loadKnowledgeBases = async () => {
    try {
      const data = await fetchApi('/api/v1/knowledge-bases');
      const kbs = data.items || data;
      setKnowledgeBases(kbs);
    } catch (error) {
      console.error('Failed to load knowledge bases:', error);
    }
  };

  const loadConfig = async (kbId: string | null) => {
    setLoading(true);
    try {
      const params = kbId ? `?kb_id=${kbId}` : '';
      const data = await fetchApi(`/api/v1/desensitization/config${params}`);
      setConfig(data);
    } catch (error) {
      console.error('Failed to load config:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveConfig = async () => {
    try {
      const params = selectedKbId ? `?kb_id=${selectedKbId}` : '';
      await fetchApi(`/api/v1/desensitization/config${params}`, {
        method: 'PUT',
        body: JSON.stringify(config),
      });
      toast.success('脱敏配置已保存');
    } catch (error) {
      console.error('Failed to save config:', error);
      toast.error('保存失败');
    }
  };

  const handleTest = async () => {
    if (!testText.trim()) {
      toast.error('请输入测试文本');
      return;
    }

    try {
      const params = selectedKbId ? `?kb_id=${selectedKbId}` : '';
      const data = await fetchApi(`/api/v1/desensitization/test${params}`, {
        method: 'POST',
        body: JSON.stringify({ text: testText }),
      });
      setTestResult(data);
    } catch (error) {
      console.error('Failed to test:', error);
      toast.error('测试失败');
    }
  };

  const handleAddRule = () => {
    if (!ruleForm.from.trim() || !ruleForm.to.trim()) {
      toast.error('请填写完整规则');
      return;
    }

    if (editingRule !== null) {
      const newRules = [...customRules];
      newRules[editingRule] = {
        from: ruleForm.from,
        to: ruleForm.to,
        is_enabled: true,
      };
      setCustomRules(newRules);
    } else {
      setCustomRules([...customRules, { from: ruleForm.from, to: ruleForm.to, is_enabled: true }]);
    }

    setRuleForm({ from: '', to: '' });
    setRuleModalOpen(false);
    setEditingRule(null);
  };

  const handleDeleteRule = (index: number) => {
    setCustomRules(customRules.filter((_, i) => i !== index));
  };

  const getLevelLabel = (level: string) => {
    const labels: Record<string, string> = {
      none: '不脱敏',
      low: '轻度',
      medium: '中度',
      high: '高度',
    };
    return labels[level] || level;
  };

  const getRiskColor = (risk: string) => {
    if (risk === 'high') return 'text-red-500';
    if (risk === 'medium') return 'text-orange-500';
    return 'text-green-500';
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-[var(--gray-50)]">
      {/* Header */}
      <header className="h-[52px] px-5 bg-white flex items-center justify-between shrink-0"
              style={{ borderBottom: '0.5px solid var(--gray-200)' }}>
        <h1 className="text-[15px] font-medium text-[var(--text-primary)]">数据脱敏配置</h1>
        <Button onClick={handleSaveConfig}>
          <Save className="w-4 h-4 mr-1" />
          保存配置
        </Button>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4">
        <div className="grid grid-cols-2 gap-4">
          {/* Left: Configuration */}
          <div className="space-y-4">
            {/* KB Selector */}
            <Card className="p-4">
              <h3 className="text-sm font-medium mb-3">应用范围</h3>
              <Select
                value={selectedKbId}
                onChange={(e) => setSelectedKbId(e.target.value)}
              >
                <option value="">全局配置（所有知识库）</option>
                {knowledgeBases.map(kb => (
                  <option key={kb.id} value={kb.id}>{kb.name}</option>
                ))}
              </Select>
              <p className="text-xs text-[var(--text-secondary)] mt-2">
                可为不同知识库设置不同的脱敏策略
              </p>
            </Card>

            {/* Level Selector */}
            <Card className="p-4">
              <h3 className="text-sm font-medium mb-3">脱敏级别</h3>
              <Select
                value={config.level}
                onChange={(e) => setConfig({ ...config, level: e.target.value })}
              >
                <option value="none">不脱敏</option>
                <option value="low">轻度脱敏（保留部分信息）</option>
                <option value="medium">中度脱敏（模糊处理）</option>
                <option value="high">高度脱敏（完全替换）</option>
              </Select>
            </Card>

            {/* PII Types */}
            <Card className="p-4">
              <h3 className="text-sm font-medium mb-3">PII 类型脱敏</h3>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm">邮箱地址</span>
                  <Switch
                    checked={config.enable_email_mask}
                    onChange={(checked) => setConfig({ ...config, enable_email_mask: checked })}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm">手机号码</span>
                  <Switch
                    checked={config.enable_phone_mask}
                    onChange={(checked) => setConfig({ ...config, enable_phone_mask: checked })}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm">身份证号</span>
                  <Switch
                    checked={config.enable_id_card_mask}
                    onChange={(checked) => setConfig({ ...config, enable_id_card_mask: checked })}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm">银行卡号</span>
                  <Switch
                    checked={config.enable_bank_card_mask}
                    onChange={(checked) => setConfig({ ...config, enable_bank_card_mask: checked })}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm">地址信息</span>
                  <Switch
                    checked={config.enable_address_mask}
                    onChange={(checked) => setConfig({ ...config, enable_address_mask: checked })}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm">姓名</span>
                  <Switch
                    checked={config.enable_name_mask}
                    onChange={(checked) => setConfig({ ...config, enable_name_mask: checked })}
                  />
                </div>
              </div>
            </Card>

            {/* Custom Rules */}
            <Card className="p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-medium">自定义替换规则</h3>
                <Button size="sm" variant="outline" onClick={() => {
                  setEditingRule(null);
                  setRuleForm({ from: '', to: '' });
                  setRuleModalOpen(true);
                }}>
                  <Plus className="w-3 h-3 mr-1" />
                  添加
                </Button>
              </div>
              {customRules.length === 0 ? (
                <p className="text-sm text-[var(--text-secondary)] py-4 text-center">
                  暂无自定义规则
                </p>
              ) : (
                <div className="space-y-2">
                  {customRules.map((rule, idx) => (
                    <div key={idx} className="flex items-center justify-between p-2 bg-[var(--gray-100)] rounded">
                      <div className="flex items-center gap-2">
                        <Badge variant="secondary">{rule.from}</Badge>
                        <span className="text-xs">→</span>
                        <Badge variant="secondary">{rule.to}</Badge>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDeleteRule(idx)}
                      >
                        <Trash2 className="w-3 h-3 text-red-500" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>

          {/* Right: Test */}
          <div className="space-y-4">
            <Card className="p-4">
              <h3 className="text-sm font-medium mb-3 flex items-center gap-2">
                <TestTube className="w-4 h-4" />
                脱敏效果测试
              </h3>
              <div className="space-y-3">
                <div>
                  <label className="block text-sm font-medium mb-1">测试文本</label>
                  <textarea
                    value={testText}
                    onChange={(e) => setTestText(e.target.value)}
                    className="w-full h-32 px-3 py-2 border border-[var(--gray-300)] rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-[var(--accent)] resize-none"
                    placeholder="输入包含敏感信息的文本，如：张三的手机号是 13812345678，邮箱是 zhangsan@example.com"
                  />
                </div>
                <Button onClick={handleTest} className="w-full">
                  测试脱敏效果
                </Button>
              </div>

              {testResult && (
                <div className="mt-4 space-y-3">
                  <div>
                    <span className="text-xs text-[var(--text-secondary)]">检测结果：</span>
                    <div className="flex gap-2 mt-1">
                      {Object.entries(testResult.detected_pii || {}).map(([type, count]) => (
                        <Badge key={type} variant="secondary">
                          {type}: {count}
                        </Badge>
                      ))}
                      {Object.keys(testResult.detected_pii || {}).length === 0 && (
                        <span className="text-xs text-[var(--text-secondary)]">未检测到 PII</span>
                      )}
                    </div>
                  </div>
                  <div>
                    <span className="text-xs text-[var(--text-secondary)]">风险等级：</span>
                    <span className={`text-sm font-medium ${getRiskColor(testResult.risk_level)}`}>
                      {testResult.risk_level === 'high' ? '高' :
                       testResult.risk_level === 'medium' ? '中' : '低'}
                    </span>
                  </div>
                  <div>
                    <span className="text-xs text-[var(--text-secondary)]">脱敏后：</span>
                    <div className="mt-1 p-2 bg-[var(--gray-100)] rounded text-sm font-mono">
                      {testResult.desensitized}
                    </div>
                  </div>
                </div>
              )}
            </Card>

            {/* Example */}
            <Card className="p-4">
              <h3 className="text-sm font-medium mb-3">脱敏示例</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-[var(--text-secondary)]">邮箱：</span>
                  <span>zhang**@example.com</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[var(--text-secondary)]">手机：</span>
                  <span>138****5678</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[var(--text-secondary)]">身份证：</span>
                  <span>1***************1X</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[var(--text-secondary)]">银行卡：</span>
                  <span>6222****5678</span>
                </div>
              </div>
            </Card>
          </div>
        </div>

        {/* Modal for Add/Edit Rule */}
        <Modal
          open={ruleModalOpen}
          onOpenChange={setRuleModalOpen}
          title={editingRule !== null ? '编辑替换规则' : '添加替换规则'}
          width="400px"
          footer={
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setRuleModalOpen(false)}>
                取消
              </Button>
              <Button type="button" onClick={handleAddRule}>
                {editingRule !== null ? '更新' : '添加'}
              </Button>
            </div>
          }
        >
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">原文本</label>
              <Input
                value={ruleForm.from}
                onChange={(e) => setRuleForm({ ...ruleForm, from: e.target.value })}
                placeholder="如：apple, CEO"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">替换为</label>
              <Input
                value={ruleForm.to}
                onChange={(e) => setRuleForm({ ...ruleForm, to: e.target.value })}
                placeholder="如：苹果，首席执行官"
              />
            </div>
          </div>
        </Modal>
      </div>
    </div>
  );
}
