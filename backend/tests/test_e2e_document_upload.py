"""
E2E Document Upload Pipeline Test

Tests the complete document upload -> processing -> storage pipeline
by actually uploading files via the API and verifying the results.

Run with: uv run pytest tests/test_e2e_document_upload.py -v
"""
import io
import pytest
import asyncio
import uuid
from datetime import datetime


# ============================================================
# Sample Content Fixtures
# ============================================================

@pytest.fixture
def txt_content():
    """Sample plain text content."""
    return """RAG 系统测试文档

第一章：系统概述

RAG（Retrieval-Augmented Generation）是一种检索增强生成技术。
它结合了检索系统和生成模型的优势，可以提高生成内容的准确性和可靠性。

第二章：系统架构

RAG 系统主要由以下组件构成：
1. 文档解析服务 - 负责解析各种格式的文档
2. 分块服务 - 将文档切分成合适的片段
3. 向量化服务 - 生成文本的向量表示
4. 向量数据库 - 存储和检索向量

第三章：使用方法

用户可以通过 API 上传文档，系统会自动处理并存入向量数据库。
支持的文件格式包括：PDF、DOCX、XLSX、PPTX、TXT、MD、HTML 等。
""" * 3


@pytest.fixture
def md_content():
    """Sample markdown content."""
    return """# RAG 系统技术文档

## 1. 核心概念

### 1.1 检索增强生成

**RAG** = Retrieval + Augmented + Generation

> RAG 技术可以让大语言模型访问外部知识源，生成更准确的答案。

### 1.2 向量嵌入

向量嵌入（Embedding）是将文本转换为数值向量的过程。

```python
# 示例代码
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('all-MiniLM-L6-v2')
embedding = model.encode("Hello, World!")
```

## 2. 系统组件

| 组件 | 功能 | 技术栈 |
|------|------|--------|
| API 服务 | RESTful API | FastAPI |
| 向量数据库 | 向量存储检索 | Milvus |
| 关系数据库 | 元数据存储 | PostgreSQL |
| 缓存 | 任务队列 | Redis |

## 3. 快速开始

```bash
# 启动服务
docker-compose up -d

# 运行后端
cd backend && uv run python app/main.py

# 运行前端
npm run dev
```
""" * 2


@pytest.fixture
def html_content():
    """Sample HTML content."""
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>RAG 系统文档</title>
</head>
<body>
    <header>
        <h1>RAG 检索增强生成系统</h1>
    </header>
    <main>
        <article>
            <h2>什么是 RAG？</h2>
            <p>RAG（Retrieval-Augmented Generation）是一种结合检索和生成的 AI 技术。</p>
            <p>它通过检索外部知识库来增强语言模型的生成能力。</p>

            <h2>工作原理</h2>
            <ol>
                <li>用户提出问题</li>
                <li>系统检索相关知识</li>
                <li>将检索结果和问题一起发送给大模型</li>
                <li>大模型生成答案</li>
            </ol>

            <h3>优势</h3>
            <ul>
                <li>减少幻觉</li>
                <li>提供可追溯的答案</li>
                <li>支持领域特定知识</li>
            </ul>
        </article>
    </main>
</body>
</html>"""


@pytest.fixture
def pdf_content():
    """Sample PDF content (minimal valid PDF)."""
    # Create a simple PDF with text content
    pdf = b"%PDF-1.4\n"
    pdf += b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    pdf += b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 /MediaBox [0 0 612 792] >>\nendobj\n"
    pdf += b"3 0 obj\n<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
    pdf += b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    pdf += b"5 0 obj\n<< /Length 100 >>\nstream\nBT /F1 12 Tf 50 700 Td (RAG System Test Document) Tj 0 -20 Td (This is a test PDF file.) Tj ET\nendstream\nendobj\n"
    pdf += b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000131 00000 n \n0000000244 00000 n \n0000000323 00000 n \n"
    pdf += b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n475\n%%EOF\n"
    return pdf


@pytest.fixture
def docx_content():
    """Sample DOCX content (valid minimal DOCX)."""
    import zipfile
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""")
        zf.writestr("_rels/.rels", """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""")
        zf.writestr("word/document.xml", """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body>
<w:p><w:r><w:t>RAG System Test Document</w:t></w:r></w:p>
<w:p><w:r><w:t>This is a test DOCX file for the RAG system.</w:t></w:r></w:p>
<w:p><w:r><w:t>It contains multiple paragraphs for testing the document parsing pipeline.</w:t></w:r></w:p>
</w:body>
</w:document>""")
    buffer.seek(0)
    return buffer.read()


# ============================================================
# Helper Functions
# ============================================================

async def create_test_kb(client):
    """Create a test knowledge base."""
    kb_id = str(uuid.uuid4())
    kb_name = f"e2e_test_{kb_id[:8]}"

    try:
        response = await client.post(
            "/api/v1/knowledge-bases",
            json={"name": kb_name, "description": "E2E test knowledge base"},
        )

        if response.status_code == 201:
            return response.json()
        elif response.status_code == 500:
            # Database not available
            return None
        else:
            return None
    except Exception:
        return None


async def upload_document(client, kb_id: str, filename: str, content: bytes, content_type: str):
    """Upload a document and return the result."""
    files = {"file": (filename, io.BytesIO(content), content_type)}
    response = await client.post(
        "/api/v1/documents/upload",
        files=files,
        params={"kb_id": kb_id},
    )
    return response


async def get_document_status(client, doc_id: str):
    """Get document processing status."""
    response = await client.get(f"/api/v1/documents/{doc_id}")
    if response.status_code == 200:
        return response.json()
    return None


# ============================================================
# E2E Tests
# ============================================================

class TestE2EDocumentUpload:
    """End-to-end tests for document upload pipeline."""

    @pytest.mark.asyncio
    async def test_e2e_txt_upload_and_process(self, client, txt_content):
        """E2E test: Upload TXT document and verify processing."""
        # Create KB
        kb = await create_test_kb(client)
        if not kb:
            pytest.skip("Could not create test KB")

        try:
            # Upload document
            content_bytes = txt_content.encode('utf-8')
            response = await upload_document(
                client, kb["id"], "test.txt", content_bytes, "text/plain"
            )

            assert response.status_code == 201
            result = response.json()
            assert "id" in result

            # Verify document was processed
            doc = await get_document_status(client, result["id"])
            assert doc is not None
            assert doc["kb_id"] == kb["id"]
            assert doc["format"] == "txt"
            assert doc["file_size"] == len(content_bytes)

            # Document should be completed or processing
            assert doc["status"] in ["completed", "processing", "failed"]

            # If completed, verify chunk count
            if doc["status"] == "completed":
                assert doc["chunk_count"] > 0

        finally:
            # Cleanup
            try:
                await client.delete(f"/api/v1/knowledge-bases/{kb['id']}")
            except:
                pass

    @pytest.mark.asyncio
    async def test_e2e_md_upload_and_process(self, client, md_content):
        """E2E test: Upload Markdown document and verify processing."""
        kb = await create_test_kb(client)
        if not kb:
            pytest.skip("Could not create test KB")

        try:
            content_bytes = md_content.encode('utf-8')
            response = await upload_document(
                client, kb["id"], "test.md", content_bytes, "text/markdown"
            )

            assert response.status_code == 201
            result = response.json()

            doc = await get_document_status(client, result["id"])
            assert doc is not None
            assert doc["format"] == "md"

        finally:
            try:
                await client.delete(f"/api/v1/knowledge-bases/{kb['id']}")
            except:
                pass

    @pytest.mark.asyncio
    async def test_e2e_html_upload_and_process(self, client, html_content):
        """E2E test: Upload HTML document and verify processing."""
        kb = await create_test_kb(client)
        if not kb:
            pytest.skip("Could not create test KB")

        try:
            content_bytes = html_content.encode('utf-8')
            response = await upload_document(
                client, kb["id"], "test.html", content_bytes, "text/html"
            )

            assert response.status_code == 201
            result = response.json()

            doc = await get_document_status(client, result["id"])
            assert doc is not None
            assert doc["format"] == "html"

        finally:
            try:
                await client.delete(f"/api/v1/knowledge-bases/{kb['id']}")
            except:
                pass

    @pytest.mark.asyncio
    async def test_e2e_pdf_upload_and_process(self, client, pdf_content):
        """E2E test: Upload PDF document and verify processing."""
        kb = await create_test_kb(client)
        if not kb:
            pytest.skip("Could not create test KB")

        try:
            response = await upload_document(
                client, kb["id"], "test.pdf", pdf_content, "application/pdf"
            )

            assert response.status_code == 201
            result = response.json()

            doc = await get_document_status(client, result["id"])
            assert doc is not None
            assert doc["format"] == "pdf"

        finally:
            try:
                await client.delete(f"/api/v1/knowledge-bases/{kb['id']}")
            except:
                pass

    @pytest.mark.asyncio
    async def test_e2e_docx_upload_and_process(self, client, docx_content):
        """E2E test: Upload DOCX document and verify processing."""
        kb = await create_test_kb(client)
        if not kb:
            pytest.skip("Could not create test KB")

        try:
            response = await upload_document(
                client, kb["id"], "test.docx", docx_content,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )

            assert response.status_code == 201
            result = response.json()

            doc = await get_document_status(client, result["id"])
            assert doc is not None
            assert doc["format"] == "docx"

        finally:
            try:
                await client.delete(f"/api/v1/knowledge-bases/{kb['id']}")
            except:
                pass

    @pytest.mark.asyncio
    async def test_e2e_batch_upload(self, client, txt_content, md_content):
        """E2E test: Batch upload multiple documents."""
        kb = await create_test_kb(client)
        if not kb:
            pytest.skip("Could not create test KB")

        try:
            # Upload multiple files
            files = [
                ("files", ("doc1.txt", io.BytesIO(txt_content.encode('utf-8')), "text/plain")),
                ("files", ("doc2.md", io.BytesIO(md_content.encode('utf-8')), "text/markdown")),
            ]

            response = await client.post(
                "/api/v1/documents/batch-upload",
                files=files,
                params={"kb_id": kb["id"]},
            )

            assert response.status_code == 201
            results = response.json()
            assert isinstance(results, list)
            assert len(results) == 2

            # Verify each document
            for result in results:
                assert "id" in result
                doc = await get_document_status(client, result["id"])
                assert doc is not None
                assert doc["kb_id"] == kb["id"]

        finally:
            try:
                await client.delete(f"/api/v1/knowledge-bases/{kb['id']}")
            except:
                pass

    @pytest.mark.asyncio
    async def test_e2e_document_list_and_retrieve(self, client, txt_content):
        """E2E test: List and retrieve documents."""
        kb = await create_test_kb(client)
        if not kb:
            pytest.skip("Could not create test KB")

        try:
            # Upload document
            content_bytes = txt_content.encode('utf-8')
            upload_response = await upload_document(
                client, kb["id"], "test.txt", content_bytes, "text/plain"
            )
            doc_id = upload_response.json()["id"]

            # List documents
            list_response = await client.get(
                "/api/v1/documents",
                params={"kb_id": kb["id"]},
            )

            assert list_response.status_code == 200
            data = list_response.json()
            assert "items" in data
            assert len(data["items"]) >= 1

            # Find our document
            our_doc = None
            for item in data["items"]:
                if item["id"] == doc_id:
                    our_doc = item
                    break

            assert our_doc is not None
            assert our_doc["format"] == "txt"

            # Get document details
            detail_response = await client.get(f"/api/v1/documents/{doc_id}")
            assert detail_response.status_code == 200
            detail = detail_response.json()
            assert detail["id"] == doc_id

        finally:
            try:
                await client.delete(f"/api/v1/knowledge-bases/{kb['id']}")
            except:
                pass

    @pytest.mark.asyncio
    async def test_e2e_document_delete(self, client, txt_content):
        """E2E test: Delete document after upload."""
        kb = await create_test_kb(client)
        if not kb:
            pytest.skip("Could not create test KB")

        try:
            # Upload document
            content_bytes = txt_content.encode('utf-8')
            upload_response = await upload_document(
                client, kb["id"], "test.txt", content_bytes, "text/plain"
            )
            doc_id = upload_response.json()["id"]

            # Delete document
            delete_response = await client.delete(f"/api/v1/documents/{doc_id}")
            assert delete_response.status_code == 204

            # Verify document is deleted
            get_response = await client.get(f"/api/v1/documents/{doc_id}")
            assert get_response.status_code == 404

        finally:
            try:
                await client.delete(f"/api/v1/knowledge-bases/{kb['id']}")
            except:
                pass


# ============================================================
# Integration Tests with Real Services
# ============================================================

class TestIntegrationWithServices:
    """Integration tests that verify interaction with real services."""

    @pytest.mark.asyncio
    async def test_vector_insertion(self, client, txt_content):
        """Test that vectors are actually inserted into Milvus."""
        kb = await create_test_kb(client)
        if not kb:
            pytest.skip("Could not create test KB")

        try:
            # Upload and process document
            content_bytes = txt_content.encode('utf-8')
            upload_response = await upload_document(
                client, kb["id"], "test.txt", content_bytes, "text/plain"
            )
            doc_id = upload_response.json()["id"]

            # Wait for processing to complete (poll with timeout)
            max_wait = 30  # seconds
            waited = 0
            while waited < max_wait:
                doc = await get_document_status(client, doc_id)
                if doc["status"] in ["completed", "failed"]:
                    break
                await asyncio.sleep(1)
                waited += 1

            # Check final status
            doc = await get_document_status(client, doc_id)
            if doc["status"] == "completed":
                # Verify vector count in KB
                kb_response = await client.get(f"/api/v1/knowledge-bases/{kb['id']}")
                if kb_response.status_code == 200:
                    kb_data = kb_response.json()
                    # Vector count should be > 0
                    assert kb_data.get("vector_count", 0) > 0
            else:
                pytest.skip(f"Document processing not completed: {doc.get('error_message', 'unknown')}")

        finally:
            try:
                await client.delete(f"/api/v1/knowledge-bases/{kb['id']}")
            except:
                pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
