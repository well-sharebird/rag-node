# 插件系统架构设计

## 概述

基于 DeepSeek Harness 的"Everything is a Plugin"理念，为 KnowRAG 实现插件化架构。

## 核心设计原则

### 1. 插件即扩展点

每个插件都是系统的扩展点，提供：
- **工具注册**：动态添加 Agent 可调用的工具
- **事件钩子**：拦截和增强系统事件
- **能力组合**：多个插件可组合成 Bundle

### 2. 生命周期管理

```
UNLOADED → LOADING → ACTIVE → UNLOADING → UNLOADED
                     ↓
                  FAILED
```

### 3. 可逆效果

所有插件操作必须是可逆的：
- 注册的工具必须能卸载
- 注册的钩子必须能移除
- 分配的资源必须能释放

## 架构组件

### Plugin（插件基类）

```python
class Plugin(ABC):
    # 元数据
    name: str
    version: str
    description: str
    author: str
    
    # 生命周期
    async def activate(ctx: PluginContext) -> None
    async def deactivate() -> None
```

### PluginContext（插件上下文）

提供插件与系统交互的接口：

```python
class PluginContext:
    def register_tool(name: str, tool: Any) -> callable
    def register_hook(event: str, handler: callable) -> callable
    def dispose() -> None  # 释放所有效果
```

### PluginRegistry（插件注册中心）

管理所有插件的注册表：

```python
class PluginRegistry:
    def register_plugin(plugin: Plugin) -> None
    def get_plugin(name: str) -> Optional[Plugin]
    def list_plugins() -> List[Plugin]
    
    # 工具管理
    def register_tool(name: str, tool: Any) -> None
    def get_tool(name: str) -> Optional[Any]
    
    # 事件系统
    def register_hook(event: str, handler: callable) -> None
    async def emit(event: str, *args, **kwargs) -> None  # 通知模式
    async def waterfall(event: str, payload: Any) -> Any  # 中间件模式
```

### PluginLoader（插件加载器）

从文件系统动态加载插件：

```python
class PluginLoader:
    def discover_plugins(plugin_dir: Path) -> List[str]
    async def load_plugin(name: str, plugin_dir: Path) -> bool
    async def unload_plugin(name: str) -> bool
    async def reload_plugin(name: str, plugin_dir: Path) -> bool  # 热重载
```

### PluginManager（插件管理器）

高层抽象，整合 Loader 和 Registry：

```python
class PluginManager:
    async def initialize() -> Dict[str, bool]
    async def shutdown() -> None
    async def hot_reload(plugin_name: str) -> bool
```

## 事件系统

### 通知模式（emit）

```python
# 插件注册钩子
ctx.register_hook("tool.call", on_tool_call_handler)

# 系统触发事件（所有钩子并行执行）
await registry.emit("tool.call", event_data)
```

### 中间件模式（waterfall）

```python
# 插件注册钩子（可修改 payload）
async def auth_middleware(payload):
    payload["authenticated"] = True
    return payload

ctx.register_hook("request.pre", auth_middleware)

# 系统触发事件（顺序执行，传递结果）
result = await registry.waterfall("request.pre", initial_payload)
```

## 使用示例

### 创建插件

```python
from packages.agent.plugins import Plugin, PluginContext

class CalculatorPlugin(Plugin):
    name = "calculator"
    version = "1.0.0"
    description = "Basic calculator"
    
    async def activate(self, ctx: PluginContext):
        # 注册工具
        def add(a, b):
            return a + b
        
        ctx.register_tool("add", add)
        
        # 注册事件钩子
        async def on_tool_call(event):
            print(f"Tool called: {event['tool_name']}")
        
        ctx.register_hook("tool.call", on_tool_call)
    
    async def deactivate(self):
        # 清理资源（自动通过 ctx.dispose() 完成）
        pass
```

### 加载插件

```python
from pathlib import Path
from packages.agent.plugins import PluginManager

async def main():
    manager = PluginManager()
    
    # 添加插件目录
    manager.add_plugin_dir(Path("plugins"))
    
    # 初始化所有插件
    results = await manager.initialize()
    print(f"Loaded: {results}")
    
    # 获取插件
    calculator = manager.get_plugin("calculator")
    
    # 热重载
    await manager.hot_reload("calculator")
    
    # 关闭
    await manager.shutdown()
```

## 与 DeepSeek Harness 对比

| 特性 | DeepSeek Harness | KnowRAG 插件系统 |
|------|------------------|------------------|
| 框架基础 | Cordis（自研） | 自研 Plugin 框架 |
| 配置驱动 | YAML 配置 | 待集成 |
| 热更新 | 支持 | 支持 |
| 事件系统 | emit/waterfall | emit/waterfall |
| 工具注册 | 动态 | 动态 |
| 依赖管理 | 自动 | 手动（待改进） |
| 沙箱隔离 | 支持 | 待实现 |

## 待实现功能

### Phase 3 后续工作

- [ ] 配置驱动插件加载（从 YAML 配置自动加载插件）
- [ ] 插件依赖管理（自动解析和加载依赖）
- [ ] 插件沙箱隔离（防止恶意插件）
- [ ] 插件市场（第三方插件分发）

### Phase 4 集成

- [ ] 与事件溯源系统集成（插件可监听/触发事件）
- [ ] 与配置驱动系统集成（配置文件定义插件）
- [ ] 与 API 层集成（动态加载工具到 Agent）

## 最佳实践

### 1. 插件命名

使用小写字母和下划线：
- ✅ `calculator`, `web_search`, `code_interpreter`
- ❌ `Calculator`, `WebSearch`

### 2. 错误处理

插件必须处理自己的错误：

```python
async def activate(self, ctx: PluginContext):
    try:
        # 初始化代码
        pass
    except Exception as e:
        self.logger.error(f"Failed to activate: {e}")
        raise
```

### 3. 资源清理

确保 `deactivate()` 清理所有资源：

```python
async def deactivate(self):
    # 关闭数据库连接
    if self.db:
        await self.db.close()
    
    # 清除缓存
    self.cache.clear()
```

### 4. 可测试性

插件应该是独立的、可测试的：

```python
# 测试
async def test_calculator_plugin():
    plugin = CalculatorPlugin()
    ctx = MockContext()
    
    await plugin.activate(ctx)
    
    assert ctx.get_tool("add")(2, 3) == 5
```

## 测试

运行测试：

```bash
cd backend
python3 -m pytest tests/test_plugin_system.py -v
```

测试结果：
- ✅ 19 个测试全部通过
- 覆盖：注册、生命周期、钩子、加载器、管理器、集成测试

## 下一步

1. **配置驱动**：从 YAML 配置自动加载插件
2. **依赖管理**：自动解析插件依赖
3. **事件集成**：与事件溯源系统深度集成
4. **API 集成**：动态加载工具到 Agent 执行流程
