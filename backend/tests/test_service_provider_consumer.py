"""
测试服务提供者/消费者模式
"""
import pytest
import asyncio
from packages.agent.services.provider import (
    ServiceStatus,
    ServiceMetadata,
    ServiceProvider,
    ServiceConsumer,
    ServiceRegistry,
    ServiceDiscovery,
    ServiceContainer,
    ModelServiceProvider,
    ToolServiceProvider,
    EventServiceProvider,
)


class TestServiceMetadata:
    """测试服务元数据"""
    
    def test_metadata_creation(self):
        """测试元数据创建"""
        metadata = ServiceMetadata(
            name="test_service",
            version="1.0.0",
            description="Test service",
            author="Test Author",
            dependencies=["dep1", "dep2"],
            capabilities=["cap1", "cap2"]
        )
        
        assert metadata.name == "test_service"
        assert metadata.version == "1.0.0"
        assert len(metadata.dependencies) == 2
        assert len(metadata.capabilities) == 2


class TestServiceProvider:
    """测试服务提供者"""
    
    @pytest.mark.asyncio
    async def test_service_lifecycle(self):
        """测试服务生命周期"""
        class TestService(ServiceProvider[str]):
            metadata = ServiceMetadata(
                name="test_service",
                version="1.0.0"
            )
            
            async def _start_impl(self):
                self.status = ServiceStatus.RUNNING
            
            async def _stop_impl(self):
                self.status = ServiceStatus.STOPPED
            
            async def provide(self) -> str:
                return "provided"
        
        service = TestService()
        
        assert service.status == ServiceStatus.STOPPED
        
        await service.start()
        assert service.status == ServiceStatus.RUNNING
        
        result = await service.provide()
        assert result == "provided"
        
        await service.stop()
        assert service.status == ServiceStatus.STOPPED
    
    @pytest.mark.asyncio
    async def test_consumer_registration(self):
        """测试消费者注册"""
        class TestService(ServiceProvider[str]):
            metadata = ServiceMetadata(
                name="test_service",
                version="1.0.0"
            )
            
            async def _start_impl(self):
                pass
            
            async def _stop_impl(self):
                pass
            
            async def provide(self) -> str:
                return "provided"
        
        service = TestService()
        
        class TestConsumer(ServiceConsumer):
            def __init__(self):
                super().__init__()
                self.events = []
            
            async def on_service_event(self, service, event, data):
                self.events.append((event, data))
        
        consumer = TestConsumer()
        service.register_consumer(consumer)
        
        assert len(service._consumers) == 1
        
        await service.notify_consumers("test_event", {"data": "test"})
        
        assert len(consumer.events) == 1
        assert consumer.events[0] == ("test_event", {"data": "test"})


class TestServiceRegistry:
    """测试服务注册中心"""
    
    @pytest.mark.asyncio
    async def test_register_service(self):
        """测试注册服务"""
        registry = ServiceRegistry()
        
        class TestService(ServiceProvider[str]):
            metadata = ServiceMetadata(
                name="test_service",
                version="1.0.0"
            )
            
            async def _start_impl(self):
                pass
            
            async def _stop_impl(self):
                pass
            
            async def provide(self) -> str:
                return "provided"
        
        service = TestService()
        registry.register_service(service)
        
        assert registry.get_service("test_service") == service
        assert len(registry.list_services()) == 1
    
    @pytest.mark.asyncio
    async def test_service_dependencies(self):
        """测试服务依赖"""
        registry = ServiceRegistry()
        
        started = []
        
        class DependentService(ServiceProvider[str]):
            metadata = ServiceMetadata(
                name="dependent_service",
                version="1.0.0",
                dependencies=["base_service"]
            )
            
            async def _start_impl(self):
                started.append("dependent")
            
            async def _stop_impl(self):
                started.append("dependent_stop")
            
            async def provide(self) -> str:
                return "dependent"
        
        class BaseService(ServiceProvider[str]):
            metadata = ServiceMetadata(
                name="base_service",
                version="1.0.0"
            )
            
            async def _start_impl(self):
                started.append("base")
            
            async def _stop_impl(self):
                started.append("base_stop")
            
            async def provide(self) -> str:
                return "base"
        
        registry.register_service(BaseService())
        registry.register_service(DependentService())
        
        await registry.start_service("dependent_service")
        
        # 依赖服务应该先启动
        assert started == ["base", "dependent"]
    
    @pytest.mark.asyncio
    async def test_start_stop_all(self):
        """测试启动/停止所有服务"""
        registry = ServiceRegistry()
        
        states = []
        
        class ServiceA(ServiceProvider[str]):
            metadata = ServiceMetadata(name="service_a", version="1.0.0")
            
            async def _start_impl(self):
                states.append("a_start")
            
            async def _stop_impl(self):
                states.append("a_stop")
            
            async def provide(self) -> str:
                return "a"
        
        class ServiceB(ServiceProvider[str]):
            metadata = ServiceMetadata(name="service_b", version="1.0.0")
            
            async def _start_impl(self):
                states.append("b_start")
            
            async def _stop_impl(self):
                states.append("b_stop")
            
            async def provide(self) -> str:
                return "b"
        
        registry.register_service(ServiceA())
        registry.register_service(ServiceB())
        
        await registry.start_all()
        assert states == ["a_start", "b_start"]
        
        await registry.stop_all()
        # 反向停止
        assert states == ["a_start", "b_start", "b_stop", "a_stop"]


class TestServiceDiscovery:
    """测试服务发现"""
    
    def test_find_by_capability(self):
        """测试按能力查找"""
        registry = ServiceRegistry()
        discovery = ServiceDiscovery(registry)
        
        class SearchService(ServiceProvider[str]):
            metadata = ServiceMetadata(
                name="search_service",
                version="1.0.0",
                capabilities=["search", "index"]
            )
            
            async def _start_impl(self):
                pass
            
            async def _stop_impl(self):
                pass
            
            async def provide(self) -> str:
                return "search"
        
        service = SearchService()
        registry.register_service(service)
        
        results = discovery.find_by_capability("search")
        assert len(results) == 1
        assert results[0].metadata.name == "search_service"
        
        results = discovery.find_by_capability("nonexistent")
        assert len(results) == 0
    
    def test_has_service(self):
        """测试服务存在性检查"""
        registry = ServiceRegistry()
        discovery = ServiceDiscovery(registry)
        
        class TestService(ServiceProvider[str]):
            metadata = ServiceMetadata(name="test", version="1.0.0")
            
            async def _start_impl(self):
                pass
            
            async def _stop_impl(self):
                pass
            
            async def provide(self) -> str:
                return "test"
        
        registry.register_service(TestService())
        
        assert discovery.has_service("test") is True
        assert discovery.has_service("nonexistent") is False


class TestServiceContainer:
    """测试服务容器"""
    
    @pytest.mark.asyncio
    async def test_container_lifecycle(self):
        """测试容器生命周期"""
        container = ServiceContainer()
        
        started = []
        
        class TestService(ServiceProvider[str]):
            metadata = ServiceMetadata(name="test", version="1.0.0")
            
            async def _start_impl(self):
                started.append("start")
            
            async def _stop_impl(self):
                started.append("stop")
            
            async def provide(self) -> str:
                return "test"
        
        container.add_service(TestService())
        
        await container.initialize()
        assert started == ["start"]
        
        await container.shutdown()
        assert started == ["start", "stop"]
    
    @pytest.mark.asyncio
    async def test_service_lookup(self):
        """测试服务查找"""
        container = ServiceContainer()
        
        class LookupService(ServiceProvider[str]):
            metadata = ServiceMetadata(
                name="lookup",
                version="1.0.0",
                capabilities=["lookup"]
            )
            
            async def _start_impl(self):
                pass
            
            async def _stop_impl(self):
                pass
            
            async def provide(self) -> str:
                return "lookup"
        
        container.add_service(LookupService())
        
        service = container.get_service("lookup")
        assert service is not None
        assert service.metadata.name == "lookup"
        
        services = container.find_services_by_capability("lookup")
        assert len(services) == 1


class TestServiceConsumer:
    """测试服务消费者"""
    
    @pytest.mark.asyncio
    async def test_bind_unbind_service(self):
        """测试绑定/解绑服务"""
        class TestService(ServiceProvider[str]):
            metadata = ServiceMetadata(name="test", version="1.0.0")
            
            async def _start_impl(self):
                pass
            
            async def _stop_impl(self):
                pass
            
            async def provide(self) -> str:
                return "test"
        
        class TestConsumer(ServiceConsumer):
            def __init__(self):
                super().__init__()
                self.events = []
            
            async def on_service_event(self, service, event, data):
                self.events.append(event)
        
        service = TestService()
        consumer = TestConsumer()
        
        consumer.bind_service("test", service)
        
        assert consumer.get_service("test") == service
        
        consumer.unbind_service("test")
        
        assert consumer.get_service("test") is None
    
    @pytest.mark.asyncio
    async def test_service_events(self):
        """测试服务事件"""
        class TestService(ServiceProvider[str]):
            metadata = ServiceMetadata(name="test", version="1.0.0")
            
            async def _start_impl(self):
                pass
            
            async def _stop_impl(self):
                pass
            
            async def provide(self) -> str:
                return "test"
        
        class TestConsumer(ServiceConsumer):
            def __init__(self):
                super().__init__()
                self.events = []
            
            async def on_service_event(self, service, event, data):
                self.events.append((event, data))
        
        service = TestService()
        consumer = TestConsumer()
        
        consumer.bind_service("test", service)
        
        await service.notify_consumers("event1", {"data": 1})
        await service.notify_consumers("event2", {"data": 2})
        
        assert len(consumer.events) == 2
        assert consumer.events[0] == ("event1", {"data": 1})
        assert consumer.events[1] == ("event2", {"data": 2})


class TestBuiltInServices:
    """测试内置服务"""
    
    @pytest.mark.asyncio
    async def test_model_service(self):
        """测试模型服务"""
        service = ModelServiceProvider(
            model_name="gpt-4",
            api_key="test-key"
        )
        
        await service.start()
        assert service.status == ServiceStatus.RUNNING
        
        call_fn = await service.provide()
        result = await call_fn("Hello")
        assert "gpt-4" in result
        
        await service.stop()
        assert service.status == ServiceStatus.STOPPED
    
    @pytest.mark.asyncio
    async def test_tool_service(self):
        """测试工具服务"""
        service = ToolServiceProvider()
        
        await service.start()
        
        service.register_tool("add", lambda a, b: a + b)
        service.register_tool("subtract", lambda a, b: a - b)
        
        tools = await service.provide()
        
        assert "add" in tools
        assert "subtract" in tools
        assert tools["add"](2, 3) == 5
        
        service.unregister_tool("add")
        tools = await service.provide()
        assert "add" not in tools
        
        await service.stop()
    
    @pytest.mark.asyncio
    async def test_event_service(self):
        """测试事件服务"""
        service = EventServiceProvider()
        
        await service.start()
        
        events = []
        
        async def handler(data):
            events.append(data)
        
        service.subscribe("test_event", handler)
        
        await service.publish("test_event", {"message": "Hello"})
        await service.publish("test_event", {"message": "World"})
        
        assert len(events) == 2
        assert events[0]["message"] == "Hello"
        assert events[1]["message"] == "World"
        
        await service.stop()


class TestServiceIntegration:
    """测试服务集成"""
    
    @pytest.mark.asyncio
    async def test_full_integration(self):
        """测试完整集成"""
        container = ServiceContainer()
        
        # 添加模型服务
        model_service = ModelServiceProvider("gpt-4", "test-key")
        container.add_service(model_service)
        
        # 添加工具服务（依赖模型服务）
        tool_service = ToolServiceProvider()
        container.add_service(tool_service)
        
        # 添加事件服务
        event_service = EventServiceProvider()
        container.add_service(event_service)
        
        # 初始化
        await container.initialize()
        
        # 验证所有服务已启动
        assert model_service.status == ServiceStatus.RUNNING
        assert tool_service.status == ServiceStatus.RUNNING
        assert event_service.status == ServiceStatus.RUNNING
        
        # 查找服务
        found = container.get_service("model_service")
        assert found == model_service
        
        # 按能力查找
        llm_services = container.find_services_by_capability("llm")
        assert len(llm_services) == 1
        
        # 关闭
        await container.shutdown()
        
        assert model_service.status == ServiceStatus.STOPPED
        assert tool_service.status == ServiceStatus.STOPPED
        assert event_service.status == ServiceStatus.STOPPED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
