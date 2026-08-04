"""
执行追踪服务 - 基于 Elasticsearch
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
import uuid

from elasticsearch import AsyncElasticsearch
from elasticsearch.exceptions import NotFoundError

from packages.core.infra.es_client import (
    get_es_client,
    ES_INDEX_TRACE,
    ES_INDEX_TRACE_AGG,
    TRACE_INDEX_SETTINGS,
    TRACE_AGG_INDEX_SETTINGS,
    ILM_POLICY,
)

logger = logging.getLogger(__name__)


class TraceContext:
    """追踪上下文"""

    def __init__(
        self,
        execution_type: str,
        execution_id: str,
        user_id: Optional[int] = None,
        tenant_id: Optional[str] = None,
    ):
        self.trace_id = str(uuid.uuid4())
        self.execution_type = execution_type
        self.execution_id = execution_id
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.run_id = str(uuid.uuid4())
        self.span_counter = 0
        self.span_stack: List[str] = []
        self.started_at = datetime.utcnow()

    def generate_span_id(self) -> str:
        self.span_counter += 1
        return f"{self.trace_id}-{self.span_counter:04d}"

    def push_span(self, span_id: str):
        self.span_stack.append(span_id)

    def pop_span(self) -> Optional[str]:
        return self.span_stack.pop() if self.span_stack else None

    @property
    def parent_span_id(self) -> Optional[str]:
        return self.span_stack[-1] if self.span_stack else None


class TraceService:
    """基于 ES 的追踪服务"""

    def __init__(self, es: Optional[AsyncElasticsearch] = None):
        self.es = es or get_es_client()
        self._buffer: List[dict] = []
        self._buffer_size = 10  # 降低阈值，确保及时刷新
        self._flush_lock = asyncio.Lock()
        self._initialized = False

    async def ensure_index(self):
        """确保索引存在"""
        if self._initialized:
            return

        try:
            # 检查主索引（使用 catch_all 异常处理）
            try:
                exists = await self.es.indices.exists(index=ES_INDEX_TRACE)
            except Exception:
                exists = False

            if not exists:
                await self.es.indices.create(
                    index=ES_INDEX_TRACE,
                    body=TRACE_INDEX_SETTINGS
                )
                logger.info("Created index: %s", ES_INDEX_TRACE)

            # 检查聚合索引
            try:
                exists = await self.es.indices.exists(index=ES_INDEX_TRACE_AGG)
            except Exception:
                exists = False

            if not exists:
                await self.es.indices.create(
                    index=ES_INDEX_TRACE_AGG,
                    body=TRACE_AGG_INDEX_SETTINGS
                )
                logger.info("Created index: %s", ES_INDEX_TRACE_AGG)

            self._initialized = True

        except Exception as e:
            logger.error("Failed to ensure indices: %s", e)
            raise

    async def start_span(
        self,
        ctx: TraceContext,
        node_type: str,
        node_name: str,
        input_data: Optional[dict] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """开始追踪跨度"""
        span_id = ctx.generate_span_id()

        # 构建路径（用于树形查询）
        path_parts = [ctx.span_counter]
        if ctx.parent_span_id:
            parent = await self._get_span(ctx.trace_id, ctx.parent_span_id)
            if parent:
                parent_path = parent.get('path', '')
                path_parts = parent_path.split('.') + [str(ctx.span_counter)] if parent_path else [str(ctx.span_counter)]

        doc = {
            "trace_id": ctx.trace_id,
            "span_id": span_id,
            "parent_span_id": ctx.parent_span_id,
            "execution_type": ctx.execution_type,
            "execution_id": ctx.execution_id,
            "run_id": ctx.run_id,
            "node_type": node_type,
            "node_name": node_name,
            "node_order": ctx.span_counter,
            "status": "running",
            "started_at": datetime.utcnow().isoformat(),
            "input_data": input_data,
            "metadata": metadata,
            "user_id": ctx.user_id,
            "tenant_id": ctx.tenant_id,
            "path": ".".join(map(str, path_parts)),
        }

        self._buffer.append(doc)
        # 立即刷新到 ES，但保留缓冲数据供 end_span 使用
        await self._flush()

        ctx.push_span(span_id)
        return span_id

    async def end_span(
        self,
        ctx: TraceContext,
        span_id: str,
        output_data: Optional[dict] = None,
        error: Optional[Exception] = None,
    ):
        """结束追踪跨度"""
        completed_at = datetime.utcnow()

        # 先从缓冲中查找 start_span 写入的数据（如果还在缓冲中）
        buffered_span = None
        for buf_doc in self._buffer:
            if buf_doc.get("span_id") == span_id:
                buffered_span = buf_doc
                break

        # 获取开始时间以计算耗时
        started_at_str = None
        if buffered_span:
            started_at_str = buffered_span.get("started_at")
        if not started_at_str:
            started_at_str = await self._get_span_field(ctx.trace_id, span_id, "started_at")

        if started_at_str:
            try:
                started_at = datetime.fromisoformat(started_at_str.replace('Z', '+00:00'))
                duration_ms = int((completed_at - started_at).total_seconds() * 1000)
            except Exception:
                duration_ms = 0
        else:
            duration_ms = 0

        update_doc = {
            "status": "failed" if error else "success",
            "completed_at": completed_at.isoformat(),
            "duration_ms": duration_ms,
        }

        if output_data:
            update_doc["output_data"] = output_data
        if error:
            update_doc["error_info"] = {
                "message": str(error),
                "type": type(error).__name__,
            }

        # 构建完整的文档（合并 start_span 和 end_span 的数据）
        full_doc = {}
        if buffered_span:
            # 复制 start_span 的所有字段
            full_doc.update(buffered_span)
            full_doc.pop("_index", None)
            full_doc.pop("_id", None)
        # 添加/更新结束时的字段
        full_doc.update(update_doc)

        try:
            # 先尝试 update（如果文档已存在）
            await self.es.update(
                index=ES_INDEX_TRACE,
                id=span_id,
                body={"doc": update_doc},
                refresh="wait_for",
            )
        except NotFoundError:
            # 文档不存在，使用完整数据创建
            await self.es.index(
                index=ES_INDEX_TRACE,
                id=span_id,
                document=full_doc,
                refresh="wait_for",
            )
        except Exception as e:
            # 其他错误时，回退到 index 完整数据
            logger.debug("Update failed, falling back to index: %s", e)
            await self.es.index(
                index=ES_INDEX_TRACE,
                id=span_id,
                document=full_doc,
                refresh="wait_for",
            )

        # 从缓冲中移除已写入的文档
        if buffered_span:
            self._buffer = [d for d in self._buffer if d.get("span_id") != span_id]

        ctx.pop_span()

    async def _maybe_flush(self):
        """检查是否需要刷新缓冲"""
        # 降低阈值，确保少量 span 也能及时刷新
        if len(self._buffer) >= self._buffer_size:
            await self._flush()

    async def _flush(self):
        """批量提交到 ES"""
        async with self._flush_lock:
            if not self._buffer:
                return

            try:
                # ES 8.x bulk API 格式：每个文档需要两个元素（action + data）
                actions = []
                for doc in self._buffer:
                    # Action line
                    actions.append({
                        "index": {
                            "_index": ES_INDEX_TRACE,
                            "_id": doc["span_id"]
                        }
                    })
                    # Data line
                    actions.append(doc)

                if actions:
                    response = await self.es.bulk(body=actions, refresh="wait_for")
                    if response.get("errors"):
                        logger.warning("Bulk indexing had errors: %s", response)

                # 不清空缓冲，保留供 end_span 使用
                # self._buffer.clear()

            except Exception as e:
                logger.debug("Failed to flush trace buffer: %s", e)
                # 不清空缓冲，下次重试

    async def finalize(self, ctx: TraceContext):
        """完成追踪，写入聚合元数据"""
        await self._flush()

        # 清空缓冲
        self._buffer.clear()

        # 计算统计信息
        try:
            stats = await self.get_trace_stats(ctx.trace_id)
            total_spans = stats.get("span_count", 0)
            total_duration_ms = stats.get("total_duration", 0)
            final_status = stats.get("final_status", "unknown")
        except Exception as e:
            logger.warning("Failed to get trace stats: %s", e)
            total_spans = 0
            total_duration_ms = 0
            final_status = "unknown"

        # 写入聚合元数据
        try:
            await self.es.index(
                index=ES_INDEX_TRACE_AGG,
                id=ctx.trace_id,
                document={
                    "trace_id": ctx.trace_id,
                    "execution_type": ctx.execution_type,
                    "execution_id": ctx.execution_id,
                    "run_id": ctx.run_id,
                    "total_spans": total_spans,
                    "total_duration_ms": total_duration_ms,
                    "final_status": final_status,
                    "started_at": ctx.started_at.isoformat(),
                    "completed_at": datetime.utcnow().isoformat(),
                    "user_id": ctx.user_id,
                    "tenant_id": ctx.tenant_id,
                }
            )
        except Exception as e:
            logger.warning("Failed to write trace metadata: %s", e)

    async def _get_span(self, trace_id: str, span_id: str) -> Optional[dict]:
        """获取跨度详情"""
        try:
            result = await self.es.get(
                index=ES_INDEX_TRACE,
                id=span_id,
            )
            return result["_source"]
        except NotFoundError:
            return None

    async def _get_span_field(self, trace_id: str, span_id: str, field: str) -> Optional[Any]:
        """获取跨度字段值"""
        try:
            result = await self.es.get(
                index=ES_INDEX_TRACE,
                id=span_id,
                _source_includes=[field],
            )
            source = result.get("_source", {})
            return source.get(field)
        except NotFoundError:
            return None

    async def get_trace_tree(self, trace_id: str) -> List[dict]:
        """获取追踪树（按路径排序）"""
        query = {
            "query": {"term": {"trace_id": trace_id}},
            "sort": [
                {"path": {"order": "asc"}},
            ],
            "size": 1000,
            "_source": True,
        }

        result = await self.es.search(**query)
        return [hit["_source"] for hit in result["hits"]["hits"]]

    async def list_traces(
        self,
        execution_type: Optional[str] = None,
        execution_id: Optional[str] = None,
        status: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        user_id: Optional[int] = None,
        search_after: Optional[list] = None,
        size: int = 20,
    ) -> Dict[str, Any]:
        """
        列出追踪记录（使用 search_after 避免深度分页）

        Returns:
            {
                "traces": [...],
                "next_search_after": [...],
                "has_more": bool
            }
        """
        # 从聚合索引查询（更快）
        query_parts = []

        if execution_type:
            query_parts.append({"term": {"execution_type": execution_type}})
        if execution_id:
            query_parts.append({"term": {"execution_id": execution_id}})
        if status:
            query_parts.append({"term": {"final_status": status}})
        if start_time:
            query_parts.append({"range": {"started_at": {"gte": start_time.isoformat()}}})
        if end_time:
            query_parts.append({"range": {"started_at": {"lte": end_time.isoformat()}}})
        if user_id:
            query_parts.append({"term": {"user_id": user_id}})

        es_query = {
            "query": {"bool": {"must": query_parts}} if query_parts else {"match_all": {}},
            "sort": [
                {"started_at": {"order": "desc"}},
                {"trace_id": {"order": "asc"}},
            ],
            "size": size,
        }

        if search_after:
            es_query["search_after"] = search_after

        result = await self.es.search(
            index=ES_INDEX_TRACE_AGG,
            **es_query
        )
        hits = result["hits"]["hits"]

        return {
            "traces": [hit["_source"] for hit in hits],
            "next_search_after": hits[-1]["sort"] if hits else None,
            "has_more": len(hits) == size,
        }

    async def get_trace_stats(self, trace_id: str) -> dict:
        """获取追踪统计"""
        # 从主索引聚合
        query = {
            "query": {"term": {"trace_id": trace_id}},
            "aggs": {
                "status_count": {"terms": {"field": "status"}},
                "avg_duration": {"avg": {"field": "duration_ms"}},
                "total_duration": {"sum": {"field": "duration_ms"}},
            },
            "size": 0,
        }

        result = await self.es.search(**query)
        aggs = result.get("aggregations", {})

        status_buckets = aggs.get("status_count", {}).get("buckets", [])
        final_status = "unknown"
        for bucket in status_buckets:
            if bucket["key"] in ["failed", "success"]:
                final_status = bucket["key"]
                break

        return {
            "span_count": result["hits"]["total"]["value"],
            "avg_duration": aggs.get("avg_duration", {}).get("value"),
            "total_duration": int(aggs.get("total_duration", {}).get("value") or 0),
            "status_breakdown": {b["key"]: b["doc_count"] for b in status_buckets},
            "final_status": final_status,
        }

    async def get_trace_duration_breakdown(self, trace_id: str) -> List[dict]:
        """获取追踪各阶段耗时分析"""
        query = {
            "query": {"term": {"trace_id": trace_id}},
            "sort": [{"node_order": {"order": "asc"}}],
            "size": 100,
            "_source": ["node_type", "node_name", "duration_ms", "status"],
        }

        result = await self.es.search(**query)
        return [
            {
                "node_type": hit["_source"].get("node_type"),
                "node_name": hit["_source"].get("node_name"),
                "duration_ms": hit["_source"].get("duration_ms"),
                "status": hit["_source"].get("status"),
            }
            for hit in result["hits"]["hits"]
        ]

    async def cleanup_old_traces(self, days: int = 90):
        """清理旧的追踪数据（ILM 已自动管理，此方法用于手动清理）"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        query = {
            "query": {
                "range": {
                    "started_at": {"lt": cutoff.isoformat()}
                }
            }
        }
        await self.es.delete_by_query(
            index=ES_INDEX_TRACE,
            **query
        )
        await self.es.delete_by_query(
            index=ES_INDEX_TRACE_AGG,
            **query
        )
