# 文档处理流水线 - 完整技术文档

## 概述

本文档详细描述 RAG 系统的文档处理流水线，包括上传、解析、清洗、脱敏、分块、向量化、索引构建等全处理流程，以及流水线追踪机制。

**最后更新时间**: 2026-08-05

## 架构概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           文档处理流水线架构                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  │  上传    │ -> │  解析    │ -> │  清洗    │ -> │  脱敏    │ -> │  分块    │
│  │ Upload   │    │ Parsing  │    │ Cleaning │    │Desensit. │    │ Chunking │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
│       │               │               │               │               │
│       v               v               v               v               v
│  ┌──────────────────────────────────────────────────────────────────────────┐
│  │                        Elasticsearch 追踪存储                             │
│  │                    (Trace Span for each stage)                          │
│  └──────────────────────────────────────────────────────────────────────────┘
│                                                                             │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  │ 向量化   │ -> │  验证    │ -> │  索引    │ -> │  完成    │
│  │Embedding │    │Validation│    │ Indexing │    │Completed │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘
│       │               │               │               │
│       v               v               v               v
│  ┌──────────────────────────────────────────────────────────────────────────┐
│  │                    Milvus 向量数据库 + PostgreSQL 元数据                   │
│  └──────────────────────────────────────────────────────────────────────────┘
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 处理阶段详解

### 阶段 0: 智能标签生成 (Tag Generation) 【新增 - 规划中】

**文件**: `backend/packages/rag/services/tag_generation_service.py`

**功能**: 在文档解析后自动生成智能标签，用于增强检索和分类

**标签类型**:
| 类型 | 说明 | 技术实现 |
|------|------|----------|
| **EXTRACTED** | 提取式标签（关键词） | TF-IDF / TextRank |
| **SEMANTIC** | 语义标签（LLM 生成） | LLM 分析文档主题 |
| **CATEGORY** | 分类标签 | 基于预定义分类树匹配 |
| **ENTITY** | 实体标签 | NER 识别人名/地名/机构等 |

**输出格式**:
```json
{
  "tags": [
    {"name": "机器学习", "type": "extracted", "score": 0.95, "source": "jieba_tfidf"},
    {"name": "向量检索", "type": "semantic", "score": 0.9, "source": "llm_semantic"},
    {"name": "技术/AI", "type": "category", "score": 0.8, "source": "content_match"},
    {"name": "张三", "type": "entity", "score": 0.85, "source": "spacy_PERSON"}
  ]
}
```

---

### 阶段 1: 文档上传 (Upload)

**文件**: `backend/packages/rag/api/documents.py`

**流程**:
1. 接收文件上传（支持拖放/点击选择）
2. 验证文件格式和大小（最大 50MB）
3. 上传到 MinIO 对象存储
4. 在 PostgreSQL 创建文档记录（status=pending）
5. 启动后台异步任务处理

**支持格式**:
- 文档：PDF, DOCX, XLSX, PPTX, TXT, MD, HTML
- 图片：JPG, JPEG, PNG, TIFF, TIF, BMP（OCR 识别）

**API 端点**:
```
POST /api/v1/documents/upload?kb_id={知识库 ID}
POST /api/v1/documents/batch-upload?kb_id={知识库 ID}  # 批量上传
```

**数据库字段**:
```python
Document {
    id: str                    # UUID
    kb_id: str                 # 知识库 ID
    filename: str              # MinIO 存储路径
    original_name: str         # 原始文件名
    format: str                # 文件扩展名
    file_size: int             # 文件大小（字节）
    status: str                # pending/processing/completed/failed
    progress: int              # 0-100 处理进度
    current_stage: str         # 当前处理阶段
    metadata_json: dict        # 追踪元数据（含 trace_id）
    version: int               # 版本号（同名文件自增）
    previous_version_id: str   # 上一版本 ID
    minio_key: str             # MinIO 对象键
    content_types: list[str]   # 内容类型列表 (text/table/image)
    error_message: str         # 错误消息
    chunk_count: int           # 分块数量
    uploaded_at: datetime      # 上传时间
    processed_at: datetime     # 处理完成时间
}
```

---

### 阶段 2: 文档解析 (Parsing)

**文件**: `backend/packages/rag/services/parsing_service.py`

**处理逻辑**:
- **PDF**: 使用 PyMuPDF 提取文本、表格、图片
- **DOCX**: 使用 python-docx 提取段落、表格
- **图片**: OCR 识别（可选）
- **多模态解析**: 分离文本、表格、图片内容类型

**解析模式**:
1. `parse_document()`: 扁平文本解析，返回纯文本
2. `parse_document_structured()`: 结构化解析，返回带内容类型标记的元素列表

**追踪数据**:
```json
{
  "node_type": "parsing",
  "node_name": "parse_document",
  "status": "success",
  "duration_ms": 844,
  "input_data": {
    "args_count": 2,
    "args": ["<binary_content>", "docx"]
  },
  "output_data": {
    "result": "<extracted_text_content>",
    "content_types": ["text", "table", "image"]
  }
}
```

---

### 阶段 3: 文本清洗 (Cleaning)

**文件**: `backend/packages/rag/preprocessing/text_cleaner.py`

**清洗规则**:
1. 移除多余空白字符
2. 标准化换行符
3. 移除特殊字符
4. 语言检测
5. 质量评分

**输出**:
```json
{
  "cleaned_text": "<清洗后文本>",
  "quality_score": 0.95,
  "language": "zh",
  "pii_detected": false
}
```

---

### 阶段 4: 数据脱敏 (Desensitization)

**文件**: `backend/packages/rag/services/desensitization_service.py`

**脱敏级别** (按知识库配置):
- **L1 - 无脱敏**: 不处理
- **L2 - 轻度脱敏**: 手机号、邮箱、身份证
- **L3 - 中度脱敏**: L2 + 人名、地名
- **L4 - 严格脱敏**: L3 + 日期、金额、机构名

**追踪数据**:
```json
{
  "node_type": "desensitization",
  "status": "success",
  "input_data": {"preview": "<原始文本前 200 字符>"},
  "output_data": {"preview": "<脱敏后文本前 200 字符>"}
}
```

---

### 阶段 5: 文本分块 (Chunking)

**文件**: `backend/packages/rag/services/chunking_service.py`

**分块策略** (通过 `FileTypeRouter` 按文件类型自动选择):
- **Semantic**: 语义分块（适合文档、文章）
- **Fixed**: 固定长度（适合技术手册、规范文档）
- **Recursive**: 递归分块（适合长文本、书籍）
- **Table**: 表格专用（每表一块，保持结构完整）

**文件类型路由配置**:
```python
# .md, .txt, .docx → Semantic 分块
# .pdf → Recursive 分块
# .xlsx → Table 分块
```

**配置参数**:
```python
{
    "strategy": "semantic",
    "chunk_size": 512,       # tokens
    "chunk_overlap": 102,    # tokens (约 20%)
    "separators": ["\n\n", "\n", "。", "！", "？"]
}
```

**内容类型处理**:
- 结构化解析后，不同内容类型分别处理
- `text`: 使用路由策略分块
- `table`: 每表格保持独立分块
- `image`: OCR 文本作为独立分块

**追踪数据**:
```json
{
  "node_type": "chunking",
  "node_name": "chunk_text",
  "status": "success",
  "duration_ms": 627,
  "input_data": {
    "args_count": 1,
    "kwargs": {
      "strategy": "semantic",
      "chunk_size": 512,
      "chunk_overlap": 102
    }
  },
  "output_data": {
    "preview": ["Chunk(text='...')", "Chunk(text='...')"],
    "length": 10
  }
}
```

---

### 阶段 5.5: 摄入质量验证 (Validation) 【新增】

**文件**: `backend/packages/rag/services/ingestion_validator.py`

**验证检查项**:
1. 向量维度一致性检查
2. 分块质量评分
3. 嵌入完整性验证
4. 元数据完整性检查

**验证结果**:
- `passed_checks`: 通过的检查数
- `warning_checks`: 警告检查数
- `failed_checks`: 失败检查数

**处理策略**: 验证失败不会中断流程，仅记录警告日志

---

### 阶段 5.6: 智能标签生成 (Tag Generation) 【新增 - 规划中】

**文件**: `backend/packages/rag/services/tag_generation_service.py`

**标签类型**:
| 类型 | 说明 | 技术实现 | 数量 |
|------|------|----------|------|
| **EXTRACTED** | 提取式标签（关键词） | TF-IDF / TextRank | 5-10 |
| **SEMANTIC** | 语义标签（LLM 生成） | LLM 分析文档主题 | 3-5 |
| **CATEGORY** | 分类标签 | 基于预定义分类树匹配 | 1-3 |
| **ENTITY** | 实体标签 | NER 识别人名/地名/机构等 | 5-10 |

**输出格式**:
```json
{
  "tags": [
    {"name": "机器学习", "type": "extracted", "score": 0.95, "source": "jieba_tfidf"},
    {"name": "向量检索", "type": "semantic", "score": 0.9, "source": "llm_semantic"},
    {"name": "技术/AI", "type": "category", "score": 0.8, "source": "content_match"}
  ]
}
```

**标签存储**:
- 存入 `documents.tags` 字段（JSON 数组）
- 同时用于元数据增强文本

---

### 阶段 5.7: 元数据增强文本 (Metadata Enrichment) 【新增 - 规划中】

**目标**: 将文档元数据拼接到 chunk 文本中，使向量包含元数据语义信息

**增强模板**:
```python
enhanced_text = f"""[文档]{doc_name} [分类]{category} [标签]{tags_str} [类型]{content_type}
{original_chunk_text}"""
```

**示例**:
```
原始文本:
"Kubernetes 集群部署需要先配置网络插件 CNI..."

增强后:
"[文档] 产品部署手册 v2.0 [分类]/产品/手册/部署 [标签] Kubernetes，部署，安全 [类型]text
Kubernetes 集群部署需要先配置网络插件 CNI..."
```

**参与向量化的元数据字段**:
| 字段 | 说明 | 示例 |
|------|------|------|
| `doc_name` | 文档名称 | "产品部署手册 v2.0" |
| `category` | 分类路径 | "/产品/手册/部署" |
| `tags` | 智能标签 | "Kubernetes，部署，安全" |
| `content_type` | 内容类型 | "text", "table", "image" |
| `chapter` | 章节标题 | "第三章：网络配置" |

**不参与向量化的字段**:
- `page`: 页码（无语义信息）
- `chunk_index`: 分块序号（无语义信息）
- `start_idx`, `end_idx`: 位置偏移（无语义信息）

**优势**:
1. 检索时自动匹配元数据语义，如查询"Kubernetes 部署文档"可命中
2. 支持自然语言过滤，如"查找所有产品手册"
3. 不改变 Milvus 结构，零迁移成本
4. 向量包含完整上下文，提升检索准确率

---

### 阶段 6: 向量化 (Embedding)

**文件**: `backend/packages/rag/services/embedding_service.py`

**模型配置** (从 Model Gateway 动态获取):
- 优先使用默认 embedding 模型 (`is_default=True`)
- 无默认模型时使用任意启用模型 (`is_enabled=True`)
- 支持多 Provider（OpenAI、Azure、本地模型等）
- 自动降级到备用模型

**模型优先级**:
1. 默认 embedding 模型 (`is_default=True`)
2. 最近更新的启用模型
3. 报错提示用户配置

**处理流程**:
1. 从 `model_configs` 表读取 embedding 模型配置
2. 获取 Provider 配置（base_url, api_key）
3. 批量发送文本到 embedding API（批量大小：10）
4. 接收向量（1024 维）

**追踪数据**:
```json
{
  "node_type": "embedding",
  "node_name": "embed_texts",
  "status": "success",
  "duration_ms": 1561,
  "input_data": {
    "args_count": 2,
    "args": ["<embedding_service>", "[chunk1, chunk2, ...]"]
  },
  "output_data": {
    "preview": ["[0.0077, 0.0068, ...]", "[0.0153, 0.0296, ...]"],
    "length": 10
  }
}
```

---

### 阶段 7: 索引构建 (Indexing)

**文件**: `backend/packages/rag/services/vector_store_service.py`

**向量存储**:
1. 检查 Milvus 集合是否存在（按知识库 `collection_name`）
2. 创建集合（如不存在）
3. 批量插入向量和元数据（批量大小：100）

**错误处理**:
- 向量删除失败时静默处理，不影响主流程

**Milvus 元数据字段** (存储于向量集合):
```python
{
    "chunk_id": str,         # 分块 ID (主键)
    "doc_id": str,           # 文档 ID (用于关联/删除)
    "kb_id": str,            # 知识库 ID (用于检索范围过滤)
    "doc_name": str,         # 文档名 (最大 200 字符)
    "text": str,             # 分块文本 (含元数据增强前缀)
    "page": int,             # 页码 (可选)
    "chapter": str,          # 章节标题 (最大 200 字符)
    "content_type": str,     # 内容类型：text/table/image
    # 注意：向量已包含增强后的元数据语义，无需额外存储 tags
}
```

**PostgreSQL 元数据字段** (存储于 documents 表):
```python
{
    "category": str,         # 分类路径，如 "/产品/手册/部署"
    "tags": list[str],       # 智能标签列表，如 ["Kubernetes", "部署"]
    "content_types": list[str],  # 检测到的内容类型
    "metadata_json": dict,   # 追踪元数据 (trace_id 等)
}
```

**更新统计**:
- 文档 chunk_count
- 知识库 vector_count

---

### 阶段 8: 完成 (Completed)

**最终状态**:
```python
Document {
    status: "completed",
    progress: 100,
    processed_at: datetime.utcnow(),
    chunk_count: 10,
    content_types: ["text", "table", "image"]  # 检测到的内容类型
}
```

**知识库统计更新**:
```python
KnowledgeBase {
    vector_count: int,      # 向量总数（累加）
    document_count: int,    # 文档总数
}
```

---

## 检索增强：元数据过滤与融合

### 已实现的过滤功能

**API 端点**: `POST /api/v1/retrieval/search`

**请求参数**:
```json
{
  "kb_id": "uuid",
  "query": "Kubernetes 部署",
  "top_k": 10,
  "tags": ["Kubernetes", "部署"],      // 按标签过滤
  "doc_ids": ["doc-uuid-1", "doc-uuid-2"],  // 按文档 ID 过滤
  "content_type": "text"               // 按内容类型过滤：text/table/image
}
```

### 元数据过滤检索

**场景**: 用户希望在特定范围内检索，如"查找产品手册中的 Kubernetes 相关内容"

**实现方式**:
```python
# 1. 标签过滤：从 PostgreSQL 查询带标签的文档
tag_docs = await db.execute(
    select(Document.id).where(Document.tags.like("%Kubernetes%"))
)

# 2. 构建 Milvus 过滤表达式
filter_expr = 'doc_id in ["uuid1", "uuid2"] AND content_type == "text"'

# 3. 执行带过滤的向量检索
results = milvus.search(
    collection_name=collection_name,
    data=[query_embedding],
    limit=top_k,
    filter=filter_expr,
    output_fields=["chunk_id", "text", "doc_name", "doc_id", "content_type"],
)
```

**支持的过滤条件**:
| 字段 | 操作符 | 示例 | 说明 |
|------|--------|------|------|
| `kb_id` | == | `kb_id == "uuid"` | 知识库范围 |
| `doc_id` | ==, in | `doc_id in ["id1", "id2"]` | 指定文档 |
| `tags` | LIKE | 查询后转 doc_id | 智能标签过滤 |
| `content_type` | ==, in | `content_type == "text"` | 内容类型 |
| `page` | ==, >, < | `page <= 10` | 页码范围 |

### 元数据增强检索效果

**传统检索** (仅向量相似度):
```
查询："Kubernetes 部署文档"
结果：匹配包含"Kubernetes 部署"语义的文本片段
问题：可能命中非文档类型的 chunk（如会议记录中的提及）
```

**元数据增强检索**:
```
查询："Kubernetes 部署文档"
向量：包含"[文档] 产品部署手册 [分类]/产品/手册 [标签]Kubernetes..."
结果：
  1. 向量本身包含元数据语义，更易匹配相关文档
  2. 可额外添加过滤：content_type == "text"
  3. 可按 doc_name 聚合，避免同一文档多 chunk 重复
```

### 标签过滤检索

**场景**: 用户希望查找特定标签的文档

```python
# 前端传递标签过滤条件
tags_filter = ["Kubernetes", "部署"]

# 后端在 PostgreSQL 中先过滤文档
tagged_docs = await db.execute(
    select(Document.id).where(
        Document.tags.like("%Kubernetes%"),
        Document.tags.like("%部署%")
    )
)
doc_ids = [d.id for d in tagged_docs]

# 在 Milvus 中按 doc_id 过滤
filter_expr = f'doc_id in {doc_ids}'
```

---

## 流水线追踪机制

### 架构设计

**文件**: `backend/packages/core/tracing.py`

**核心组件**:
1. **TraceContext**: 追踪上下文（trace_id, execution_id）
2. **TraceService**: 追踪服务（写入 Elasticsearch）
3. **@traceable 装饰器**: 自动记录函数执行
4. **trace_execution 上下文**: 手动控制追踪范围

### 追踪数据模型

**Elasticsearch 索引**: `execution_traces`

**字段映射**:
```json
{
  "trace_id": "keyword",           # 追踪 ID
  "span_id": "keyword",            # 跨度 ID
  "parent_span_id": "keyword",     # 父跨度 ID
  "execution_type": "keyword",     # document_pipeline | agent_execution
  "execution_id": "keyword",       # 文档 ID 或 Agent ID
  "node_type": "keyword",          # parsing | chunking | embedding | ...
  "node_name": "keyword",          # 函数名
  "status": "keyword",             # success | failed | running
  "started_at": "date",
  "completed_at": "date",
  "duration_ms": "integer",
  "input_data": "object",          # 输入数据摘要
  "output_data": "object",         # 输出数据摘要
  "error_info": "object"           # 错误信息
}
```

### 使用示例

**装饰器方式**:
```python
@traceable(node_type='parsing', node_name='parse_document')
async def parse_document(content: bytes, format: str) -> str:
    ...
```

**上下文方式**:
```python
async with trace_execution(
    execution_type="document_pipeline",
    execution_id=doc_id,
) as trace_ctx:
    await process_document(doc_id)
```

---

## 前端实现

### 组件结构

```
packages/rag/src/components/
├── DocumentPipelineTracing.tsx   # 流水线追踪主组件
├── PipelineStageCard.tsx         # 单个阶段卡片
├── DocumentDetailPanel.tsx       # 文档详情侧边栏
└── DocumentsView.tsx             # 文档列表（含入口按钮）
```

### API 端点

**获取流水线详情**:
```
GET /api/v1/documents/{doc_id}/pipeline
```

**响应结构**:
```json
{
  "document_id": "uuid",
  "stages": [
    {
      "stage": "parsing",
      "label": "Parsing",
      "status": "completed",
      "duration_ms": 844,
      "input_summary": {
        "preview": "<输入预览>",
        "count": 2,
        "size": null
      },
      "output_summary": {
        "preview": "<输出预览>",
        "count": 10,
        "size": null
      },
      "error": null,
      "span_id": "trace_id-0001"
    }
  ],
  "total_duration_ms": 3032,
  "status": "completed"
}
```

### 使用入口

1. 进入 **知识库** → 选择任一知识库
2. 在文档列表中找到目标文档
3. 点击操作列的 **紫色"流水线"按钮**（带有 Activity 图标 📊）
4. 弹窗显示完整处理流程

---

## 数据库迁移

### metadata_json 字段

**迁移文件**: `backend/alembic/versions/011_add_metadata_json_to_documents.py`

**SQL**:
```sql
ALTER TABLE documents ADD COLUMN metadata_json VARCHAR(2000) NULL;
```

**用途**: 存储追踪元数据，主要是 `trace_id`

**示例**:
```json
{
  "trace_id": "397c4ff0-e591-4b4b-912a-8bfd430cc2ab"
}
```

---

## 错误处理

### 失败重试

**单个文档重试**:
```
POST /api/v1/documents/{doc_id}/reprocess?force=true
```
- `force=true`: 强制重新处理已完成文档（例如修改分块策略后）
- `force=false` (默认): 仅允许失败/ pending 状态的文档重试

**批量重试** (仅失败文档):
```
POST /api/v1/documents/batch-reprocess?kb_id={kb_id}&failed_only=true
POST /api/v1/documents/batch-reprocess?kb_id={kb_id}&doc_ids=[id1,id2]
```
- `failed_only=true`: 仅重试失败文档
- `doc_ids`: 指定文档 ID 列表

### 错误状态流转

```
pending -> processing -> failed
                         ↓
                    可重新触发 reprocess
                         
正常流程:
pending -> processing -> completed
```

### 版本控制

同名文档上传时自动版本递增:
- `version`: 版本号（从 1 开始递增）
- `previous_version_id`: 指向上一版本 ID

**获取版本历史**:
```
GET /api/v1/documents/{doc_id}/versions
```

---

## 性能优化

### 1. 批量处理

- Embedding: 批量发送（默认 10 个/批）
- 向量插入: 批量 INSERT（100 个/批）

### 2. 异步处理

- 上传后立即返回，后台异步处理
- 前端轮询进度接口：`GET /api/v1/documents/{doc_id}/progress`

### 3. 进度追踪

```python
PROCESS_STAGES = {
    "parsing": 10,
    "cleaning": 20,
    "desensitization": 30,
    "chunking": 50,
    "embedding": 70,
    "validation": 85,
    "indexing": 95,
    "completed": 100,
}
```

### 4. MinIO 上传重试

```python
# 指数退避：1s, 2s, 4s
# 触发条件：SlowDown 或 timeout 错误
# 最大重试次数：3 次
```

---

## 监控与调试

### 日志关键字

```bash
# 处理开始
"Processing document | doc_id=xxx"

# 各阶段完成
"Document cleaned | id=xxx quality=0.95"
"Document chunked | doc_id=xxx chunks=10"
"Document embedded | doc_id=xxx vectors=10"

# 处理完成
"Document processing completed | doc_id=xxx chunks=10"
```

### Elasticsearch 查询

```bash
# 查询某文档的所有追踪
GET execution_traces/_search
{
  "query": {
    "term": {
      "trace_id": "397c4ff0-e591-4b4b-912a-8bfd430cc2ab"
    }
  },
  "sort": [{"started_at": "asc"}]
}
```

---

## 常见问题

### Q1: 流水线显示为空？

**原因**: 
- 文档上传时未启用追踪功能（旧文档）
- Elasticsearch 服务不可用

**解决**: 重新上传文档

### Q2: 输入输出数据显示二进制？

**原因**: 已修复，需重启后端服务

### Q3: Milvus 删除向量失败？

**原因**: Milvus QueryNode 状态异常（getrandom 错误）

**解决**: 重启 Milvus 服务
```bash
docker restart milvus-standalone
```

---

## 附录：处理阶段定义

```python
PROCESS_STAGES = {
    "parsing": 10,         # 文档解析完成
    "cleaning": 20,        # 文本清洗完成
    "desensitization": 30, # 数据脱敏完成
    "chunking": 50,        # 文本分块完成
    "embedding": 70,       # 向量化完成
    "validation": 85,      # 质量验证完成
    "indexing": 95,        # 索引构建完成
    "completed": 100,      # 全部完成
}
```

---

## 附录：Embedding 模型解析逻辑

**优先级顺序**:

1. **默认模型** (`is_default=True, is_enabled=True`)
   - 从 `model_configs` 表查询
   - 推荐的生产配置方式

2. **任意启用模型** (`is_enabled=True`)
   - 按 `updated_at` 降序取最新
   - 自动设置为默认模型

3. **错误提示**
   - 无可用模型时报错
   - 提示用户前往模型管理配置

**模型参数解析**:
```python
{
    "provider": str,        # 提供商类型 (openai/azure/local)
    "model_name": str,      # 模型 ID (e.g., text-embedding-3-small)
    "api_url": str,         # API 基础地址
    "api_key": str,         # API 密钥
    "dim": int,             # 向量维度 (默认 1024)
}
```

---

## 相关文件索引

### 核心处理

| 组件 | 文件路径 |
|------|----------|
| API 路由 | `backend/packages/rag/api/documents.py` |
| 流水线 Worker | `backend/packages/rag/workers/document_pipeline.py` |
| 文档服务 | `backend/packages/rag/services/document_service.py` |
| 解析服务 | `backend/packages/rag/services/parsing_service.py` |
| 分块服务 | `backend/packages/rag/services/chunking_service.py` |
| 嵌入服务 | `backend/packages/rag/services/embedding_service.py` |
| 向量存储 | `backend/packages/rag/services/vector_store_service.py` |
| 文本清洗 | `backend/packages/rag/preprocessing/text_cleaner.py` |
| 脱敏服务 | `backend/packages/rag/services/desensitization_service.py` |
| 质量验证 | `backend/packages/rag/services/ingestion_validator.py` |
| 文件路由 | `backend/packages/rag/services/file_type_router.py` |

### 追踪与监控

| 组件 | 文件路径 |
|------|----------|
| 追踪服务 | `backend/packages/agent/services/trace_service.py` |
| 追踪装饰器 | `backend/packages/core/tracing.py` |
| ES 客户端 | `backend/packages/core/infra/es_client.py` |

### 前端组件

| 组件 | 文件路径 |
|------|----------|
| 流水线追踪 | `packages/rag/src/components/DocumentPipelineTracing.tsx` |
| 阶段卡片 | `packages/rag/src/components/PipelineStageCard.tsx` |
| 文档详情 | `packages/rag/src/components/DocumentDetailPanel.tsx` |
| 文档列表 | `packages/rag/src/components/DocumentsView.tsx` |

### 数据模型

| 组件 | 文件路径 |
|------|----------|
| 文档模型 | `backend/packages/rag/models/document.py` |
| 知识库模型 | `backend/packages/rag/models/knowledge_base.py` |
| Schema | `backend/packages/rag/schemas/document.py` |
