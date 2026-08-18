# 热更新系统架构文档

## 概述

热更新系统支持运行时监听文件和插件变化，自动重载配置和插件，无需重启服务。这对于开发环境和需要高可用的生产环境至关重要。

## 核心组件

### 1. FileWatcher（文件监听器）

**职责**: 使用 watchdog 库监听文件系统变化

**关键特性**:
- **防抖处理**: 避免文件保存期间触发多次重载（默认 0.5 秒延迟）
- **内容哈希检测**: 只有文件内容真正变化时才触发（避免时间戳变化误报）
- **模式匹配**: 支持监听模式（`*.yaml`）和忽略模式（`__pycache__`）
- **异步回调**: 支持同步和异步回调函数

**执行流程**:
```
文件变化 → 检查模式 → 计算哈希 → 防抖处理 → 通知回调
```

**代码示例**:
```python
config = HotReloadConfig(
    watch_dirs=["/config", "/plugins"],
    watch_patterns=["*.yaml", "*.py"],
    ignore_patterns=["__pycache__", "*.log"]
)

watcher = FileWatcher(config)
watcher.add_watch("*.yaml", on_config_change)
watcher.start()
```

### 2. ConfigHotReloader（配置热重载器）

**职责**: 监听配置文件变化并自动重载

**支持格式**:
- YAML (`.yaml`, `.yml`)
- JSON (`.json`)

**工作流程**:
```
1. 监听到 .yaml 文件变化
2. 检查变更类型（MODIFIED/CREATED/DELETED）
3. 重新加载文件内容
4. 更新缓存
5. 通知所有注册的回调
```

**回调机制**:
```python
async def on_config_reload(config: Dict, path: str):
    # 重新应用配置
    await apply_new_config(config)

reloader.on_reload(on_config_reload)
```

### 3. PluginHotSwapper（插件热插拔）

**职责**: 支持运行时加载/卸载/重载插件

**核心能力**:
- **自动检测**: 监听插件目录的 `.py` 文件变化
- **依赖安全**: 先卸载旧版本再加载新版本
- **错误隔离**: 插件加载失败不影响其他插件

**重载流程**:
```
插件文件变化 → 识别插件名称 → 卸载旧版本 → 加载新版本 → 通知注册中心
```

**使用示例**:
```python
swapper = service.setup_plugin_hotswap("/plugins")
swapper.set_registry(plugin_registry)

# 自动监听 /plugins 目录
# 修改插件代码后自动重载
```

### 4. HotReloadService（热更新服务）

**职责**: 整合文件监听、配置重载、插件热插拔

**统一管理**:
- 单一入口启动/停止服务
- 统一的配置管理
- 协调各个子系统

**使用示例**:
```python
service = create_hot_reload_service(
    watch_dirs=["/config", "/plugins"],
    enabled=True
)

service.watch_config(on_config_change)
service.setup_plugin_hotswap("/plugins")
service.start()
```

## 设计模式

### 1. 观察者模式
FileWatcher 作为被观察者，ConfigHotReloader 和 PluginHotSwapper 作为观察者。

```python
# 发布
watcher._notify_callbacks(path, change)

# 订阅
watcher.add_watch("*.yaml", callback)
```

### 2. 策略模式
支持三种重载策略：

```python
class ReloadStrategy(Enum):
    IMMEDIATE = "immediate"  # 立即重载
    DEBOUNCE = "debounce"    # 防抖重载（默认）
    BATCH = "batch"          # 批量重载
```

### 3. 模板方法模式
ConfigHotReloader 定义了重载的骨架：

```python
def _on_config_change(self, change):
    if DELETED:
        self._handle_delete()
    elif MODIFIED or CREATED:
        self._load_config()  # 子类可重写
        self._notify_reload()  # 子类可重写
```

## 关键技术实现

### 1. 防抖处理

**问题**: 编辑器保存文件时可能触发多次修改事件

**解决**: 使用延迟定时器，0.5 秒内只触发一次

```python
def _debounce_notify(self, path, change):
    if path in self._debounce_timers:
        self._debounce_timers[path].cancel()
    
    timer = loop.call_later(0.5, notify)
    self._debounce_timers[path] = timer
```

### 2. 内容哈希检测

**问题**: 文件访问时间戳变化会误触发重载

**解决**: 计算 MD5 哈希，只有内容真正变化才触发

```python
def _compute_hash(self, path):
    with open(path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

# 检查哈希是否变化
if old_hash == new_hash:
    return  # 内容未变，忽略
```

### 3. 异步回调支持

**问题**: 重载回调可能是同步或异步函数

**解决**: 自动检测并调度

```python
async def _notify_reload(self, config, path):
    for callback in self._reload_callbacks:
        if asyncio.iscoroutinefunction(callback):
            await callback(config, path)
        else:
            callback(config, path)
```

### 4. 错误隔离

**问题**: 单个插件加载失败不应影响其他插件

**解决**: 每个操作独立 try-except

```python
try:
    await self._plugin_registry.load_plugin(path)
except Exception as e:
    logger.error(f"Failed to load plugin: {e}")
    # 不抛出异常，继续处理其他插件
```

## 使用场景

### 1. 开发环境
- 修改配置文件后立即生效
- 调整插件代码后自动重载
- 无需重启服务，提高开发效率

### 2. 生产环境
- 动态调整日志级别
- 更新限流配置
- 热修复紧急 Bug（通过插件热插拔）

### 3. 配置中心
- 监听远程配置中心的本地缓存
- 配置变更后自动应用
- 支持灰度发布

## 依赖管理

### 可选依赖
```python
try:
    from watchdog.observers import Observer
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
```

**安装**:
```bash
pip install watchdog
```

**降级方案**: 如果 watchdog 不可用，服务优雅降级（不启用热更新）

## 测试覆盖

**测试文件**: `tests/test_hot_reload.py`

**测试统计**:
- 总测试数：30 个
- 通过率：100%

**测试分类**:
| 类别 | 测试数 | 通过率 |
|------|--------|--------|
| ChangeType | 1 | 100% |
| ReloadStrategy | 1 | 100% |
| FileChange | 2 | 100% |
| HotReloadConfig | 2 | 100% |
| FileWatcher | 6 | 100% |
| ConfigHotReloader | 5 | 100% |
| PluginHotSwapper | 2 | 100% |
| HotReloadService | 6 | 100% |
| Integration | 5 | 100% |

## 性能优化

### 1. 懒加载
只在需要时启动 watchdog observer

### 2. 哈希缓存
缓存已计算的文件哈希，避免重复计算

### 3. 批量处理
支持 BATCH 策略，一次处理多个文件变化

### 4. 异步处理
文件 I/O 和回调执行使用异步，不阻塞主线程

## 安全考虑

### 1. 文件权限
只监听授权目录，防止监听敏感文件

```python
ignore_patterns=["__pycache__", "*.log", ".git", ".env"]
```

### 2. 异常捕获
所有回调执行都有 try-except 保护

### 3. 资源清理
服务停止时正确释放 watchdog 资源

```python
def stop(self):
    if self._observer:
        self._observer.stop()
        self._observer.join()
```

## 与其他系统集成

### 1. 配置驱动系统
```python
# 配置变更后重新构建 LangGraph
async def on_config_change(config, path):
    await config_graph_builder.rebuild(config)

hot_reload_service.watch_config(on_config_change)
```

### 2. 插件系统
```python
# 插件热插拔
swapper = hot_reload_service.setup_plugin_hotswap("/plugins")
swapper.set_registry(plugin_manager)
```

### 3. 事件总线
```python
# 发布配置变更事件
async def on_config_change(config, path):
    await event_bus.publish("config.reloaded", {
        "path": path,
        "config": config
    })
```

## 限制和注意事项

### 1. Python 模块重载限制
- 已导入的模块不会自动重新加载
- 需要使用 `importlib.reload()` 手动重载
- 建议插件系统设计为可热插拔架构

### 2. 文件竞争条件
- 大文件写入可能触发多次事件
- 使用防抖和内容哈希检测缓解

### 3. 生产环境谨慎使用
- 建议仅在开发环境启用完整热更新
- 生产环境可只启用配置热更新

## 未来优化方向

1. **远程配置监听**: 支持监听远程配置中心（如 etcd、Consul）
2. **版本回滚**: 配置变更失败时自动回滚到上一个版本
3. **变更审计**: 记录每次配置变更的历史
4. **增量重载**: 只重载变更的部分，而不是整个配置
5. **多进程同步**: 在多进程环境下同步重载

## 总结

热更新系统通过监听文件系统变化，实现了配置和插件的运行时重载，显著提升了开发效率和系统可用性。核心设计原则：

1. **非侵入式**: 使用标准 watchdog 库，不依赖特定框架
2. **异步友好**: 完全支持 asyncio，不阻塞事件循环
3. **错误隔离**: 单个失败不影响整体
4. **灵活配置**: 支持自定义监听目录、模式、策略

通过 30 个测试用例验证了系统的可靠性和健壮性。
