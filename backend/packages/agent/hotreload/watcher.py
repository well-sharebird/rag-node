"""
热更新系统

监听文件变化，支持配置/插件热加载，无需重启服务
"""
import asyncio
import logging
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Any
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent, FileDeletedEvent, FileMovedEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    Observer = None
    FileSystemEventHandler = object


logger = logging.getLogger(__name__)


class ChangeType(str, Enum):
    """文件变更类型"""
    MODIFIED = "modified"
    CREATED = "created"
    DELETED = "deleted"
    MOVED = "moved"


class ReloadStrategy(str, Enum):
    """重载策略"""
    IMMEDIATE = "immediate"  # 立即重载
    DEBOUNCE = "debounce"    # 防抖（延迟重载）
    BATCH = "batch"          # 批量重载


@dataclass
class FileChange:
    """文件变更事件"""
    path: str
    change_type: ChangeType
    old_path: Optional[str] = None
    content_hash: Optional[str] = None
    timestamp: float = 0.0


@dataclass
class HotReloadConfig:
    """热更新配置"""
    watch_dirs: List[str] = field(default_factory=list)
    watch_patterns: List[str] = field(default_factory=list)  # *.yaml, *.py
    ignore_patterns: List[str] = field(default_factory=list)  # __pycache__, *.pyc
    debounce_seconds: float = 0.5
    strategy: ReloadStrategy = ReloadStrategy.DEBOUNCE
    enabled: bool = True


class FileWatcher:
    """
    文件监听器
    
    使用 watchdog 监听文件系统变化
    """
    
    def __init__(self, config: HotReloadConfig):
        self.config = config
        self._callbacks: Dict[str, List[Callable]] = {}
        self._debounce_timers: Dict[str, asyncio.TimerHandle] = {}
        self._content_hashes: Dict[str, str] = {}
        self._observer = None
        self._event_loop = None
        
        if not WATCHDOG_AVAILABLE:
            logger.warning("watchdog not installed, hot reload disabled")
    
    def _compute_hash(self, path: str) -> Optional[str]:
        """计算文件内容哈希"""
        try:
            with open(path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception:
            return None
    
    def _should_watch(self, path: str) -> bool:
        """检查文件是否应该被监听"""
        path_obj = Path(path)
        
        # 检查忽略模式
        for pattern in self.config.ignore_patterns:
            if path_obj.match(pattern):
                return False
            if pattern in str(path):
                return False
        
        # 检查监听模式
        if self.config.watch_patterns:
            for pattern in self.config.watch_patterns:
                if path_obj.match(pattern):
                    return True
            return False
        
        return True
    
    def _on_file_change(self, event):
        """文件系统事件回调"""
        if not self._event_loop or not self._event_loop.is_running():
            return
        
        path = event.src_path
        change_type = ChangeType.MODIFIED
        
        if isinstance(event, FileCreatedEvent):
            change_type = ChangeType.CREATED
        elif isinstance(event, FileDeletedEvent):
            change_type = ChangeType.DELETED
        elif isinstance(event, FileMovedEvent):
            change_type = ChangeType.MOVED
        
        if not self._should_watch(path):
            return
        
        # 计算内容哈希
        content_hash = self._compute_hash(path) if change_type in [ChangeType.MODIFIED, ChangeType.CREATED] else None
        
        # 检测内容是否真的变化
        if change_type == ChangeType.MODIFIED:
            old_hash = self._content_hashes.get(path)
            if old_hash == content_hash:
                return  # 内容未变，忽略
        
        self._content_hashes[path] = content_hash
        
        file_change = FileChange(
            path=path,
            change_type=change_type,
            content_hash=content_hash,
            timestamp=event.event_time if hasattr(event, 'event_time') else 0.0
        )
        
        # 根据策略处理
        if self.config.strategy == ReloadStrategy.DEBOUNCE:
            self._debounce_notify(path, file_change)
        else:
            self._notify_callbacks(path, file_change)
    
    def _debounce_notify(self, path: str, change: FileChange):
        """防抖通知"""
        def notify():
            self._notify_callbacks(path, change)
            if path in self._debounce_timers:
                del self._debounce_timers[path]
        
        if path in self._debounce_timers:
            self._debounce_timers[path].cancel()
        
        loop = self._event_loop or asyncio.get_event_loop()
        timer = loop.call_later(self.config.debounce_seconds, notify)
        self._debounce_timers[path] = timer
    
    def _notify_callbacks(self, path: str, change: FileChange):
        """通知所有回调"""
        # 精确匹配回调
        for pattern, callbacks in self._callbacks.items():
            if path.endswith(pattern) or pattern == '*':
                for callback in callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            asyncio.create_task(callback(change))
                        else:
                            callback(change)
                    except Exception as e:
                        logger.error(f"Error in file change callback: {e}")
    
    def add_watch(self, path_pattern: str, callback: Callable[[FileChange], Any]):
        """添加监听回调"""
        if path_pattern not in self._callbacks:
            self._callbacks[path_pattern] = []
        self._callbacks[path_pattern].append(callback)
        logger.info(f"Added watch for pattern: {path_pattern}")
    
    def remove_watch(self, path_pattern: str, callback: Callable):
        """移除监听回调"""
        if path_pattern in self._callbacks:
            try:
                self._callbacks[path_pattern].remove(callback)
            except ValueError:
                pass
    
    def start(self):
        """启动监听"""
        if not WATCHDOG_AVAILABLE:
            return
        
        self._observer = Observer()
        handler = FileSystemEventHandler()
        handler.on_modified = self._on_file_change
        handler.on_created = self._on_file_change
        handler.on_deleted = self._on_file_change
        handler.on_moved = self._on_file_change
        
        for watch_dir in self.config.watch_dirs:
            path = Path(watch_dir)
            if path.exists() and path.is_dir():
                self._observer.schedule(handler, str(path), recursive=True)
                logger.info(f"Watching directory: {watch_dir}")
        
        self._observer.start()
        self._event_loop = asyncio.get_event_loop()
        logger.info("File watcher started")
    
    def stop(self):
        """停止监听"""
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None
        
        for timer in self._debounce_timers.values():
            timer.cancel()
        self._debounce_timers.clear()
        
        logger.info("File watcher stopped")


class ConfigHotReloader:
    """
    配置热重载
    
    监听配置文件变化并自动重载
    """
    
    def __init__(self, watcher: FileWatcher):
        self.watcher = watcher
        self._configs: Dict[str, Any] = {}
        self._reload_callbacks: List[Callable] = []
        
        # 监听配置文件
        watcher.add_watch("*.yaml", self._on_config_change)
        watcher.add_watch("*.yml", self._on_config_change)
        watcher.add_watch("*.json", self._on_config_change)
    
    def _on_config_change(self, change: FileChange):
        """配置文件变更处理"""
        logger.info(f"Config file changed: {change.path} ({change.change_type.value})")
        
        if change.change_type == ChangeType.DELETED:
            # 配置删除，从缓存移除
            if change.path in self._configs:
                del self._configs[change.path]
        elif change.change_type in [ChangeType.MODIFIED, ChangeType.CREATED]:
            # 配置修改/创建，重新加载
            try:
                config = self._load_config(change.path)
                self._configs[change.path] = config
                
                # 通知回调
                asyncio.create_task(self._notify_reload(config, change.path))
            except Exception as e:
                logger.error(f"Failed to reload config {change.path}: {e}")
    
    def _load_config(self, path: str) -> Dict:
        """加载配置文件"""
        import yaml
        
        with open(path, 'r', encoding='utf-8') as f:
            if path.endswith('.json'):
                return json.load(f)
            else:
                return yaml.safe_load(f)
    
    def get_config(self, path: str) -> Optional[Dict]:
        """获取配置"""
        return self._configs.get(path)
    
    def on_reload(self, callback: Callable):
        """注册重载回调"""
        self._reload_callbacks.append(callback)
    
    async def _notify_reload(self, config: Dict, path: str):
        """通知所有回调配置已重载"""
        for callback in self._reload_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(config, path)
                else:
                    callback(config, path)
            except Exception as e:
                logger.error(f"Error in reload callback: {e}")


class PluginHotSwapper:
    """
    插件热插拔
    
    支持运行时加载/卸载插件
    """
    
    def __init__(self, watcher: FileWatcher, plugin_dir: str):
        self.watcher = watcher
        self.plugin_dir = Path(plugin_dir)
        self._loaded_plugins: Dict[str, Any] = {}
        self._plugin_registry = None
        
        # 监听插件目录
        watcher.add_watch("*.py", self._on_plugin_change)
    
    def set_registry(self, registry):
        """设置插件注册中心"""
        self._plugin_registry = registry
    
    def _on_plugin_change(self, change: FileChange):
        """插件文件变更处理"""
        plugin_path = Path(change.path)
        
        # 检查是否在插件目录
        try:
            relative_path = plugin_path.relative_to(self.plugin_dir)
            plugin_name = relative_path.parts[0] if len(relative_path.parts) > 1 else plugin_path.stem
        except ValueError:
            return
        
        logger.info(f"Plugin file changed: {plugin_name} ({change.change_type.value})")
        
        if change.change_type == ChangeType.DELETED:
            # 插件删除，卸载
            asyncio.create_task(self._unload_plugin(plugin_name))
        elif change.change_type in [ChangeType.MODIFIED, ChangeType.CREATED]:
            # 插件修改/创建，重新加载
            asyncio.create_task(self._reload_plugin(plugin_name, change.path))
    
    async def _reload_plugin(self, plugin_name: str, path: str):
        """重新加载插件"""
        try:
            # 如果已加载，先卸载
            if plugin_name in self._loaded_plugins:
                await self._unload_plugin(plugin_name)
            
            # 重新加载
            if self._plugin_registry:
                await self._plugin_registry.load_plugin(path)
                logger.info(f"Plugin reloaded: {plugin_name}")
        except Exception as e:
            logger.error(f"Failed to reload plugin {plugin_name}: {e}")
    
    async def _unload_plugin(self, plugin_name: str):
        """卸载插件"""
        try:
            if self._plugin_registry:
                await self._plugin_registry.unload_plugin(plugin_name)
                if plugin_name in self._loaded_plugins:
                    del self._loaded_plugins[plugin_name]
                logger.info(f"Plugin unloaded: {plugin_name}")
        except Exception as e:
            logger.error(f"Failed to unload plugin {plugin_name}: {e}")


class HotReloadService:
    """
    热更新服务
    
    整合文件监听、配置重载、插件热插拔
    """
    
    def __init__(self, config: HotReloadConfig):
        self.config = config
        self.watcher = FileWatcher(config)
        self.config_reloader = ConfigHotReloader(self.watcher)
        self.plugin_swapper: Optional[PluginHotSwapper] = None
        self._started = False
    
    def setup_plugin_hotswap(self, plugin_dir: str):
        """设置插件热插拔"""
        self.plugin_swapper = PluginHotSwapper(self.watcher, plugin_dir)
        return self.plugin_swapper
    
    def start(self):
        """启动热更新服务"""
        if not self.config.enabled:
            logger.info("Hot reload is disabled")
            return
        
        if not WATCHDOG_AVAILABLE:
            logger.warning("watchdog not installed, hot reload unavailable")
            return
        
        self.watcher.start()
        self._started = True
        logger.info("Hot reload service started")
    
    def stop(self):
        """停止热更新服务"""
        if self._started:
            self.watcher.stop()
            self._started = False
            logger.info("Hot reload service stopped")
    
    def watch_config(self, callback: Callable):
        """监听配置重载"""
        self.config_reloader.on_reload(callback)
    
    def get_config(self, path: str) -> Optional[Dict]:
        """获取配置"""
        return self.config_reloader.get_config(path)


def create_hot_reload_service(
    watch_dirs: List[str],
    watch_patterns: List[str] = None,
    ignore_patterns: List[str] = None,
    enabled: bool = True
) -> HotReloadService:
    """创建热更新服务"""
    
    config = HotReloadConfig(
        watch_dirs=watch_dirs,
        watch_patterns=watch_patterns or ["*.yaml", "*.yml", "*.json", "*.py"],
        ignore_patterns=ignore_patterns or ["__pycache__", "*.pyc", "*.pyo", ".git", "*.log"],
        enabled=enabled
    )
    
    return HotReloadService(config)
