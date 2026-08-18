"""
事件驱动扩展系统

提供事件总线、拦截器、转换器等扩展机制
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar, Generic
from datetime import datetime
import asyncio
import uuid


class ExtensionPointType(str, Enum):
    """扩展点类型"""
    INTERCEPTOR = "interceptor"  # 拦截器
    TRANSFORMER = "transformer"  # 转换器
    DECORATOR = "decorator"      # 装饰器
    HANDLER = "handler"          # 处理器
    MIDDLEWARE = "middleware"    # 中间件


class ExecutionOrder(str, Enum):
    """执行顺序"""
    PRE = "pre"           # 前置
    POST = "post"         # 后置
    AROUND = "around"     # 环绕
    ON_ERROR = "on_error" # 错误处理


@dataclass
class ExtensionContext:
    """
    扩展上下文
    
    携带扩展点执行所需的所有信息
    """
    event_type: str
    payload: Any
    metadata: Dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: Optional[Exception] = None
    should_continue: bool = True  # 是否继续执行后续扩展
    timestamp: datetime = field(default_factory=datetime.utcnow)
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    def stop_propagation(self):
        """停止传播"""
        self.should_continue = False
    
    def set_result(self, result: Any):
        """设置结果"""
        self.result = result
        self.should_continue = False
    
    def set_error(self, error: Exception):
        """设置错误"""
        self.error = error
        self.should_continue = False


T = TypeVar('T')


class Extension(ABC, Generic[T]):
    """
    扩展基类
    
    所有扩展必须继承此类
    """
    
    name: str = "unnamed_extension"
    description: str = ""
    version: str = "1.0.0"
    priority: int = 0  # 优先级，数字越大越先执行
    
    @abstractmethod
    async def execute(self, ctx: ExtensionContext) -> T:
        """执行扩展"""
        pass
    
    def supports(self, event_type: str) -> bool:
        """是否支持该事件类型"""
        return True
    
    def on_success(self, ctx: ExtensionContext, result: T):
        """成功回调"""
        pass
    
    def on_error(self, ctx: ExtensionContext, error: Exception):
        """错误回调"""
        pass


class Interceptor(Extension[None]):
    """
    拦截器
    
    在事件处理前后执行，可以修改 payload 或阻止执行
    """
    
    execution_order: ExecutionOrder = ExecutionOrder.PRE
    
    async def execute(self, ctx: ExtensionContext) -> None:
        """执行拦截"""
        if self.execution_order == ExecutionOrder.PRE:
            await self.pre_handle(ctx)
        elif self.execution_order == ExecutionOrder.POST:
            await self.post_handle(ctx)
        elif self.execution_order == ExecutionOrder.AROUND:
            await self.around_handle(ctx)
        elif self.execution_order == ExecutionOrder.ON_ERROR:
            if ctx.error:
                await self.on_error_handle(ctx)
    
    @abstractmethod
    async def pre_handle(self, ctx: ExtensionContext) -> None:
        """前置处理"""
        pass
    
    async def post_handle(self, ctx: ExtensionContext) -> None:
        """后置处理"""
        pass
    
    async def around_handle(self, ctx: ExtensionContext) -> None:
        """环绕处理"""
        pass
    
    async def on_error_handle(self, ctx: ExtensionContext) -> None:
        """错误处理"""
        pass


class Transformer(Extension[Any]):
    """
    转换器
    
    转换事件 payload，返回新的 payload
    """
    
    async def execute(self, ctx: ExtensionContext) -> Any:
        """执行转换"""
        return await self.transform(ctx.payload)
    
    @abstractmethod
    async def transform(self, payload: Any) -> Any:
        """转换 payload"""
        pass


class EventHandler(Extension[None]):
    """
    事件处理器
    
    响应特定事件，执行自定义逻辑
    """
    
    target_event: str = ""
    
    def supports(self, event_type: str) -> bool:
        return event_type == self.target_event
    
    async def execute(self, ctx: ExtensionContext) -> None:
        """执行处理"""
        await self.handle(ctx.payload)
    
    @abstractmethod
    async def handle(self, payload: Any) -> None:
        """处理事件"""
        pass


class ExtensionRegistry:
    """
    扩展注册中心
    
    管理所有扩展的注册和执行
    """
    
    def __init__(self):
        self._extensions: Dict[str, List[Extension]] = {}
        self._interceptors: Dict[str, List[Interceptor]] = {}
        self._transformers: Dict[str, List[Transformer]] = {}
        self._handlers: Dict[str, List[EventHandler]] = {}
    
    def register(self, extension: Extension) -> None:
        """注册扩展"""
        event_type = getattr(extension, 'target_event', 'all')
        
        if event_type not in self._extensions:
            self._extensions[event_type] = []
        
        self._extensions[event_type].append(extension)
        
        # 分类注册
        if isinstance(extension, Interceptor):
            if event_type not in self._interceptors:
                self._interceptors[event_type] = []
            self._interceptors[event_type].append(extension)
        
        elif isinstance(extension, Transformer):
            if event_type not in self._transformers:
                self._transformers[event_type] = []
            self._transformers[event_type].append(extension)
        
        elif isinstance(extension, EventHandler):
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append(extension)
    
    def unregister(self, extension: Extension) -> None:
        """注销扩展"""
        event_type = getattr(extension, 'target_event', 'all')
        
        if event_type in self._extensions:
            try:
                self._extensions[event_type].remove(extension)
            except ValueError:
                pass
        
        # 从分类中移除
        if isinstance(extension, Interceptor) and event_type in self._interceptors:
            try:
                self._interceptors[event_type].remove(extension)
            except ValueError:
                pass
        
        elif isinstance(extension, Transformer) and event_type in self._transformers:
            try:
                self._transformers[event_type].remove(extension)
            except ValueError:
                pass
        
        elif isinstance(extension, EventHandler) and event_type in self._handlers:
            try:
                self._handlers[event_type].remove(extension)
            except ValueError:
                pass
    
    def get_extensions(self, event_type: str) -> List[Extension]:
        """获取指定事件类型的扩展"""
        extensions = self._extensions.get(event_type, [])
        extensions.extend(self._extensions.get('all', []))
        
        # 按优先级排序
        return sorted(extensions, key=lambda e: e.priority, reverse=True)
    
    async def execute_interceptors(
        self,
        event_type: str,
        ctx: ExtensionContext,
        order: ExecutionOrder = ExecutionOrder.PRE
    ) -> None:
        """执行拦截器"""
        interceptors = self._interceptors.get(event_type, [])
        interceptors.extend(self._interceptors.get('all', []))
        
        # 过滤并排序
        matching = [
            i for i in interceptors
            if i.execution_order == order and i.supports(event_type)
        ]
        matching.sort(key=lambda i: i.priority, reverse=True)
        
        for interceptor in matching:
            if not ctx.should_continue:
                break
            
            try:
                await interceptor.execute(ctx)
            except Exception as e:
                if order == ExecutionOrder.ON_ERROR:
                    # 错误处理器的错误不应该再触发错误处理
                    pass
                else:
                    ctx.set_error(e)
    
    async def execute_transformers(
        self,
        event_type: str,
        ctx: ExtensionContext
    ) -> Any:
        """执行转换器"""
        transformers = self._transformers.get(event_type, [])
        transformers.extend(self._transformers.get('all', []))
        
        # 过滤并排序
        matching = [
            t for t in transformers
            if t.supports(event_type)
        ]
        matching.sort(key=lambda t: t.priority, reverse=True)
        
        result = ctx.payload
        
        for transformer in matching:
            if not ctx.should_continue:
                break
            
            try:
                result = await transformer.transform(result)
            except Exception as e:
                ctx.set_error(e)
                break
        
        return result
    
    async def execute_handlers(
        self,
        event_type: str,
        ctx: ExtensionContext
    ) -> None:
        """执行处理器"""
        handlers = self._handlers.get(event_type, [])
        handlers.extend(self._handlers.get('all', []))
        
        # 过滤并排序
        matching = [
            h for h in handlers
            if h.supports(event_type)
        ]
        matching.sort(key=lambda h: h.priority, reverse=True)
        
        for handler in matching:
            if not ctx.should_continue:
                break
            
            try:
                await handler.execute(ctx)
            except Exception as e:
                ctx.set_error(e)


class EventBus:
    """
    事件总线
    
    统一的事件发布和订阅接口
    """
    
    def __init__(self, registry: Optional[ExtensionRegistry] = None):
        self._registry = registry or ExtensionRegistry()
        self._subscribers: Dict[str, List[Callable]] = {}
    
    @property
    def registry(self) -> ExtensionRegistry:
        """获取扩展注册中心"""
        return self._registry
    
    def subscribe(self, event_type: str, handler: Callable) -> callable:
        """
        订阅事件
        
        Returns:
            取消订阅函数
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        
        self._subscribers[event_type].append(handler)
        
        def unsubscribe():
            try:
                self._subscribers[event_type].remove(handler)
            except ValueError:
                pass
        
        return unsubscribe
    
    async def publish(self, event_type: str, payload: Any, **metadata) -> ExtensionContext:
        """
        发布事件
        
        执行顺序：
        1. PRE 拦截器
        2. 转换器
        3. 处理器
        4. POST 拦截器
        5. 错误处理（如果有错误）
        
        Returns:
            扩展上下文
        """
        ctx = ExtensionContext(
            event_type=event_type,
            payload=payload,
            metadata=metadata
        )
        
        try:
            # 1. PRE 拦截器
            await self._registry.execute_interceptors(
                event_type, ctx, ExecutionOrder.PRE
            )
            
            if not ctx.should_continue:
                return ctx
            
            # 2. 转换器
            if not ctx.error:
                ctx.payload = await self._registry.execute_transformers(
                    event_type, ctx
                )
            
            if not ctx.should_continue:
                return ctx
            
            # 3. 处理器
            if not ctx.error:
                await self._registry.execute_handlers(event_type, ctx)
            
            if not ctx.should_continue:
                return ctx
            
            # 4. POST 拦截器
            await self._registry.execute_interceptors(
                event_type, ctx, ExecutionOrder.POST
            )
            
            # 5. 通知订阅者
            await self._notify_subscribers(event_type, ctx)
            
        except Exception as e:
            ctx.set_error(e)
            # 6. 错误处理
            await self._registry.execute_interceptors(
                event_type, ctx, ExecutionOrder.ON_ERROR
            )
        
        return ctx
    
    async def _notify_subscribers(
        self,
        event_type: str,
        ctx: ExtensionContext
    ) -> None:
        """通知订阅者"""
        subscribers = self._subscribers.get(event_type, [])
        
        for handler in subscribers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(ctx)
                else:
                    handler(ctx)
            except Exception as e:
                print(f"Error in subscriber {event_type}: {e}")
    
    def register_extension(self, extension: Extension) -> None:
        """注册扩展"""
        self._registry.register(extension)
    
    def unregister_extension(self, extension: Extension) -> None:
        """注销扩展"""
        self._registry.unregister(extension)


__all__ = [
    "ExtensionPointType",
    "ExecutionOrder",
    "ExtensionContext",
    "Extension",
    "Interceptor",
    "Transformer",
    "EventHandler",
    "ExtensionRegistry",
    "EventBus",
]
