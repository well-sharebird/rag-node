# 数据清洗原子能力与 Agent Flow 封装设计

**版本**: v1.0  
**更新日期**: 2026-07-29

---

## 1. 原子能力分析

### 1.1 当前清洗流程的原子化程度

当前数据清洗流程已经具备较好的原子化基础，每个步骤都是独立的方法：

```
┌─────────────────────────────────────────────────────────────────┐
│ TextCleaner 类                                                   │
├─────────────────────────────────────────────────────────────────┤
│ • calculate_quality_score(text, html) → float                   │
│ • detect_language(text) → str                                   │
│ • compute_simhash(text) → int                                   │
│ • hamming_distance(h1, h2) → int                                │
│ • is_duplicate(text, existing_hashes) → bool                    │
│ • detect_and_remove_pii(text) → (str, Dict)                     │
│ • remove_noise(text) → str                                      │
│ • detect_encoding(content) → str                                │
│ • clean(text, html, existing_hashes) → CleaningResult           │  ← 编排方法
└─────────────────────────────────────────────────────────────────┘
```

**原子化评估**:

| 步骤 | 原子性 | 可复用性 | 可组合性 | 状态 |
|------|--------|----------|----------|------|
| 质量评分 | ✅ | ✅ | ✅ | 可封装为 Agent |
| 语言检测 | ✅ | ✅ | ✅ | 可封装为 Agent |
| SimHash 计算 | ✅ | ✅ | ✅ | 可封装为 Agent |
| 重复检测 | ✅ | ✅ | ✅ | 可封装为 Agent |
| 噪音过滤 | ✅ | ✅ | ✅ | 可封装为 Agent |
| PII 检测 | ✅ | ✅ | ✅ | 可封装为 Agent |
| PII 脱敏 | ✅ | ✅ | ✅ | 可封装为 Agent |
| 自定义替换 | ✅ | ✅ | ✅ | 可封装为 Agent |
| 完整清洗流程 | ✅ | ✅ | ✅ | 可封装为 Flow |

---

## 2. Agent 节点设计

### 2.1 Agent 节点接口定义

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class AgentInput:
    """Agent 输入"""
    text: str                          # 输入文本
    metadata: Dict[str, Any] = None    # 元数据
    config: Dict[str, Any] = None      # 配置参数

@dataclass
class AgentOutput:
    """Agent 输出"""
    success: bool                      # 是否成功
    data: Any                          # 输出数据
    metadata: Dict[str, Any] = None    # 元数据
    error: Optional[str] = None        # 错误信息

class BaseCleaningAgent(ABC):
    """数据清洗 Agent 基类"""
    
    name: str = "base_cleaning_agent"
    description: str = "基础清洗 Agent"
    
    @abstractmethod
    async def execute(self, input: AgentInput) -> AgentOutput:
        """执行清洗任务"""
        pass
```

### 2.2 原子 Agent 列表

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        数据清洗原子 Agent 列表                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐          │
│  │ QualityAgent     │  │ LanguageAgent    │  │ SimHashAgent     │          │
│  │ 质量评分 Agent    │  │ 语言检测 Agent    │  │ 指纹计算 Agent    │          │
│  ├──────────────────┤  ├──────────────────┤  ├──────────────────┤          │
│  │ 输入：text       │  │ 输入：text       │  │ 输入：text       │          │
│  │ 输出：score      │  │ 输出：language   │  │ 输出：simhash    │          │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘          │
│                                                                             │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐          │
│  │ DedupAgent       │  │ NoiseAgent       │  │ PIIDetectAgent   │          │
│  │ 重复检测 Agent    │  │ 噪音过滤 Agent    │  │ PII 检测 Agent     │          │
│  ├──────────────────┤  ├──────────────────┤  ├──────────────────┤          │
│  │ 输入：text+hashes│  │ 输入：text       │  │ 输入：text       │          │
│  │ 输出：is_dup     │  │ 输出：cleaned    │  │ 输出：pii_types  │          │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘          │
│                                                                             │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐          │
│  │ PIIMaskAgent     │  │ CustomRuleAgent  │  │ EncodingAgent    │          │
│  │ PII 脱敏 Agent     │  │ 自定义规则 Agent  │  │ 编码检测 Agent    │          │
│  ├──────────────────┤  ├──────────────────┤  ├──────────────────┤          │
│  │ 输入：text+config│  │ 输入：text+rules │  │ 输入：bytes      │          │
│  │ 输出：masked     │  │ 输出：replaced   │  │ 输出：encoding   │          │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Agent 实现示例

### 3.1 质量评分 Agent

```python
from app.preprocessing.text_cleaner import TextCleaner

class QualityScoreAgent(BaseCleaningAgent):
    """质量评分 Agent"""
    
    name = "quality_score_agent"
    description = "评估文本质量并返回 0-1 评分"
    
    def __init__(self, config: Optional[Dict] = None):
        self.cleaner = TextCleaner(config)
    
    async def execute(self, input: AgentInput) -> AgentOutput:
        try:
            text = input.text
            html = input.metadata.get("html") if input.metadata else None
            
            score = self.cleaner.calculate_quality_score(text, html)
            
            return AgentOutput(
                success=True,
                data={"quality_score": score},
                metadata={
                    "score_level": self._get_level(score),
                    "recommendation": self._get_recommendation(score)
                }
            )
        except Exception as e:
            return AgentOutput(
                success=False,
                data=None,
                error=str(e)
            )
    
    def _get_level(self, score: float) -> str:
        if score >= 0.8:
            return "high"
        elif score >= 0.5:
            return "medium"
        else:
            return "low"
    
    def _get_recommendation(self, score: float) -> str:
        if score < 0.3:
            return "建议重新获取或人工审核"
        elif score < 0.5:
            return "建议进行额外清洗"
        else:
            return "质量合格，可继续处理"
```

### 3.2 语言检测 Agent

```python
from app.preprocessing.text_cleaner import TextCleaner

class LanguageDetectionAgent(BaseCleaningAgent):
    """语言检测 Agent"""
    
    name = "language_detection_agent"
    description = "检测文本语言并返回 ISO 语言代码"
    
    def __init__(self):
        self.cleaner = TextCleaner()
    
    async def execute(self, input: AgentInput) -> AgentOutput:
        try:
            text = input.text
            language = self.cleaner.detect_language(text)
            
            return AgentOutput(
                success=True,
                data={"language": language, "language_name": self._get_language_name(language)},
                metadata={"confidence": "high" if language != "unknown" else "low"}
            )
        except Exception as e:
            return AgentOutput(
                success=False,
                data=None,
                error=str(e)
            )
    
    def _get_language_name(self, code: str) -> str:
        names = {
            "zh": "中文",
            "en": "English",
            "ja": "日本語",
            "ko": "한국어",
            "ar": "العربية",
            "ru": "Русский",
            "unknown": "未知"
        }
        return names.get(code, code)
```

### 3.3 PII 脱敏 Agent

```python
from app.services.desensitization_service import DesensitizationService, DesensitizationConfig

class PIIMaskingAgent(BaseCleaningAgent):
    """PII 脱敏 Agent"""
    
    name = "pii_masking_agent"
    description = "根据配置对文本进行 PII 脱敏处理"
    
    def __init__(self, config: DesensitizationConfig):
        self.config = config
    
    async def execute(self, input: AgentInput) -> AgentOutput:
        try:
            from app.services.desensitization_service import DesensitizationService
            
            service = DesensitizationService(None, self.config)
            desensitized = service.apply(input.text)
            
            # 检测脱敏前后的 PII 变化
            stats_before = service.detect_pii(input.text)
            stats_after = service.detect_pii(desensitized)
            
            return AgentOutput(
                success=True,
                data={"text": desensitized},
                metadata={
                    "pii_before": stats_before,
                    "pii_after": stats_after,
                    "masked_count": sum(stats_before.values()) - sum(stats_after.values())
                }
            )
        except Exception as e:
            return AgentOutput(
                success=False,
                data=None,
                error=str(e)
            )
```

### 3.4 自定义替换 Agent

```python
import re

class CustomRuleAgent(BaseCleaningAgent):
    """自定义规则替换 Agent"""
    
    name = "custom_rule_agent"
    description = "根据自定义规则进行文本替换 (如 apple→苹果)"
    
    def __init__(self, rules: list[dict]):
        """
        rules: [{"from": "apple", "to": "苹果", "is_enabled": true}, ...]
        """
        self.rules = [r for r in rules if r.get("is_enabled", True)]
    
    async def execute(self, input: AgentInput) -> AgentOutput:
        try:
            text = input.text
            replacements_made = []
            
            for rule in self.rules:
                from_text = rule.get("from", "")
                to_text = rule.get("to", "")
                
                if from_text:
                    # 不区分大小写替换
                    pattern = re.compile(re.escape(from_text), re.IGNORECASE)
                    matches = pattern.findall(text)
                    if matches:
                        text = pattern.sub(to_text, text)
                        replacements_made.append({
                            "from": from_text,
                            "to": to_text,
                            "count": len(matches)
                        })
            
            return AgentOutput(
                success=True,
                data={"text": text},
                metadata={"replacements": replacements_made}
            )
        except Exception as e:
            return AgentOutput(
                success=False,
                data=None,
                error=str(e)
            )
```

---

## 4. Agent Flow 编排设计

### 4.1 Flow 编排器接口

```python
from typing import List, Callable
from enum import Enum

class FlowStrategy(Enum):
    """Flow 执行策略"""
    SEQUENTIAL = "sequential"      # 顺序执行
    PARALLEL = "parallel"          # 并行执行
    CONDITIONAL = "conditional"    # 条件分支
    ITERATIVE = "iterative"        # 迭代执行

class AgentFlowOrchestrator:
    """Agent Flow 编排器"""
    
    def __init__(self, flow_id: str):
        self.flow_id = flow_id
        self.agents: List[BaseCleaningAgent] = []
        self.strategy = FlowStrategy.SEQUENTIAL
        self.conditions: dict = {}
    
    def add_agent(self, agent: BaseCleaningAgent):
        """添加 Agent 节点"""
        self.agents.append(agent)
        return self
    
    def set_strategy(self, strategy: FlowStrategy):
        """设置执行策略"""
        self.strategy = strategy
        return self
    
    def add_condition(self, agent_name: str, condition: Callable[[AgentOutput], bool]):
        """添加条件判断"""
        self.conditions[agent_name] = condition
        return self
    
    async def execute(self, input: AgentInput) -> AgentOutput:
        """执行 Flow"""
        current_data = input
        
        for agent in self.agents:
            # 执行 Agent
            output = await agent.execute(current_data)
            
            if not output.success:
                return AgentOutput(
                    success=False,
                    data=None,
                    error=f"Agent '{agent.name}' failed: {output.error}"
                )
            
            # 根据输出更新下一个 Agent 的输入
            current_data = self._prepare_next_input(current_data, output, agent)
            
            # 检查条件分支
            if agent.name in self.conditions:
                if not self.conditions[agent.name](output):
                    break  # 条件不满足，终止流程
        
        return AgentOutput(
            success=True,
            data=current_data.data,
            metadata=self._collect_metadata(current_data)
        )
```

### 4.2 标准清洗 Flow

```python
async def create_standard_cleaning_flow(config: dict = None) -> AgentFlowOrchestrator:
    """
    创建标准数据清洗 Flow
    
    Flow 步骤:
    1. 编码检测 → 2. 语言检测 → 3. 质量评分 → 4. 噪音过滤 → 5. PII 脱敏 → 6. 自定义替换
    """
    from app.preprocessing.text_cleaner import TextCleaner
    from app.services.desensitization_service import DesensitizationConfig
    
    flow = AgentFlowOrchestrator(flow_id="standard_cleaning_flow")
    
    # 1. 语言检测
    flow.add_agent(LanguageDetectionAgent())
    
    # 2. 质量评分
    flow.add_agent(QualityScoreAgent(config))
    
    # 3. 噪音过滤 (使用 TextCleaner 的 remove_noise 方法)
    flow.add_agent(NoiseFilterAgent())
    
    # 4. PII 脱敏
    pii_config = DesensitizationConfig(
        level=DesensitizationLevel.MEDIUM,
        enable_email_mask=True,
        enable_phone_mask=True,
        enable_id_card_mask=True,
    )
    flow.add_agent(PIIMaskingAgent(pii_config))
    
    # 5. 自定义替换
    custom_rules = [
        {"from": "apple", "to": "苹果", "is_enabled": True},
        {"from": "CEO", "to": "首席执行官", "is_enabled": True},
    ]
    flow.add_agent(CustomRuleAgent(custom_rules))
    
    return flow
```

### 4.3 Flow 执行示例

```python
# 创建清洗 Flow
flow = await create_standard_cleaning_flow()

# 准备输入
input_data = AgentInput(
    text="张三的邮箱是 zhangsan@apple.com，电话 13812345678。apple 公司 CEO 访华。",
    metadata={"source": "document_001"}
)

# 执行 Flow
output = await flow.execute(input_data)

# 输出结果
print(f"Success: {output.success}")
print(f"Cleaned Text: {output.data['text']}")
print(f"Metadata: {output.metadata}")
```

---

## 5. Agent 注册与发现

### 5.1 Agent 注册表

```python
from typing import Dict, Type

class AgentRegistry:
    """Agent 注册表"""
    
    _registry: Dict[str, Type[BaseCleaningAgent]] = {}
    
    @classmethod
    def register(cls, agent_class: Type[BaseCleaningAgent]):
        """注册 Agent 类"""
        cls._registry[agent_class.name] = agent_class
        return agent_class
    
    @classmethod
    def get(cls, name: str) -> Type[BaseCleaningAgent]:
        """获取 Agent 类"""
        if name not in cls._registry:
            raise ValueError(f"Agent '{name}' not found")
        return cls._registry[name]
    
    @classmethod
    def list_agents(cls) -> list[str]:
        """列出所有已注册的 Agent"""
        return list(cls._registry.keys())

# 注册所有原子 Agent
AgentRegistry.register(QualityScoreAgent)
AgentRegistry.register(LanguageDetectionAgent)
AgentRegistry.register(PIIMaskingAgent)
AgentRegistry.register(CustomRuleAgent)
AgentRegistry.register(NoiseFilterAgent)
AgentRegistry.register(DedupAgent)
```

### 5.2 数据库模型扩展

```python
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

class AgentNode(Base):
    """Agent 节点配置表"""
    
    __tablename__ = "cleaning_agent_nodes"
    
    id = Column(Integer, primary_key=True)
    flow_id = Column(String(100), ForeignKey("cleaning_flows.id"), nullable=False)
    agent_type = Column(String(100), nullable=False)  # 关联 AgentRegistry
    agent_name = Column(String(200))  # 自定义名称
    agent_config = Column(JSONB, default=dict)  # Agent 特定配置
    order_index = Column(Integer, default=0)  # 执行顺序
    is_enabled = Column(Boolean, default=True)
    condition_expression = Column(Text)  # 条件表达式 (JSON)
    
    # 输入输出映射
    input_mapping = Column(JSONB, default=dict)  # 如何将上游输出映射为输入
    output_mapping = Column(JSONB, default=dict)  # 如何将输出传递给下游

class CleaningFlow(Base):
    """清洗 Flow 配置表"""
    
    __tablename__ = "cleaning_flows"
    
    id = Column(String(100), primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    strategy = Column(String(20), default="sequential")  # sequential/parallel/conditional
    kb_id = Column(String(36), ForeignKey("knowledge_bases.id"))  # 关联知识库
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    
    nodes = relationship("AgentNode", back_populates="flow", cascade="all, delete-orphan")
```

---

## 6. 与现有 Agent 系统集成

### 6.1 接入 Agent Builder

将数据清洗 Agent 注册为系统技能：

```python
# backend/app/skills/data_cleaning_skills.py

from app.skills.create_agent_skill import register_skill

@register_skill(
    name="data_quality_check",
    description="检查数据质量并返回评分",
    category="data_cleaning"
)
async def data_quality_check(text: str) -> dict:
    agent = QualityScoreAgent()
    input_data = AgentInput(text=text)
    output = await agent.execute(input_data)
    return output.data if output.success else {"error": output.error}

@register_skill(
    name="pii_masking",
    description="对文本进行 PII 脱敏处理",
    category="data_cleaning"
)
async def pii_masking(text: str, level: str = "medium") -> dict:
    config = DesensitizationConfig(level=DesensitizationLevel(level))
    agent = PIIMaskingAgent(config)
    input_data = AgentInput(text=text)
    output = await agent.execute(input_data)
    return {"text": output.data["text"]} if output.success else {"error": output.error}

@register_skill(
    name="custom_text_replacement",
    description="根据自定义规则替换文本",
    category="data_cleaning"
)
async def custom_text_replacement(text: str, rules: list[dict]) -> dict:
    agent = CustomRuleAgent(rules)
    input_data = AgentInput(text=text)
    output = await agent.execute(input_data)
    return output.data if output.success else {"error": output.error}
```

### 6.2 Agent Flow 配置 UI

在现有 Agent 管理界面中添加 Flow 配置：

```typescript
// src/components/DataCleaningFlowBuilder.tsx

interface AgentNode {
  id: string;
  agentType: string;
  agentName: string;
  config: Record<string, any>;
  orderIndex: number;
  condition?: string;
}

interface CleaningFlow {
  id: string;
  name: string;
  description: string;
  strategy: 'sequential' | 'parallel' | 'conditional';
  nodes: AgentNode[];
  kbId?: string;
}

export function DataCleaningFlowBuilder() {
  const [flow, setFlow] = useState<CleaningFlow>({
    id: '',
    name: '',
    strategy: 'sequential',
    nodes: []
  });
  
  const availableAgents = [
    { type: 'quality_score', name: '质量评分', icon: '📊' },
    { type: 'language_detection', name: '语言检测', icon: '🌐' },
    { type: 'pii_masking', name: 'PII 脱敏', icon: '🔒' },
    { type: 'custom_rule', name: '自定义替换', icon: '🔄' },
    { type: 'noise_filter', name: '噪音过滤', icon: '🧹' },
    { type: 'dedup', name: '重复检测', icon: '🔍' },
  ];
  
  return (
    <div className="flow-builder">
      <div className="agent-palette">
        {availableAgents.map(agent => (
          <div key={agent.type} className="agent-node" draggable>
            {agent.icon} {agent.name}
          </div>
        ))}
      </div>
      <div className="flow-canvas">
        {/* 拖拽编排区域 */}
      </div>
    </div>
  );
}
```

---

## 7. 实施计划

### 7.1 Phase 1: 原子 Agent 封装 (1-2 周)

| 任务 | 优先级 | 工作量 |
|------|--------|--------|
| 定义 Agent 基类和接口 | P0 | 2h |
| 实现 QualityScoreAgent | P0 | 2h |
| 实现 LanguageDetectionAgent | P0 | 2h |
| 实现 PIIMaskingAgent | P0 | 3h |
| 实现 CustomRuleAgent | P0 | 2h |
| 实现 NoiseFilterAgent | P1 | 2h |
| 实现 DedupAgent | P1 | 2h |
| 实现 AgentRegistry | P0 | 3h |

### 7.2 Phase 2: Flow 编排器 (1-2 周)

| 任务 | 优先级 | 工作量 |
|------|--------|--------|
| 实现 AgentFlowOrchestrator | P0 | 4h |
| 实现 Sequential 策略 | P0 | 2h |
| 实现 Conditional 策略 | P1 | 4h |
| 实现 Parallel 策略 | P1 | 4h |
| 数据库模型设计与迁移 | P0 | 3h |
| 标准 Flow 模板 | P0 | 2h |

### 7.3 Phase 3: 前端配置界面 (1-2 周)

| 任务 | 优先级 | 工作量 |
|------|--------|--------|
| Flow 列表页 | P0 | 4h |
| Flow 创建/编辑页 | P0 | 8h |
| 拖拽式编排界面 | P1 | 12h |
| Agent 配置表单 | P0 | 6h |
| Flow 测试工具 | P1 | 4h |

### 7.4 Phase 4: 与现有系统集成 (1 周)

| 任务 | 优先级 | 工作量 |
|------|--------|--------|
| 注册为 Agent 技能 | P0 | 3h |
| 集成到文档处理流程 | P0 | 4h |
| 集成到 Agent Builder | P1 | 4h |
| 添加监控和日志 | P1 | 4h |

---

## 8. 使用场景示例

### 场景 1: 多语言文档清洗

```
Flow 配置:
1. LanguageDetectionAgent → 检测语言
2. [条件分支]
   - 如果 language == "zh": 使用中文 PII 规则
   - 如果 language == "en": 使用英文 PII 规则
   - 其他：跳过 PII 脱敏
3. NoiseFilterAgent → 噪音过滤
4. CustomRuleAgent → 术语统一
```

### 场景 2: 高敏感数据清洗

```
Flow 配置:
1. EncodingAgent → 检测编码
2. QualityScoreAgent → 质量评估
3. [条件] 如果 score < 0.3 → 终止并告警
4. PIIMaskingAgent (level=high) → 高度脱敏
5. CustomRuleAgent → 敏感词替换
6. DedupAgent → 重复检测
7. [条件] 如果 is_duplicate → 标记并跳过入库
```

### 场景 3: 快速轻量清洗

```
Flow 配置:
1. NoiseFilterAgent → 噪音过滤
2. CustomRuleAgent → 术语统一
(跳过 PII 脱敏和重复检测，适用于内部可信数据)
```

---

## 9. 总结

### 当前状态

✅ 数据清洗流程已经是原子化设计  
✅ 每个步骤都是独立方法，可直接封装  
✅ 有清晰的输入输出数据结构  

### 后续工作

1. 定义统一的 Agent 接口
2. 封装 7-8 个原子 Agent
3. 实现 Flow 编排器
4. 创建前端配置界面
5. 与现有 Agent 系统集成

### 收益

- **灵活性**: 用户可自定义清洗流程
- **可复用**: 原子 Agent 可在其他场景复用
- **可观测**: 每个 Agent 的执行情况可追踪
- **可扩展**: 新增清洗能力只需添加新 Agent

---

**文档维护者**: AI Assistant  
**最后更新**: 2026-07-29
