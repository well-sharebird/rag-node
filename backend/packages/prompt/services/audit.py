"""审计日志服务"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from sqlalchemy.orm import selectinload

from packages.prompt.models.prompt_template import PromptAuditLog as PromptAuditLogModel


class AuditService:
    """审计日志服务

    记录所有提示词相关的敏感操作：
    - 创建/更新模板
    - 创建/发布版本
    - 设置/删除标签
    - 回滚操作
    - 评估运行
    """

    # 行动作枚举
    ACTION_CREATE = "create"
    ACTION_UPDATE = "update"
    ACTION_DELETE = "delete"
    ACTION_TAG = "tag"
    ACTION_ROLLBACK = "rollback"
    ACTION_EVAL = "eval"
    ACTION_RELEASE = "release"
    ACTION_ARCHIVE = "archive"

    # 资源类型枚举
    RESOURCE_TEMPLATE = "template"
    RESOURCE_VERSION = "version"
    RESOURCE_TAG = "tag"
    RESOURCE_TEST_CASE = "test_case"

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log(
        self,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: int,
        old_value: Optional[Dict[str, Any]] = None,
        new_value: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> PromptAuditLogModel:
        """记录审计日志

        Args:
            actor: 操作人
            action: 动作
            resource_type: 资源类型
            resource_id: 资源 ID
            old_value: 旧值（JSON）
            new_value: 新值（JSON）
            ip_address: IP 地址
            user_agent: 用户代理

        Returns:
            创建的审计日志对象
        """
        log_entry = PromptAuditLogModel(
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            old_value=old_value,
            new_value=new_value,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(log_entry)
        await self.db.commit()
        await self.db.refresh(log_entry)
        return log_entry

    async def list_logs(
        self,
        actor: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[int] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[List[PromptAuditLogModel], int]:
        """查询审计日志

        Args:
            actor: 操作人过滤
            action: 动作过滤
            resource_type: 资源类型过滤
            resource_id: 资源 ID 过滤
            offset: 偏移量
            limit: 数量限制

        Returns:
            (日志列表，总数)
        """
        query = select(PromptAuditLogModel)

        # 过滤条件
        if actor:
            query = query.where(PromptAuditLogModel.actor == actor)
        if action:
            query = query.where(PromptAuditLogModel.action == action)
        if resource_type:
            query = query.where(PromptAuditLogModel.resource_type == resource_type)
        if resource_id is not None:
            query = query.where(PromptAuditLogModel.resource_id == resource_id)

        # 总数
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # 数据
        query = query.order_by(desc(PromptAuditLogModel.created_at))
        query = query.offset(offset).limit(limit)

        result = await self.db.execute(query)
        logs = list(result.scalars().all())
        return logs, total

    async def get_logs_by_resource(
        self, resource_type: str, resource_id: int, limit: int = 20
    ) -> List[PromptAuditLogModel]:
        """获取特定资源的操作历史

        Args:
            resource_type: 资源类型
            resource_id: 资源 ID
            limit: 数量限制

        Returns:
            审计日志列表（按时间倒序）
        """
        result = await self.db.execute(
            select(PromptAuditLogModel)
            .where(PromptAuditLogModel.resource_type == resource_type)
            .where(PromptAuditLogModel.resource_id == resource_id)
            .order_by(desc(PromptAuditLogModel.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_logs_by_actor(
        self, actor: str, limit: int = 50
    ) -> List[PromptAuditLogModel]:
        """获取特定用户的操作历史

        Args:
            actor: 操作人
            limit: 数量限制

        Returns:
            审计日志列表（按时间倒序）
        """
        result = await self.db.execute(
            select(PromptAuditLogModel)
            .where(PromptAuditLogModel.actor == actor)
            .order_by(desc(PromptAuditLogModel.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())
