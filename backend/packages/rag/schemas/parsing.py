"""Structured parsing output schemas for multi-modal document processing."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ContentElement:
    """A single content piece extracted from a document."""
    content_type: str  # "text", "table", "image"
    text: str
    page: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class ParsedDocument:
    """Structured result of document parsing with content type separation."""
    full_text: str = ""                              # Legacy flat text (backward compat)
    elements: list[ContentElement] = field(default_factory=list)
    content_types: set[str] = field(default_factory=set)
