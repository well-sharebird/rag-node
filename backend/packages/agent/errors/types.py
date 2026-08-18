"""
统一错误处理系统

提供结构化错误类型、错误分类和恢复策略
"""
from enum import Enum
from typing import Any, Dict, List, Optional, Type
from dataclasses import dataclass, field
from datetime import datetime
import traceback


class ErrorCategory(str, Enum):
    """错误分类"""
    VALIDATION = "validation"          # 验证错误
    AUTHENTICATION = "authentication"  # 认证错误
    AUTHORIZATION = "authorization"    # 授权错误
    NOT_FOUND = "not_found"            # 资源未找到
    CONFLICT = "conflict"              # 冲突错误
    RATE_LIMIT = "rate_limit"          # 速率限制
    TIMEOUT = "timeout"                # 超时错误
    NETWORK = "network"                # 网络错误
    INTERNAL = "internal"              # 内部错误
    CONFIGURATION = "configuration"    # 配置错误
    DEPENDENCY = "dependency"          # 依赖错误
    PLUGIN = "plugin"                  # 插件错误
    SERVICE = "service"                # 服务错误
    EVENT = "event"                    # 事件错误


class ErrorSeverity(str, Enum):
    """错误严重程度"""
    LOW = "low"              # 低，可忽略
    MEDIUM = "medium"        # 中，需要处理
    HIGH = "high"            # 高，需要立即处理
    CRITICAL = "critical"    # 严重，系统不可用


class RecoveryStrategy(str, Enum):
    """恢复策略"""
    IGNORE = "ignore"            # 忽略
    RETRY = "retry"              # 重试
    RETRY_WITH_BACKOFF = "retry_with_backoff"  # 指数退避重试
    FALLBACK = "fallback"        # 降级
    ABORT = "abort"              # 中止
    ROLLBACK = "rollback"        # 回滚


@dataclass
class ErrorContext:
    """
    错误上下文
    
    携带错误相关的上下文信息
    """
    error_code: str
    message: str
    category: ErrorCategory
    severity: ErrorSeverity = ErrorSeverity.MEDIUM
    recovery_strategy: RecoveryStrategy = RecoveryStrategy.ABORT
    timestamp: datetime = field(default_factory=datetime.utcnow)
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)
    stack_trace: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    
    def __post_init__(self):
        if self.stack_trace is None:
            self.stack_trace = traceback.format_exc()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "category": self.category.value,
            "severity": self.severity.value,
            "recovery_strategy": self.recovery_strategy.value,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "metadata": self.metadata,
            "details": self.details,
            "stack_trace": self.stack_trace,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
        }
    
    def with_metadata(self, **kwargs) -> "ErrorContext":
        """添加元数据"""
        self.metadata.update(kwargs)
        return self
    
    def with_detail(self, key: str, value: Any) -> "ErrorContext":
        """添加详细信息"""
        self.details[key] = value
        return self


class AgentError(Exception):
    """
    Agent 基础错误类
    
    所有自定义错误应该继承此类
    """
    
    error_code: str = "unknown_error"
    category: ErrorCategory = ErrorCategory.INTERNAL
    severity: ErrorSeverity = ErrorSeverity.MEDIUM
    recovery_strategy: RecoveryStrategy = RecoveryStrategy.ABORT
    
    def __init__(
        self,
        message: str,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        details: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None
    ):
        super().__init__(message)
        self.message = message
        self.correlation_id = correlation_id
        self.causation_id = causation_id
        self.metadata = metadata or {}
        self.details = details or {}
        self.original_error = original_error
        self.timestamp = datetime.utcnow()
    
    def to_context(self) -> ErrorContext:
        """转换为错误上下文"""
        return ErrorContext(
            error_code=self.error_code,
            message=self.message,
            category=self.category,
            severity=self.severity,
            recovery_strategy=self.recovery_strategy,
            correlation_id=self.correlation_id,
            causation_id=self.causation_id,
            metadata=self.metadata,
            details=self.details,
            stack_trace=traceback.format_exc(),
        )
    
    def __str__(self) -> str:
        return f"[{self.error_code}] {self.message}"
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.message})"


# ============ 验证错误 ============

class ValidationError(AgentError):
    """验证错误"""
    
    error_code = "validation_error"
    category = ErrorCategory.VALIDATION
    severity = ErrorSeverity.LOW
    recovery_strategy = RecoveryStrategy.ABORT
    
    def __init__(self, message: str, field: Optional[str] = None, **kwargs):
        super().__init__(message, **kwargs)
        if field:
            self.details["field"] = field


class InvalidConfigError(ValidationError):
    """配置验证错误"""
    
    error_code = "invalid_config"
    details: Dict[str, Any] = {"config_key": None}
    
    def __init__(self, message: str, config_key: Optional[str] = None, **kwargs):
        super().__init__(message, **kwargs)
        if config_key:
            self.details["config_key"] = config_key


# ============ 认证授权错误 ============

class AuthenticationError(AgentError):
    """认证错误"""
    
    error_code = "authentication_error"
    category = ErrorCategory.AUTHENTICATION
    severity = ErrorSeverity.HIGH
    recovery_strategy = RecoveryStrategy.ABORT


class UnauthorizedError(AuthenticationError):
    """未授权错误"""
    
    error_code = "unauthorized"
    severity = ErrorSeverity.HIGH


class TokenExpiredError(AuthenticationError):
    """Token 过期错误"""
    
    error_code = "token_expired"
    severity = ErrorSeverity.MEDIUM
    recovery_strategy = RecoveryStrategy.RETRY


class AuthorizationError(AgentError):
    """授权错误"""
    
    error_code = "authorization_error"
    category = ErrorCategory.AUTHORIZATION
    severity = ErrorSeverity.HIGH
    recovery_strategy = RecoveryStrategy.ABORT


class PermissionDeniedError(AuthorizationError):
    """权限拒绝错误"""
    
    error_code = "permission_denied"
    severity = ErrorSeverity.HIGH


# ============ 资源错误 ============

class NotFoundError(AgentError):
    """资源未找到错误"""
    
    error_code = "not_found"
    category = ErrorCategory.NOT_FOUND
    severity = ErrorSeverity.MEDIUM
    recovery_strategy = RecoveryStrategy.ABORT
    
    def __init__(self, message: str, resource_type: Optional[str] = None, **kwargs):
        super().__init__(message, **kwargs)
        if resource_type:
            self.details["resource_type"] = resource_type


class ConflictError(AgentError):
    """冲突错误"""
    
    error_code = "conflict"
    category = ErrorCategory.CONFLICT
    severity = ErrorSeverity.MEDIUM
    recovery_strategy = RecoveryStrategy.ABORT


class DuplicateError(ConflictError):
    """重复错误"""
    
    error_code = "duplicate"
    severity = ErrorSeverity.MEDIUM


# ============ 限流超时错误 ============

class RateLimitError(AgentError):
    """速率限制错误"""
    
    error_code = "rate_limit"
    category = ErrorCategory.RATE_LIMIT
    severity = ErrorSeverity.MEDIUM
    recovery_strategy = RecoveryStrategy.RETRY_WITH_BACKOFF
    
    def __init__(self, message: str, retry_after: Optional[int] = None, **kwargs):
        super().__init__(message, **kwargs)
        if retry_after:
            self.details["retry_after"] = retry_after


class TimeoutError(AgentError):
    """超时错误"""
    
    error_code = "timeout"
    category = ErrorCategory.TIMEOUT
    severity = ErrorSeverity.HIGH
    recovery_strategy = RecoveryStrategy.RETRY
    
    def __init__(self, message: str, operation: Optional[str] = None, **kwargs):
        super().__init__(message, **kwargs)
        if operation:
            self.details["operation"] = operation


# ============ 网络服务错误 ============

class NetworkError(AgentError):
    """网络错误"""
    
    error_code = "network_error"
    category = ErrorCategory.NETWORK
    severity = ErrorSeverity.HIGH
    recovery_strategy = RecoveryStrategy.RETRY


class ServiceUnavailableError(AgentError):
    """服务不可用错误"""
    
    error_code = "service_unavailable"
    category = ErrorCategory.SERVICE
    severity = ErrorSeverity.CRITICAL
    recovery_strategy = RecoveryStrategy.FALLBACK


class DependencyError(AgentError):
    """依赖错误"""
    
    error_code = "dependency_error"
    category = ErrorCategory.DEPENDENCY
    severity = ErrorSeverity.HIGH
    recovery_strategy = RecoveryStrategy.FALLBACK


# ============ 插件事件错误 ============

class PluginError(AgentError):
    """插件错误"""
    
    error_code = "plugin_error"
    category = ErrorCategory.PLUGIN
    severity = ErrorSeverity.HIGH
    recovery_strategy = RecoveryStrategy.ABORT
    
    def __init__(self, message: str, plugin_name: Optional[str] = None, **kwargs):
        super().__init__(message, **kwargs)
        if plugin_name:
            self.details["plugin_name"] = plugin_name


class PluginLoadError(PluginError):
    """插件加载错误"""
    
    error_code = "plugin_load_error"
    severity = ErrorSeverity.HIGH


class PluginActivationError(PluginError):
    """插件激活错误"""
    
    error_code = "plugin_activation_error"
    severity = ErrorSeverity.HIGH


class EventError(AgentError):
    """事件错误"""
    
    error_code = "event_error"
    category = ErrorCategory.EVENT
    severity = ErrorSeverity.MEDIUM
    recovery_strategy = RecoveryStrategy.ABORT
    
    def __init__(self, message: str, event_type: Optional[str] = None, **kwargs):
        super().__init__(message, **kwargs)
        if event_type:
            self.details["event_type"] = event_type


# ============ 内部错误 ============

class InternalError(AgentError):
    """内部错误"""
    
    error_code = "internal_error"
    category = ErrorCategory.INTERNAL
    severity = ErrorSeverity.CRITICAL
    recovery_strategy = RecoveryStrategy.ABORT


class ConfigurationError(AgentError):
    """配置错误"""
    
    error_code = "configuration_error"
    category = ErrorCategory.CONFIGURATION
    severity = ErrorSeverity.HIGH
    recovery_strategy = RecoveryStrategy.ABORT


# ============ 错误处理器 ============

class ErrorHandler:
    """
    错误处理器
    
    提供错误分类、恢复策略执行、错误日志等功能
    """
    
    def __init__(self):
        self._handlers: Dict[ErrorCategory, List[callable]] = {}
        self._error_log: List[ErrorContext] = []
    
    def register_handler(
        self,
        category: ErrorCategory,
        handler: callable
    ) -> None:
        """注册错误处理器"""
        if category not in self._handlers:
            self._handlers[category] = []
        self._handlers[category].append(handler)
    
    def unregister_handler(
        self,
        category: ErrorCategory,
        handler: callable
    ) -> None:
        """注销错误处理器"""
        if category in self._handlers:
            try:
                self._handlers[category].remove(handler)
            except ValueError:
                pass
    
    async def handle(self, error: AgentError) -> bool:
        """
        处理错误
        
        Returns:
            是否成功处理
        """
        context = error.to_context()
        
        # 记录错误日志
        self._error_log.append(context)
        
        # 调用注册的处理器
        handlers = self._handlers.get(error.category, [])
        
        success = False
        for handler in handlers:
            try:
                result = handler(error, context)
                if asyncio.iscoroutine(result):
                    result = await result
                if result:
                    success = True
            except Exception as e:
                print(f"Error handler failed: {e}")
        
        # 执行恢复策略
        success = await self._execute_recovery(context)
        
        return success
    
    async def _execute_recovery(self, context: ErrorContext) -> bool:
        """执行恢复策略"""
        strategy = context.recovery_strategy
        
        if strategy == RecoveryStrategy.IGNORE:
            return True
        
        elif strategy == RecoveryStrategy.RETRY:
            return await self._retry(context)
        
        elif strategy == RecoveryStrategy.RETRY_WITH_BACKOFF:
            return await self._retry_with_backoff(context)
        
        elif strategy == RecoveryStrategy.FALLBACK:
            return await self._fallback(context)
        
        elif strategy == RecoveryStrategy.ABORT:
            return False
        
        elif strategy == RecoveryStrategy.ROLLBACK:
            return await self._rollback(context)
        
        return False
    
    async def _retry(self, context: ErrorContext) -> bool:
        """重试"""
        if context.retry_count < context.max_retries:
            context.retry_count += 1
            return True
        return False
    
    async def _retry_with_backoff(self, context: ErrorContext) -> bool:
        """指数退避重试"""
        if context.retry_count < context.max_retries:
            import asyncio
            delay = (2 ** context.retry_count)  # 指数退避
            await asyncio.sleep(delay)
            context.retry_count += 1
            return True
        return False
    
    async def _fallback(self, context: ErrorContext) -> bool:
        """降级处理"""
        # 子类可以实现具体的降级逻辑
        print(f"Fallback for error: {context.error_code}")
        return True
    
    async def _rollback(self, context: ErrorContext) -> bool:
        """回滚处理"""
        # 子类可以实现具体的回滚逻辑
        print(f"Rollback for error: {context.error_code}")
        return True
    
    def get_error_log(self, limit: int = 100) -> List[ErrorContext]:
        """获取错误日志"""
        return self._error_log[-limit:]
    
    def clear_error_log(self) -> None:
        """清空错误日志"""
        self._error_log.clear()
    
    def get_error_summary(self) -> Dict[str, Any]:
        """获取错误摘要"""
        summary = {
            "total_errors": len(self._error_log),
            "by_category": {},
            "by_severity": {},
            "recent_errors": [],
        }
        
        for error in self._error_log[-100:]:
            # 按分类统计
            cat = error.category.value
            summary["by_category"][cat] = summary["by_category"].get(cat, 0) + 1
            
            # 按严重程度统计
            sev = error.severity.value
            summary["by_severity"][sev] = summary["by_severity"].get(sev, 0) + 1
        
        # 最近错误
        summary["recent_errors"] = [
            {
                "error_code": e.error_code,
                "message": e.message,
                "category": e.category.value,
                "timestamp": e.timestamp.isoformat(),
            }
            for e in self._error_log[-10:]
        ]
        
        return summary


# 导入 asyncio 用于异步处理
import asyncio


__all__ = [
    "ErrorCategory",
    "ErrorSeverity",
    "RecoveryStrategy",
    "ErrorContext",
    "AgentError",
    "ValidationError",
    "InvalidConfigError",
    "AuthenticationError",
    "UnauthorizedError",
    "TokenExpiredError",
    "AuthorizationError",
    "PermissionDeniedError",
    "NotFoundError",
    "ConflictError",
    "DuplicateError",
    "RateLimitError",
    "TimeoutError",
    "NetworkError",
    "ServiceUnavailableError",
    "DependencyError",
    "PluginError",
    "PluginLoadError",
    "PluginActivationError",
    "EventError",
    "InternalError",
    "ConfigurationError",
    "ErrorHandler",
]
