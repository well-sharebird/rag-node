# 事件驱动扩展系统架构设计

## 概述

基于事件驱动架构（Event-Driven Architecture, EDA）重新设计 KnowRAG 的扩展机制，替代传统的回调函数模式。

## 核心设计理念

### 1. 扩展点即事件

每个扩展点都是一个事件，扩展通过监听和响应事件来增强系统行为：

```
事件发布 → 拦截器 → 转换器 → 处理器 → 订阅者
```

### 2. 关注点分离

- **拦截器（Interceptor）**: 前置/后置/环绕处理
- **转换器（Transformer）**: 数据格式转换
- **处理器（Handler）**: 业务逻辑执行
- **订阅者（Subscriber）**: 异步通知

### 3. 可组合性

多个扩展可以组合成扩展链，按优先级顺序执行：

```python
# 扩展链示例
Auth → Validation → Logging → Cache → Business Logic
```

## 架构组件

### ExtensionContext（扩展上下文）

携带扩展执行的所有信息：

```python
@dataclass
class ExtensionContext:
    event_type: str           # 事件类型
    payload: Any              # 事件数据
    metadata: Dict[str, Any]  # 元数据
    result: Any               # 执行结果
    error: Optional[Exception] # 错误
    should_continue: bool     # 是否继续
    correlation_id: str       # 关联 ID（追踪因果链）
    timestamp: datetime       # 时间戳
```

### Extension（扩展基类）

所有扩展的抽象基类：

```python
class Extension(ABC, Generic[T]):
    name: str
    version: str
    priority: int  # 优先级
    
    async def execute(self, ctx: ExtensionContext) -> T
    def supports(self, event_type: str) -> bool
```

### Interceptor（拦截器）

在事件处理的生命周期中插入逻辑：

```python
class Interceptor(Extension[None]):
    execution_order: ExecutionOrder
    
    async def pre_handle(self, ctx) -> None      # 前置
    async def post_handle(self, ctx) -> None     # 后置
    async def around_handle(self, ctx) -> None   # 环绕
    async def on_error_handle(self, ctx) -> None # 错误处理
```

**执行顺序**:
- `PRE`: 在业务逻辑之前执行（如认证、验证）
- `POST`: 在业务逻辑之后执行（如日志、缓存）
- `AROUND`: 环绕业务逻辑（如事务、重试）
- `ON_ERROR`: 错误处理（如降级、告警）

### Transformer（转换器）

转换事件 payload：

```python
class Transformer(Extension[Any]):
    async def transform(self, payload: Any) -> Any
```

**用途**:
- 数据格式标准化
- 字段映射
- 数据增强

### EventHandler（事件处理器）

响应特定事件：

```python
class EventHandler(Extension[None]):
    target_event: str  # 目标事件类型
    
    async def handle(self, payload: Any) -> None
```

### ExtensionRegistry（扩展注册中心）

管理所有扩展的注册和执行：

```python
class ExtensionRegistry:
    def register(extension: Extension) -> None
    def unregister(extension: Extension) -> None
    def get_extensions(event_type: str) -> List[Extension]
    
    async def execute_interceptors(event_type, ctx, order) -> None
    async def execute_transformers(event_type, ctx) -> Any
    async def execute_handlers(event_type, ctx) -> None
```

### EventBus（事件总线）

统一的事件发布和订阅接口：

```python
class EventBus:
    def subscribe(event_type: str, handler: Callable) -> callable
    async def publish(event_type: str, payload: Any, **metadata) -> ExtensionContext
    def register_extension(extension: Extension) -> None
```

**发布流程**:
1. PRE 拦截器（按优先级）
2. 转换器（按优先级）
3. 处理器（按优先级）
4. POST 拦截器（按优先级）
5. 订阅者（异步通知）
6. ON_ERROR 拦截器（如果有错误）

## 使用示例

### 创建拦截器

```python
from packages.agent.events import Interceptor, ExecutionOrder

class AuthInterceptor(Interceptor):
    name = "auth_interceptor"
    priority = 90
    execution_order = ExecutionOrder.PRE
    
    async def pre_handle(self, ctx: ExtensionContext) -> None:
        user = ctx.metadata.get("user")
        
        if not user:
            ctx.stop_propagation()
            raise PermissionError("User not authenticated")
```

### 创建转换器

```python
from packages.agent.events import Transformer

class PayloadTransformer(Transformer):
    name = "payload_transformer"
    priority = 50
    
    async def transform(self, payload: Any) -> Any:
        if isinstance(payload, dict):
            # 标准化键名
            return {k.lower(): v for k, v in payload.items()}
        return payload
```

### 创建处理器

```python
from packages.agent.events import EventHandler

class MetricsHandler(EventHandler):
    name = "metrics_handler"
    target_event = "all"  # 监听所有事件
    
    async def handle(self, payload: Any) -> None:
        # 收集指标
        self.metrics.append({
            "timestamp": time.time(),
            "event_type": payload.get("type"),
        })
```

### 使用事件总线

```python
from packages.agent.events import EventBus

async def main():
    bus = EventBus()
    
    # 注册扩展
    bus.register_extension(AuthInterceptor())
    bus.register_extension(PayloadTransformer())
    bus.register_extension(MetricsHandler())
    
    # 发布事件
    result = await bus.publish(
        "message.user",
        {"content": "Hello"},
        user={"role": "admin"}
    )
    
    if result.error:
        print(f"Error: {result.error}")
```

## 扩展示例

### 认证拦截器

```python
class AuthInterceptor(Interceptor):
    execution_order = ExecutionOrder.PRE
    priority = 90
    
    async def pre_handle(self, ctx):
        user = ctx.metadata.get("user")
        if not user:
            ctx.stop_propagation()
            raise PermissionError("Unauthenticated")
```

### 日志拦截器

```python
class LoggingInterceptor(Interceptor):
    priority = 100  # 最高优先级
    
    async def pre_handle(self, ctx):
        print(f"[LOG] {ctx.event_type}: {ctx.payload}")
    
    async def post_handle(self, ctx):
        if ctx.error:
            print(f"[ERROR] {ctx.error}")
```

### 缓存拦截器

```python
class CacheInterceptor(Interceptor):
    execution_order = ExecutionOrder.AROUND
    priority = 70
    
    async def around_handle(self, ctx):
        cache_key = str(ctx.payload)
        
        # 检查缓存
        if cache_key in self.cache:
            ctx.set_result(self.cache[cache_key])
            return
```

### 重试拦截器

```python
class RetryInterceptor(Interceptor):
    execution_order = ExecutionOrder.ON_ERROR
    priority = 60
    
    async def on_error_handle(self, ctx):
        if self.retry_count < self.max_retries:
            self.retry_count += 1
            ctx.error = None  # 重置错误
            ctx.should_continue = True  # 重试
```

## 与回调模式对比

| 特性 | 回调模式 | 事件驱动模式 |
|------|----------|--------------|
| 耦合度 | 高（硬编码） | 低（松耦合） |
| 可扩展性 | 差（需修改源码） | 好（动态注册） |
| 可测试性 | 差 | 好 |
| 组合能力 | 弱 | 强（扩展链） |
| 优先级控制 | 无 | 有 |
| 错误隔离 | 差 | 好 |
| 热更新 | 不支持 | 支持 |

## 最佳实践

### 1. 扩展命名

使用小写字母和下划线：
- ✅ `auth_interceptor`, `logging_handler`
- ❌ `AuthInterceptor`, `LoggingHandler`

### 2. 优先级设置

```
100: 日志（最先执行）
90:  认证
80:  验证
70:  缓存
60:  重试
50:  转换
40:  增强
10:  业务逻辑
5:   指标收集
```

### 3. 错误处理

扩展应该处理自己的错误：

```python
async def pre_handle(self, ctx):
    try:
        # 业务逻辑
        pass
    except Exception as e:
        ctx.set_error(e)
        ctx.stop_propagation()
```

### 4. 停止传播

使用 `ctx.stop_propagation()` 阻止后续扩展执行：

```python
async def pre_handle(self, ctx):
    if not self.has_permission():
        ctx.stop_propagation()
        raise PermissionError("Access denied")
```

## 测试

运行测试：

```bash
cd backend
python3 -m pytest tests/test_event_driven_extensions.py -v
```

测试结果：
- ✅ 20 个测试全部通过
- 覆盖：上下文、注册中心、总线、拦截器、转换器、处理器、集成测试

## 与 DeepSeek Harness 对比

| 特性 | DeepSeek Harness | KnowRAG 事件驱动 |
|------|------------------|------------------|
| 扩展类型 | 插件钩子 | 拦截器/转换器/处理器 |
| 执行顺序 | 固定 | 可配置优先级 |
| 事件总线 | emit/waterfall | EventBus |
| 上下文 | PluginContext | ExtensionContext |
| 关联追踪 | correlation_id | correlation_id |
| 错误处理 | 捕获日志 | 结构化错误传播 |

## 集成点

### 与事件溯源集成

```python
# 扩展可以触发领域事件
class EventSourcingHandler(EventHandler):
    async def handle(self, payload):
        event = AgentEvent(
            type=payload["type"],
            data=payload["data"]
        )
        await event_store.append(event)
```

### 与插件系统集成

```python
# 插件可以注册扩展
class MyPlugin(Plugin):
    async def activate(self, ctx):
        ctx.register_extension(AuthInterceptor())
        ctx.register_extension(LoggingInterceptor())
```

### 与配置驱动集成

```yaml
# 配置文件定义扩展
extensions:
  - type: interceptor
    class: AuthInterceptor
    priority: 90
  - type: transformer
    class: PayloadTransformer
    priority: 50
```

## 下一步

1. **集成到 API 层**: 在 Agent 执行流程中嵌入事件总线
2. **性能优化**: 异步执行、批量处理
3. **可观测性**: 指标收集、分布式追踪
4. **扩展市场**: 第三方扩展分发

## 参考文档

- [事件溯源架构](ARCHITECTURE_EVENT_SOURCING.md)
- [插件系统架构](ARCHITECTURE_PLUGIN_SYSTEM.md)
- [配置驱动架构](ARCHITECTURE_CONFIG_DRIVEN.md)
