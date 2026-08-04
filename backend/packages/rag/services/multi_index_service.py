"""
Stage 5 - Multi-Index Storage Service
支持 5 路索引写入：Dense Vector (Milvus) + Sparse Vector (BGE-M3) + BM25 (ES) + KG (Neo4j) + Object (MinIO)
"""
from __future__ import annotations
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger("app.services.multi_index")


@dataclass
class IndexWriteResult:
    """Result of writing to a single index"""
    index_type: str  # dense, sparse, bm25, kg, object
    success: bool
    count: int = 0
    error: Optional[str] = None


@dataclass
class MultiIndexResult:
    """Overall result of multi-index write"""
    doc_id: str
    kb_id: str
    results: List[IndexWriteResult] = field(default_factory=list)
    total_written: int = 0

    def add_result(self, result: IndexWriteResult):
        self.results.append(result)
        if result.success:
            self.total_written += result.count

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if not r.success)

    @property
    def all_success(self) -> bool:
        return self.failed_count == 0


class MultiIndexService:
    """
    Service for writing to multiple indices in parallel.
    Supports: Dense Vector, Sparse Vector, BM25, Knowledge Graph, Object Storage
    """

    def __init__(
        self,
        milvus_client=None,
        sparse_encoder=None,
        es_client=None,
        neo4j_client=None,
        minio_client=None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.milvus_client = milvus_client
        self.sparse_encoder = sparse_encoder  # BGE-M3 sparse encoder
        self.es_client = es_client
        self.neo4j_client = neo4j_client
        self.minio_client = minio_client
        self.config = config or {}

        # Index configuration
        self.enable_sparse = self.config.get("enable_sparse", False)
        self.enable_bm25 = self.config.get("enable_bm25", False)
        self.enable_kg = self.config.get("enable_kg", False)
        self.enable_object = self.config.get("enable_object", True)

    async def write_document(
        self,
        doc_id: str,
        kb_id: str,
        collection_name: str,
        doc_name: str,
        chunks: List[Any],
        dense_embeddings: List[List[float]],
        original_content: Optional[bytes] = None,
        entities: Optional[List[Any]] = None,
        relations: Optional[List[Any]] = None,
    ) -> MultiIndexResult:
        """
        Write document to all configured indices.

        Args:
            doc_id: Document ID
            kb_id: Knowledge base ID
            collection_name: Milvus collection name
            doc_name: Document name
            chunks: List of Chunk objects
            dense_embeddings: Dense embeddings from main embedding model
            original_content: Original file bytes for object storage
            entities: Extracted entities for KG
            relations: Extracted relations for KG

        Returns:
            MultiIndexResult with status for each index
        """
        result = MultiIndexResult(doc_id=doc_id, kb_id=kb_id)

        # 1. Dense Vector (Milvus) - always enabled
        dense_result = await self._write_dense(
            collection_name, doc_id, kb_id, doc_name, chunks, dense_embeddings
        )
        result.add_result(dense_result)

        # 2. Sparse Vector (BGE-M3) - optional
        if self.enable_sparse and self.sparse_encoder:
            sparse_result = await self._write_sparse(
                collection_name, doc_id, kb_id, doc_name, chunks
            )
            result.add_result(sparse_result)

        # 3. BM25 Full-text (Elasticsearch) - optional
        if self.enable_bm25 and self.es_client:
            bm25_result = await self._write_bm25(
                kb_id, doc_id, doc_name, chunks
            )
            result.add_result(bm25_result)

        # 4. Knowledge Graph (Neo4j) - optional
        if self.enable_kg and self.neo4j_client and entities:
            kg_result = await self._write_kg(
                kb_id, doc_id, doc_name, entities, relations
            )
            result.add_result(kg_result)

        # 5. Object Storage (MinIO) - optional
        if self.enable_object and self.minio_client and original_content:
            object_result = await self._write_object(
                kb_id, doc_id, original_content
            )
            result.add_result(object_result)

        logger.info(
            "Multi-index write completed | doc=%s success=%d/%d total=%d",
            doc_id, result.success_count, len(result.results), result.total_written
        )

        return result

    async def _write_dense(
        self,
        collection_name: str,
        doc_id: str,
        kb_id: str,
        doc_name: str,
        chunks: List[Any],
        embeddings: List[List[float]],
    ) -> IndexWriteResult:
        """Write dense vectors to Milvus"""
        try:
            from packages.rag.services.vector_store_service import insert_chunks

            count = insert_chunks(
                self.milvus_client,
                collection_name,
                doc_id,
                kb_id,
                doc_name,
                embeddings,
                chunks,
            )

            return IndexWriteResult(
                index_type="dense",
                success=True,
                count=count,
            )
        except Exception as e:
            logger.exception("Dense vector write failed")
            return IndexWriteResult(
                index_type="dense",
                success=False,
                error=str(e),
            )

    async def _write_sparse(
        self,
        collection_name: str,
        doc_id: str,
        kb_id: str,
        doc_name: str,
        chunks: List[Any],
    ) -> IndexWriteResult:
        """Write sparse vectors to Milvus"""
        try:
            # Generate sparse embeddings using BGE-M3
            chunk_texts = [c.text for c in chunks]
            sparse_embeddings = await self.sparse_encoder.encode_sparse(chunk_texts)

            # Write to Milvus sparse vector collection
            data = []
            for i, (sparse_emb, chunk) in enumerate(zip(sparse_embeddings, chunks)):
                # Convert sparse embedding to dict format for Milvus
                sparse_dict = {
                    str(k): v for k, v in zip(sparse_emb.indices, sparse_emb.values)
                }

                row = {
                    "chunk_id": f"{doc_id}_sparse_{i}",
                    "doc_id": doc_id,
                    "kb_id": kb_id,
                    "sparse_vector": sparse_dict,
                    "text": chunk.text[:65535],
                    "doc_name": doc_name[:500],
                }
                data.append(row)

            result = self.milvus_client.insert(
                collection_name=f"{collection_name}_sparse",
                data=data,
            )

            return IndexWriteResult(
                index_type="sparse",
                success=True,
                count=result.get("insert_count", 0),
            )
        except Exception as e:
            logger.exception("Sparse vector write failed")
            return IndexWriteResult(
                index_type="sparse",
                success=False,
                error=str(e),
            )

    async def _write_bm25(
        self,
        kb_id: str,
        doc_id: str,
        doc_name: str,
        chunks: List[Any],
    ) -> IndexWriteResult:
        """Write documents to Elasticsearch for BM25 search"""
        try:
            index_name = f"kb_{kb_id}"

            # Combine chunks into single document
            full_text = "\n\n".join(c.text for c in chunks)

            # Extract keywords from chunk metadata
            keywords = []
            for chunk in chunks:
                if hasattr(chunk, "metadata"):
                    if "tags" in chunk.metadata:
                        keywords.extend(chunk.metadata["tags"])

            doc = {
                "doc_id": doc_id,
                "kb_id": kb_id,
                "doc_name": doc_name,
                "title": doc_name,
                "content": full_text,
                "keywords": list(set(keywords)),
                "chunk_count": len(chunks),
            }

            await self.es_client.index_document(index_name, doc_id, doc)

            return IndexWriteResult(
                index_type="bm25",
                success=True,
                count=1,
            )
        except Exception as e:
            logger.exception("BM25 index write failed")
            return IndexWriteResult(
                index_type="bm25",
                success=False,
                error=str(e),
            )

    async def _write_kg(
        self,
        kb_id: str,
        doc_id: str,
        doc_name: str,
        entities: List[Any],
        relations: Optional[List[Any]] = None,
    ) -> IndexWriteResult:
        """Write entities and relations to Neo4j"""
        try:
            count = 0

            # Create entities as nodes
            for entity in entities:
                await self.neo4j_client.create_entity(
                    entity_id=f"{doc_id}_{entity.text}",
                    label=entity.entity_type,
                    properties={
                        "text": entity.text,
                        "doc_id": doc_id,
                        "kb_id": kb_id,
                        "doc_name": doc_name,
                        "linked_id": entity.linked_id,
                    },
                )
                count += 1

            # Create relations
            if relations:
                for rel in relations:
                    await self.neo4j_client.create_relationship(
                        source_id=f"{doc_id}_{rel.subject.text}",
                        target_id=f"{doc_id}_{rel.object.text}",
                        relation=rel.predicate,
                        source_label=rel.subject.entity_type,
                        target_label=rel.object.entity_type,
                    )
                    count += 1

            return IndexWriteResult(
                index_type="kg",
                success=True,
                count=count,
            )
        except Exception as e:
            logger.exception("KG write failed")
            return IndexWriteResult(
                index_type="kg",
                success=False,
                error=str(e),
            )

    async def _write_object(
        self,
        kb_id: str,
        doc_id: str,
        content: bytes,
    ) -> IndexWriteResult:
        """Write original document to MinIO object storage"""
        try:
            from packages.core.config import settings as app_settings

            key = f"{kb_id}/original/{doc_id}"
            self.minio_client.put_object(
                app_settings.minio_bucket,
                key,
                io.BytesIO(content),
                len(content),
                content_type="application/octet-stream",
            )

            return IndexWriteResult(
                index_type="object",
                success=True,
                count=1,
            )
        except Exception as e:
            logger.exception("Object storage write failed")
            return IndexWriteResult(
                index_type="object",
                success=False,
                error=str(e),
            )

    async def hybrid_search(
        self,
        collection_name: str,
        kb_id: str,
        query: str,
        query_embedding: List[float],
        top_k: int = 10,
        use_bm25: bool = True,
        use_sparse: bool = True,
        rrf_k: int = 60,
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search with RRF (Reciprocal Rank Fusion).

        Combines results from:
        - Dense vector search (Milvus)
        - Sparse vector search (BGE-M3)
        - BM25 full-text search (Elasticsearch)

        Args:
            collection_name: Milvus collection name
            kb_id: Knowledge base ID
            query: Search query text
            query_embedding: Query embedding vector
            top_k: Result count
            use_bm25: Whether to include BM25 results
            use_sparse: Whether to include sparse vector results
            rrf_k: RRF constant (default 60)

        Returns:
            Fused and ranked results
        """
        import asyncio

        # Run searches in parallel
        tasks = [
            self._search_dense(collection_name, query_embedding, top_k),
        ]

        if use_sparse and self.sparse_encoder:
            tasks.append(self._search_sparse(collection_name, query, top_k))

        if use_bm25 and self.es_client:
            tasks.append(self._search_bm25(kb_id, query, top_k))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Parse results
        all_results = []
        for result in results:
            if isinstance(result, list):
                all_results.append(result)
            else:
                logger.warning("Search task failed: %s", result)

        if not all_results:
            return []

        # Apply RRF fusion
        return self._rrf_fusion(all_results, rrf_k, top_k)

    async def _search_dense(
        self,
        collection_name: str,
        query_embedding: List[float],
        top_k: int,
    ) -> List[Tuple[str, float, Dict]]:
        """Dense vector search"""
        from packages.rag.services.vector_store_service import search_vectors

        results = search_vectors(
            self.milvus_client,
            collection_name,
            query_embedding,
            top_k,
        )

        return [
            (r["chunk_id"], r["score"], r)
            for r in results
        ]

    async def _search_sparse(
        self,
        collection_name: str,
        query: str,
        top_k: int,
    ) -> List[Tuple[str, float, Dict]]:
        """Sparse vector search"""
        try:
            # Generate sparse embedding for query
            sparse_emb = await self.sparse_encoder.encode_sparse([query])

            # Search in Milvus
            sparse_dict = {
                str(k): v for k, v in zip(sparse_emb[0].indices, sparse_emb[0].values)
            }

            results = self.milvus_client.search(
                collection_name=f"{collection_name}_sparse",
                data=[sparse_dict],
                limit=top_k,
                output_fields=["chunk_id", "text", "doc_name"],
            )

            return [
                (hit["entity"]["chunk_id"], hit["distance"], dict(hit["entity"]))
                for result in results
                for hit in result
            ]
        except Exception as e:
            logger.warning("Sparse search failed: %s", e)
            return []

    async def _search_bm25(
        self,
        kb_id: str,
        query: str,
        top_k: int,
    ) -> List[Tuple[str, float, Dict]]:
        """BM25 full-text search"""
        try:
            index_name = f"kb_{kb_id}"
            results = await self.es_client.search(index_name, query, size=top_k)

            return [
                (r["id"], r["score"], r["source"])
                for r in results
            ]
        except Exception as e:
            logger.warning("BM25 search failed: %s", e)
            return []

    def _rrf_fusion(
        self,
        result_lists: List[List[Tuple[str, float, Dict]]],
        k: int = 60,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Reciprocal Rank Fusion (RRF) to combine multiple result lists.

        RRF formula: score = sum(1 / (k + rank)) for each result

        Args:
            result_lists: List of result lists, each containing (id, score, metadata)
            k: RRF constant (default 60)
            top_k: Number of results to return

        Returns:
            Fused and ranked results
        """
        # Calculate RRF scores
        rrf_scores: Dict[str, float] = {}
        result_map: Dict[str, Dict] = {}

        for results in result_lists:
            for rank, (item_id, score, metadata) in enumerate(results):
                rrf_score = 1.0 / (k + rank)
                rrf_scores[item_id] = rrf_scores.get(item_id, 0) + rrf_score

                # Keep first metadata seen
                if item_id not in result_map:
                    result_map[item_id] = {
                        "chunk_id": item_id,
                        "score": score,
                        "metadata": metadata,
                    }

        # Sort by RRF score
        sorted_items = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

        # Build final results
        final_results = []
        for item_id, rrf_score in sorted_items[:top_k]:
            result = result_map[item_id]
            result["rrf_score"] = rrf_score
            final_results.append(result)

        return final_results


# Global instance
_multi_index_service: Optional[MultiIndexService] = None


def get_multi_index_service(
    milvus_client=None,
    sparse_encoder=None,
    es_client=None,
    neo4j_client=None,
    minio_client=None,
    config: Optional[Dict[str, Any]] = None,
) -> MultiIndexService:
    """Get or create multi-index service"""
    global _multi_index_service
    if _multi_index_service is None:
        _multi_index_service = MultiIndexService(
            milvus_client=milvus_client,
            sparse_encoder=sparse_encoder,
            es_client=es_client,
            neo4j_client=neo4j_client,
            minio_client=minio_client,
            config=config,
        )
    return _multi_index_service


def reset_multi_index_service():
    """Reset the global service instance"""
    global _multi_index_service
    _multi_index_service = None
