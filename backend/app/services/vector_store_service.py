from __future__ import annotations
from pymilvus import MilvusClient

from app.services.chunking_service import Chunk
from app.config import settings as app_settings


def insert_chunks(
    milvus: MilvusClient,
    collection_name: str,
    doc_id: str,
    kb_id: str,
    doc_name: str,
    embeddings: list[list[float]],
    chunks: list[Chunk],
) -> int:
    """
    插入向量块到 Milvus

    注意：Milvus dynamic field 有 65536 字节限制，需要严格控制字段长度
    """
    data = []
    for i, (emb, chunk) in enumerate(zip(embeddings, chunks)):
        ct = getattr(chunk, 'content_type', 'text')

        # 严格控制字段长度，避免超过 Milvus dynamic field 限制 (65536 bytes)
        # 预留 1000 字节安全余量
        text_max_len = 50000

        # 截断文本
        text = chunk.text[:text_max_len] if len(chunk.text) > text_max_len else chunk.text

        # 截断 metadata 字段
        chapter = chunk.metadata.get("chapter", "")
        if len(chapter) > 200:
            chapter = chapter[:200]

        row = {
            "chunk_id": f"{doc_id}_{i}",
            "doc_id": doc_id,
            "kb_id": kb_id,
            "vector": emb,
            "text": text,
            "page": chunk.metadata.get("page", 0),
            "chapter": chapter,
            "doc_name": doc_name[:200],
            "content_type": ct,
        }
        data.append(row)

    result = milvus.insert(collection_name=collection_name, data=data)
    return result["insert_count"]


def search_vectors(
    milvus: MilvusClient,
    collection_name: str,
    query_embedding: list[float],
    top_k: int = 10,
    min_score: float = 0.0,
    content_type_filter: str | list[str] | None = None,
) -> list[dict]:
    filter_expr = None
    if content_type_filter:
        if isinstance(content_type_filter, list):
            types = ', '.join(f'"{t}"' for t in content_type_filter)
            filter_expr = f'content_type in [{types}]'
        else:
            filter_expr = f'content_type == "{content_type_filter}"'

    results = milvus.search(
        collection_name=collection_name,
        data=[query_embedding],
        limit=top_k,
        filter=filter_expr,
        output_fields=["chunk_id", "text", "doc_name", "doc_id", "page", "chapter", "content_type"],
    )

    hits = []
    for result in results:
        for hit in result:
            if hit["distance"] < min_score:
                continue
            hits.append({
                "chunk_id": hit["entity"].get("chunk_id", ""),
                "content": hit["entity"].get("text", ""),
                "score": round(hit["distance"], 4),
                "content_type": hit["entity"].get("content_type", "text"),
                "metadata": {
                    "doc_name": hit["entity"].get("doc_name", ""),
                    "doc_id": hit["entity"].get("doc_id", ""),
                    "page": hit["entity"].get("page"),
                    "chapter": hit["entity"].get("chapter"),
                },
            })
    return hits


def delete_by_doc_id(milvus: MilvusClient, collection_name: str, doc_id: str) -> int:
    result = milvus.delete(
        collection_name=collection_name,
        filter=f'doc_id == "{doc_id}"',
    )
    return result.get("delete_count", 0)
