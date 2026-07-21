"""
RRF (Reciprocal Rank Fusion) 融合排序服务
结合多路检索结果（Vector + BM25 + Sparse）进行融合排序
"""
from __future__ import annotations
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict

logger = logging.getLogger("app.services.rrf")


@dataclass
class SearchResult:
    """搜索结果项"""
    chunk_id: str
    doc_id: str
    kb_id: str
    text: str
    doc_name: str
    score: float
    source: str  # dense, bm25, sparse
    rank: int = 0
    rrf_score: float = 0.0
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class RRFFusion:
    """
    RRF 融合排序
    Reciprocal Rank Fusion: score = 1 / (k + rank)
    """

    def __init__(self, k: int = 60):
        """
        Args:
            k: RRF 常数，用于调节排名权重
               - 较小的 k 更重视排名靠前的结果
               - 较大的 k 更平滑
        """
        self.k = k

    def fuse(
        self,
        result_lists: List[List[SearchResult]],
        top_k: int = 10,
    ) -> List[SearchResult]:
        """
        融合多路检索结果

        Args:
            result_lists: 多路检索结果列表 [[result1, result2...], [result1, result2...], ...]
            top_k: 返回前 K 个结果

        Returns:
            融合后的排序结果
        """
        # 计算每个结果的 RRF 分数
        rrf_scores: Dict[str, float] = defaultdict(float)
        result_map: Dict[str, SearchResult] = {}

        for results in result_lists:
            for rank, result in enumerate(results):
                # RRF 分数 = 1 / (k + rank)
                rrf_score = 1.0 / (self.k + rank)
                rrf_scores[result.chunk_id] += rrf_score

                # 保存第一个出现的结果（包含完整信息）
                if result.chunk_id not in result_map:
                    result_map[result.chunk_id] = result

        # 按 RRF 分数排序
        sorted_items = sorted(
            rrf_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )

        # 构建最终结果
        final_results = []
        for chunk_id, rrf_score in sorted_items[:top_k]:
            result = result_map[chunk_id]
            result.rrf_score = rrf_score
            final_results.append(result)

        return final_results

    def fuse_with_weights(
        self,
        result_lists: List[Tuple[List[SearchResult], float]],
        top_k: int = 10,
    ) -> List[SearchResult]:
        """
        带权重的 RRF 融合

        Args:
            result_lists: [(results, weight), ...]
            top_k: 返回前 K 个结果

        Returns:
            融合后的排序结果
        """
        rrf_scores: Dict[str, float] = defaultdict(float)
        result_map: Dict[str, SearchResult] = {}

        for results, weight in result_lists:
            for rank, result in enumerate(results):
                rrf_score = weight / (self.k + rank)
                rrf_scores[result.chunk_id] += rrf_score

                if result.chunk_id not in result_map:
                    result_map[result.chunk_id] = result

        sorted_items = sorted(
            rrf_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )

        final_results = []
        for chunk_id, rrf_score in sorted_items[:top_k]:
            result = result_map[chunk_id]
            result.rrf_score = rrf_score
            final_results.append(result)

        return final_results


class HybridSearchService:
    """
    混合检索服务
    整合 Vector + BM25 + Sparse 三路检索 + RRF 融合
    """

    def __init__(
        self,
        milvus_client=None,
        es_client=None,
        sparse_encoder=None,
        rrf_k: int = 60,
    ):
        self.milvus = milvus_client
        self.es_client = es_client
        self.sparse_encoder = sparse_encoder
        self.rrf = RRFFusion(k=rrf_k)

    async def hybrid_search(
        self,
        collection_name: str,
        kb_id: str,
        query: str,
        query_embedding: List[float],
        top_k: int = 10,
        use_dense: bool = True,
        use_bm25: bool = True,
        use_sparse: bool = False,
        weights: Optional[Dict[str, float]] = None,
    ) -> List[SearchResult]:
        """
        执行混合检索

        Args:
            collection_name: Milvus 集合名
            kb_id: 知识库 ID
            query: 查询文本
            query_embedding: 查询向量
            top_k: 返回数量
            use_dense: 使用稠密向量检索
            use_bm25: 使用 BM25 检索
            use_sparse: 使用稀疏向量检索
            weights: 各路径权重 {"dense": 1.0, "bm25": 0.8, "sparse": 0.6}

        Returns:
            融合后的搜索结果
        """
        import asyncio

        # 默认权重
        if weights is None:
            weights = {"dense": 1.0, "bm25": 0.8, "sparse": 0.6}

        # 并行执行多路检索
        tasks = []

        if use_dense and self.milvus:
            tasks.append(self._search_dense(
                collection_name, query_embedding, top_k * 2, weights.get("dense", 1.0)
            ))

        if use_bm25 and self.es_client:
            tasks.append(self._search_bm25(
                kb_id, query, top_k * 2, weights.get("bm25", 0.8)
            ))

        if use_sparse and self.sparse_encoder and self.milvus:
            tasks.append(self._search_sparse(
                collection_name, query, top_k * 2, weights.get("sparse", 0.6)
            ))

        if not tasks:
            logger.warning("No search methods enabled")
            return []

        # 等待所有检索完成
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        valid_results = []
        for result in results:
            if isinstance(result, list):
                valid_results.append(result)
            else:
                logger.warning("Search task failed: %s", result)

        if not valid_results:
            return []

        # 如果只有一路结果，直接返回
        if len(valid_results) == 1:
            return valid_results[0][:top_k]

        # RRF 融合
        fused = self.rrf.fuse(valid_results, top_k)
        return fused

    async def _search_dense(
        self,
        collection_name: str,
        query_embedding: List[float],
        top_k: int,
        weight: float = 1.0,
    ) -> List[SearchResult]:
        """稠密向量检索"""
        try:
            from app.services.vector_store_service import search_vectors

            results = search_vectors(
                self.milvus,
                collection_name,
                query_embedding,
                top_k,
            )

            return [
                SearchResult(
                    chunk_id=r.get("chunk_id", ""),
                    doc_id=r.get("metadata", {}).get("doc_id", ""),
                    kb_id=r.get("metadata", {}).get("kb_id", ""),
                    text=r.get("content", ""),
                    doc_name=r.get("metadata", {}).get("doc_name", ""),
                    score=r.get("score", 0) * weight,
                    source="dense",
                    rank=i,
                    metadata=r.get("metadata", {}),
                )
                for i, r in enumerate(results)
            ]
        except Exception as e:
            logger.exception("Dense search failed")
            return []

    async def _search_bm25(
        self,
        kb_id: str,
        query: str,
        top_k: int,
        weight: float = 0.8,
    ) -> List[SearchResult]:
        """BM25 全文检索"""
        try:
            if not self.es_client:
                return []

            index_name = f"kb_{kb_id}"
            results = await self.es_client.search(index_name, query, size=top_k)

            return [
                SearchResult(
                    chunk_id=r["id"],
                    doc_id=r["source"].get("doc_id", ""),
                    kb_id=r["source"].get("kb_id", ""),
                    text=r["source"].get("content", ""),
                    doc_name=r["source"].get("doc_name", ""),
                    score=r["score"] * weight,
                    source="bm25",
                    rank=i,
                    metadata=r["source"],
                )
                for i, r in enumerate(results)
            ]
        except Exception as e:
            logger.exception("BM25 search failed")
            return []

    async def _search_sparse(
        self,
        collection_name: str,
        query: str,
        top_k: int,
        weight: float = 0.6,
    ) -> List[SearchResult]:
        """稀疏向量检索"""
        try:
            if not self.sparse_encoder or not self.milvus:
                return []

            # 生成稀疏向量
            sparse_emb = await self.sparse_encoder.encode_sparse([query])
            sparse_dict = {
                str(k): v for k, v in zip(sparse_emb[0].indices, sparse_emb[0].values)
            }

            # 搜索
            results = self.milvus.search(
                collection_name=f"{collection_name}_sparse",
                data=[sparse_dict],
                limit=top_k,
                output_fields=["chunk_id", "text", "doc_id", "kb_id", "doc_name"],
            )

            return [
                SearchResult(
                    chunk_id=hit["entity"].get("chunk_id", ""),
                    doc_id=hit["entity"].get("doc_id", ""),
                    kb_id=hit["entity"].get("kb_id", ""),
                    text=hit["entity"].get("text", ""),
                    doc_name=hit["entity"].get("doc_name", ""),
                    score=hit["distance"] * weight,
                    source="sparse",
                    rank=i,
                    metadata=hit["entity"],
                )
                for i, hit in enumerate(results[0]) if results
            ]
        except Exception as e:
            logger.exception("Sparse search failed")
            return []


# ============================================================
# 简化的 RRF 工具函数（用于现有代码集成）
# ============================================================

def rrf_fusion(
    result_lists: List[List[Dict[str, Any]]],
    top_k: int = 10,
    k: int = 60,
    id_field: str = "chunk_id",
) -> List[Dict[str, Any]]:
    """
    简化的 RRF 融合函数（用于快速集成到现有代码）

    Args:
        result_lists: 多路检索结果列表
        top_k: 返回数量
        k: RRF 常数
        id_field: 用于去重的 ID 字段

    Returns:
        融合后的结果
    """
    rrf_scores: Dict[str, float] = defaultdict(float)
    result_map: Dict[str, Dict[str, Any]] = {}

    for results in result_lists:
        for rank, result in enumerate(results):
            item_id = result.get(id_field, "")
            if not item_id:
                continue

            rrf_score = 1.0 / (k + rank)
            rrf_scores[item_id] += rrf_score

            if item_id not in result_map:
                result_map[item_id] = result.copy()

    # 排序
    sorted_items = sorted(
        rrf_scores.items(),
        key=lambda x: x[1],
        reverse=True
    )

    # 构建结果
    final_results = []
    for item_id, rrf_score in sorted_items[:top_k]:
        result = result_map[item_id]
        result["rrf_score"] = rrf_score
        final_results.append(result)

    return final_results


def weighted_rrf_fusion(
    result_lists: List[Tuple[List[Dict[str, Any]], float]],
    top_k: int = 10,
    k: int = 60,
    id_field: str = "chunk_id",
) -> List[Dict[str, Any]]:
    """
    带权重的 RRF 融合

    Args:
        result_lists: [(results, weight), ...]
        top_k: 返回数量
        k: RRF 常数
        id_field: 用于去重的 ID 字段

    Returns:
        融合后的结果
    """
    rrf_scores: Dict[str, float] = defaultdict(float)
    result_map: Dict[str, Dict[str, Any]] = {}

    for results, weight in result_lists:
        for rank, result in enumerate(results):
            item_id = result.get(id_field, "")
            if not item_id:
                continue

            rrf_score = weight / (k + rank)
            rrf_scores[item_id] += rrf_score

            if item_id not in result_map:
                result_map[item_id] = result.copy()

    sorted_items = sorted(
        rrf_scores.items(),
        key=lambda x: x[1],
        reverse=True
    )

    final_results = []
    for item_id, rrf_score in sorted_items[:top_k]:
        result = result_map[item_id]
        result["rrf_score"] = rrf_score
        final_results.append(result)

    return final_results


# Global instance
_hybrid_search_service: Optional[HybridSearchService] = None


def get_hybrid_search_service(
    milvus_client=None,
    es_client=None,
    sparse_encoder=None,
) -> HybridSearchService:
    """Get or create hybrid search service"""
    global _hybrid_search_service
    if _hybrid_search_service is None:
        _hybrid_search_service = HybridSearchService(
            milvus_client=milvus_client,
            es_client=es_client,
            sparse_encoder=sparse_encoder,
        )
    return _hybrid_search_service
