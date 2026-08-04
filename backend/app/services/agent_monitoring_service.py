"""
Agent 监控和调试服务

提供以下功能：
1. 执行轨迹追踪
2. Token 消耗监控
3. 延迟监控
4. 错误告警
5. 调试断点
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.models.agent import AgentConfig, AgentCallLog, AgentMemory
from app.models.user import User

logger = logging.getLogger("app.services.agent_monitoring")


class AgentExecutionTrace:
    """Agent 执行轨迹追踪器"""

    def __init__(self, run_id: str, agent_id: str, user_id: int):
        self.run_id = run_id
        self.agent_id = agent_id
        self.user_id = user_id
        self.start_time = datetime.utcnow()
        self.end_time: Optional[datetime] = None
        self.steps: List[Dict[str, Any]] = []
        self.tokens: Dict[str, int] = {
            "input": 0,
            "output": 0,
            "total": 0,
        }
        self.errors: List[str] = []
        self.metadata: Dict[str, Any] = {}

    def add_step(self, step_name: str, data: Dict[str, Any], duration_ms: Optional[int] = None):
        """添加执行步骤"""
        self.steps.append({
            "step": step_name,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data,
            "duration_ms": duration_ms,
        })

    def add_token_usage(self, input_tokens: int, output_tokens: int):
        """添加 Token 使用记录"""
        self.tokens["input"] += input_tokens
        self.tokens["output"] += output_tokens
        self.tokens["total"] += input_tokens + output_tokens

    def add_error(self, error: str):
        """添加错误记录"""
        self.errors.append(error)

    def complete(self):
        """标记执行完成"""
        self.end_time = datetime.utcnow()

    @property
    def duration_ms(self) -> int:
        """计算执行时长（毫秒）"""
        if not self.end_time:
            return 0
        return int((self.end_time - self.start_time).total_seconds() * 1000)

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "run_id": self.run_id,
            "agent_id": self.agent_id,
            "user_id": self.user_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "steps": self.steps,
            "tokens": self.tokens,
            "errors": self.errors,
            "metadata": self.metadata,
        }


class AgentMonitoringService:
    """
    Agent 监控服务

    功能：
    1. 执行轨迹记录
    2. Token 消耗统计
    3. 延迟监控
    4. 错误率分析
    5. 告警通知
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._active_traces: Dict[str, AgentExecutionTrace] = {}

        # 告警阈值配置
        self.alert_thresholds = {
            "max_latency_ms": 10000,  # 最大延迟 10 秒
            "max_error_rate": 0.1,  # 最大错误率 10%
            "max_tokens_per_run": 100000,  # 单次最大 Token 数
            "max_runs_per_minute": 60,  # 每分钟最大运行次数
        }

    # ============================================================
    # 执行轨迹追踪
    # ============================================================

    def start_trace(self, agent_id: str, user_id: int) -> AgentExecutionTrace:
        """
        开始执行轨迹追踪

        Args:
            agent_id: Agent ID
            user_id: 用户 ID

        Returns:
            执行轨迹对象
        """
        run_id = str(uuid4())
        trace = AgentExecutionTrace(run_id, agent_id, user_id)
        self._active_traces[run_id] = trace

        logger.info(
            "[AgentMonitor] Trace started | run=%s agent=%s user=%s",
            run_id, agent_id, user_id
        )

        return trace

    def get_trace(self, run_id: str) -> Optional[AgentExecutionTrace]:
        """获取执行轨迹"""
        return self._active_traces.get(run_id)

    def end_trace(self, run_id: str) -> Optional[AgentExecutionTrace]:
        """
        结束执行轨迹追踪

        Args:
            run_id: 运行 ID

        Returns:
            完成的轨迹对象
        """
        trace = self._active_traces.pop(run_id, None)
        if trace:
            trace.complete()
            logger.info(
                "[AgentMonitor] Trace completed | run=%s duration=%dms tokens=%d",
                run_id, trace.duration_ms, trace.tokens["total"]
            )
        return trace

    # ============================================================
    # Token 消耗监控
    # ============================================================

    async def get_token_stats(
        self,
        agent_id: Optional[str] = None,
        user_id: Optional[int] = None,
        time_range: str = "24h",
    ) -> dict:
        """
        获取 Token 消耗统计

        Args:
            agent_id: Agent ID（可选）
            user_id: 用户 ID（可选）
            time_range: 时间范围（24h, 7d, 30d）

        Returns:
            Token 统计数据
        """
        # 计算时间范围
        now = datetime.utcnow()
        if time_range == "24h":
            start_time = now - timedelta(hours=24)
        elif time_range == "7d":
            start_time = now - timedelta(days=7)
        elif time_range == "30d":
            start_time = now - timedelta(days=30)
        else:
            start_time = now - timedelta(hours=24)

        # 构建查询
        query = select(
            AgentCallLog.agent_id,
            func.sum(AgentCallLog.input_tokens).label("total_input"),
            func.sum(AgentCallLog.output_tokens).label("total_output"),
            func.sum(AgentCallLog.total_tokens).label("total"),
            func.count(AgentCallLog.id).label("run_count"),
        ).where(
            AgentCallLog.created_at >= start_time
        )

        if agent_id:
            query = query.where(AgentCallLog.agent_id == agent_id)
        if user_id:
            query = query.where(AgentCallLog.user_id == user_id)

        query = query.group_by(AgentCallLog.agent_id)
        result = await self.db.execute(query)
        rows = result.all()

        # 汇总统计
        total_input = sum(row.total_input or 0 for row in rows)
        total_output = sum(row.total_output or 0 for row in rows)
        total_all = sum(row.total or 0 for row in rows)
        total_runs = sum(row.run_count or 0 for row in rows)

        return {
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_all,
            "total_runs": total_runs,
            "avg_tokens_per_run": total_all / total_runs if total_runs > 0 else 0,
            "time_range": time_range,
            "by_agent": [
                {
                    "agent_id": row.agent_id,
                    "input_tokens": row.total_input or 0,
                    "output_tokens": row.total_output or 0,
                    "total_tokens": row.total or 0,
                    "runs": row.run_count or 0,
                }
                for row in rows
            ],
        }

    # ============================================================
    # 延迟监控
    # ============================================================

    async def get_latency_stats(
        self,
        agent_id: Optional[str] = None,
        user_id: Optional[int] = None,
        time_range: str = "24h",
    ) -> dict:
        """
        获取延迟统计

        Args:
            agent_id: Agent ID（可选）
            user_id: 用户 ID（可选）
            time_range: 时间范围

        Returns:
            延迟统计数据
        """
        now = datetime.utcnow()
        if time_range == "24h":
            start_time = now - timedelta(hours=24)
        elif time_range == "7d":
            start_time = now - timedelta(days=7)
        elif time_range == "30d":
            start_time = now - timedelta(days=30)
        else:
            start_time = now - timedelta(hours=24)

        # 构建查询
        query = select(
            AgentCallLog.latency_ms,
        ).where(
            AgentCallLog.created_at >= start_time,
            AgentCallLog.status == "success",
        )

        if agent_id:
            query = query.where(AgentCallLog.agent_id == agent_id)
        if user_id:
            query = query.where(AgentCallLog.user_id == user_id)

        result = await self.db.execute(query)
        latencies = [row.latency_ms for row in result.all() if row.latency_ms > 0]

        if not latencies:
            return {
                "count": 0,
                "min_ms": 0,
                "max_ms": 0,
                "avg_ms": 0,
                "p50_ms": 0,
                "p95_ms": 0,
                "p99_ms": 0,
            }

        latencies.sort()
        count = len(latencies)

        return {
            "count": count,
            "min_ms": min(latencies),
            "max_ms": max(latencies),
            "avg_ms": sum(latencies) / count,
            "p50_ms": latencies[int(count * 0.5)],
            "p95_ms": latencies[int(count * 0.95)],
            "p99_ms": latencies[int(count * 0.99)],
            "time_range": time_range,
        }

    # ============================================================
    # 错误分析
    # ============================================================

    async def get_error_stats(
        self,
        agent_id: Optional[str] = None,
        user_id: Optional[int] = None,
        time_range: str = "24h",
    ) -> dict:
        """
        获取错误统计

        Args:
            agent_id: Agent ID（可选）
            user_id: 用户 ID（可选）
            time_range: 时间范围

        Returns:
            错误统计数据
        """
        now = datetime.utcnow()
        if time_range == "24h":
            start_time = now - timedelta(hours=24)
        elif time_range == "7d":
            start_time = now - timedelta(days=7)
        elif time_range == "30d":
            start_time = now - timedelta(days=30)
        else:
            start_time = now - timedelta(hours=24)

        # 总运行次数
        total_query = select(func.count(AgentCallLog.id)).where(
            AgentCallLog.created_at >= start_time
        )
        if agent_id:
            total_query = total_query.where(AgentCallLog.agent_id == agent_id)
        if user_id:
            total_query = total_query.where(AgentCallLog.user_id == user_id)

        total_result = await self.db.execute(total_query)
        total_runs = total_result.scalar() or 0

        # 错误次数
        error_query = select(func.count(AgentCallLog.id)).where(
            AgentCallLog.created_at >= start_time,
            AgentCallLog.status == "error",
        )
        if agent_id:
            error_query = error_query.where(AgentCallLog.agent_id == agent_id)
        if user_id:
            error_query = error_query.where(AgentCallLog.user_id == user_id)

        error_result = await self.db.execute(error_query)
        error_count = error_result.scalar() or 0

        # 错误类型分布（使用 text 避免 GROUP BY 问题）
        from sqlalchemy import text
        error_type_query = text("""
            SELECT LEFT(error_message, 50) as error_prefix, COUNT(id) as count
            FROM agent_call_logs
            WHERE created_at >= :start_time
              AND status = :status
              AND error_message IS NOT NULL
              AND agent_id = :agent_id
            GROUP BY LEFT(error_message, 50)
            ORDER BY COUNT(id) DESC
            LIMIT 10
        """)

        error_type_result = await self.db.execute(
            error_type_query,
            {"start_time": start_time, "status": "error", "agent_id": agent_id}
        )
        error_types = [
            {"error": row.error_prefix, "count": row.count}
            for row in error_type_result.all()
        ]

        return {
            "total_runs": total_runs,
            "error_count": error_count,
            "error_rate": error_count / total_runs if total_runs > 0 else 0,
            "error_types": error_types,
            "time_range": time_range,
        }

    # ============================================================
    # 告警检查
    # ============================================================

    async def check_alerts(self, agent_id: str) -> List[Dict[str, Any]]:
        """
        检查告警条件

        Args:
            agent_id: Agent ID

        Returns:
            告警列表
        """
        alerts = []

        # 检查错误率
        error_stats = await self.get_error_stats(agent_id=agent_id, time_range="1h")
        if error_stats["error_rate"] > self.alert_thresholds["max_error_rate"]:
            alerts.append({
                "type": "high_error_rate",
                "severity": "warning",
                "message": f"错误率过高：{error_stats['error_rate']:.2%}",
                "threshold": self.alert_thresholds["max_error_rate"],
                "actual": error_stats["error_rate"],
            })

        # 检查延迟
        latency_stats = await self.get_latency_stats(agent_id=agent_id, time_range="1h")
        if latency_stats["p95_ms"] > self.alert_thresholds["max_latency_ms"]:
            alerts.append({
                "type": "high_latency",
                "severity": "warning",
                "message": f"P95 延迟过高：{latency_stats['p95_ms']}ms",
                "threshold": self.alert_thresholds["max_latency_ms"],
                "actual": latency_stats["p95_ms"],
            })

        # 检查 Token 消耗
        token_stats = await self.get_token_stats(agent_id=agent_id, time_range="1h")
        if token_stats["total_tokens"] > self.alert_thresholds["max_tokens_per_run"]:
            alerts.append({
                "type": "high_token_usage",
                "severity": "info",
                "message": f"Token 消耗过高：{token_stats['total_tokens']}",
                "threshold": self.alert_thresholds["max_tokens_per_run"],
                "actual": token_stats["total_tokens"],
            })

        return alerts

    # ============================================================
    # 调试断点
    # ============================================================

    def set_debug_mode(self, run_id: str, enabled: bool = True):
        """
        设置调试模式

        Args:
            run_id: 运行 ID
            enabled: 是否启用
        """
        trace = self._active_traces.get(run_id)
        if trace:
            trace.metadata["debug_mode"] = enabled
            logger.info("[AgentMonitor] Debug mode %s for run=%s", "enabled" if enabled else "disabled", run_id)

    def add_debug_point(self, run_id: str, point_name: str, data: Dict[str, Any]):
        """
        添加调试断点数据

        Args:
            run_id: 运行 ID
            point_name: 断点名称
            data: 断点数据
        """
        trace = self._active_traces.get(run_id)
        if trace:
            trace.add_step(f"debug:{point_name}", data)
            logger.debug("[AgentMonitor] Debug point %s: %s", point_name, data)


async def create_monitoring_service(db: AsyncSession) -> AgentMonitoringService:
    """创建监控服务实例"""
    return AgentMonitoringService(db)
