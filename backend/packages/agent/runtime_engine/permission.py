"""
Permission Engine - 梯度化权限管理

实现三种权限级别：
1. Free - 无需审批，直接执行
2. Ask-first - 询问用户，等待确认
3. Approve-once - 每次执行都需要单独审批

核心职责：
- 权限检查：在执行前验证工具/操作是否有权限
- 审批流程：对于需要审批的操作，发起审批请求
- 权限缓存：缓存已批准的权限，避免重复询问
"""
import logging
import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger(__name__)


class PermissionLevel(str, Enum):
    """权限级别"""
    FREE = "free"              # 自由执行，无需审批
    ASK_FIRST = "ask_first"    # 首次询问，后续缓存
    APPROVE_ONCE = "approve_once"  # 每次都需要审批


class PermissionStatus(str, Enum):
    """审批状态"""
    PENDING = "pending"        # 等待审批
    APPROVED = "approved"      # 已批准
    REJECTED = "rejected"      # 已拒绝
    EXPIRED = "expired"        # 已过期


class PermissionRequest(BaseModel):
    """权限请求"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str
    operation: str
    parameters: Dict[str, Any]
    permission_level: PermissionLevel
    risk_level: str = "medium"  # low, medium, high, critical
    reason: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    status: PermissionStatus = PermissionStatus.PENDING
    approver_id: Optional[int] = None  # 审批人 ID
    approved_at: Optional[datetime] = None

    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at


class PermissionCacheEntry(BaseModel):
    """权限缓存条目"""
    tool_name: str
    operation: str
    user_id: int
    permission_level: PermissionLevel
    approved_at: datetime
    expires_at: datetime
    approval_count: int = 0  # 已使用次数（用于限制次数）
    max_approvals: Optional[int] = None  # 最大使用次数


class PermissionEngine:
    """
    权限引擎

    提供梯度化权限管理：
    1. Free - 直接执行
    2. Ask-first - 首次询问，批准后缓存
    3. Approve-once - 每次都需审批
    """

    def __init__(self, db: AsyncSession, user_id: int):
        self.db = db
        self.user_id = user_id
        self._permission_cache: Dict[str, PermissionCacheEntry] = {}
        self._pending_requests: Dict[str, PermissionRequest] = {}

        # 默认权限配置
        self._default_tool_permissions: Dict[str, PermissionLevel] = {
            "knowledge_base_search": PermissionLevel.FREE,
            "code_interpreter": PermissionLevel.ASK_FIRST,
            "file_read": PermissionLevel.FREE,
            "file_write": PermissionLevel.ASK_FIRST,
            "file_delete": PermissionLevel.APPROVE_ONCE,
            "api_call": PermissionLevel.ASK_FIRST,
            "database_query": PermissionLevel.APPROVE_ONCE,
            "system_command": PermissionLevel.APPROVE_ONCE,
        }

        # 风险等级对应的默认过期时间
        self._risk_expiry = {
            "low": timedelta(hours=24),
            "medium": timedelta(hours=4),
            "high": timedelta(hours=1),
            "critical": timedelta(minutes=15),
        }

    async def check_permission(
        self,
        tool_name: str,
        operation: str = "execute",
        parameters: Optional[Dict[str, Any]] = None,
    ) -> tuple[bool, Optional[PermissionRequest]]:
        """
        检查是否有权限执行操作

        Returns:
            (has_permission, permission_request)
            - has_permission: True=可以直接执行，False=需要审批或被拒绝
            - permission_request: 如果需要审批，返回请求对象；否则为 None
        """
        # 1. 确定权限级别
        permission_level = self._get_permission_level(tool_name, operation)

        # 2. Free 级别直接允许
        if permission_level == PermissionLevel.FREE:
            logger.debug(f"Permission FREE: {tool_name}.{operation}")
            return True, None

        # 3. 检查缓存
        cache_key = f"{self.user_id}:{tool_name}:{operation}"
        if cache_key in self._permission_cache:
            cache_entry = self._permission_cache[cache_key]
            if not self._is_cache_expired(cache_entry):
                # 检查使用次数
                if (cache_entry.max_approvals is None or
                    cache_entry.approval_count < cache_entry.max_approvals):
                    logger.debug(f"Permission cached: {tool_name}.{operation}")
                    cache_entry.approval_count += 1
                    return True, None

        # 4. Approve-once 级别每次都创建新请求
        # 5. Ask-first 级别如果没有缓存也创建请求
        request = await self._create_permission_request(
            tool_name=tool_name,
            operation=operation,
            parameters=parameters or {},
            permission_level=permission_level,
        )

        return False, request

    def _get_permission_level(
        self,
        tool_name: str,
        operation: str,
    ) -> PermissionLevel:
        """获取工具的权限级别"""
        # 先查找特定工具的权限配置
        if tool_name in self._default_tool_permissions:
            return self._default_tool_permissions[tool_name]

        # 默认使用 Ask-first
        return PermissionLevel.ASK_FIRST

    def _is_cache_expired(self, entry: PermissionCacheEntry) -> bool:
        """检查缓存是否过期"""
        return datetime.utcnow() > entry.expires_at

    async def _create_permission_request(
        self,
        tool_name: str,
        operation: str,
        parameters: Dict[str, Any],
        permission_level: PermissionLevel,
    ) -> PermissionRequest:
        """创建权限请求"""
        # 评估风险等级
        risk_level = self._assess_risk_level(tool_name, operation, parameters)

        # 计算过期时间
        expires_at = datetime.utcnow() + self._risk_expiry.get(
            risk_level, timedelta(hours=1)
        )

        request = PermissionRequest(
            tool_name=tool_name,
            operation=operation,
            parameters=parameters,
            permission_level=permission_level,
            risk_level=risk_level,
            reason=self._generate_reason(tool_name, operation, parameters),
            expires_at=expires_at,
        )

        # 保存到待审批队列
        self._pending_requests[request.id] = request

        logger.info(
            f"Permission request created: {request.id} "
            f"tool={tool_name} level={permission_level} risk={risk_level}"
        )

        return request

    def _assess_risk_level(
        self,
        tool_name: str,
        operation: str,
        parameters: Dict[str, Any],
    ) -> str:
        """
        评估操作的风险等级

        考虑因素：
        - 工具类型
        - 操作性质
        - 参数敏感性
        """
        # 高风险操作
        high_risk_tools = {"database_query", "system_command", "file_delete"}
        high_risk_ops = {"delete", "drop", "truncate", "execute"}

        if tool_name in high_risk_tools:
            return "high"
        if operation in high_risk_ops:
            return "high"

        # 中等风险操作
        medium_risk_tools = {"file_write", "api_call", "code_interpreter"}
        if tool_name in medium_risk_tools:
            return "medium"

        # 检查参数中是否有敏感内容
        sensitive_params = {"password", "secret", "key", "token"}
        for param_name in parameters.keys():
            if any(s in param_name.lower() for s in sensitive_params):
                return "medium"

        return "low"

    def _generate_reason(
        self,
        tool_name: str,
        operation: str,
        parameters: Dict[str, Any],
    ) -> str:
        """生成权限请求原因说明"""
        return f"请求执行 {tool_name}.{operation} 操作"

    async def approve_permission(
        self,
        request_id: str,
        approver_id: int,
    ) -> bool:
        """
        批准权限请求

        Returns:
            bool: 是否批准成功
        """
        if request_id not in self._pending_requests:
            logger.warning(f"Permission request not found: {request_id}")
            return False

        request = self._pending_requests[request_id]

        if request.status != PermissionStatus.PENDING:
            logger.warning(f"Request already processed: {request_id}")
            return False

        # 更新请求状态
        request.status = PermissionStatus.APPROVED
        request.approver_id = approver_id
        request.approved_at = datetime.utcnow()

        # 添加到缓存（Ask-first 级别才缓存）
        if request.permission_level == PermissionLevel.ASK_FIRST:
            cache_key = f"{self.user_id}:{request.tool_name}:{request.operation}"
            self._permission_cache[cache_key] = PermissionCacheEntry(
                tool_name=request.tool_name,
                operation=request.operation,
                user_id=self.user_id,
                permission_level=PermissionLevel.ASK_FIRST,
                approved_at=datetime.utcnow(),
                expires_at=request.expires_at,
                approval_count=1,
                max_approvals=None,  # 无限制
            )

        # 从待审批队列移除
        del self._pending_requests[request_id]

        logger.info(f"Permission approved: {request_id}")
        return True

    async def reject_permission(
        self,
        request_id: str,
        approver_id: int,
    ) -> bool:
        """拒绝权限请求"""
        if request_id not in self._pending_requests:
            return False

        request = self._pending_requests[request_id]
        request.status = PermissionStatus.REJECTED
        request.approver_id = approver_id

        del self._pending_requests[request_id]

        logger.info(f"Permission rejected: {request_id}")
        return True

    def get_pending_requests(self) -> List[PermissionRequest]:
        """获取所有待审批的请求"""
        return list(self._pending_requests.values())

    def clear_expired_cache(self) -> int:
        """清理过期的权限缓存"""
        expired_keys = [
            key for key, entry in self._permission_cache.items()
            if self._is_cache_expired(entry)
        ]
        for key in expired_keys:
            del self._permission_cache[key]
        return len(expired_keys)

    def get_permission_stats(self) -> Dict[str, Any]:
        """获取权限统计信息"""
        return {
            "pending_requests": len(self._pending_requests),
            "cached_permissions": len(self._permission_cache),
            "approved_count": sum(
                1 for r in self._pending_requests.values()
                if r.status == PermissionStatus.APPROVED
            ),
            "rejected_count": sum(
                1 for r in self._pending_requests.values()
                if r.status == PermissionStatus.REJECTED
            ),
        }
