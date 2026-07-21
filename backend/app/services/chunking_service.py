"""
Stage 3 - Intelligent Chunking Strategies
支持 5 种策略：Fixed, Semantic, Recursive, Agentic, Small-to-Big
"""
from __future__ import annotations
import re
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Callable
from abc import ABC, abstractmethod

logger = logging.getLogger("app.services.chunking")


@dataclass
class Chunk:
    """Chunk with rich metadata"""
    text: str
    metadata: dict = field(default_factory=dict)
    chunk_id: Optional[str] = None
    parent_id: Optional[str] = None  # For Small-to-Big strategy
    child_ids: List[str] = field(default_factory=list)  # For Small-to-Big
    start_idx: int = 0  # Character offset in original text
    end_idx: int = 0
    token_count: int = 0  # Estimated token count
    content_type: str = "text"  # "text", "table", "image"


def chunk_text(
    text: str,
    strategy: str = "fixed",
    chunk_size: int = 512,
    chunk_overlap: int = 50,
    separators: Optional[List[str]] = None,
    llm_service=None,  # For Agentic strategy
    small_chunk_size: Optional[int] = None,  # For Small-to-Big
    content_type: str = "text",  # Content type tag: "text", "table", "image"
) -> List[Chunk]:
    """
    Chunk text using the specified strategy.

    Args:
        text: Input text to chunk
        strategy: One of 'fixed', 'semantic', 'recursive', 'agentic', 'small_to_big'
        chunk_size: Target chunk size (characters or tokens depending on strategy)
        chunk_overlap: Overlap between consecutive chunks
        separators: Custom separators for semantic/recursive splitting
        llm_service: LLM service for agentic chunking
        small_chunk_size: Smaller chunk size for small-to-big strategy
        content_type: Content type for metadata tracking ("text", "table", "image")

    Returns:
        List of Chunk objects
    """
    if strategy == "semantic":
        chunks = _semantic_chunk(text, chunk_size, chunk_overlap, separators)
    elif strategy == "recursive":
        chunks = _recursive_chunk(text, chunk_size, chunk_overlap, separators)
    elif strategy == "agentic":
        if llm_service is None:
            logger.warning("Agentic chunking requires llm_service, falling back to recursive")
            chunks = _recursive_chunk(text, chunk_size, chunk_overlap, separators)
        else:
            chunks = _agentic_chunk(text, llm_service, chunk_size, chunk_overlap)
    elif strategy == "small_to_big":
        small_size = small_chunk_size or max(chunk_size // 4, 128)
        chunks = _small_to_big_chunk(text, chunk_size, small_size, chunk_overlap, separators)
    else:
        chunks = _fixed_chunk(text, chunk_size, chunk_overlap)

    # Tag all chunks with content_type and propagate to metadata
    for chunk in chunks:
        chunk.content_type = content_type
        chunk.metadata["content_type"] = content_type
    return chunks


def _count_tokens(text: str) -> int:
    """Estimate token count from text (4 chars ≈ 1 token for English, 1 char ≈ 1 token for CJK)"""
    # Simple heuristic: CJK chars = 1 token, other chars ≈ 4 tokens
    cjk_pattern = re.compile(r"[一-鿿぀-ヿ가-힯]")
    cjk_count = len(cjk_pattern.findall(text))
    other_count = len(text) - cjk_count
    return cjk_count + (other_count // 4) + 1


def _fixed_chunk(text: str, chunk_size: int, chunk_overlap: int) -> List[Chunk]:
    """
    Fixed-size chunking based on token count (not characters).
    Splits text into chunks of approximately chunk_size tokens.
    """
    if not text.strip():
        return []

    # Split into paragraphs first
    paragraphs = text.split("\n\n")
    chunks = []
    current_tokens = []
    current_text = ""
    current_token_count = 0
    start_idx = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        para_tokens = _count_tokens(para)

        # Check if adding this paragraph exceeds chunk_size
        if current_token_count + para_tokens > chunk_size and current_tokens:
            # Create chunk from accumulated tokens
            chunk_text = "\n\n".join(current_tokens)
            chunks.append(Chunk(
                text=chunk_text.strip(),
                start_idx=start_idx,
                end_idx=start_idx + len(chunk_text),
                token_count=current_token_count,
            ))

            # Handle overlap - keep last portion that fits in overlap
            if chunk_overlap > 0 and len(current_tokens) > 1:
                overlap_tokens = []
                overlap_count = 0
                for t in reversed(current_tokens):
                    t_count = _count_tokens(t)
                    if overlap_count + t_count <= chunk_overlap:
                        overlap_tokens.insert(0, t)
                        overlap_count += t_count
                    else:
                        break
                current_tokens = overlap_tokens
                current_text = "\n\n".join(current_tokens)
                current_token_count = overlap_count
                start_idx = start_idx + len(chunk_text) - len(current_text)
            else:
                current_tokens = []
                current_text = ""
                current_token_count = 0
                start_idx = start_idx + len(chunk_text)

            current_tokens.append(para)
            current_text = para
            current_token_count = para_tokens
        else:
            current_tokens.append(para)
            current_text = "\n\n".join(current_tokens)
            current_token_count += para_tokens

    # Don't forget the last chunk
    if current_tokens:
        chunk_text = "\n\n".join(current_tokens)
        chunks.append(Chunk(
            text=chunk_text.strip(),
            start_idx=start_idx,
            end_idx=start_idx + len(chunk_text),
            token_count=current_token_count,
        ))

    return chunks


def _semantic_chunk(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    separators: Optional[List[str]] = None,
) -> List[Chunk]:
    """
    Semantic chunking using configurable separators.
    Tries to split at semantic boundaries (paragraphs, sentences, etc.)
    """
    if separators is None:
        separators = ["\n\n", "\n", ". ", "。", "！", "！？", "? ", " "]

    # Build regex from separators (longer separators first)
    sorted_separators = sorted(separators, key=len, reverse=True)
    escaped = [re.escape(s) for s in sorted_separators if s]
    if not escaped:
        escaped = [re.escape("\n\n"), re.escape("\n")]
    pattern = "(" + "|".join(escaped) + ")"

    # Split text while keeping separators
    parts = re.split(pattern, text)

    # Recombine: merge separator with preceding content
    sentences = []
    buf = ""
    for part in parts:
        if re.match(pattern, part):
            buf += part
            if buf.strip():
                sentences.append(buf)
            buf = ""
        else:
            buf += part
    if buf.strip():
        sentences.append(buf)

    # Merge sentences into chunks up to chunk_size tokens
    chunks = []
    current = ""
    current_start = 0
    for sent in sentences:
        if _count_tokens(current + sent) > chunk_size and current:
            chunks.append(Chunk(
                text=current.strip(),
                start_idx=current_start,
                end_idx=current_start + len(current),
                token_count=_count_tokens(current),
            ))
            # Apply overlap
            if chunk_overlap > 0 and len(current) > chunk_overlap:
                # Find overlap point
                overlap_start = max(0, len(current) - chunk_overlap)
                # Try to break at word boundary
                space_idx = current.find(" ", overlap_start)
                if space_idx > overlap_start:
                    overlap_start = space_idx
                current = current[overlap_start:] + sent
                current_start = current_start + overlap_start
            else:
                current = sent
                current_start = current_start + len(current) - len(sent)
        else:
            current += sent

    if current.strip():
        chunks.append(Chunk(
            text=current.strip(),
            start_idx=current_start,
            end_idx=current_start + len(current),
            token_count=_count_tokens(current),
        ))

    return chunks


def _recursive_chunk(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    separators: Optional[List[str]] = None,
) -> List[Chunk]:
    """
    Recursive character-based chunking with hierarchical separators.
    Similar to LangChain's RecursiveCharacterTextSplitter.
    """
    if separators is None:
        # Hierarchical separators from coarse to fine
        separators = [
            "\n\n\n",  # Section breaks
            "\n\n",    # Paragraph breaks
            "\n",      # Line breaks
            ". ",      # Sentence breaks (English)
            "。",      # Sentence breaks (Chinese)
            "! ",      # Exclamation
            "? ",      # Question
            "！",     # Chinese exclamation
            "？",     # Chinese question
            " ",       # Word breaks
            "",        # Character level (last resort)
        ]

    def _split(text: str, sep_idx: int) -> List[str]:
        if sep_idx >= len(separators):
            return [text] if text else []

        sep = separators[sep_idx]
        if not sep:
            # Character level - split into individual characters
            return list(text) if text else []

        # Split by separator
        parts = text.split(sep)

        # If only one part, try next separator
        if len(parts) == 1:
            return _split(text, sep_idx + 1)

        # Re-add separator to parts (except last)
        result = []
        for i, part in enumerate(parts):
            if part:
                if i < len(parts) - 1:
                    result.append(part + sep)
                else:
                    result.append(part)

        return result

    # Split text into units
    units = _split(text, 0)

    # Combine units into chunks
    chunks = []
    current = ""
    current_start = 0

    for unit in units:
        if _count_tokens(current + unit) > chunk_size and current:
            chunks.append(Chunk(
                text=current.strip(),
                start_idx=current_start,
                end_idx=current_start + len(current),
                token_count=_count_tokens(current),
            ))

            # Handle overlap
            if chunk_overlap > 0 and len(current) > chunk_overlap:
                overlap_start = max(0, len(current) - chunk_overlap)
                current = current[overlap_start:] + unit
                current_start = current_start + overlap_start
            else:
                current = unit
                current_start = current_start + len(current) - len(unit)
        else:
            current += unit

    if current.strip():
        chunks.append(Chunk(
            text=current.strip(),
            start_idx=current_start,
            end_idx=current_start + len(current),
            token_count=_count_tokens(current),
        ))

    return chunks


def _agentic_chunk(
    text: str,
    llm_service,
    chunk_size: int,
    chunk_overlap: int,
) -> List[Chunk]:
    """
    Agentic chunking using LLM to identify semantic boundaries.
    The LLM analyzes the text and suggests optimal chunk boundaries.
    """
    # Prompt the LLM to identify chunk boundaries
    prompt = f"""
Analyze the following text and identify optimal chunk boundaries for a RAG system.
The target chunk size is approximately {chunk_size} tokens.

Return the chunk boundaries as a list of character positions where each chunk should start.
Format: [0, 512, 1024, ...]

Text to analyze (first 5000 chars):
{text[:5000]}

Respond with ONLY the JSON array of character positions, no explanation.
"""

    try:
        # Call LLM to get chunk boundaries
        import asyncio

        async def get_boundaries():
            result = await llm_service.generate(prompt)
            return result

        boundaries_str = asyncio.get_event_loop().run_until_complete(get_boundaries())

        # Parse the response
        import json
        boundaries = json.loads(boundaries_str.strip())

        if not isinstance(boundaries, list) or not boundaries:
            logger.warning("LLM returned invalid boundaries, falling back to recursive")
            return _recursive_chunk(text, chunk_size, chunk_overlap)

        # Create chunks from boundaries
        chunks = []
        for i, start in enumerate(boundaries):
            end = boundaries[i + 1] if i + 1 < len(boundaries) else len(text)
            chunk_text = text[start:end]
            chunks.append(Chunk(
                text=chunk_text.strip(),
                start_idx=start,
                end_idx=end,
                token_count=_count_tokens(chunk_text),
            ))

        return chunks

    except Exception as e:
        logger.warning("Agentic chunking failed (%s), falling back to recursive", e)
        return _recursive_chunk(text, chunk_size, chunk_overlap)


def _small_to_big_chunk(
    text: str,
    chunk_size: int,
    small_chunk_size: int,
    chunk_overlap: int,
    separators: Optional[List[str]] = None,
) -> List[Chunk]:
    """
    Small-to-Big chunking strategy.
    Creates small chunks for retrieval, but returns parent (larger) chunks in results.
    This improves retrieval precision while maintaining context.
    """
    # First, create large (parent) chunks
    parent_chunks = _recursive_chunk(text, chunk_size, chunk_overlap, separators)

    # Then, split each parent into smaller child chunks
    result = []
    for parent in parent_chunks:
        # Generate child chunk IDs
        import uuid
        child_ids = []

        # Split parent into small chunks
        small_chunks = _recursive_chunk(
            parent.text,
            small_chunk_size,
            min(chunk_overlap, small_chunk_size // 4),
            separators,
        )

        for child in small_chunks:
            child_id = f"chunk_{uuid.uuid4().hex[:8]}"
            child_ids.append(child_id)

        # Parent chunk gets the child IDs
        parent_id = f"parent_{uuid.uuid4().hex[:8]}"
        parent.chunk_id = parent_id
        parent.child_ids = child_ids

        # Also set child metadata
        for child in small_chunks:
            child.parent_id = parent_id

        result.append(parent)

    return result


# Utility functions for external use

def estimate_tokens(text: str) -> int:
    """Public API to estimate token count"""
    return _count_tokens(text)


def get_chunking_strategies() -> List[str]:
    """Return list of available chunking strategies"""
    return ["fixed", "semantic", "recursive", "agentic", "small_to_big"]
