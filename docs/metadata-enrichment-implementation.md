# 元数据增强检索实现总结

**更新日期**: 2026-08-05

## 概述

本次优化实现了文档处理流水线的元数据增强和智能标签生成，以及基于元数据的检索过滤功能，显著提升检索准确率和范围。

---

## 核心改进

### 1. 智能标签生成服务

**文件**: `backend/packages/rag/services/tag_generation_service.py`

支持 4 种标签类型：

| 类型 | 说明 | 技术实现 | 数量 |
|------|------|----------|------|
| **EXTRACTED** | 提取式标签 | TF-IDF / TextRank (jieba) | 5-10 |
| **SEMANTIC** | 语义标签 | LLM 分析文档主题 | 3-5 |
| **CATEGORY** | 分类标签 | 预定义分类树匹配 | 1-3 |
| **ENTITY** | 实体标签 | NER 识别 (spaCy) | 5-10 |

**使用示例**:
```python
from packages.rag.services.tag_generation_service import get_tag_generation_service

tag_service = get_tag_generation_service(llm_service)
tags = await tag_service.generate_tags(
    text=full_document_text,
    doc_name="产品部署手册",
    category="/产品/手册/部署",
    top_k=10,
)
# 输出：[Tag(name="Kubernetes", type="extracted", score=0.95), ...]
```

---

### 2. 元数据增强文本

**位置**: `backend/packages/rag/workers/document_pipeline.py`

在分块后、向量化前，将元数据拼接到每个 chunk 文本中：

```python
# 增强模板
metadata_prefix = f"[文档]{doc.original_name} [分类]{doc.category or '未分类'} [标签]{tags_str}\n"

# 应用到每个 chunk
for chunk in all_chunks:
    chunk.text = metadata_prefix + chunk.text
```

**增强后的文本示例**:
```
[文档] 产品部署手册 v2.0 [分类]/产品/手册/部署 [标签] Kubernetes，部署，安全
Kubernetes 集群部署需要先配置网络插件 CNI，推荐使用 Calico 或 Flannel...
```

**优势**:
1. 向量包含元数据语义，检索时自动匹配
2. 查询"产品手册"可命中相关文档
3. 不改变 Milvus 结构，零迁移成本

---

### 3. 检索过滤功能

**文件**: `backend/packages/rag/services/retrieval_service.py`

**新增请求参数** (`SearchRequest`):
```python
class SearchRequest(BaseModel):
    kb_id: str
    query: str
    top_k: int = 5
    tags: list[str] | None = None           # 按标签过滤
    doc_ids: list[str] | None = None        # 按文档 ID 过滤
    content_type: str | None = None         # 按内容类型过滤
    enable_rerank: bool = False
    enable_multimodal: bool = False
```

**过滤逻辑**:
```python
# 1. 标签过滤：查询 PostgreSQL 获取匹配文档
tag_docs = await db.execute(
    select(Document.id).where(Document.tags.like("%Kubernetes%"))
)

# 2. 构建 Milvus 过滤表达式
filter_expr = 'doc_id in ["uuid1", "uuid2"] AND content_type == "text"'

# 3. 执行带过滤的检索
hits = search_vectors(
    milvus, kb.collection_name, query_embedding,
    top_k=top_k,
    filter=filter_expr,
)
```

---

### 4. 处理流水线阶段更新

**文件**: `backend/packages/rag/workers/document_pipeline.py`

**新增阶段**:
```python
PROCESS_STAGES = {
    "parsing": 10,
    "cleaning": 20,
    "desensitization": 30,
    "chunking": 50,
    "tag_generation": 60,       # 智能标签生成
    "metadata_enrichment": 65,  # 元数据增强文本
    "embedding": 70,
    "validation": 85,
    "indexing": 95,
    "completed": 100,
}
```

---

## 修改的文件列表

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `tag_generation_service.py` | 新增 | 智能标签生成服务 |
| `document_pipeline.py` | 修改 | 集成标签生成和元数据增强 |
| `retrieval_service.py` | 修改 | 支持标签/文档 ID/内容类型过滤 |
| `vector_store_service.py` | 修改 | search_vectors 支持自定义 filter |
| `retrieval.py` (Schema) | 修改 | SearchRequest 新增过滤字段 |
| `document-processing-pipeline.md` | 修改 | 文档更新 |

---

## 使用示例

### 1. 上传文档（自动触发标签生成和元数据增强）

```bash
curl -X POST "http://localhost:8000/api/v1/documents/upload?kb_id=uuid" \
  -F "file=@manual.pdf"
```

### 2. 按标签过滤检索

```bash
curl -X POST "http://localhost:8000/api/v1/retrieval/search" \
  -H "Content-Type: application/json" \
  -d '{
    "kb_id": "uuid",
    "query": "Kubernetes 部署",
    "tags": ["Kubernetes", "部署"],
    "top_k": 10
  }'
```

### 3. 按内容类型过滤检索

```bash
curl -X POST "http://localhost:8000/api/v1/retrieval/search" \
  -H "Content-Type: application/json" \
  -d '{
    "kb_id": "uuid",
    "query": "配置表格",
    "content_type": "table",
    "top_k": 5
  }'
```

### 4. 手动更新文档标签

```bash
curl -X PUT "http://localhost:8000/api/v1/documents/{doc_id}" \
  -H "Content-Type: application/json" \
  -d '{
    "tags": ["Kubernetes", "部署", "运维", "生产环境"]
  }'
```

### 5. 获取文档详情（含标签）

```bash
curl "http://localhost:8000/api/v1/documents/{doc_id}"
```

响应:
```json
{
  "id": "uuid",
  "name": "产品部署手册.pdf",
  "category": "/产品/手册/部署",
  "tags": ["Kubernetes", "部署", "安全", "生产环境"],
  "chunk_count": 42,
  "status": "completed"
}
```

---

## 检索效果对比

### 优化前
```
查询："Kubernetes 部署文档"
问题：
- 仅匹配文本语义，可能命中非文档类型
- 无法按标签/分类过滤
- 相似内容不同来源难以区分
```

### 优化后
```
查询："Kubernetes 部署文档" + tags=["部署"]
优势:
- 向量包含元数据语义："[文档] 产品部署手册 [标签] Kubernetes，部署..."
- 支持标签过滤，精确缩小范围
- 支持内容类型过滤（text/table/image）
- 可按文档 ID 精确过滤
```

---

## 已实现的前端功能

### 1. 文档详情面板展示标签

**组件**: `packages/rag/src/components/DocumentDetailPanel.tsx`

- 展示文档基本信息、分类、标签
- 标签以 Badge 形式展示

### 2. 手动编辑标签

**功能**:
- 点击编辑按钮进入编辑模式
- 输入新标签后按回车添加
- 点击标签上的 X 删除标签
- 保存按钮提交到后端

**UI 交互**:
```
┌─────────────────────────────────┐
│ 分类和标签           [编辑图标] │
├─────────────────────────────────┤
│ 📁 /产品/手册/部署              │
│                                 │
│ 输入标签后按回车添加  [+] 添加  │
│ ┌─────┐ ┌─────┐ ┌─────┐        │
│ │K8s ×│ │部署 ×│ │安全 ×│       │
│ └─────┘ └─────┘ └─────┘        │
│                                 │
│ [保存] [取消]                   │
└─────────────────────────────────┘
```

---

## 下一步优化建议

### 1. 分类体系管理 UI
- 提供可视化分类树配置
- 支持动态添加/修改分类

### 2. 标签质量评估
- 记录标签命中率（检索时标签的使用频率）
- 定期清理低质量标签

### 3. 实体识别优化
- 集成专业 NER 模型（HanLP、LTP）
- 支持自定义实体类型

### 4. 混合检索增强
- 标签倒排索引 + 向量检索融合
- 使用 RRF（Reciprocal Rank Fusion）融合多路结果

---

## 测试建议

### 1. 标签生成测试
```python
# 测试文档
text = "Kubernetes 集群部署指南..."
tags = await tag_service.generate_tags(text, top_k=10)
assert len(tags) >= 5
assert any("Kubernetes" in t.name for t in tags)
```

### 2. 检索过滤测试
```python
# 测试标签过滤
response = await search_chunks(db, redis, milvus, SearchRequest(
    kb_id="uuid",
    query="部署",
    tags=["Kubernetes"],
    top_k=10,
))
# 验证结果都包含指定标签
```

---

## 相关文档

- 完整流水线文档：`docs/document-processing-pipeline.md`
- 标签生成服务：`backend/packages/rag/services/tag_generation_service.py`
- 检索服务：`backend/packages/rag/services/retrieval_service.py`
