"""
服务提供者/消费者模式

清晰定义能力边界，实现松耦合的服务架构
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TypeVar, Generic, Callable
from dataclasses import dataclass, field
from enum import Enum
import asyncio


class ServiceStatus(str, Enum):
    """服务状态"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    FAILED = "failed"


@dataclass
class ServiceMetadata:
    """服务元数据"""
    name: str
    version: str
    description: str = ""
    author: str = ""
    dependencies: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)


T = TypeVar('T')


class ServiceProvider(ABC, Generic[T]):
    """
    服务提供者
    
    定义服务接口和实现
    """
    
    metadata: ServiceMetadata
    
    def __init__(self):
        self.status = ServiceStatus.STOPPED
        self._consumers: List["ServiceConsumer"] = []
    
    async def start(self) -> None:
        """启动服务（模板方法）"""
        await self._start_impl()
    
    @abstractmethod
    async def _start_impl(self) -> None:
        """启动服务实现"""
        pass
    
    async def stop(self) -> None:
        """停止服务（模板方法）"""
        await self._stop_impl()
    
    @abstractmethod
    async def _stop_impl(self) -> None:
        """停止服务实现"""
        pass
    
    @abstractmethod
    async def provide(self) -> T:
        """提供服务"""
        pass
    
    def register_consumer(self, consumer: "ServiceConsumer") -> None:
        """注册消费者"""
        self._consumers.append(consumer)
    
    def unregister_consumer(self, consumer: "ServiceConsumer") -> None:
        """注销消费者"""
        try:
            self._consumers.remove(consumer)
        except ValueError:
            pass
    
    async def notify_consumers(self, event: str, data: Any) -> None:
        """通知所有消费者"""
        for consumer in self._consumers:
            try:
                await consumer.on_service_event(self, event, data)
            except Exception as e:
                print(f"Error notifying consumer: {e}")


class ServiceConsumer(ABC):
    """
    服务消费者
    
    消费服务提供的能力
    """
    
    def __init__(self):
        self._services: Dict[str, ServiceProvider] = {}
    
    def bind_service(self, name: str, service: ServiceProvider) -> None:
        """绑定服务"""
        self._services[name] = service
        service.register_consumer(self)
    
    def unbind_service(self, name: str) -> None:
        """解绑服务"""
        if name in self._services:
            self._services[name].unregister_consumer(self)
            del self._services[name]
    
    def get_service(self, name: str) -> Optional[ServiceProvider]:
        """获取服务"""
        return self._services.get(name)
    
    async def on_service_event(
        self,
        service: ServiceProvider,
        event: str,
        data: Any
    ) -> None:
        """服务事件回调"""
        pass


class ServiceRegistry:
    """
    服务注册中心
    
    管理所有服务的注册、发现和生命周期
    """
    
    def __init__(self):
        self._services: Dict[str, ServiceProvider] = {}
        self._consumers: Dict[str, ServiceConsumer] = {}
        self._started: List[str] = []
    
    def register_service(self, service: ServiceProvider) -> None:
        """注册服务"""
        name = service.metadata.name
        self._services[name] = service
    
    def unregister_service(self, name: str) -> None:
        """注销服务"""
        if name in self._services:
            self._services.pop(name)
            self._started.discard(name)
    
    def get_service(self, name: str) -> Optional[ServiceProvider]:
        """获取服务"""
        return self._services.get(name)
    
    def list_services(self) -> List[ServiceProvider]:
        """列出所有服务"""
        return list(self._services.values())
    
    def register_consumer(self, consumer: ServiceConsumer, name: str = None) -> None:
        """注册消费者"""
        consumer_name = name or consumer.__class__.__name__
        self._consumers[consumer_name] = consumer
    
    def get_consumer(self, name: str) -> Optional[ServiceConsumer]:
        """获取消费者"""
        return self._consumers.get(name)
    
    async def start_service(self, name: str) -> None:
        """启动服务"""
        service = self.get_service(name)
        if not service:
            raise ValueError(f"Service not found: {name}")
        
        # 检查依赖
        for dep in service.metadata.dependencies:
            if dep not in self._started:
                await self.start_service(dep)
        
        try:
            service.status = ServiceStatus.STARTING
            await service.start()
            service.status = ServiceStatus.RUNNING
            if name not in self._started:
                self._started.append(name)
        except Exception as e:
            service.status = ServiceStatus.FAILED
            raise
    
    async def stop_service(self, name: str) -> None:
        """停止服务"""
        service = self.get_service(name)
        if not service:
            raise ValueError(f"Service not found: {name}")
        
        try:
            service.status = ServiceStatus.STOPPING
            await service.stop()
            service.status = ServiceStatus.STOPPED
            if name in self._started:
                self._started.remove(name)
        except Exception as e:
            service.status = ServiceStatus.FAILED
            raise
    
    async def start_all(self) -> None:
        """启动所有服务"""
        for name in self._services.keys():
            if name not in self._started:
                await self.start_service(name)
    
    async def stop_all(self) -> None:
        """停止所有服务（反向顺序）"""
        for name in reversed(list(self._started)):
            await self.stop_service(name)


class ServiceDiscovery:
    """
    服务发现
    
    支持按能力、标签等条件查找服务
    """
    
    def __init__(self, registry: ServiceRegistry):
        self._registry = registry
    
    def find_by_capability(self, capability: str) -> List[ServiceProvider]:
        """按能力查找服务"""
        services = []
        for service in self._registry.list_services():
            if capability in service.metadata.capabilities:
                services.append(service)
        return services
    
    def find_by_name(self, name: str) -> Optional[ServiceProvider]:
        """按名称查找服务"""
        return self._registry.get_service(name)
    
    def find_all(self) -> List[ServiceProvider]:
        """查找所有服务"""
        return self._registry.list_services()
    
    def has_service(self, name: str) -> bool:
        """检查服务是否存在"""
        return name in [s.metadata.name for s in self._registry.list_services()]


class ServiceContainer:
    """
    服务容器
    
    整合注册中心、发现、生命周期管理
    """
    
    def __init__(self):
        self._registry = ServiceRegistry()
        self._discovery = ServiceDiscovery(self._registry)
    
    @property
    def registry(self) -> ServiceRegistry:
        """获取注册中心"""
        return self._registry
    
    @property
    def discovery(self) -> ServiceDiscovery:
        """获取服务发现"""
        return self._discovery
    
    def add_service(self, service: ServiceProvider) -> None:
        """添加服务"""
        self._registry.register_service(service)
    
    def add_consumer(self, consumer: ServiceConsumer, name: str = None) -> None:
        """添加消费者"""
        self._registry.register_consumer(consumer, name)
    
    async def initialize(self) -> None:
        """初始化所有服务"""
        await self._registry.start_all()
    
    async def shutdown(self) -> None:
        """关闭所有服务"""
        await self._registry.stop_all()
    
    def get_service(self, name: str) -> Optional[ServiceProvider]:
        """获取服务"""
        return self._discovery.find_by_name(name)
    
    def find_services_by_capability(self, capability: str) -> List[ServiceProvider]:
        """按能力查找服务"""
        return self._discovery.find_by_capability(capability)


# 服务提供者实现示例

class ModelServiceProvider(ServiceProvider[Callable]):
    """
    模型服务提供者
    
    提供 LLM 模型调用能力
    """
    
    metadata = ServiceMetadata(
        name="model_service",
        version="1.0.0",
        description="LLM model service",
        capabilities=["llm", "embedding", "chat"]
    )
    
    def __init__(self, model_name: str, api_key: str):
        super().__init__()
        self.model_name = model_name
        self.api_key = api_key
        self._client = None
    
    async def _start_impl(self) -> None:
        """初始化模型客户端"""
        # 实际实现会初始化 LLM 客户端
        self._client = {"model": self.model_name}
        self.status = ServiceStatus.RUNNING
    
    async def _stop_impl(self) -> None:
        """关闭客户端"""
        self._client = None
        self.status = ServiceStatus.STOPPED
    
    async def provide(self) -> Callable:
        """提供模型调用函数"""
        async def call_model(prompt: str, **kwargs) -> str:
            if not self._client:
                raise RuntimeError("Service not started")
            # 实际调用 LLM
            return f"Response from {self.model_name}"
        
        return call_model


class ToolServiceProvider(ServiceProvider[Dict[str, Any]]):
    """
    工具服务提供者
    
    提供工具注册和调用能力
    """
    
    metadata = ServiceMetadata(
        name="tool_service",
        version="1.0.0",
        description="Tool service",
        capabilities=["tools", "functions"],
        dependencies=["model_service"]  # 依赖模型服务
    )
    
    def __init__(self):
        super().__init__()
        self._tools: Dict[str, Any] = {}
    
    async def _start_impl(self) -> None:
        """启动工具服务"""
        # 初始化工具
        self._tools = {}
        self.status = ServiceStatus.RUNNING
    
    async def _stop_impl(self) -> None:
        """停止工具服务"""
        self._tools.clear()
        self.status = ServiceStatus.STOPPED
    
    async def provide(self) -> Dict[str, Any]:
        """提供工具字典"""
        return self._tools.copy()
    
    def register_tool(self, name: str, tool: Any) -> None:
        """注册工具"""
        self._tools[name] = tool
    
    def unregister_tool(self, name: str) -> None:
        """注销工具"""
        if name in self._tools:
            del self._tools[name]


class EventServiceProvider(ServiceProvider[Any]):
    """
    事件服务提供者
    
    提供事件发布/订阅能力
    """
    
    metadata = ServiceMetadata(
        name="event_service",
        version="1.0.0",
        description="Event bus service",
        capabilities=["events", "pubsub"]
    )
    
    def __init__(self):
        super().__init__()
        self._handlers: Dict[str, List[Callable]] = {}
    
    async def _start_impl(self) -> None:
        """启动事件服务"""
        self._handlers = {}
        self.status = ServiceStatus.RUNNING
    
    async def _stop_impl(self) -> None:
        """停止事件服务"""
        self._handlers.clear()
        self.status = ServiceStatus.STOPPED
    
    async def provide(self) -> Any:
        """提供事件总线"""
        return self
    
    def subscribe(self, event: str, handler: Callable) -> None:
        """订阅事件"""
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append(handler)
    
    async def publish(self, event: str, data: Any) -> None:
        """发布事件"""
        handlers = self._handlers.get(event, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                print(f"Error in event handler: {e}")


__all__ = [
    "ServiceStatus",
    "ServiceMetadata",
    "ServiceProvider",
    "ServiceConsumer",
    "ServiceRegistry",
    "ServiceDiscovery",
    "ServiceContainer",
    "ModelServiceProvider",
    "ToolServiceProvider",
    "EventServiceProvider",
]
