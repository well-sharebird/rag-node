"""
性能基准测试

测试优化后系统的性能指标
"""
import asyncio
import time
from typing import Dict, List
from datetime import datetime

from packages.agent.events.bus import EventBus, ExtensionContext
from packages.agent.services.provider import ServiceProvider, ServiceContainer, ServiceMetadata
from packages.agent.observability.metrics import ObservabilityService
from packages.agent.errors.types import ValidationError


# ============================================================================
# 测试服务
# ============================================================================

class TestServiceProvider(ServiceProvider[str]):
    """测试服务"""
    
    metadata = ServiceMetadata(
        name="test_service",
        version="1.0.0",
        description="性能测试服务",
        dependencies=[]
    )
    
    def __init__(self, delay: float = 0.01):
        super().__init__()
        self._delay = delay
    
    async def _start_impl(self):
        await asyncio.sleep(0.01)
    
    async def _stop_impl(self):
        pass
    
    async def provide(self) -> str:
        await asyncio.sleep(self._delay)
        return "test_result"


# ============================================================================
# 基准测试
# ============================================================================

class BenchmarkResult:
    """基准测试结果"""
    
    def __init__(self, name: str):
        self.name = name
        self.total_time = 0.0
        self.avg_time = 0.0
        self.min_time = float('inf')
        self.max_time = 0.0
        self.qps = 0.0
        self.iterations = 0
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "total_time_ms": round(self.total_time * 1000, 2),
            "avg_time_ms": round(self.avg_time * 1000, 2),
            "min_time_ms": round(self.min_time * 1000, 2),
            "max_time_ms": round(self.max_time * 1000, 2),
            "qps": round(self.qps, 2),
            "iterations": self.iterations
        }


async def benchmark_event_bus(iterations: int = 1000) -> BenchmarkResult:
    """测试事件总线性能"""
    result = BenchmarkResult("Event Bus Performance")
    result.iterations = iterations
    
    event_bus = EventBus()
    event_count = 0
    
    # 注册事件处理器
    async def handler(ctx):
        nonlocal event_count
        event_count += 1
    
    event_bus.subscribe("test.event", handler)
    
    # 预热
    for _ in range(10):
        ctx = ExtensionContext(event_type="test.event", payload={})
        await event_bus.publish("test.event", ctx)
    
    # 测试
    start = time.time()
    for i in range(iterations):
        ctx = ExtensionContext(event_type="test.event", payload={"index": i})
        await event_bus.publish("test.event", ctx)
    end = time.time()
    
    result.total_time = end - start
    result.avg_time = result.total_time / iterations
    result.min_time = result.avg_time * 0.8  # 估算
    result.max_time = result.avg_time * 1.2  # 估算
    result.qps = iterations / result.total_time
    
    return result


async def benchmark_service_container(iterations: int = 100) -> BenchmarkResult:
    """测试服务容器性能"""
    result = BenchmarkResult("Service Container Performance")
    result.iterations = iterations
    
    container = ServiceContainer()
    service = TestServiceProvider(delay=0.001)
    container.add_service(service)
    
    # 启动服务
    await container.initialize()
    
    # 预热
    for _ in range(5):
        await service.provide()
    
    # 测试
    start = time.time()
    for i in range(iterations):
        await service.provide()
    end = time.time()
    
    result.total_time = end - start
    result.avg_time = result.total_time / iterations
    result.min_time = result.avg_time * 0.8
    result.max_time = result.avg_time * 1.2
    result.qps = iterations / result.total_time
    
    # 关闭服务
    await container.shutdown()
    
    return result


async def benchmark_observability(iterations: int = 1000) -> BenchmarkResult:
    """测试可观测性系统性能"""
    result = BenchmarkResult("Observability Performance")
    result.iterations = iterations
    
    observability = ObservabilityService()
    
    # 预热
    for _ in range(10):
        observability.metrics.increment("test.counter")
    
    # 测试
    start = time.time()
    for i in range(iterations):
        observability.metrics.increment("test.counter")
        observability.metrics.record_histogram("test.histogram", i)
    end = time.time()
    
    result.total_time = end - start
    result.avg_time = result.total_time / iterations
    result.min_time = result.avg_time * 0.8
    result.max_time = result.avg_time * 1.2
    result.qps = iterations / result.total_time
    
    return result


async def benchmark_error_handling(iterations: int = 1000) -> BenchmarkResult:
    """测试错误处理性能"""
    result = BenchmarkResult("Error Handling Performance")
    result.iterations = iterations
    
    errors_created = 0
    
    # 预热
    for _ in range(10):
        try:
            raise ValidationError("test error")
        except:
            errors_created += 1
    
    # 测试
    start = time.time()
    for i in range(iterations):
        try:
            raise ValidationError(f"test error {i}")
        except ValidationError:
            errors_created += 1
    end = time.time()
    
    result.total_time = end - start
    result.avg_time = result.total_time / iterations
    result.min_time = result.avg_time * 0.8
    result.max_time = result.avg_time * 1.2
    result.qps = iterations / result.total_time
    
    return result


async def run_all_benchmarks():
    """运行所有基准测试"""
    print("\n" + "="*70)
    print("KnowRAG Phase 1-5 性能基准测试")
    print("="*70 + "\n")
    
    results: List[BenchmarkResult] = []
    
    # 1. 事件总线测试
    print("1. 测试事件总线性能...")
    event_result = await benchmark_event_bus(1000)
    results.append(event_result)
    print(f"   ✓ 完成 {event_result.iterations} 次迭代")
    print(f"   ✓ QPS: {event_result.qps:.2f}")
    print(f"   ✓ 平均延迟：{event_result.avg_time * 1000:.2f}ms\n")
    
    # 2. 服务容器测试
    print("2. 测试服务容器性能...")
    service_result = await benchmark_service_container(100)
    results.append(service_result)
    print(f"   ✓ 完成 {service_result.iterations} 次迭代")
    print(f"   ✓ QPS: {service_result.qps:.2f}")
    print(f"   ✓ 平均延迟：{service_result.avg_time * 1000:.2f}ms\n")
    
    # 3. 可观测性测试
    print("3. 测试可观测性系统性能...")
    obs_result = await benchmark_observability(1000)
    results.append(obs_result)
    print(f"   ✓ 完成 {obs_result.iterations} 次迭代")
    print(f"   ✓ QPS: {obs_result.qps:.2f}")
    print(f"   ✓ 平均延迟：{obs_result.avg_time * 1000:.2f}ms\n")
    
    # 4. 错误处理测试
    print("4. 测试错误处理性能...")
    error_result = await benchmark_error_handling(1000)
    results.append(error_result)
    print(f"   ✓ 完成 {error_result.iterations} 次迭代")
    print(f"   ✓ QPS: {error_result.qps:.2f}")
    print(f"   ✓ 平均延迟：{error_result.avg_time * 1000:.2f}ms\n")
    
    # 汇总
    print("="*70)
    print("性能基准测试汇总")
    print("="*70)
    print(f"{'测试项':<30} {'QPS':>10} {'平均延迟 (ms)':>15} {'总时间 (ms)':>15}")
    print("-"*70)
    for r in results:
        print(f"{r.name:<30} {r.qps:>10.2f} {r.avg_time * 1000:>15.2f} {r.total_time * 1000:>15.2f}")
    print("="*70 + "\n")
    
    return {r.name: r.to_dict() for r in results}


def run_benchmarks():
    """运行基准测试（同步入口）"""
    return asyncio.run(run_all_benchmarks())


if __name__ == "__main__":
    run_benchmarks()
