"""
Agent 中间件系统（参考 DeerFlow 设计）

中间件生命周期：
1. before_agent(state, runtime) -> dict | None
   - 在模型调用前修改状态
   - 返回字典合并到 state，或 None 表示不修改

2. after_agent(state, runtime) -> dict | None
   - 在模型调用后修改状态
   - 处理工具调用结果、生成标题等

3. wrap_tool_call(request, handler) -> ToolMessage
   - 包装工具调用
   - 可以拦截、修改、记录工具调用
"""
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Callable

logger = logging.getLogger(__name__)


class AgentMiddleware(ABC):
    """Agent 中间件基类"""
    
    def before_agent(self, state: Dict[str, Any], runtime: 'RuntimeContext') -> Optional[Dict[str, Any]]:
        """
        在模型调用前执行
        
        Args:
            state: 当前状态
            runtime: 运行时上下文
            
        Returns:
            要合并到 state 的字典，或 None
        """
        return None
    
    def after_agent(self, state: Dict[str, Any], runtime: 'RuntimeContext') -> Optional[Dict[str, Any]]:
        """
        在模型调用后执行
        
        Args:
            state: 当前状态（包含模型响应）
            runtime: 运行时上下文
            
        Returns:
            要合并到 state 的字典，或 None
        """
        return None
    
    async def wrap_tool_call(
        self, 
        request: Dict[str, Any], 
        handler: Callable
    ) -> Any:
        """
        包装工具调用
        
        Args:
            request: 工具调用请求 {"name": ..., "args": ..., "tool_call_id": ...}
            handler: 实际的工具执行函数
            
        Returns:
            工具执行结果（ToolMessage 或其他）
        """
        # 默认：直接执行，不拦截
        return await handler(request)


class RuntimeContext:
    """
    运行时上下文（统一管理运行时信息）
    
    参考 DeerFlow 设计，集中管理：
    - thread_id: 线程 ID
    - user_id: 用户 ID
    - session_id: 会话 ID（可选）
    - sandbox_id: 沙箱 ID（可选）
    - workspace_path: 工作区路径
    - uploads_path: 上传文件路径
    - outputs_path: 输出文件路径
    """
    
    def __init__(
        self,
        thread_id: str,
        user_id: int,
        session_id: Optional[str] = None,
        **kwargs: Any,
    ):
        self.thread_id = thread_id
        self.user_id = user_id
        self.session_id = session_id
        
        # 扩展字段（中间件可以添加）
        self._extras = kwargs
    
    @property
    def sandbox_id(self) -> Optional[str]:
        return self._extras.get("sandbox_id")
    
    @sandbox_id.setter
    def sandbox_id(self, value: str):
        self._extras["sandbox_id"] = value
    
    @property
    def workspace_path(self) -> Optional[str]:
        return self._extras.get("workspace_path")
    
    @workspace_path.setter
    def workspace_path(self, value: str):
        self._extras["workspace_path"] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取扩展字段"""
        return self._extras.get(key, default)
    
    def set(self, key: str, value: Any):
        """设置扩展字段"""
        self._extras[key] = value
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于日志/调试）"""
        return {
            "thread_id": self.thread_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            **self._extras,
        }


class MiddlewareChain:
    """
    中间件链（按顺序执行所有中间件）
    
    参考 DeerFlow 设计：
    - 基础层：ThreadData, Sandbox, ToolErrorHandling
    - 功能层：Summarization, TodoList, Title, Memory, etc.
    """
    
    def __init__(self, middlewares: Optional[list] = None):
        self.middlewares = middlewares or []
    
    def add(self, middleware: AgentMiddleware):
        """添加中间件到链尾"""
        self.middlewares.append(middleware)
    
    async def before_agent(self, state: Dict[str, Any], runtime: RuntimeContext) -> Dict[str, Any]:
        """
        执行所有中间件的 before_agent
        
        按顺序执行，每个中间件的返回值合并到 state
        支持同步和异步方法
        """
        import inspect
        result = dict(state)
        
        for mw in self.middlewares:
            try:
                method = mw.before_agent
                if inspect.iscoroutinefunction(method):
                    updates = await method(result, runtime)
                else:
                    updates = method(result, runtime)
                if updates:
                    result.update(updates)
                    logger.debug("[MiddlewareChain] %s added: %s", mw.__class__.__name__, list(updates.keys()))
            except Exception as e:
                logger.error("[MiddlewareChain] %s.before_agent failed: %s", mw.__class__.__name__, e)
                # 继续执行下一个中间件（容错）
        
        return result
    
    async def after_agent(self, state: Dict[str, Any], runtime: RuntimeContext, response: Any = None) -> Dict[str, Any]:
        """
        执行所有中间件的 after_agent
        
        按顺序执行，每个中间件的返回值合并到 state
        
        Args:
            state: 当前状态
            runtime: 运行时上下文
            response: 模型响应（可选）
        """
        import inspect
        result = dict(state)
        
        for mw in self.middlewares:
            try:
                method = mw.after_agent
                # 检查是否支持 response 参数
                sig = inspect.signature(method)
                is_async = inspect.iscoroutinefunction(method)
                
                if len(sig.parameters) >= 3:
                    if is_async:
                        updates = await method(result, runtime, response)
                    else:
                        updates = method(result, runtime, response)
                else:
                    if is_async:
                        updates = await method(result, runtime)
                    else:
                        updates = method(result, runtime)
                        
                if updates:
                    result.update(updates)
                    logger.debug("[MiddlewareChain] %s added: %s", mw.__class__.__name__, list(updates.keys()))
            except Exception as e:
                logger.error("[MiddlewareChain] %s.after_agent failed: %s", mw.__class__.__name__, e)
                # 继续执行下一个中间件（容错）
        
        return result
    
    async def wrap_tool_call(
        self, 
        request: Dict[str, Any], 
        handler: Callable,
        state: Dict[str, Any],
        runtime: RuntimeContext,
    ) -> Any:
        """
        包装工具调用（所有中间件嵌套包装）
        
        执行顺序：
        middleware[0].wrap -> middleware[1].wrap -> ... -> handler -> ... -> middleware[1].wrap -> middleware[0].wrap
        """
        # 递归包装：从最后一个中间件开始，向前包装
        async def execute_with_middleware(index: int, current_handler: Callable) -> Any:
            if index < 0:
                # 所有中间件都已包装，执行实际 handler
                return await current_handler(request)
            
            mw = self.middlewares[index]
            
            # 创建包装函数，传递给下一个中间件
            async def wrapped_by_next() -> Any:
                return await execute_with_middleware(index - 1, current_handler)
            
            try:
                return await mw.wrap_tool_call(request, wrapped_by_next)
            except Exception as e:
                logger.error("[MiddlewareChain] %s.wrap_tool_call failed: %s", mw.__class__.__name__, e)
                # 降级：直接执行 handler
                return await current_handler(request)
        
        return await execute_with_middleware(len(self.middlewares) - 1, handler)
