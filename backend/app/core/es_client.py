"""
Elasticsearch 客户端配置
"""
import logging
from typing import Optional
from elasticsearch import AsyncElasticsearch
from app.config import settings

logger = logging.getLogger(__name__)

# 全局 ES 客户端实例
_es_client: Optional[AsyncElasticsearch] = None


def get_es_client() -> AsyncElasticsearch:
    """获取 Elasticsearch 客户端单例"""
    global _es_client
    if _es_client is None:
        es_scheme = getattr(settings, 'es_scheme', 'http') or 'http'
        _es_client = AsyncElasticsearch(
            hosts=[{
                "host": settings.es_host,
                "port": settings.es_port,
                "scheme": es_scheme,
            }],
            basic_auth=(settings.es_user, settings.es_password) if settings.es_user else None,
            retry_on_timeout=True,
            max_retries=3,
        )
        logger.info(
            "Elasticsearch client initialized | host=%s port=%s scheme=%s",
            settings.es_host, settings.es_port, es_scheme
        )
    return _es_client


async def close_es_client():
    """关闭 ES 连接"""
    global _es_client
    if _es_client:
        await _es_client.close()
        _es_client = None
        logger.info("Elasticsearch client closed")


# ES 索引名称
ES_INDEX_TRACE = "execution_traces"
ES_INDEX_TRACE_AGG = "execution_traces_aggs"

# 索引配置（简化版，移除 ILM 依赖）
TRACE_INDEX_SETTINGS = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
    },
    "mappings": {
        "properties": {
            # 核心字段
            "trace_id": {"type": "keyword"},
            "span_id": {"type": "keyword"},
            "parent_span_id": {"type": "keyword"},

            # 执行上下文
            "execution_type": {"type": "keyword"},
            "execution_id": {"type": "keyword"},
            "run_id": {"type": "keyword"},

            # 节点信息
            "node_type": {"type": "keyword"},
            "node_name": {"type": "keyword"},
            "node_order": {"type": "integer"},

            # 状态与时间
            "status": {"type": "keyword"},
            "started_at": {"type": "date"},
            "completed_at": {"type": "date"},
            "duration_ms": {"type": "integer"},

            # 输入输出（不索引，仅存储）
            "input_data": {"type": "object", "enabled": False},
            "output_data": {"type": "object", "enabled": False},
            "error_info": {"type": "object", "enabled": False},

            # 元数据
            "metadata": {"type": "object"},
            "tenant_id": {"type": "keyword"},
            "user_id": {"type": "integer"},

            # 层级路径（用于树形查询）
            "path": {"type": "keyword"},
        }
    }
}

# 聚合索引配置（用于快速列表查询）
TRACE_AGG_INDEX_SETTINGS = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
    },
    "mappings": {
        "properties": {
            "trace_id": {"type": "keyword"},
            "execution_type": {"type": "keyword"},
            "execution_id": {"type": "keyword"},
            "started_at": {"type": "date"},
            "completed_at": {"type": "date"},
            "total_spans": {"type": "integer"},
            "total_duration_ms": {"type": "integer"},
            "final_status": {"type": "keyword"},
        }
    }
}

# ILM 策略
ILM_POLICY = {
    "policy": {
        "phases": {
            "hot": {
                "min_age": "0ms",
                "actions": {
                    "rollover": {"max_size": "50gb", "max_age": "7d"},
                    "set_priority": {"priority": 100}
                }
            },
            "warm": {
                "min_age": "7d",
                "actions": {
                    "set_priority": {"priority": 50},
                    "shrink": {"number_of_shards": 1}
                }
            },
            "cold": {
                "min_age": "30d",
                "actions": {
                    "set_priority": {"priority": 0},
                    "freeze": {}
                }
            },
            "delete": {
                "min_age": "90d",
                "actions": {"delete": {}}
            }
        }
    }
}
