from __future__ import annotations
ALLOWED_EXTENSIONS = {"pdf", "docx", "txt", "md", "html", "htm"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

MIME_MAP = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/plain": "txt",
    "text/markdown": "md",
    "text/html": "html",
}


def get_extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def is_allowed_format(extension: str) -> bool:
    return extension in ALLOWED_EXTENSIONS


def is_within_size_limit(file_size: int) -> bool:
    return file_size <= MAX_FILE_SIZE
