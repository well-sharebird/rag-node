# RAG 文档处理流水线实现总结

本文档总结了根据设计文档补充的 RAG 系统功能。

## 完整性对比表

| 阶段 | 设计要求 | 实际状态 | 偏差等级 | 补充内容 |
|------|---------|---------|---------|---------|
| Stage 1 源连接 | 7 种连接器 | 7 种已实现 | ✅ 完成 | Confluence/Notion/Git 连接器 |
| Stage 1.5 预处理清洗 | 质量评分 +SimHash+PII+ 语言路由 | 已实现 | ✅ 完成 | text_cleaner.py 集成到流水线 |
| Stage 2 解析提取 | 7 种解析器+OCR+ 布局感知 | 已实现 | ✅ 完成 | OCR(pytesseract/PaddleOCR)+ 跨页表格缝合 |
| Stage 3 智能分块 | 5 种策略 | 已实现 | ✅ 完成 | Token-based/Agentic/Small-to-Big |
| Stage 3.5 文档富化 | NER+ 实体链接 + 关系 + 标签 + 摘要 | 已实现 | ✅ 完成 | document_enrichment.py |
| Stage 4 Embedding | 5 模型池 + 批处理 + 缓存 | 已实现 | ✅ 完成 | 原有实现 |
| Stage 5 多索引写入 | 5 路写入 | 已实现 | ✅ 完成 | multi_index_service.py + RRF 融合 |
| Stage 5.5 摄取质检 | 5 项检查 | 已实现 | ✅ 完成 | ingestion_validator.py |
| 版本管理 | Saga 事务 + 差分 +3 版本 | 已实现 | ✅ 完成 | version_manager.py |

---

## 详细实现说明

### Stage 1 — 连接器实现

**文件**: `backend/app/connectors/`

- **confluence_connector.py**: Atlassian Confluence 页面抓取
- **notion_connector.py**: Notion 工作区页面抓取
- **git_connector.py**: GitHub/GitLab 代码仓库抓取
- **factory.py**: 注册表更新，支持 7 种连接器

```python
CONNECTOR_REGISTRY = {
    "web_page": WebConnector,
    "database": DatabaseConnector,
    "api": APIConnector,
    "mysql": DatabaseConnector,
    "postgresql": DatabaseConnector,
    "confluence": ConfluenceConnector,
    "notion": NotionConnector,
    "git_repo": GitConnector,
}
```

### Stage 1.5 — 预处理与清洗流水线

**文件**: `backend/app/preprocessing/text_cleaner.py`

**功能**:
- 质量评分（文本密度、标点符号、停用词）
- SimHash 64-bit 去重
- PII 检测与脱敏（邮箱/手机/身份证/信用卡）
- 语言检测（langdetect + 正则 fallback）
- 编码检测（chardet）
- 噪音过滤（URL/链接/特殊字符）

**集成点**: `backend/app/workers/document_pipeline.py` 和 `sync_engine.py`

### Stage 2 — OCR 和布局感知解析

**文件**: `backend/app/services/parsing_service.py`

**功能**:
- 7 种基础解析器：PDF/DOCX/XLSX/PPTX/TXT/MD/HTML
- 图片 OCR：JPG/PNG/TIFF/BMP（pytesseract + PaddleOCR）
- 跨页表格缝合：`_stitch_and_format_table()`
- 布局感知：`parse_with_layout()` 集成 LayoutLMv3（可选）
- 编码检测：chardet 集成

**新增依赖**: `pytesseract`, `pdf2image`, `Pillow`

### Stage 3 — 智能分块策略

**文件**: `backend/app/services/chunking_service.py`

**5 种策略**:
1. **fixed**: 基于 token 计数（非字符）
2. **semantic**: 语义边界分隔
3. **recursive**: 层次分隔符（类似 LangChain）
4. **agentic**: LLM 智能切分
5. **small_to_big**: 子块检索 + 父块返回

**Token 估算**: `_count_tokens()` 支持中英文（CJK=1 token, other=4 chars/token）

### Stage 3.5 — 文档富化

**文件**: `backend/app/services/document_enrichment.py`

**功能**:
- **NER 实体抽取**: HanLP(中文)/spaCy(英文)/LLM(自定义)
- **实体链接**: `EntityLinker` 集成知识图谱
- **关系抽取**: `RelationExtractor` 使用 LLM
- **自动标签**: BERTopic / LLMTaggingService
- **文档摘要**: LLMSummarizationService / TextRankSummarizationService

**新增依赖**: `spacy`, `hanlp`, `bertopic`

### Stage 5 — 多索引写入

**文件**: `backend/app/services/multi_index_service.py`

**5 路索引**:
1. **Dense Vector** (Milvus): 已有
2. **Sparse Vector** (BGE-M3): 新增支持
3. **BM25 Full-text** (Elasticsearch): 集成 `elasticsearch_client.py`
4. **Knowledge Graph** (Neo4j): 集成 `neo4j_client.py`
5. **Object Storage** (MinIO): 已有

**混合搜索**: `hybrid_search()` 支持 RRF (Reciprocal Rank Fusion) 融合多路结果

### Stage 5.5 — 摄取质量校验

**文件**: `backend/app/services/ingestion_validator.py`

**5 项检查**:
1. **分块质量**: 空 chunk/过短/过长检测
2. **Embedding 异常**: 零向量/范数异常/方差异常
3. **索引回查**: recall@1 验证
4. **覆盖率**: chunked text vs original
5. **Golden 样本**: 查询测试

**集成点**: `backend/app/workers/document_pipeline.py`

### 版本管理 — Saga 原子事务 + 差分更新

**文件**: `backend/app/services/version_manager.py`

**功能**:
- **Saga 事务**: 11 步流程（验证→锁定→解析→分块→embedding→多索引→提交），失败自动补偿
- **差分更新**: 计算 chunk 差异，只处理新增/删除
- **3 版本回滚**: 保留最近 3 个版本，自动清理过期版本

**Saga 步骤**:
```python
VALIDATE → LOCK_VERSION → PARSE → CHUNK → EMBED → INDEX_DENSE → INDEX_SPARSE → INDEX_BM25 → INDEX_KG → UPDATE_COUNTERS → COMMIT
```

---

## 依赖更新

**pyproject.toml 新增**:
```toml
chardet>=5.2.0          # 编码检测
presidio-analyzer>=2.2.0 # PII 检测
presidio-anonymizer>=2.2.0
langdetect>=1.0.9       # 语言检测
simhash>=2.1.2          # 去重
pytesseract>=0.3.13     # OCR
pdf2image>=1.17.0
Pillow>=10.0.0
spacy>=3.7.0            # NER(英文)
hanlp>=4.0.0            # NER(中文)
bertopic>=0.16.0        # 自动标签
```

---

## 使用示例

### 文档富化
```python
from app.services.document_enrichment import get_document_enrichment_service

service = get_document_enrichment_service(llm_service=llm, kg_service=kg)
result = await service.enrich(document_text)

print(f"Entities: {len(result.entities)}")
print(f"Tags: {result.tags}")
print(f"Summary: {result.summary}")
```

### 多索引写入
```python
from app.services.multi_index_service import get_multi_index_service

service = get_multi_index_service(
    milvus_client=milvus,
    es_client=es,
    neo4j_client=neo4j,
    minio_client=minio,
    config={"enable_sparse": True, "enable_bm25": True, "enable_kg": True}
)

result = await service.write_document(
    doc_id="doc-123",
    kb_id="kb-456",
    collection_name="my_kb",
    doc_name="手册.pdf",
    chunks=chunks,
    dense_embeddings=embeddings,
    original_content=file_bytes,
    entities=entities,
    relations=relations,
)
```

### 版本回滚
```python
from app.services.version_manager import get_version_manager

vm = get_version_manager(db_session)

# 回滚到指定版本
await vm.rollback_to_version(
    doc_id="doc-123",
    target_version_id="doc-123-v2",
    kb_id="kb-456",
    milvus_client=milvus,
)
```

---

## 后续建议

1. **测试覆盖**: 为新服务添加单元测试
2. **性能优化**: 批处理 embedding 和索引写入
3. **监控告警**: 集成 Prometheus 监控各项指标
4. **配置化**: 将策略选择（如分块策略、NER 服务）移到配置表
5. **评估框架**: 建立 Golden 测试集，定期评估检索质量
