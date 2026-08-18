"""
测试统一错误处理系统
"""
import pytest
import asyncio
from packages.agent.errors.types import (
    ErrorCategory,
    ErrorSeverity,
    RecoveryStrategy,
    ErrorContext,
    AgentError,
    ValidationError,
    InvalidConfigError,
    AuthenticationError,
    UnauthorizedError,
    TokenExpiredError,
    AuthorizationError,
    PermissionDeniedError,
    NotFoundError,
    ConflictError,
    DuplicateError,
    RateLimitError,
    TimeoutError,
    NetworkError,
    ServiceUnavailableError,
    DependencyError,
    PluginError,
    PluginLoadError,
    PluginActivationError,
    EventError,
    InternalError,
    ConfigurationError,
    ErrorHandler,
)


class TestErrorContext:
    """测试错误上下文"""
    
    def test_context_creation(self):
        """测试上下文创建"""
        ctx = ErrorContext(
            error_code="test_error",
            message="Test error message",
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.MEDIUM,
            recovery_strategy=RecoveryStrategy.RETRY,
        )
        
        assert ctx.error_code == "test_error"
        assert ctx.message == "Test error message"
        assert ctx.category == ErrorCategory.VALIDATION
        assert ctx.severity == ErrorSeverity.MEDIUM
        assert ctx.recovery_strategy == RecoveryStrategy.RETRY
        assert ctx.retry_count == 0
        assert ctx.max_retries == 3
    
    def test_context_to_dict(self):
        """测试上下文转字典"""
        ctx = ErrorContext(
            error_code="test_error",
            message="Test message",
            category=ErrorCategory.INTERNAL,
        )
        
        data = ctx.to_dict()
        
        assert data["error_code"] == "test_error"
        assert data["message"] == "Test message"
        assert data["category"] == "internal"
        assert "timestamp" in data
    
    def test_context_with_metadata(self):
        """测试添加元数据"""
        ctx = ErrorContext(
            error_code="test_error",
            message="Test message",
            category=ErrorCategory.VALIDATION,
        )
        
        ctx.with_metadata(user_id="123", action="create")
        
        assert ctx.metadata["user_id"] == "123"
        assert ctx.metadata["action"] == "create"
    
    def test_context_with_detail(self):
        """测试添加详细信息"""
        ctx = ErrorContext(
            error_code="test_error",
            message="Test message",
            category=ErrorCategory.VALIDATION,
        )
        
        ctx.with_detail("field", "email")
        ctx.with_detail("reason", "invalid_format")
        
        assert ctx.details["field"] == "email"
        assert ctx.details["reason"] == "invalid_format"


class TestAgentError:
    """测试 Agent 基础错误"""
    
    def test_agent_error_creation(self):
        """测试基础错误创建"""
        error = AgentError(
            message="Something went wrong",
            correlation_id="corr-123",
            metadata={"user_id": "123"},
        )
        
        assert error.message == "Something went wrong"
        assert error.correlation_id == "corr-123"
        assert error.metadata["user_id"] == "123"
        assert error.error_code == "unknown_error"
        assert error.category == ErrorCategory.INTERNAL
    
    def test_agent_error_to_context(self):
        """测试错误转上下文"""
        error = AgentError(message="Test error")
        
        ctx = error.to_context()
        
        assert ctx.error_code == error.error_code
        assert ctx.message == error.message
        assert ctx.category == error.category
        assert ctx.severity == error.severity
    
    def test_agent_error_str(self):
        """测试错误字符串表示"""
        error = AgentError(message="Test error")
        
        assert str(error) == "[unknown_error] Test error"
    
    def test_agent_error_repr(self):
        """测试错误表示"""
        error = AgentError(message="Test error")
        
        assert "AgentError" in repr(error)
        assert "Test error" in repr(error)


class TestValidationError:
    """测试验证错误"""
    
    def test_validation_error(self):
        """测试验证错误"""
        error = ValidationError(
            message="Invalid input",
            field="email",
        )
        
        assert error.error_code == "validation_error"
        assert error.category == ErrorCategory.VALIDATION
        assert error.severity == ErrorSeverity.LOW
        assert error.details["field"] == "email"
    
    def test_invalid_config_error(self):
        """测试配置验证错误"""
        error = InvalidConfigError(
            message="Invalid API key",
            config_key="api_key",
        )
        
        assert error.error_code == "invalid_config"
        assert error.details["config_key"] == "api_key"


class TestAuthenticationError:
    """测试认证错误"""
    
    def test_authentication_error(self):
        """测试认证错误"""
        error = AuthenticationError(message="Authentication failed")
        
        assert error.error_code == "authentication_error"
        assert error.category == ErrorCategory.AUTHENTICATION
        assert error.severity == ErrorSeverity.HIGH
    
    def test_unauthorized_error(self):
        """测试未授权错误"""
        error = UnauthorizedError(message="Not authorized")
        
        assert error.error_code == "unauthorized"
        assert error.severity == ErrorSeverity.HIGH
    
    def test_token_expired_error(self):
        """测试 Token 过期错误"""
        error = TokenExpiredError(message="Token expired")
        
        assert error.error_code == "token_expired"
        assert error.recovery_strategy == RecoveryStrategy.RETRY


class TestAuthorizationError:
    """测试授权错误"""
    
    def test_authorization_error(self):
        """测试授权错误"""
        error = AuthorizationError(message="Access denied")
        
        assert error.error_code == "authorization_error"
        assert error.category == ErrorCategory.AUTHORIZATION
    
    def test_permission_denied_error(self):
        """测试权限拒绝错误"""
        error = PermissionDeniedError(message="Permission denied")
        
        assert error.error_code == "permission_denied"
        assert error.severity == ErrorSeverity.HIGH


class TestResourceErrors:
    """测试资源错误"""
    
    def test_not_found_error(self):
        """测试未找到错误"""
        error = NotFoundError(
            message="User not found",
            resource_type="user",
        )
        
        assert error.error_code == "not_found"
        assert error.category == ErrorCategory.NOT_FOUND
        assert error.details["resource_type"] == "user"
    
    def test_conflict_error(self):
        """测试冲突错误"""
        error = ConflictError(message="Resource conflict")
        
        assert error.error_code == "conflict"
        assert error.category == ErrorCategory.CONFLICT
    
    def test_duplicate_error(self):
        """测试重复错误"""
        error = DuplicateError(message="Email already exists")
        
        assert error.error_code == "duplicate"
        assert error.severity == ErrorSeverity.MEDIUM


class TestRateLimitTimeoutErrors:
    """测试限流超时错误"""
    
    def test_rate_limit_error(self):
        """测试速率限制错误"""
        error = RateLimitError(
            message="Rate limit exceeded",
            retry_after=60,
        )
        
        assert error.error_code == "rate_limit"
        assert error.category == ErrorCategory.RATE_LIMIT
        assert error.recovery_strategy == RecoveryStrategy.RETRY_WITH_BACKOFF
        assert error.details["retry_after"] == 60
    
    def test_timeout_error(self):
        """测试超时错误"""
        error = TimeoutError(
            message="Request timeout",
            operation="database_query",
        )
        
        assert error.error_code == "timeout"
        assert error.category == ErrorCategory.TIMEOUT
        assert error.recovery_strategy == RecoveryStrategy.RETRY
        assert error.details["operation"] == "database_query"


class TestNetworkServiceErrors:
    """测试网络服务错误"""
    
    def test_network_error(self):
        """测试网络错误"""
        error = NetworkError(message="Connection failed")
        
        assert error.error_code == "network_error"
        assert error.category == ErrorCategory.NETWORK
        assert error.severity == ErrorSeverity.HIGH
    
    def test_service_unavailable_error(self):
        """测试服务不可用错误"""
        error = ServiceUnavailableError(message="Service down")
        
        assert error.error_code == "service_unavailable"
        assert error.severity == ErrorSeverity.CRITICAL
        assert error.recovery_strategy == RecoveryStrategy.FALLBACK
    
    def test_dependency_error(self):
        """测试依赖错误"""
        error = DependencyError(message="Database connection failed")
        
        assert error.error_code == "dependency_error"
        assert error.category == ErrorCategory.DEPENDENCY
        assert error.recovery_strategy == RecoveryStrategy.FALLBACK


class TestPluginEventErrors:
    """测试插件事件错误"""
    
    def test_plugin_error(self):
        """测试插件错误"""
        error = PluginError(
            message="Plugin failed",
            plugin_name="calculator",
        )
        
        assert error.error_code == "plugin_error"
        assert error.category == ErrorCategory.PLUGIN
        assert error.details["plugin_name"] == "calculator"
    
    def test_plugin_load_error(self):
        """测试插件加载错误"""
        error = PluginLoadError(message="Failed to load plugin")
        
        assert error.error_code == "plugin_load_error"
        assert error.severity == ErrorSeverity.HIGH
    
    def test_plugin_activation_error(self):
        """测试插件激活错误"""
        error = PluginActivationError(message="Failed to activate")
        
        assert error.error_code == "plugin_activation_error"
    
    def test_event_error(self):
        """测试事件错误"""
        error = EventError(
            message="Event processing failed",
            event_type="message.user",
        )
        
        assert error.error_code == "event_error"
        assert error.category == ErrorCategory.EVENT
        assert error.details["event_type"] == "message.user"


class TestInternalErrors:
    """测试内部错误"""
    
    def test_internal_error(self):
        """测试内部错误"""
        error = InternalError(message="Unexpected error")
        
        assert error.error_code == "internal_error"
        assert error.severity == ErrorSeverity.CRITICAL
    
    def test_configuration_error(self):
        """测试配置错误"""
        error = ConfigurationError(message="Invalid configuration")
        
        assert error.error_code == "configuration_error"
        assert error.category == ErrorCategory.CONFIGURATION


class TestErrorHandler:
    """测试错误处理器"""
    
    @pytest.mark.asyncio
    async def test_error_handler_creation(self):
        """测试错误处理器创建"""
        handler = ErrorHandler()
        
        assert handler._handlers == {}
        assert handler._error_log == []
    
    @pytest.mark.asyncio
    async def test_register_handler(self):
        """测试注册处理器"""
        handler = ErrorHandler()
        
        called = []
        
        def my_handler(error, context):
            called.append(error)
            return True
        
        handler.register_handler(ErrorCategory.VALIDATION, my_handler)
        
        assert ErrorCategory.VALIDATION in handler._handlers
        assert my_handler in handler._handlers[ErrorCategory.VALIDATION]
    
    @pytest.mark.asyncio
    async def test_unregister_handler(self):
        """测试注销处理器"""
        handler = ErrorHandler()
        
        def my_handler(error, context):
            return True
        
        handler.register_handler(ErrorCategory.VALIDATION, my_handler)
        handler.unregister_handler(ErrorCategory.VALIDATION, my_handler)
        
        assert my_handler not in handler._handlers.get(ErrorCategory.VALIDATION, [])
    
    @pytest.mark.asyncio
    async def test_handle_error(self):
        """测试处理错误"""
        handler = ErrorHandler()
        
        error = ValidationError(message="Invalid input")
        
        success = await handler.handle(error)
        
        # 错误应该被记录
        assert len(handler._error_log) == 1
        assert handler._error_log[0].error_code == "validation_error"
    
    @pytest.mark.asyncio
    async def test_handle_error_with_handler(self):
        """测试带处理器的错误处理"""
        handler = ErrorHandler()
        
        called = []
        
        def validation_handler(error, context):
            called.append(error)
            return True
        
        handler.register_handler(ErrorCategory.VALIDATION, validation_handler)
        
        error = ValidationError(message="Invalid input")
        success = await handler.handle(error)
        
        assert len(called) == 1
        assert isinstance(called[0], ValidationError)
    
    @pytest.mark.asyncio
    async def test_retry_strategy(self):
        """测试重试策略"""
        handler = ErrorHandler()
        
        error = TimeoutError(message="Timeout")
        ctx = error.to_context()
        
        # 第一次重试
        result = await handler._retry(ctx)
        assert result is True
        assert ctx.retry_count == 1
        
        # 达到最大重试次数
        ctx.retry_count = 3
        result = await handler._retry(ctx)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_retry_with_backoff(self):
        """测试指数退避重试"""
        handler = ErrorHandler()
        
        error = RateLimitError(message="Rate limit")
        ctx = error.to_context()
        
        result = await handler._retry_with_backoff(ctx)
        
        assert result is True
        assert ctx.retry_count == 1
    
    @pytest.mark.asyncio
    async def test_fallback_strategy(self):
        """测试降级策略"""
        handler = ErrorHandler()
        
        error = ServiceUnavailableError(message="Service down")
        ctx = error.to_context()
        
        result = await handler._fallback(ctx)
        
        # 降级应该返回 True（继续处理）
        assert result is True
    
    @pytest.mark.asyncio
    async def test_abort_strategy(self):
        """测试中止策略"""
        handler = ErrorHandler()
        
        error = InternalError(message="Critical error")
        ctx = error.to_context()
        
        result = await handler._execute_recovery(ctx)
        
        # 中止应该返回 False
        assert result is False
    
    @pytest.mark.asyncio
    async def test_get_error_log(self):
        """测试获取错误日志"""
        handler = ErrorHandler()
        
        for i in range(10):
            error = ValidationError(message=f"Error {i}")
            await handler.handle(error)
        
        log = handler.get_error_log(limit=5)
        
        assert len(log) == 5
        # 应该返回最新的 5 个
        assert "Error 9" in log[-1].message
    
    @pytest.mark.asyncio
    async def test_clear_error_log(self):
        """测试清空错误日志"""
        handler = ErrorHandler()
        
        error = ValidationError(message="Test")
        await handler.handle(error)
        
        handler.clear_error_log()
        
        assert len(handler._error_log) == 0
    
    @pytest.mark.asyncio
    async def test_get_error_summary(self):
        """测试获取错误摘要"""
        handler = ErrorHandler()
        
        # 添加不同类型的错误
        await handler.handle(ValidationError(message="Validation 1"))
        await handler.handle(ValidationError(message="Validation 2"))
        await handler.handle(AuthenticationError(message="Auth failed"))
        
        summary = handler.get_error_summary()
        
        assert summary["total_errors"] == 3
        assert summary["by_category"]["validation"] == 2
        assert summary["by_category"]["authentication"] == 1
        assert len(summary["recent_errors"]) == 3


class TestErrorInheritance:
    """测试错误继承"""
    
    def test_error_isinstance(self):
        """测试错误类型检查"""
        error = ValidationError(message="Test")
        
        assert isinstance(error, ValidationError)
        assert isinstance(error, AgentError)
        assert isinstance(error, Exception)
    
    def test_error_hierarchy(self):
        """测试错误层次结构"""
        error = UnauthorizedError(message="Not authorized")
        
        assert isinstance(error, UnauthorizedError)
        assert isinstance(error, AuthenticationError)
        assert isinstance(error, AgentError)


class TestErrorCorrelation:
    """测试错误关联"""
    
    def test_correlation_id(self):
        """测试关联 ID"""
        error = AgentError(
            message="Test error",
            correlation_id="corr-123",
            causation_id="cause-456",
        )
        
        ctx = error.to_context()
        
        assert ctx.correlation_id == "corr-123"
        assert ctx.causation_id == "cause-456"
    
    def test_error_chain(self):
        """测试错误链"""
        original = ValueError("Original error")
        
        error = AgentError(
            message="Wrapped error",
            original_error=original,
        )
        
        assert error.original_error == original


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
