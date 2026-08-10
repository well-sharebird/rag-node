# 文档标签功能使用指南

**更新日期**: 2026-08-05

## 功能概述

RAG 系统现在支持智能标签生成和手动管理，帮助用户更好地组织和检索文档。

---

## 标签来源

### 1. 智能标签（自动生成）

文档处理时自动生成 4 种类型的标签：

| 类型 | 说明 | 技术实现 | 示例 |
|------|------|----------|------|
| **提取式** | 从文档内容提取关键词 | TF-IDF / TextRank | "Kubernetes", "部署", "CNI" |
| **语义式** | LLM 分析文档主题生成 | LLM 生成 | "容器编排", "云原生" |
| **分类式** | 基于预定义分类树 | 分类匹配 | "技术/AI", "产品/手册" |
| **实体式** | NER 识别命名实体 | spaCy NER | "张三", "北京", "阿里云" |

### 2. 手动标签（用户添加）

用户可以通过前端界面手动添加/删除标签。

---

## 前端使用

### 1. 文档列表视图

**位置**: 知识库 → 文档列表

**标签列显示**:
- 最多显示前 5 个标签（紫色 Badge）
- 超过 5 个显示 `+N` 计数
- 点击标签图标可编辑

```
┌────────────────────────────────────────────────────┐
│ 文档名称    知识库    分类    标签                 │
├────────────────────────────────────────────────────┤
│ 部署手册    产品库    /产品   [K8s] [部署] [运维] ✏️│
│ API 文档     技术库    /技术   [API] [+2]          ✏️│
└────────────────────────────────────────────────────┘
```

### 2. 文档详情面板

**位置**: 点击文档行 → 详情侧边栏

**展示内容**:
- 分类路径（带图标）
- 智能标签列表（可编辑）
- 内容类型（text/table/image）

**编辑标签**:
1. 点击标题旁的 ✏️ 编辑图标
2. 输入标签名称，按回车添加
3. 点击标签上的 × 删除
4. 点击「保存」提交

```
┌─────────────────────────────────┐
│ 分类和标签           [✏️]      │
├─────────────────────────────────┤
│ 📁 /产品/手册/部署              │
│                                 │
│ ┌─────────────────────────┐     │
│ │ 输入标签后按回车添加 [+] │     │
│ └─────────────────────────┘     │
│                                 │
│ ┌──────┐ ┌──────┐ ┌──────┐     │
│ │K8s ×│ │部署 ×│ │安全 ×│     │
│ └──────┘ └──────┘ └──────┘     │
│                                 │
│ [💾 保存]  [取消]               │
└─────────────────────────────────┘
```

### 3. 内容类型显示

处理完成后，显示文档包含的内容类型：

```
┌─────────────────────────────────┐
│ 内容类型                        │
├─────────────────────────────────┤
│ 📄 text    📊 table    🖼️ image │
└─────────────────────────────────┘
```

---

## API 使用

### 获取文档列表（含标签）

```bash
GET /api/v1/documents?kb_id={kb_id}
```

响应:
```json
{
  "items": [
    {
      "id": "uuid",
      "name": "部署手册.pdf",
      "category": "/产品/手册/部署",
      "tags": ["Kubernetes", "部署", "运维"],
      "content_types": ["text", "table"],
      "status": "completed"
    }
  ]
}
```

### 更新文档标签

```bash
PUT /api/v1/documents/{doc_id}
Content-Type: application/json

{
  "tags": ["Kubernetes", "部署", "运维", "生产环境"]
}
```

### 按标签过滤检索

```bash
POST /api/v1/retrieval/search
Content-Type: application/json

{
  "kb_id": "uuid",
  "query": "Kubernetes 配置",
  "tags": ["Kubernetes", "部署"],
  "top_k": 10
}
```

---

## 后端实现

### 标签生成服务

**文件**: `backend/packages/rag/services/tag_generation_service.py`

```python
from packages.rag.services.tag_generation_service import get_tag_generation_service

tag_service = get_tag_generation_service(llm_service)
tags = await tag_service.generate_tags(
    text=full_document_text,
    doc_name="产品部署手册",
    category="/产品/手册/部署",
    top_k=10,
)
```

### 处理流水线集成

**文件**: `backend/packages/rag/workers/document_pipeline.py`

处理阶段：
```
解析 → 清洗 → 脱敏 → 分块 → 标签生成 → 元数据增强 → 向量化
                    ↓                        ↓
              4 种标签类型            前缀拼接到 chunk
```

### 元数据增强

每个 chunk 的文本前自动添加元数据前缀：

```python
metadata_prefix = f"[文档]{doc_name} [分类]{category} [标签]{tags_str}\n"
# 示例："[文档] 产品部署手册 [分类]/产品/手册/部署 [标签] Kubernetes，部署，安全\n"
```

---

## 标签最佳实践

### 1. 标签命名规范

✅ 推荐:
- 简洁明确：`Kubernetes`, `部署`, `运维`
- 使用行业术语：`CNI`, `CI/CD`, `DevOps`
- 分层标签：`L1/安全`, `L2/网络`

❌ 避免:
- 过长标签：`这是一个非常长的标签名称`
- 模糊标签：`重要`, `参考`, `文档`
- 特殊字符：`标签@#$`

### 2. 标签数量

- 智能生成：5-10 个（自动去重）
- 手动添加：建议 3-8 个
- 过多标签会降低检索精度

### 3. 标签维护

- 定期审查低频标签
- 合并同义标签（如 `K8s` 和 `Kubernetes`）
- 删除过时标签

---

## 故障排查

### 标签不显示

**原因**: 文档处理时标签生成失败

**解决**:
1. 检查后端日志中是否有 `Tag generation failed` 警告
2. 确认 `jieba` 库已安装（关键词提取依赖）
3. 手动添加标签

### 标签编辑保存失败

**原因**: API 调用失败或网络问题

**解决**:
1. 打开浏览器开发者工具查看网络请求
2. 检查 `PUT /api/v1/documents/{doc_id}` 是否返回 200
3. 刷新页面重试

### 智能标签质量差

**原因**: 文档内容太短或格式问题

**解决**:
1. 确保文档有足够文本内容（>500 字）
2. 手动添加补充标签
3. 考虑调整标签生成策略

---

## 相关文件

- 标签生成服务：`backend/packages/rag/services/tag_generation_service.py`
- 文档流水线：`backend/packages/rag/workers/document_pipeline.py`
- 前端列表：`packages/rag/src/components/DocumentsView.tsx`
- 前端详情：`packages/rag/src/components/DocumentDetailPanel.tsx`
