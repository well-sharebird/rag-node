from __future__ import annotations
import re
from dataclasses import dataclass, field


@dataclass
class Chunk:
    text: str
    metadata: dict = field(default_factory=dict)


def chunk_text(
    text: str,
    strategy: str = "fixed",
    chunk_size: int = 512,
    chunk_overlap: int = 50,
    separators: list[str] | None = None,
) -> list[Chunk]:
    if strategy == "semantic":
        return _semantic_chunk(text, chunk_size, chunk_overlap, separators)
    return _fixed_chunk(text, chunk_size, chunk_overlap)


def _fixed_chunk(text: str, chunk_size: int, chunk_overlap: int) -> list[Chunk]:
    if not text.strip():
        return []

    paragraphs = text.split("\n\n")
    chunks = []
    current = ""
    current_size = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        para_chars = len(para)

        if current_size + para_chars > chunk_size and current:
            chunks.append(Chunk(text=current.strip()))
            # Overlap: keep last portion
            if chunk_overlap > 0 and len(current) > chunk_overlap:
                current = current[-chunk_overlap:] + "\n\n" + para
                current_size = len(current)
            else:
                current = para
                current_size = para_chars
        else:
            current = (current + "\n\n" + para) if current else para
            current_size = len(current)

    if current.strip():
        chunks.append(Chunk(text=current.strip()))

    return chunks


def _semantic_chunk(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    separators: list[str] | None = None,
) -> list[Chunk]:
    if separators is None:
        separators = ["\n\n", "\n", ". ", "。", " "]

    # Build regex from separators
    escaped = [re.escape(s) for s in separators if s]
    if not escaped:
        escaped = [re.escape("\n\n"), re.escape("\n")]
    pattern = "(" + "|".join(escaped) + ")"
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

    # Merge sentences into chunks up to chunk_size
    chunks = []
    current = ""
    for sent in sentences:
        if len(current) + len(sent) > chunk_size and current:
            chunks.append(Chunk(text=current.strip()))
            # Apply overlap
            if chunk_overlap > 0 and len(current) > chunk_overlap:
                current = current[-chunk_overlap:] + sent
            else:
                current = sent
        else:
            current += sent

    if current.strip():
        chunks.append(Chunk(text=current.strip()))

    return chunks
