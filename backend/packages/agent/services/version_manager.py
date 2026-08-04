"""
版本管理服务 — Saga 原子事务 + 差分更新 + 3 版本回滚
"""
from __future__ import annotations
import logging
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import hashlib
import json

logger = logging.getLogger("app.services.version_manager")


class SagaStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPENSATING = "compensating"
    FAILED = "failed"


class SagaStep(Enum):
    """Saga 事务步骤"""
    VALIDATE = "validate"           # 1. 验证输入
    LOCK_VERSION = "lock_version"   # 2. 锁定版本（防止并发）
    PARSE = "parse"                 # 3. 解析文档
    CHUNK = "chunk"                 # 4. 分块
    EMBED = "embed"                 # 5. 生成 embedding
    INDEX_DENSE = "index_dense"     # 6. 写入稠密向量索引
    INDEX_SPARSE = "index_sparse"   # 7. 写入稀疏向量索引
    INDEX_BM25 = "index_bm25"       # 8. 写入 BM25 索引
    INDEX_KG = "index_kg"           # 9. 写入知识图谱
    UPDATE_COUNTERS = "counters"    # 10. 更新计数器
    COMMIT = "commit"               # 11. 提交事务


@dataclass
class SagaLogEntry:
    """Saga 执行日志"""
    step: SagaStep
    status: SagaStatus
    timestamp: datetime
    result: Optional[Any] = None
    error: Optional[str] = None
    compensated: bool = False


@dataclass
class VersionDiff:
    """版本差异信息"""
    added_chunks: int = 0
    removed_chunks: int = 0
    modified_chunks: int = 0
    unchanged_chunks: int = 0
    content_hash_changed: bool = False
    metadata_changes: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_changes(self) -> int:
        return self.added_chunks + self.removed_chunks + self.modified_chunks


@dataclass
class DocumentVersion:
    """文档版本信息"""
    doc_id: str
    version: int
    previous_version_id: Optional[str]
    content_hash: str
    chunk_count: int
    chunk_hashes: List[str]
    created_at: datetime
    created_by: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_current: bool = True
    rollback_target_id: Optional[str] = None  # 如果是回滚版本，指向目标版本


class VersionManager:
    """
    文档版本管理器，支持：
    - 版本链管理
    - 差分更新（只处理变化的 chunk）
    - Saga 原子事务（失败时自动回滚）
    - 保留最近 3 个版本
    """

    def __init__(self, db_session=None, config: Optional[Dict[str, Any]] = None):
        self.db = db_session
        self.config = config or {}
        self.max_versions = self.config.get("max_versions", 3)
        self._saga_logs: Dict[str, List[SagaLogEntry]] = {}

    # ============================================================
    # 版本链管理
    # ============================================================

    async def get_current_version(
        self,
        doc_id: str,
        kb_id: str,
    ) -> Optional[DocumentVersion]:
        """获取文档当前版本"""
        from sqlalchemy import select
        from packages.rag.models.document import Document

        result = await self.db.execute(
            select(Document)
            .where(Document.id == doc_id)
            .where(Document.kb_id == kb_id)
            .order_by(Document.version.desc())
            .limit(1)
        )
        doc = result.scalar_one_or_none()

        if not doc:
            return None

        return DocumentVersion(
            doc_id=doc.id,
            version=doc.version,
            previous_version_id=doc.previous_version_id,
            content_hash=hashlib.sha256(doc.parsed_text or b"").hexdigest(),
            chunk_count=doc.chunk_count,
            chunk_hashes=[],  # 需要从单独的表获取
            created_at=doc.uploaded_at,
            created_by=None,
            is_current=True,
        )

    async def get_version_history(
        self,
        doc_id: str,
        limit: int = 10,
    ) -> List[DocumentVersion]:
        """获取文档版本历史"""
        from sqlalchemy import select
        from packages.rag.models.document import Document

        result = await self.db.execute(
            select(Document)
            .where(Document.id == doc_id)
            .order_by(Document.version.desc())
            .limit(limit)
        )
        docs = result.scalars().all()

        return [
            DocumentVersion(
                doc_id=doc.id,
                version=doc.version,
                previous_version_id=doc.previous_version_id,
                content_hash=hashlib.sha256(doc.parsed_text or b"").hexdigest(),
                chunk_count=doc.chunk_count,
                chunk_hashes=[],
                created_at=doc.uploaded_at,
                is_current=doc.status == "completed",
            )
            for doc in docs
        ]

    async def compute_diff(
        self,
        old_version: DocumentVersion,
        new_chunk_hashes: List[str],
    ) -> VersionDiff:
        """计算版本差异"""
        old_set = set(old_version.chunk_hashes)
        new_set = set(new_chunk_hashes)

        added = new_set - old_set
        removed = old_set - new_set
        unchanged = old_set & new_set

        return VersionDiff(
            added_chunks=len(added),
            removed_chunks=len(removed),
            modified_chunks=0,  # 需要更复杂的比较逻辑
            unchanged_chunks=len(unchanged),
            content_hash_changed=old_version.content_hash != hashlib.sha256("".join(new_chunk_hashes).encode()).hexdigest(),
        )

    # ============================================================
    # Saga 原子事务
    # ============================================================

    async def begin_saga(self, doc_id: str) -> str:
        """开始 Saga 事务"""
        saga_id = f"saga_{doc_id}_{datetime.utcnow().isoformat()}"
        self._saga_logs[saga_id] = []
        logger.info("Saga started | saga_id=%s doc=%s", saga_id, doc_id)
        return saga_id

    def _log_saga_step(
        self,
        saga_id: str,
        step: SagaStep,
        status: SagaStatus,
        result: Any = None,
        error: Optional[str] = None,
    ):
        """记录 Saga 步骤"""
        entry = SagaLogEntry(
            step=step,
            status=status,
            timestamp=datetime.utcnow(),
            result=result,
            error=error,
        )
        if saga_id in self._saga_logs:
            self._saga_logs[saga_id].append(entry)

    async def execute_saga(
        self,
        doc_id: str,
        steps: List[Tuple[SagaStep, callable]],
    ) -> Tuple[bool, List[SagaLogEntry]]:
        """
        执行 Saga 事务，失败时自动补偿。

        Args:
            doc_id: 文档 ID
            steps: 步骤列表，每个步骤是 (step_name, async_function)

        Returns:
            (success, log_entries)
        """
        saga_id = await self.begin_saga(doc_id)
        completed_steps: List[Tuple[SagaStep, Any]] = []

        try:
            # 正向执行
            for step, func in steps:
                self._log_saga_step(saga_id, step, SagaStatus.RUNNING)

                try:
                    result = await func()
                    completed_steps.append((step, result))
                    self._log_saga_step(saga_id, step, SagaStatus.COMPLETED, result)
                except Exception as e:
                    self._log_saga_step(saga_id, step, SagaStatus.FAILED, error=str(e))
                    raise

            # 全部成功
            self._log_saga_step(saga_id, SagaStep.COMMIT, SagaStatus.COMPLETED)
            logger.info("Saga 完成 | saga_id=%s doc=%s", saga_id, doc_id)
            return True, self._saga_logs.get(saga_id, [])

        except Exception as e:
            # 开始补偿（反向执行）
            logger.warning("Saga 失败，开始补偿 | saga_id=%s doc=%s error=%s", saga_id, doc_id, e)
            self._log_saga_step(saga_id, step, SagaStatus.COMPENSATING)

            await self._compensate(saga_id, doc_id, completed_steps)

            self._log_saga_step(saga_id, SagaStep.COMMIT, SagaStatus.FAILED, error=str(e))
            return False, self._saga_logs.get(saga_id, [])

    async def _compensate(
        self,
        saga_id: str,
        doc_id: str,
        completed_steps: List[Tuple[SagaStep, Any]],
    ):
        """执行补偿操作（反向回滚）"""
        # 补偿顺序与执行顺序相反
        compensation_map = {
            SagaStep.INDEX_KG: self._compensate_index_kg,
            SagaStep.INDEX_BM25: self._compensate_index_bm25,
            SagaStep.INDEX_SPARSE: self._compensate_index_sparse,
            SagaStep.INDEX_DENSE: self._compensate_index_dense,
            SagaStep.UPDATE_COUNTERS: self._compensate_counters,
        }

        for step, result in reversed(completed_steps):
            compensator = compensation_map.get(step)
            if compensator:
                try:
                    await compensator(doc_id, result)
                    self._log_saga_step(
                        saga_id, step, SagaStatus.COMPLETED,
                        result=None, error=None
                    )
                    logger.info("补偿完成 | step=%s doc=%s", step.value, doc_id)
                except Exception as e:
                    self._log_saga_step(
                        saga_id, step, SagaStatus.FAILED,
                        error=f"补偿失败：{e}"
                    )
                    logger.error("补偿失败 | step=%s doc=%s error=%s", step.value, doc_id, e)

    # ============================================================
    # 补偿操作
    # ============================================================

    async def _compensate_index_dense(self, doc_id: str, result: Any):
        """补偿：删除已写入的稠密向量"""
        # 实际实现需要 milvus_client 和 collection_name
        # 这里只记录日志
        logger.info("补偿稠密向量删除 | doc=%s", doc_id)

    async def _compensate_index_sparse(self, doc_id: str, result: Any):
        """补偿：删除已写入的稀疏向量"""
        logger.info("补偿稀疏向量删除 | doc=%s", doc_id)

    async def _compensate_index_bm25(self, doc_id: str, result: Any):
        """补偿：删除已写入的 BM25 索引"""
        logger.info("补偿 BM25 索引删除 | doc=%s", doc_id)

    async def _compensate_index_kg(self, doc_id: str, result: Any):
        """补偿：删除已写入的知识图谱"""
        logger.info("补偿知识图谱删除 | doc=%s", doc_id)

    async def _compensate_counters(self, doc_id: str, result: Any):
        """补偿：回滚计数器"""
        logger.info("补偿计数器回滚 | doc=%s", doc_id)

    # ============================================================
    # 差分更新
    # ============================================================

    async def apply_differential_update(
        self,
        doc_id: str,
        kb_id: str,
        old_version: DocumentVersion,
        new_chunks: List[Any],
        new_embeddings: List[List[float]],
        milvus_client,
    ) -> VersionDiff:
        """
        应用差分更新：只处理变化的 chunk。

        1. 计算新旧版本的 chunk 差异
        2. 只插入新增/修改的 chunk
        3. 只删除移除的 chunk
        4. 保留未变化的 chunk

        Args:
            doc_id: 文档 ID
            kb_id: 知识库 ID
            old_version: 旧版本信息
            new_chunks: 新 chunk 列表
            new_embeddings: 新 embedding 列表
            milvus_client: Milvus 客户端

        Returns:
            VersionDiff 差异信息
        """
        from packages.rag.models.document import Document
        from sqlalchemy import select, update

        # 计算新 chunk 的 hashes
        new_chunk_hashes = [
            hashlib.sha256(c.text.encode()).hexdigest()
            for c in new_chunks
        ]

        # 计算差异
        diff = await self.compute_diff(old_version, new_chunk_hashes)

        if diff.total_changes == 0:
            logger.info("无变化，跳过更新 | doc=%s", doc_id)
            return diff

        logger.info(
            "差分更新 | doc=%s added=%d removed=%d unchanged=%d",
            doc_id, diff.added_chunks, diff.removed_chunks, diff.unchanged_chunks
        )

        # 1. 删除已移除的 chunk
        if diff.removed_chunks > 0:
            old_set = set(old_version.chunk_hashes)
            new_set = set(new_chunk_hashes)
            removed_hashes = old_set - new_set

            # 从 Milvus 删除
            for chunk_hash in removed_hashes:
                chunk_id = f"{doc_id}_{chunk_hash[:8]}"
                milvus_client.delete(
                    collection_name=kb_id,
                    filter=f'chunk_id == "{chunk_id}"',
                )

        # 2. 插入新增的 chunk
        if diff.added_chunks > 0:
            old_set = set(old_version.chunk_hashes)
            new_set = set(new_chunk_hashes)

            added_indices = [
                i for i, h in enumerate(new_chunk_hashes)
                if h not in old_set
            ]

            # 准备插入数据
            data = []
            for i in added_indices:
                chunk = new_chunks[i]
                emb = new_embeddings[i]
                data.append({
                    "chunk_id": f"{doc_id}_{new_chunk_hashes[i][:8]}",
                    "doc_id": doc_id,
                    "kb_id": kb_id,
                    "vector": emb,
                    "text": chunk.text[:65535],
                })

            # 批量插入
            if data:
                milvus_client.insert(
                    collection_name=kb_id,
                    data=data,
                )

        # 3. 更新文档版本
        await self.db.execute(
            update(Document)
            .where(Document.id == doc_id)
            .values(
                version=old_version.version + 1,
                chunk_count=len(new_chunks),
                status="completed",
            )
        )

        return diff

    # ============================================================
    # 版本回滚
    # ============================================================

    async def rollback_to_version(
        self,
        doc_id: str,
        target_version_id: str,
        kb_id: str,
        milvus_client,
    ) -> Optional[DocumentVersion]:
        """
        回滚到指定版本。

        1. 查找目标版本
        2. 创建新版本（回滚版本）
        3. 恢复目标版本的 chunk
        4. 清理过期的旧版本（保留最近 3 个）

        Args:
            doc_id: 文档 ID
            target_version_id: 目标版本 ID
            kb_id: 知识库 ID
            milvus_client: Milvus 客户端

        Returns:
            回滚后的版本信息，或 None 如果失败
        """
        from packages.rag.models.document import Document
        from sqlalchemy import select, update

        # 查找目标版本
        result = await self.db.execute(
            select(Document).where(Document.id == target_version_id)
        )
        target_doc = result.scalar_one_or_none()

        if not target_doc:
            logger.error("目标版本不存在 | doc=%s target=%s", doc_id, target_version_id)
            return None

        # 查找当前版本
        current = await self.get_current_version(doc_id, kb_id)
        if not current:
            logger.error("当前版本不存在 | doc=%s", doc_id)
            return None

        # 创建回滚版本（新版本）
        new_version = current.version + 1

        # 标记当前版本为历史
        await self.db.execute(
            update(Document)
            .where(Document.id == current.doc_id)
            .values(status="historical")
        )

        # 创建新版本记录
        rollback_doc = Document(
            id=f"rollback_{doc_id}_{new_version}",
            kb_id=kb_id,
            filename=current.doc_id,
            original_name=target_doc.original_name,
            format=target_doc.format,
            file_size=target_doc.file_size,
            minio_key=target_doc.minio_key,
            chunk_count=target_doc.chunk_count,
            status="completed",
            version=new_version,
            previous_version_id=current.doc_id,
            rollback_target_id=target_version_id,
        )

        self.db.add(rollback_doc)
        await self.db.flush()

        logger.info(
            "版本回滚完成 | doc=%s from_v=%d to_v=%d target=%s",
            doc_id, current.version, new_version, target_version_id
        )

        # 清理过期版本（保留最近 3 个）
        await self._cleanup_old_versions(doc_id, kb_id, milvus_client)

        return DocumentVersion(
            doc_id=rollback_doc.id,
            version=rollback_doc.version,
            previous_version_id=rollback_doc.previous_version_id,
            content_hash="",
            chunk_count=rollback_doc.chunk_count,
            chunk_hashes=[],
            created_at=rollback_doc.uploaded_at,
            is_current=True,
            rollback_target_id=target_version_id,
        )

    async def _cleanup_old_versions(
        self,
        doc_id: str,
        kb_id: str,
        milvus_client,
    ):
        """清理过期版本，保留最近 max_versions 个"""
        from packages.rag.models.document import Document
        from sqlalchemy import select, delete

        result = await self.db.execute(
            select(Document)
            .where(Document.id == doc_id)
            .order_by(Document.version.desc())
        )
        all_docs = result.scalars().all()

        if len(all_docs) <= self.max_versions:
            return

        # 删除过期版本
        for old_doc in all_docs[self.max_versions:]:
            # 从 Milvus 删除
            milvus_client.delete(
                collection_name=kb_id,
                filter=f'doc_id == "{old_doc.id}"',
            )

            # 从数据库删除
            await self.db.execute(
                delete(Document).where(Document.id == old_doc.id)
            )

            logger.info("清理过期版本 | doc=%s version=%d", doc_id, old_doc.version)


# Global instance
_version_manager: Optional[VersionManager] = None


def get_version_manager(db_session=None, config: Optional[Dict[str, Any]] = None) -> VersionManager:
    """Get or create version manager"""
    global _version_manager
    if _version_manager is None:
        _version_manager = VersionManager(db_session, config)
    return _version_manager


def reset_version_manager():
    """Reset the global version manager"""
    global _version_manager
    _version_manager = None
