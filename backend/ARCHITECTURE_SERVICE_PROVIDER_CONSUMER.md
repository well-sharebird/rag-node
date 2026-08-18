# 服务提供者/消费者模式架构设计

## 概述

基于 Service Provider/Consumer 模式重新设计 KnowRAG 的服务架构，清晰定义能力边界，实现松耦合的模块化设计。

## 核心设计理念

### 1. 能力边界清晰

每个服务有明确的职责边界：
- **Provider**: 提供特定能力（模型调用、工具注册、事件发布）
- **Consumer**: 消费服务提供的能力
- **Registry**: 管理服务生命周期

### 2. 依赖倒置

高层模块不依赖低层模块，都依赖抽象：

```python
# Agent 不直接依赖 LLM 实现
class Agent(ServiceConsumer):
    def __init__(self):
        self.model_service: ServiceProvider[Callable]
        self.tool_service: ServiceProvider[Dict]
```

### 3. 生命周期管理

服务有明确的生命周期状态：

```
STOPPED → STARTING → RUNNING → STOPPING → STOPPED
                  ↓
               FAILED
```

## 架构组件

### ServiceMetadata（服务元数据）

描述服务的基本信息：

```python
@dataclass
class ServiceMetadata:
    name: str                    # 服务名称
    version: str                 # 版本号
    description: str             # 描述
    author: str                  # 作者
    dependencies: List[str]      # 依赖服务列表
    capabilities: List[str]      # 提供的能力列表
```

### ServiceProvider（服务提供者）

定义服务接口和实现：

```python
class ServiceProvider(ABC, Generic[T]):
    metadata: ServiceMetadata
    
    async def start() -> None           # 启动服务
    async def stop() -> None            # 停止服务
    async def provide() -> T            # 提供服务实例
    
    def register_consumer(consumer)     # 注册消费者
    async def notify_consumers(event)   # 通知消费者
```

**模板方法模式**:
```python
async def start(self):
    await self._start_impl()  # 子类实现

async def _start_impl(self):
    """子类实现启动逻辑"""
    pass
```

### ServiceConsumer（服务消费者）

消费服务提供的能力：

```python
class ServiceConsumer(ABC):
    def bind_service(name, service)        # 绑定服务
    def unbind_service(name)               # 解绑服务
    def get_service(name) -> ServiceProvider
    
    async def on_service_event(service, event, data)
        """服务事件回调"""
```

### ServiceRegistry（服务注册中心）

管理所有服务的注册、发现和生命周期：

```python
class ServiceRegistry:
    def register_service(service) -> None
    def unregister_service(name) -> None
    def get_service(name) -> Optional[ServiceProvider]
    def list_services() -> List[ServiceProvider]
    
    async def start_service(name) -> None   # 启动单个服务
    async def stop_service(name) -> None    # 停止单个服务
    async def start_all() -> None           # 启动所有
    async def stop_all() -> None            # 停止所有
```

**依赖管理**:
```python
async def start_service(self, name: str):
    service = self.get_service(name)
    
    # 先启动依赖
    for dep in service.metadata.dependencies:
        if dep not in self._started:
            await self.start_service(dep)
    
    # 启动当前服务
    await service.start()
```

### ServiceDiscovery（服务发现）

支持按能力、标签等条件查找服务：

```python
class ServiceDiscovery:
    def find_by_capability(capability) -> List[ServiceProvider]
    def find_by_name(name) -> Optional[ServiceProvider]
    def find_all() -> List[ServiceProvider]
    def has_service(name) -> bool
```

### ServiceContainer（服务容器）

整合注册中心、发现、生命周期管理：

```python
class ServiceContainer:
    def add_service(service) -> None
    def add_consumer(consumer) -> None
    async def initialize() -> None    # 初始化所有
    async def shutdown() -> None      # 关闭所有
    
    def get_service(name) -> Optional[ServiceProvider]
    def find_services_by_capability(cap) -> List[ServiceProvider]
```

## 内置服务

### ModelServiceProvider

提供 LLM 模型调用能力：

```python
class ModelServiceProvider(ServiceProvider[Callable]):
    metadata = ServiceMetadata(
        name="model_service",
        version="1.0.0",
        capabilities=["llm", "embedding", "chat"]
    )
    
    def __init__(self, model_name: str, api_key: str)
    
    async def provide(self) -> Callable:
        """返回模型调用函数"""
        async def call_model(prompt: str, **kwargs) -> str:
            return await self._client.chat(prompt)
        return call_model
```

### ToolServiceProvider

提供工具注册和调用能力：

```python
class ToolServiceProvider(ServiceProvider[Dict[str, Any]]):
    metadata = ServiceMetadata(
        name="tool_service",
        version="1.0.0",
        capabilities=["tools", "functions"],
        dependencies=["model_service"]
    )
    
    def register_tool(name: str, tool: Any) -> None
    def unregister_tool(name: str) -> None
    async def provide(self) -> Dict[str, Any]
```

### EventServiceProvider

提供事件发布/订阅能力：

```python
class EventServiceProvider(ServiceProvider[Any]):
    metadata = ServiceMetadata(
        name="event_service",
        version="1.0.0",
        capabilities=["events", "pubsub"]
    )
    
    def subscribe(event: str, handler: Callable) -> None
    async def publish(event: str, data: Any) -> None
    async def provide(self) -> Any  # 返回事件总线本身
```

## 使用示例

### 基本使用

```python
from packages.agent.services import (
    ServiceContainer,
    ModelServiceProvider,
    ToolServiceProvider,
    EventServiceProvider,
)

async def main():
    # 创建容器
    container = ServiceContainer()
    
    # 添加服务
    container.add_service(ModelServiceProvider("gpt-4", "api-key"))
    container.add_service(ToolServiceProvider())
    container.add_service(EventServiceProvider())
    
    # 初始化（按依赖顺序启动）
    await container.initialize()
    
    # 获取服务
    model_service = container.get_service("model_service")
    call_model = await model_service.provide()
    
    # 调用模型
    response = await call_model("Hello, world!")
    
    # 按能力查找
    llm_services = container.find_services_by_capability("llm")
    
    # 关闭
    await container.shutdown()
```

### 自定义服务

```python
from packages.agent.services import ServiceProvider, ServiceMetadata

class DatabaseServiceProvider(ServiceProvider[AsyncSession]):
    metadata = ServiceMetadata(
        name="database",
        version="1.0.0",
        capabilities=["persistence", "query"],
        dependencies=["config"]  # 依赖配置服务
    )
    
    def __init__(self, connection_string: str):
        super().__init__()
        self.connection_string = connection_string
    
    async def _start_impl(self):
        # 初始化数据库连接
        self.engine = create_async_engine(self.connection_string)
        self.status = ServiceStatus.RUNNING
    
    async def _stop_impl(self):
        # 关闭连接
        await self.engine.dispose()
        self.status = ServiceStatus.STOPPED
    
    async def provide(self) -> AsyncSession:
        async with AsyncSession(self.engine) as session:
            yield session
```

### 服务消费者

```python
from packages.agent.services import ServiceConsumer

class AgentService(ServiceConsumer):
    def __init__(self):
        super().__init__()
        self._model = None
        self._tools = None
    
    async def initialize(self):
        # 绑定服务
        self.bind_service("model", model_service)
        self.bind_service("tools", tool_service)
        
        # 获取服务实例
        self._model = await self.get_service("model").provide()
        self._tools = await self.get_service("tools").provide()
    
    async def chat(self, message: str) -> str:
        # 使用服务
        response = await self._model(message)
        return response
    
    async def on_service_event(self, service, event, data):
        # 处理服务事件
        if event == "model.changed":
            self._model = await service.provide()
```

## 与 DeepSeek Harness 对比

| 特性 | DeepSeek Harness | KnowRAG 服务模式 |
|------|------------------|------------------|
| 服务发现 | Cordis 上下文注入 | ServiceDiscovery |
| 依赖管理 | 自动解析 | 显式声明 |
| 生命周期 | 插件加载/卸载 | START/RUNNING/STOP |
| 能力边界 | 插件能力 | Service Capabilities |
| 服务组合 | Bundle | ServiceContainer |

## 最佳实践

### 1. 服务命名

使用小写字母和下划线：
- ✅ `model_service`, `tool_service`, `event_bus`
- ❌ `ModelService`, `ToolService`

### 2. 依赖声明

显式声明所有依赖：

```python
metadata = ServiceMetadata(
    name="agent_service",
    dependencies=["model_service", "tool_service", "event_bus"]
)
```

### 3. 错误处理

服务启动失败应该设置状态：

```python
async def _start_impl(self):
    try:
        # 初始化逻辑
        self.status = ServiceStatus.RUNNING
    except Exception as e:
        self.status = ServiceStatus.FAILED
        raise
```

### 4. 资源清理

确保服务停止时清理资源：

```python
async def _stop_impl(self):
    # 关闭连接
    if self.connection:
        await self.connection.close()
    
    # 清除缓存
    self.cache.clear()
    
    self.status = ServiceStatus.STOPPED
```

## 测试

运行测试：

```bash
cd backend
python3 -m pytest tests/test_service_provider_consumer.py -v
```

测试结果：
- ✅ 16 个测试全部通过
- 覆盖：元数据、生命周期、注册中心、发现、容器、消费者、内置服务、集成测试

## 与事件驱动集成

服务可以发布/订阅事件：

```python
class AgentService(ServiceConsumer):
    async def chat(self, message: str):
        # 发布事件
        event_service = self.get_service("event_bus")
        await event_service.publish("agent.chat.start", {
            "message": message
        })
        
        # 处理逻辑
        response = await self._model(message)
        
        # 发布完成事件
        await event_service.publish("agent.chat.complete", {
            "response": response
        })
```

## 与插件系统集成

插件可以作为服务提供者：

```python
class PluginServiceProvider(ServiceProvider[Plugin]):
    metadata = ServiceMetadata(
        name="plugin_loader",
        capabilities=["plugins", "extensions"]
    )
    
    async def provide(self) -> Plugin:
        return self._plugin
```

## 下一步

1. **服务持久化**: 支持服务状态持久化
2. **健康检查**: 定期检查服务健康状态
3. **服务监控**: 指标收集和告警
4. **动态加载**: 支持运行时动态加载服务

## 参考文档

- [事件溯源架构](ARCHITECTURE_EVENT_SOURCING.md)
- [插件系统架构](ARCHITECTURE_PLUGIN_SYSTEM.md)
- [事件驱动扩展](ARCHITECTURE_EVENT_DRIVEN_EXTENSIONS.md)
