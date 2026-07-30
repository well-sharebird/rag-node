# 数据清洗流程详解

**版本**: v1.0  
**更新日期**: 2026-07-29

---

## 1. 清洗流程概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        数据清洗处理流程                                      │
└─────────────────────────────────────────────────────────────────────────────┘

原始文档 (PDF/Word/Excel 等)
        │
        ▼
┌─────────────────┐
│ Stage 2: 文档解析  │  输出：raw_text (原始文本)
│ Document Parse  │
└─────────────────┘
        │
        ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ Stage 1.5: 预处理与清洗 (TextCleaner.clean())                               │
│ ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│ │ 1. 质量评分   │→ │ 2. 语言检测   │→ │ 3. SimHash   │→ │ 4. 重复检测   │   │
│ │ Quality Score│  │  Language    │  │  SimHash     │  │  Dedup Check │   │
│ └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │
│ ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                      │
│ │ 5. 噪音过滤   │→ │ 6. PII 检测    │→ │ 7. 输出结果   │                      │
│ │ Noise Remove │  │  PII Detect  │  │  CleaningResult│                     │
│ └──────────────┘  └──────────────┘  └──────────────┘                      │
└────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ Stage 1.6: 数据脱敏 (DesensitizationService.apply())                        │
│ ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                      │
│ │ 1. PII 脱敏    │→ │ 2. 自定义规则  │→ │ 3. 脱敏文本   │                      │
│ │ PII Masking  │  │ Custom Rules │  │  Desensitized │                     │
│ └──────────────┘  └──────────────┘  └──────────────┘                      │
│ • 邮箱：zhang**@example.com                                                 │
│ • 手机：138****5678                                                         │
│ • 身份证：1***************1X                                                 │
│ • 自定义：apple → 苹果，CEO → 首席执行官                                       │
└────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ Stage 3: 分块切分 (Chunking)                                                │
│ • 根据文件类型选择分块策略 (Fixed/Semantic/Recursive/Parent-Child 等)            │
│ • 输出：Chunk[] (文本块数组，带元数据)                                         │
└────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ Stage 4: 向量嵌入 (Embedding)                                               │
│ • 调用嵌入模型 API 将文本转换为向量                                            │
│ • 输出：embeddings (浮点数数组)                                               │
└────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ Stage 5: 向量入库 (Milvus Insert)                                           │
│ • 将向量 + 元数据插入 Milvus 向量数据库                                         │
│ • 输出：insert_count (插入数量)                                               │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Stage 1.5 详解：预处理与清洗

### 2.1 执行位置

**文件**: `backend/app/preprocessing/text_cleaner.py`  
**类**: `TextCleaner`  
**方法**: `clean(text, html, existing_hashes)`

### 2.2 清洗步骤

#### 步骤 1: 质量评分 (Quality Scoring)

```python
quality_score = calculate_quality_score(text, html)
```

**评分维度**:
| 维度 | 权重 | 说明 |
|------|------|------|
| 文本长度 | 动态 | <100 字符×0.5, <500 字符×0.8 |
| 文本密度 | 动态 | text/html 比率，低于阈值降分 |
| 标点符号 | 动态 | 标点比率<1% 或>20% 降分 |
| 停用词 | 动态 | 停用词比率<5% 降分 |

**输出**: `quality_score: float (0.0-1.0)`

---

#### 步骤 2: 语言检测 (Language Detection)

```python
language = detect_language(text)
```

**检测方法**:
1. **首选**: `langdetect` 库 (高精度)
2. **Fallback**: 正则表达式匹配

**支持的语言**:
| 语言 | 代码 | 检测方式 |
|------|------|----------|
| 中文 | zh | CJK 字符范围 |
| 英文 | en | 默认 fallback |
| 日文 | ja | 平假名/片假名 |
| 韩文 | ko | 韩文字符 |
| 阿拉伯文 | ar | 阿拉伯字符范围 |
| 俄文 | ru | 西里尔字母 |

**输出**: `language: str (ISO 语言代码)`

---

#### 步骤 3: SimHash 计算

```python
simhash = compute_simhash(text)
```

**算法**:
1. 分词：提取单词 tokens
2. 哈希：对每个 token 计算 MD5
3. 向量累加：64 位向量累加
4. 二值化：正负转 0/1

**输出**: `simhash: int (64 位指纹)`

---

#### 步骤 4: 重复检测 (Deduplication)

```python
is_duplicate = is_duplicate(text, existing_hashes, threshold=3)
```

**判定规则**:
- 汉明距离 ≤ 3 → 判定为重复
- 无历史 hashes → 不检测

**输出**: `is_duplicate: bool`

---

#### 步骤 5: 噪音过滤 (Noise Removal)

```python
cleaned = remove_noise(text)
```

**过滤的噪音类型**:
| 类型 | 正则模式 | 示例 |
|------|----------|------|
| URL | `https?://\S+` | https://example.com/page |
| WWW 链接 | `www\.\S+` | www.example.com |
| @提及 | `@\w+` | @username |
| #标签 | `#\w+` | #hashtag |
| 全大写单词 | `[A-Z]{2,}` | IMPORTANT |
| 特殊字符 | `[^\w\s.,!?;:()\"'-]` | 各种 emoji、控制字符 |

**输出**: `cleaned_text: str`

---

#### 步骤 6: PII 检测与移除

```python
cleaned, pii_counts = detect_and_remove_pii(cleaned)
```

**检测的 PII 类型**:
| 类型 | 正则模式 | 替换为 |
|------|----------|--------|
| 邮箱 | `[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}` | `[EMAIL]` |
| 电话 (国际) | `(?:\+?\d{1,3}[-.]?)?\(?\d{3}\)?[-.]?\d{3}[-.]?\d{4}` | `[PHONE]` |
| 手机 (中国) | `1[3-9]\d{9}` | `[PHONE_CN]` |
| 身份证 (中国) | `\d{17}[\dXx]` | `[ID_CARD_CN]` |
| 美国社保号 | `\d{3}-\d{2}-\d{4}` | `[SSN]` |
| 银行卡 | `\d{4}[-.]?\d{4}[-.]?\d{4}[-.]?\d{4}` | `[CREDIT_CARD]` |
| IP 地址 | `\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}` | `[IP_ADDRESS]` |
| 护照 | `[A-Z]{1,2}\d{6,9}` | `[PASSPORT]` |

**输出**: 
- `cleaned_text: str` (PII 被替换为 `[TYPE]`)
- `pii_types: Dict[str, int]` (各类 PII 数量)

---

### 2.3 清洗结果数据结构

```python
@dataclass
class CleaningResult:
    text: str              # 原始文本
    quality_score: float   # 质量评分 (0-1)
    language: str          # 语言代码 (zh/en/ja/ko/ar/ru/unknown)
    is_duplicate: bool     # 是否重复
    pii_detected: bool     # 是否检测到 PII
    cleaned_text: str      # 清洗后的文本
    simhash: Optional[int] # 64 位 SimHash 指纹
    pii_types: Dict[str, int]  # PII 类型计数
```

**示例**:
```python
CleaningResult(
    text="张三的邮箱是 zhangsan@example.com，电话 13812345678",
    quality_score=0.85,
    language="zh",
    is_duplicate=False,
    pii_detected=True,
    cleaned_text="张三的邮箱是 [EMAIL]，电话 [PHONE_CN]",
    simhash=12345678901234567890,
    pii_types={"email": 1, "phone_cn": 1}
)
```

---

## 3. Stage 1.6 详解：数据脱敏

### 3.1 执行位置

**文件**: `backend/app/services/desensitization_service.py`  
**类**: `DesensitizationService`  
**方法**: `apply(text)`

### 3.2 脱敏配置

**配置来源**: 数据库表 `desensitization_config`

```python
@dataclass
class DesensitizationConfig:
    kb_id: Optional[str]        # 知识库 ID (None=全局配置)
    level: DesensitizationLevel # 脱敏级别
    custom_rules: List[dict]    # 自定义替换规则
    enable_email_mask: bool     # 邮箱脱敏
    enable_phone_mask: bool     # 手机脱敏
    enable_id_card_mask: bool   # 身份证脱敏
    enable_bank_card_mask: bool # 银行卡脱敏
    enable_address_mask: bool   # 地址脱敏
    enable_name_mask: bool      # 姓名脱敏
```

**脱敏级别**:
| 级别 | 说明 | 适用场景 |
|------|------|----------|
| none | 不脱敏 | 内部可信数据 |
| low | 轻度脱敏 | 保留部分信息 |
| medium | 中度脱敏 | 默认级别 |
| high | 高度脱敏 | 对外公开数据 |
| custom | 自定义规则 | 特殊需求 |

### 3.3 脱敏方法

| 方法 | 说明 | 示例 |
|------|------|------|
| REPLACE | 字符替换 | `13812345678` → `***********` |
| MASK | 掩码 | `13812345678` → `138****5678` |
| HASH | 哈希加密 | `zhangsan` → `a1b2c3d4...` |
| TRUNCATE | 截断 | `北京市海淀区...` → `北京市...` |
| KEEP_FIRST | 保首 | `zhangsan` → `z********` |
| KEEP_LAST | 保尾 | `zhangsan` → `********n` |

### 3.4 自定义替换规则

**格式**:
```json
[
  {"from": "apple", "to": "苹果", "is_enabled": true},
  {"from": "CEO", "to": "首席执行官", "is_enabled": true}
]
```

**处理逻辑**:
- 不区分大小写匹配
- 全局替换

### 3.5 脱敏结果

**输入**: 清洗后的文本 (Stage 1.5 输出)  
**输出**: 脱敏后的文本

**示例**:
```
输入："张三的邮箱是 zhangsan@example.com，电话 13812345678，apple 公司 CEO"

输出："张**的邮箱是 zhang**@example.com，电话 138****5678，苹果公司 首席执行官"
```

---

## 4. 完整数据流示例

### 4.1 输入文档

```
文件：product_manual.pdf
大小：2.5MB
格式：PDF
```

### 4.2 Stage 2: 解析输出

```python
raw_text = """
Apple Inc. 产品手册

联系方式：support@apple.com
客服电话：13812345678

iPhone 15 Pro 采用 A17 Pro 芯片...
"""
```

### 4.3 Stage 1.5: 清洗输出

```python
cleaning_result = CleaningResult(
    text=raw_text,  # 原始文本
    quality_score=0.92,
    language="zh",
    is_duplicate=False,
    pii_detected=True,
    cleaned_text="""
Apple Inc 产品手册

联系方式 [EMAIL]
客服电话 [PHONE_CN]

iPhone 15 Pro 采用 A17 Pro 芯片
""",
    simhash=98765432109876543210,
    pii_types={"email": 1, "phone_cn": 1}
)
```

### 4.4 Stage 1.6: 脱敏输出

```python
desensitized_text = """
苹果公司 产品手册

联系方式 zhang**@example.com
客服电话 138****5678

iPhone 15 Pro 采用 A17 Pro 芯片
"""
# 注：实际脱敏效果取决于配置
# - 邮箱：zhang**@example.com (保留前后)
# - 手机：138****5678 (保留前后)
# - 自定义规则：Apple Inc → 苹果公司
```

### 4.5 Stage 3: 分块输出

```python
chunks = [
    Chunk(
        text="苹果公司 产品手册\n\n联系方式 zhang**@example.com",
        metadata={"page": 1, "content_type": "text"},
        chunk_id="chunk_001",
        start_idx=0,
        end_idx=50,
        token_count=25
    ),
    Chunk(
        text="iPhone 15 Pro 采用 A17 Pro 芯片...",
        metadata={"page": 1, "content_type": "text"},
        chunk_id="chunk_002",
        start_idx=51,
        end_idx=100,
        token_count=30
    ),
]
```

### 4.6 Stage 4: 嵌入输出

```python
embeddings = [
    [0.0123, -0.0456, 0.0789, ...],  # chunk_001 的向量 (1024 维)
    [0.0234, -0.0567, 0.0890, ...],  # chunk_002 的向量
]
```

### 4.7 Stage 5: 入库结果

```python
# Milvus 插入结果
{
    "insert_count": 2,
    "chunk_ids": ["doc123_0", "doc123_1"],
    "collection": "kb_456_collection"
}
```

---

## 5. 清洗流程配置

### 5.1 TextCleaner 配置

```python
config = {
    "min_text_ratio": 0.3,      # 最小文本密度
    "simhash_bits": 64,         # SimHash 位数
    "enable_pii_removal": True, # 启用 PII 移除
    "enable_dedup": True,       # 启用去重
    "quality_threshold": 0.2,   # 质量阈值
}
```

### 5.2 脱敏配置 (按知识库)

```yaml
# 知识库 A (对外公开)
desensitization_config_A:
  level: high
  enable_email_mask: true
  enable_phone_mask: true
  enable_id_card_mask: true
  enable_bank_card_mask: true
  custom_rules:
    - from: "内部"
      to: "受限"

# 知识库 B (内部使用)
desensitization_config_B:
  level: low
  enable_email_mask: false  # 不脱敏
  enable_phone_mask: false
  custom_rules: []
```

---

## 6. 质量监控指标

### 6.1 清洗质量

| 指标 | 计算方式 | 目标值 |
|------|----------|--------|
| 平均质量评分 | `avg(quality_score)` | >0.7 |
| 重复检测率 | `duplicates/total` | <5% |
| PII 检出率 | `docs_with_pii/total` | 取决于数据 |
| 语言识别准确率 | `correct_lang/total` | >95% |

### 6.2 脱敏质量

| 指标 | 计算方式 | 目标值 |
|------|----------|--------|
| PII 脱敏覆盖率 | `masked_pii/total_pii` | 100% |
| 自定义规则应用 | `rules_applied` | 取决于配置 |
| 误脱敏率 | `false_positive/total` | <1% |

---

## 7. 异常处理

### 7.1 清洗异常

| 异常 | 处理方式 |
|------|----------|
| 空文本 | 返回空 CleaningResult |
| 编码错误 | 使用 utf-8 fallback |
| langdetect 失败 | 使用正则 fallback |

### 7.2 脱敏异常

| 异常 | 处理方式 |
|------|----------|
| 配置加载失败 | 使用默认配置 |
| 自定义规则解析失败 | 跳过该规则 |
| 正则编译失败 | 跳过该规则 |

---

## 8. 相关文件索引

| 文件 | 作用 |
|------|------|
| `backend/app/preprocessing/text_cleaner.py` | 清洗核心逻辑 |
| `backend/app/services/desensitization_service.py` | 脱敏核心逻辑 |
| `backend/app/workers/document_pipeline.py` | 处理流程编排 |
| `backend/app/models/desensitization_config.py` | 脱敏配置模型 |

---

**文档维护者**: AI Assistant  
**最后更新**: 2026-07-29
