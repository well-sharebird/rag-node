"""
MMR (Maximal Marginal Relevance) 多样性采样服务
平衡检索结果的相关性和多样性，避免返回过于相似的内容
"""
from __future__ import annotations
import logging
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

logger = logging.getLogger("app.services.mmr")


def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """计算两个向量的余弦相似度"""
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(np.dot(vec1, vec2) / (norm1 * norm2))


def mmr_select(
    query_embedding: np.ndarray,
    candidate_embeddings: List[np.ndarray],
    candidates: List[Dict[str, Any]],
    lambda_param: float = 0.5,
    k: int = 5,
) -> List[Dict[str, Any]]:
    """
    使用 MMR 算法选择多样化且相关的结果。

    MMR 公式:
    MMR = argmax [ λ * Relevance(query, doc) - (1-λ) * max(Similarity(doc, selected_docs)) ]

    Args:
        query_embedding: 查询向量
        candidate_embeddings: 候选文档的向量列表
        candidates: 候选文档列表（包含元数据）
        lambda_param: 相关性/多样性权衡参数 (0-1)
            - 1.0: 只考虑相关性（退化为普通检索）
            - 0.5: 相关性和多样性平衡（推荐）
            - 0.0: 只考虑多样性
        k: 返回结果数量

    Returns:
        经过 MMR 选择的结果列表
    """
    if not candidates or not candidate_embeddings:
        return []

    k = min(k, len(candidates))
    if k <= 0:
        return []

    # 如果只有一个候选，直接返回
    if len(candidates) == 1:
        return [candidates[0]]

    # 转换为 numpy 数组
    query_vec = np.array(query_embedding)
    emb_array = np.array(candidate_embeddings)

    # 计算所有候选与查询的相似度
    query_similarities = np.array([
        cosine_similarity(query_vec, emb) for emb in emb_array
    ])

    # 已选中的索引
    selected_indices: List[int] = []
    # 未选中的索引
    remaining_indices = list(range(len(candidates)))

    # 首先选择与查询最相似的文档
    first_idx = int(np.argmax(query_similarities))
    selected_indices.append(first_idx)
    remaining_indices.remove(first_idx)

    # 迭代选择剩余文档
    while len(selected_indices) < k and remaining_indices:
        best_mmr_score = float('-inf')
        best_idx = remaining_indices[0]

        for idx in remaining_indices:
            # 相关性分数
            relevance = query_similarities[idx]

            # 多样性分数（与已选文档的最大相似度）
            diversity = max([
                cosine_similarity(emb_array[idx], emb_array[selected_idx])
                for selected_idx in selected_indices
            ]) if selected_indices else 0.0

            # MMR 分数
            mmr_score = lambda_param * relevance - (1 - lambda_param) * diversity

            if mmr_score > best_mmr_score:
                best_mmr_score = mmr_score
                best_idx = idx

        selected_indices.append(best_idx)
        remaining_indices.remove(best_idx)

    # 返回选中的文档
    return [candidates[i] for i in selected_indices]


def apply_mmr_to_results(
    query_embedding: List[float],
    results: List[Dict[str, Any]],
    embedding_field: str = "embedding",
    lambda_param: float = 0.5,
    k: int = 5,
) -> List[Dict[str, Any]]:
    """
    对检索结果应用 MMR 重排序。

    Args:
        query_embedding: 查询向量
        results: 检索结果列表（需要包含 embedding 字段）
        embedding_field: 向量字段名
        lambda_param: MMR 参数
        k: 返回结果数量

    Returns:
        经过 MMR 重排序的结果
    """
    if not results:
        return []

    # 提取向量
    embeddings = []
    for result in results:
        emb = result.get(embedding_field)
        if emb is None:
            logger.warning("Result missing embedding field: %s", result.get("id", "unknown"))
            continue
        embeddings.append(np.array(emb))

    if not embeddings:
        return []

    # 应用 MMR
    selected = mmr_select(
        query_embedding=np.array(query_embedding),
        candidate_embeddings=embeddings,
        candidates=results,
        lambda_param=lambda_param,
        k=k,
    )

    return selected


def compute_diversity_score(results: List[Dict[str, Any]], embedding_field: str = "embedding") -> float:
    """
    计算结果集的多样性分数（平均成对余弦距离）。

    Returns:
        0-1 之间的分数，1 表示最多样化
    """
    if len(results) < 2:
        return 1.0

    embeddings = []
    for result in results:
        emb = result.get(embedding_field)
        if emb is not None:
            embeddings.append(np.array(emb))

    if len(embeddings) < 2:
        return 1.0

    # 计算所有成对相似度
    similarities = []
    for i in range(len(embeddings)):
        for j in range(i + 1, len(embeddings)):
            sim = cosine_similarity(embeddings[i], embeddings[j])
            similarities.append(sim)

    if not similarities:
        return 1.0

    # 返回平均距离（1 - 相似度）
    avg_similarity = np.mean(similarities)
    return 1.0 - avg_similarity


# ============================================================
# 带 MMR 的检索服务封装
# ============================================================

class MMRService:
    """MMR 检索服务"""

    def __init__(self, milvus_client=None):
        self.milvus_client = milvus_client

    def search_with_mmr(
        self,
        collection_name: str,
        query_embedding: List[float],
        k: int = 10,
        mmr_k: int = 5,
        lambda_param: float = 0.5,
        filter_expr: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        执行带 MMR 多样性采样的检索。

        Args:
            collection_name: 集合名称
            query_embedding: 查询向量
            k: 初始检索数量（应该大于 mmr_k）
            mmr_k: 最终返回数量
            lambda_param: MMR 参数
            filter_expr: Milvus 过滤表达式

        Returns:
            经过 MMR 选择的结果
        """
        if self.milvus_client is None:
            logger.error("Milvus client not available")
            return []

        # 第一步：检索更多候选（k 应该大于 mmr_k）
        search_k = max(k, mmr_k * 3)  # 获取 3 倍数量的候选

        try:
            results = self.milvus_client.search(
                collection_name=collection_name,
                data=[query_embedding],
                limit=search_k,
                filter=filter_expr,
                output_fields=["chunk_id", "text", "doc_id", "doc_name", "kb_id"],
            )

            # 格式化结果
            formatted_results = []
            for result in results[0] if results else []:
                formatted_results.append({
                    "chunk_id": result["entity"].get("chunk_id", ""),
                    "text": result["entity"].get("text", ""),
                    "doc_id": result["entity"].get("doc_id", ""),
                    "doc_name": result["entity"].get("doc_name", ""),
                    "kb_id": result["entity"].get("kb_id", ""),
                    "score": result["distance"],
                    "embedding": result["entity"].get("vector", query_embedding),  # 如果有存储
                })

            # 如果没有 embedding，使用分数作为替代
            if formatted_results and "embedding" not in formatted_results[0]:
                logger.warning("No embeddings in results, using score-based MMR fallback")
                # 简化的 MMR：基于分数排序，跳过过于相似的结果
                return self._score_based_diversify(formatted_results, mmr_k)

            # 应用 MMR
            mmr_results = apply_mmr_to_results(
                query_embedding=query_embedding,
                results=formatted_results,
                embedding_field="embedding",
                lambda_param=lambda_param,
                k=mmr_k,
            )

            return mmr_results

        except Exception as e:
            logger.exception("MMR search failed")
            return []

    def _score_based_diversify(
        self,
        results: List[Dict[str, Any]],
        k: int,
    ) -> List[Dict[str, Any]]:
        """
        基于分数的简化多样性选择（当没有 embedding 时的 fallback）。
        使用滑动窗口避免连续选择相似文档。
        """
        if len(results) <= k:
            return results

        # 按分数排序
        sorted_results = sorted(results, key=lambda x: x.get("score", 0), reverse=True)

        # 简单多样性：每隔几个选一个
        step = max(1, len(sorted_results) // k)
        selected = []

        for i in range(0, len(sorted_results), step):
            if len(selected) >= k:
                break
            selected.append(sorted_results[i])

        # 如果没选够，从剩余中选
        if len(selected) < k:
            remaining = [r for r in sorted_results if r not in selected]
            selected.extend(remaining[:k - len(selected)])

        return selected[:k]


# Global instance
_mmr_service: Optional[MMRService] = None


def get_mmr_service(milvus_client=None) -> MMRService:
    """Get or create MMR service"""
    global _mmr_service
    if _mmr_service is None:
        _mmr_service = MMRService(milvus_client)
    return _mmr_service
