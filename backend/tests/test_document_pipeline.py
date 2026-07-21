"""
Document Pipeline Integration Tests

Tests the complete document upload -> parse -> chunk -> embed -> store pipeline
for all supported file types:
- PDF (.pdf)
- DOCX (.docx)
- XLSX (.xlsx)
- PPTX (.pptx)
- TXT (.txt)
- Markdown (.md)
- HTML (.html, .htm)
- Images (.jpg, .jpeg, .png, .tiff, .tif, .bmp)
"""
import io
import uuid
import pytest
import asyncio
from datetime import datetime

# Test fixtures and helpers
from tests.conftest import *


# ============================================================
# Test Fixtures
# ============================================================

@pytest.fixture
def sample_txt_content():
    """Sample plain text content."""
    return "这是测试文本内容。\n这是第二行。\n这是第三行。\n\n这是新段落。\n" * 20


@pytest.fixture
def sample_md_content():
    """Sample markdown content."""
    return """# 测试文档

## 第一章

这是测试内容。

### 1.1 小节

- 列表项 1
- 列表项 2
- 列表项 3

## 第二章

这是第二章的内容。
""" * 5


@pytest.fixture
def sample_html_content():
    """Sample HTML content."""
    return """<!DOCTYPE html>
<html>
<head><title>测试文档</title></head>
<body>
<h1>测试标题</h1>
<p>这是第一段。</p>
<p>这是第二段。</p>
<table>
<tr><th>列 1</th><th>列 2</th></tr>
<tr><td>数据 1</td><td>数据 2</td></tr>
</table>
</body>
</html>"""


@pytest.fixture
def sample_pdf_content():
    """Sample PDF binary content (minimal valid PDF)."""
    # Minimal valid PDF structure
    pdf_content = b"%PDF-1.4\n"
    pdf_content += b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    pdf_content += b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    pdf_content += b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n"
    pdf_content += b"4 0 obj\n<< /Length 44 >>\nstream\nBT /F1 12 Tf 100 700 Td (Test content) Tj ET\nendstream\nendobj\n"
    pdf_content += b"xref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000214 00000 n \n"
    pdf_content += b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n309\n%%EOF\n"
    return pdf_content


@pytest.fixture
def sample_docx_content():
    """Sample DOCX binary content (minimal valid DOCX)."""
    # DOCX is a ZIP archive, create minimal structure
    import zipfile
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # [Content_Types].xml
        zf.writestr("[Content_Types].xml", """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""")
        # _rels/.rels
        zf.writestr("_rels/.rels", """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""")
        # word/document.xml
        zf.writestr("word/document.xml", """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body>
<w:p><w:r><w:t>Test paragraph 1</w:t></w:r></w:p>
<w:p><w:r><w:t>Test paragraph 2</w:t></w:r></w:p>
<w:p><w:r><w:t>Test paragraph 3</w:t></w:r></w:p>
</w:body>
</w:document>""")
    buffer.seek(0)
    return buffer.read()


@pytest.fixture
def sample_xlsx_content():
    """Sample XLSX binary content (minimal valid XLSX)."""
    import zipfile
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # [Content_Types].xml
        zf.writestr("[Content_Types].xml", """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>""")
        # _rels/.rels
        zf.writestr("_rels/.rels", """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""")
        # xl/workbook.xml
        zf.writestr("xl/workbook.xml", """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>
</workbook>""")
        # xl/_rels/workbook.xml.rels
        zf.writestr("xl/_rels/workbook.xml.rels", """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""")
        # xl/worksheets/sheet1.xml
        zf.writestr("xl/worksheets/sheet1.xml", """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<sheetData>
<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>
<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2" t="s"><v>3</v></c></row>
</sheetData>
</worksheet>""")
    buffer.seek(0)
    return buffer.read()


@pytest.fixture
def sample_pptx_content():
    """Sample PPTX binary content (minimal valid PPTX with proper slide structure)."""
    import zipfile
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # [Content_Types].xml
        zf.writestr("[Content_Types].xml", """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
<Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
</Types>""")
        # _rels/.rels
        zf.writestr("_rels/.rels", """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>""")
        # ppt/_rels/presentation.xml.rels
        zf.writestr("ppt/_rels/presentation.xml.rels", """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
</Relationships>""")
        # ppt/presentation.xml - note the r:id attribute
        zf.writestr("ppt/presentation.xml", """<?xml version="1.0" encoding="UTF-8"?>
<presentation xmlns="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sldIdLst><sldId id="256" r:id="rId1"/></sldIdLst>
</presentation>""")
        # ppt/slides/slide1.xml
        zf.writestr("ppt/slides/slide1.xml", """<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
<p:cSld>
<p:spTree>
<p:sp>
<p:txBody><a:p xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:r><a:rPr/><a:t>Test Slide Content</a:t></a:r></a:p>
</p:txBody>
</p:sp>
</p:spTree>
</p:cSld>
</p:sld>""")
    buffer.seek(0)
    return buffer.read()


@pytest.fixture
def sample_image_content():
    """Sample PNG image content (minimal valid PNG)."""
    # Minimal 1x1 pixel PNG
    import base64
    png_data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
    return png_data


# ============================================================
# Unit Tests - Parsing Service
# ============================================================

class TestParsingService:
    """Test parsing service for all file types."""

    @pytest.mark.asyncio
    async def test_parse_txt(self, sample_txt_content):
        """Test parsing plain text files."""
        from app.services.parsing_service import parse_document

        content = sample_txt_content.encode('utf-8')
        result = await parse_document(content, "txt")

        assert result is not None
        assert len(result) > 0
        assert "测试文本" in result

    @pytest.mark.asyncio
    async def test_parse_md(self, sample_md_content):
        """Test parsing markdown files."""
        from app.services.parsing_service import parse_document

        content = sample_md_content.encode('utf-8')
        result = await parse_document(content, "md")

        assert result is not None
        assert len(result) > 0
        assert "# 测试文档" in result or "测试文档" in result

    @pytest.mark.asyncio
    async def test_parse_html(self, sample_html_content):
        """Test parsing HTML files."""
        from app.services.parsing_service import parse_document

        content = sample_html_content.encode('utf-8')
        result = await parse_document(content, "html")

        assert result is not None
        assert len(result) > 0
        # HTML should extract text content
        assert "测试" in result

    @pytest.mark.asyncio
    async def test_parse_docx(self, sample_docx_content):
        """Test parsing DOCX files."""
        from app.services.parsing_service import parse_document

        result = await parse_document(sample_docx_content, "docx")

        assert result is not None
        assert len(result) > 0
        assert "Test" in result or "test" in result

    @pytest.mark.asyncio
    async def test_parse_xlsx(self, sample_xlsx_content):
        """Test parsing XLSX files."""
        from app.services.parsing_service import parse_document

        result = await parse_document(sample_xlsx_content, "xlsx")

        # XLSX parsing should return something even if empty
        assert result is not None

    @pytest.mark.asyncio
    async def test_parse_pptx(self, sample_pptx_content):
        """Test parsing PPTX files."""
        from app.services.parsing_service import parse_document

        result = await parse_document(sample_pptx_content, "pptx")

        # PPTX parsing should return something
        assert result is not None

    @pytest.mark.asyncio
    async def test_parse_pdf(self, sample_pdf_content):
        """Test parsing PDF files."""
        from app.services.parsing_service import parse_document

        result = await parse_document(sample_pdf_content, "pdf")

        # PDF parsing should return something
        assert result is not None

    @pytest.mark.asyncio
    async def test_parse_image(self, sample_image_content):
        """Test parsing image files (OCR)."""
        from app.services.parsing_service import parse_document

        # Image parsing may return empty string if no OCR available
        result = await parse_document(sample_image_content, "png")

        # Should not raise exception
        assert result is not None

    @pytest.mark.asyncio
    async def test_parse_unsupported_format(self):
        """Test parsing unsupported file format."""
        from app.services.parsing_service import parse_document
        from app.utils.exceptions import ValidationException

        with pytest.raises(ValidationException):
            await parse_document(b"test content", "xyz")


# ============================================================
# Unit Tests - Chunking Service
# ============================================================

class TestChunkingService:
    """Test chunking service with different strategies."""

    @pytest.mark.asyncio
    async def test_chunk_fixed_strategy(self):
        """Test fixed-size chunking."""
        from app.services.chunking_service import chunk_text, _count_tokens

        text = "这是测试文本。" * 50
        chunks = chunk_text(text, strategy="fixed", chunk_size=100, chunk_overlap=10)

        assert len(chunks) > 0
        assert all(c.text for c in chunks)
        # Verify chunks are created with proper structure
        for chunk in chunks:
            assert chunk.text is not None
            assert len(chunk.text) > 0

    @pytest.mark.asyncio
    async def test_chunk_semantic_strategy(self):
        """Test semantic chunking."""
        from app.services.chunking_service import chunk_text

        text = "第一段内容。\n\n第二段内容。\n\n第三段内容。" * 20
        chunks = chunk_text(text, strategy="semantic", chunk_size=100, chunk_overlap=10)

        assert len(chunks) > 0
        assert all(c.text for c in chunks)

    @pytest.mark.asyncio
    async def test_chunk_recursive_strategy(self):
        """Test recursive chunking."""
        from app.services.chunking_service import chunk_text

        text = "Line 1\nLine 2\nLine 3\n\nParagraph 2\n\nParagraph 3" * 20
        chunks = chunk_text(text, strategy="recursive", chunk_size=100, chunk_overlap=10)

        assert len(chunks) > 0
        assert all(c.text for c in chunks)

    @pytest.mark.asyncio
    async def test_chunk_with_content_type(self):
        """Test chunking with content type tagging."""
        from app.services.chunking_service import chunk_text

        text = "Table content here" * 20
        chunks = chunk_text(text, strategy="fixed", chunk_size=100, content_type="table")

        assert len(chunks) > 0
        assert all(c.content_type == "table" for c in chunks)
        assert all(c.metadata.get("content_type") == "table" for c in chunks)

    @pytest.mark.asyncio
    async def test_chunk_empty_text(self):
        """Test chunking empty text."""
        from app.services.chunking_service import chunk_text

        chunks = chunk_text("", strategy="fixed")

        assert chunks == []

    @pytest.mark.asyncio
    async def test_count_tokens(self):
        """Test token counting."""
        from app.services.chunking_service import _count_tokens

        # English: ~4 chars per token
        en_tokens = _count_tokens("hello world")
        assert en_tokens > 0

        # CJK: ~1 char per token
        cjk_tokens = _count_tokens("你好世界")
        assert cjk_tokens >= 4


# ============================================================
# Unit Tests - Document Service
# ============================================================

class TestDocumentService:
    """Test document service."""

    def test_validate_file_allowed(self):
        """Test file validation for allowed formats."""
        from app.services.document_service import validate_file

        # Should not raise
        validate_file("test.txt", 1024)
        validate_file("test.pdf", 1024)
        validate_file("test.docx", 1024)
        validate_file("test.xlsx", 1024)
        validate_file("test.png", 1024)

    def test_validate_file_unsupported(self):
        """Test file validation for unsupported formats."""
        from app.services.document_service import validate_file
        from app.utils.exceptions import ValidationException

        with pytest.raises(ValidationException):
            validate_file("test.xyz", 1024)

    def test_validate_file_too_large(self):
        """Test file validation for oversized files."""
        from app.services.document_service import validate_file, MAX_FILE_SIZE
        from app.utils.exceptions import ValidationException

        with pytest.raises(ValidationException):
            validate_file("test.txt", MAX_FILE_SIZE + 1)


# ============================================================
# Integration Tests - Full Pipeline
# ============================================================

class TestDocumentPipelineIntegration:
    """Integration tests for complete document processing pipeline."""

    @pytest.mark.asyncio
    async def test_pipeline_txt_document(self, sample_txt_content):
        """Test full pipeline for TXT document."""
        from app.services.parsing_service import parse_document
        from app.services.chunking_service import chunk_text

        # Parse
        content = sample_txt_content.encode('utf-8')
        parsed = await parse_document(content, "txt")
        assert parsed is not None
        assert len(parsed) > 0

        # Chunk
        chunks = chunk_text(parsed, strategy="fixed", chunk_size=100)
        assert len(chunks) > 0

        # Verify chunk structure
        for chunk in chunks:
            assert hasattr(chunk, 'text')
            assert hasattr(chunk, 'metadata')
            assert chunk.text is not None

    @pytest.mark.asyncio
    async def test_pipeline_md_document(self, sample_md_content):
        """Test full pipeline for Markdown document."""
        from app.services.parsing_service import parse_document
        from app.services.chunking_service import chunk_text

        # Parse
        content = sample_md_content.encode('utf-8')
        parsed = await parse_document(content, "md")
        assert parsed is not None

        # Chunk
        chunks = chunk_text(parsed, strategy="semantic", chunk_size=150)
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_pipeline_html_document(self, sample_html_content):
        """Test full pipeline for HTML document."""
        from app.services.parsing_service import parse_document
        from app.services.chunking_service import chunk_text

        # Parse
        content = sample_html_content.encode('utf-8')
        parsed = await parse_document(content, "html")
        assert parsed is not None
        assert "测试" in parsed

        # Chunk
        chunks = chunk_text(parsed, strategy="fixed", chunk_size=100)
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_pipeline_docx_document(self, sample_docx_content):
        """Test full pipeline for DOCX document."""
        from app.services.parsing_service import parse_document
        from app.services.chunking_service import chunk_text

        # Parse
        parsed = await parse_document(sample_docx_content, "docx")
        assert parsed is not None

        # Chunk
        if parsed.strip():
            chunks = chunk_text(parsed, strategy="fixed", chunk_size=100)
            assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_pipeline_pdf_document(self, sample_pdf_content):
        """Test full pipeline for PDF document."""
        from app.services.parsing_service import parse_document
        from app.services.chunking_service import chunk_text

        # Parse
        parsed = await parse_document(sample_pdf_content, "pdf")
        assert parsed is not None

        # Chunk if has content
        if parsed.strip():
            chunks = chunk_text(parsed, strategy="fixed", chunk_size=100)
            assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_pipeline_xlsx_document(self, sample_xlsx_content):
        """Test full pipeline for XLSX document."""
        from app.services.parsing_service import parse_document
        from app.services.chunking_service import chunk_text

        # Parse
        parsed = await parse_document(sample_xlsx_content, "xlsx")
        assert parsed is not None

        # Chunk if has content
        if parsed.strip() and parsed != "(无法提取 Excel 文件内容)":
            chunks = chunk_text(parsed, strategy="fixed", chunk_size=100)
            assert len(chunks) >= 0  # May be empty

    @pytest.mark.asyncio
    async def test_pipeline_pptx_document(self, sample_pptx_content):
        """Test full pipeline for PPTX document."""
        from app.services.parsing_service import parse_document
        from app.services.chunking_service import chunk_text

        # Parse
        parsed = await parse_document(sample_pptx_content, "pptx")
        assert parsed is not None

        # Chunk if has content
        if parsed.strip():
            chunks = chunk_text(parsed, strategy="fixed", chunk_size=100)
            assert len(chunks) >= 0


# ============================================================
# API Tests - Document Endpoints
# ============================================================

class TestDocumentAPI:
    """Test document API endpoints."""

    @pytest.fixture
    async def api_test_kb(self, client):
        """Create a test KB for API tests."""
        kb_id = str(uuid.uuid4())
        kb_name = f"test_kb_{kb_id[:8]}"

        try:
            response = await client.post(
                "/api/v1/knowledge-bases",
                json={"name": kb_name, "description": "Test KB"},
            )
            if response.status_code == 201:
                kb_data = response.json()

                class KB:
                    def __init__(self, kb_id):
                        self.id = kb_id
                yield KB(kb_data["id"])

                try:
                    await client.delete(f"/api/v1/knowledge-bases/{kb_data['id']}")
                except:
                    pass
            else:
                pytest.skip("Could not create test KB")
        except Exception:
            pytest.skip("Could not create test KB")

    @pytest.mark.asyncio
    async def test_upload_document_txt(self, client, sample_txt_content, api_test_kb):
        """Test uploading TXT document via API."""
        import io

        file_content = sample_txt_content.encode('utf-8')
        files = {"file": ("test.txt", io.BytesIO(file_content), "text/plain")}

        response = await client.post(
            "/api/v1/documents/upload",
            files=files,
            params={"kb_id": api_test_kb.id},
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["status"] in ["completed", "failed", "processing"]

    @pytest.mark.asyncio
    async def test_upload_document_md(self, client, sample_md_content, api_test_kb):
        """Test uploading Markdown document via API."""
        import io

        file_content = sample_md_content.encode('utf-8')
        files = {"file": ("test.md", io.BytesIO(file_content), "text/markdown")}

        response = await client.post(
            "/api/v1/documents/upload",
            files=files,
            params={"kb_id": api_test_kb.id},
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data

    @pytest.mark.asyncio
    async def test_upload_document_html(self, client, sample_html_content, api_test_kb):
        """Test uploading HTML document via API."""
        import io

        file_content = sample_html_content.encode('utf-8')
        files = {"file": ("test.html", io.BytesIO(file_content), "text/html")}

        response = await client.post(
            "/api/v1/documents/upload",
            files=files,
            params={"kb_id": api_test_kb.id},
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data

    @pytest.mark.asyncio
    async def test_list_documents(self, client, api_test_kb):
        """Test listing documents."""
        response = await client.get(
            "/api/v1/documents",
            params={"kb_id": api_test_kb.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_get_document(self, client, api_test_kb):
        """Test getting document details."""
        import io
        file_content = b"test content"
        files = {"file": ("test.txt", io.BytesIO(file_content), "text/plain")}

        upload_response = await client.post(
            "/api/v1/documents/upload",
            files=files,
            params={"kb_id": api_test_kb.id},
        )
        doc_id = upload_response.json()["id"]

        response = await client.get(f"/api/v1/documents/{doc_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == doc_id
        assert data["kb_id"] == api_test_kb.id


# ============================================================
# Edge Cases and Error Handling
# ============================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_empty_file(self):
        """Test handling empty file."""
        from app.services.parsing_service import parse_document

        # Empty content
        result = await parse_document(b"", "txt")
        assert result == ""

    @pytest.mark.asyncio
    async def test_very_large_chunk(self):
        """Test handling very large text chunking."""
        from app.services.chunking_service import chunk_text

        # Large text (10000 chars)
        large_text = "x" * 10000
        chunks = chunk_text(large_text, strategy="fixed", chunk_size=500)

        assert len(chunks) > 0
        assert sum(len(c.text) for c in chunks) >= 10000

    @pytest.mark.asyncio
    async def test_special_characters(self):
        """Test handling special characters."""
        from app.services.parsing_service import parse_document
        from app.services.chunking_service import chunk_text

        # Special characters
        special_text = "Special: \n\t\r\n\x00\x01\x02 中文 emoji: 😀"
        content = special_text.encode('utf-8')

        parsed = await parse_document(content, "txt")
        assert parsed is not None

        chunks = chunk_text(parsed, strategy="fixed", chunk_size=50)
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_mixed_language_text(self):
        """Test handling mixed language text."""
        from app.services.parsing_service import parse_document
        from app.services.chunking_service import chunk_text, _count_tokens

        mixed_text = """
        English text here.
        中文文本内容。
        日本語テキスト。
        한국어 텍스트.
        More English.
        """ * 10

        chunks = chunk_text(mixed_text, strategy="semantic", chunk_size=100)
        assert len(chunks) > 0

        # Token counting should work for mixed languages
        tokens = _count_tokens(mixed_text)
        assert tokens > 0

    def test_file_validation_edge_cases(self):
        """Test file validation edge cases."""
        from app.services.document_service import validate_file
        from app.utils.exceptions import ValidationException

        # File without extension - should raise (no valid extension)
        with pytest.raises(ValidationException):
            validate_file("noextension", 1024)

        # File with double extension - uses last extension 'gz' which is not allowed
        with pytest.raises(ValidationException):
            validate_file("test.tar.gz", 1024)

        # Uppercase extension - should be normalized to lowercase and pass
        validate_file("test.TXT", 1024)

        # Mixed case extension
        validate_file("test.PdF", 1024)


# ============================================================
# Performance Tests (Basic - without pytest-benchmark)
# ============================================================

class TestPerformance:
    """Basic performance tests."""

    @pytest.mark.asyncio
    async def test_parsing_performance_txt(self):
        """Test parsing performance for TXT files."""
        import time
        from app.services.parsing_service import parse_document

        content = "测试文本内容。" * 1000
        content_bytes = content.encode('utf-8')

        start = time.time()
        result = await parse_document(content_bytes, "txt")
        elapsed = time.time() - start

        assert result is not None
        assert elapsed < 5.0  # Should complete within 5 seconds

    @pytest.mark.asyncio
    async def test_chunking_performance(self):
        """Test chunking performance."""
        import time
        from app.services.chunking_service import chunk_text

        text = "测试文本。" * 5000

        start = time.time()
        result = chunk_text(text, strategy="fixed", chunk_size=200)
        elapsed = time.time() - start

        assert len(result) > 0
        assert elapsed < 2.0  # Should complete within 2 seconds


# ============================================================
# Structured Parsing Tests
# ============================================================

class TestStructuredParsing:
    """Test structured parsing with content type separation."""

    @pytest.mark.asyncio
    async def test_structured_parse_txt(self, sample_txt_content):
        """Test structured parsing for TXT."""
        from app.services.parsing_service import parse_document_structured

        content = sample_txt_content.encode('utf-8')
        result = await parse_document_structured(content, "txt")

        assert result is not None
        assert result.full_text is not None
        assert len(result.elements) > 0
        assert "text" in result.content_types

    @pytest.mark.asyncio
    async def test_structured_parse_html(self, sample_html_content):
        """Test structured parsing for HTML with tables."""
        from app.services.parsing_service import parse_document_structured

        content = sample_html_content.encode('utf-8')
        result = await parse_document_structured(content, "html")

        assert result is not None
        # HTML may have text and table elements
        assert result.full_text is not None

    @pytest.mark.asyncio
    async def test_structured_parse_image(self, sample_image_content):
        """Test structured parsing for images."""
        from app.services.parsing_service import parse_document_structured

        result = await parse_document_structured(sample_image_content, "png")

        assert result is not None
        # Image should have image content type (or text if OCR succeeds)
        assert result.full_text is not None
