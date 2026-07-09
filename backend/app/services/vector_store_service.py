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
    data = []
    for i, (emb, chunk) in enumerate(zip(embeddings, chunks)):
        row = {
            "chunk_id": f"{doc_id}_{i}",
            "doc_id": doc_id,
            "kb_id": kb_id,
            "vector": emb,
            "text": chunk.text[:65535],
            "page": chunk.metadata.get("page", 0),
            "chapter": chunk.metadata.get("chapter", "")[:512],
            "doc_name": doc_name[:500],
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
) -> list[dict]:
    results = milvus.search(
        collection_name=collection_name,
        data=[query_embedding],
        limit=top_k,
        output_fields=["chunk_id", "text", "doc_name", "doc_id", "page", "chapter"],
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
