"""
插件系统基础

定义插件接口和注册机制
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from enum import Enum
import asyncio


class PluginStatus(str, Enum):
    """插件状态"""
    UNLOADED = "unloaded"
    LOADING = "loading"
    ACTIVE = "active"
    UNLOADING = "unloading"
    FAILED = "failed"


class PluginContext:
    """
    插件上下文
    
    提供插件与系统交互的接口
    """
    
    def __init__(self, registry: "PluginRegistry"):
        self._registry = registry
        self._effects = []  # 可逆效果列表
    
    def register_tool(self, name: str, tool: Any) -> callable:
        """
        注册工具
        
        Returns:
            卸载函数
        """
        self._registry.register_tool(name, tool)
        
        def unregister():
            self._registry.unregister_tool(name)
        
        self._effects.append(unregister)
        return unregister
    
    def register_hook(self, event: str, handler: callable) -> callable:
        """
        注册事件钩子
        
        Returns:
            卸载函数
        """
        self._registry.register_hook(event, handler)
        
        def unregister():
            self._registry.unregister_hook(event, handler)
        
        self._effects.append(unregister)
        return unregister
    
    def dispose(self):
        """释放所有效果"""
        for effect in reversed(self._effects):
            try:
                effect()
            except Exception as e:
                print(f"Error disposing effect: {e}")
        self._effects.clear()


class Plugin(ABC):
    """
    插件基类
    
    所有插件必须继承此类并实现生命周期方法
    """
    
    # 插件元数据
    name: str = "unnamed_plugin"
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    
    def __init__(self):
        self.status = PluginStatus.UNLOADED
        self.ctx: Optional[PluginContext] = None
    
    @abstractmethod
    async def activate(self, ctx: PluginContext) -> None:
        """
        激活插件
        
        在此注册工具、钩子等
        """
        pass
    
    @abstractmethod
    async def deactivate(self) -> None:
        """
        停用插件
        
        清理资源，卸载钩子等
        """
        pass
    
    async def load(self, ctx: PluginContext) -> None:
        """加载插件（模板方法）"""
        self.status = PluginStatus.LOADING
        try:
            self.ctx = ctx
            await self.activate(ctx)
            self.status = PluginStatus.ACTIVE
        except Exception as e:
            self.status = PluginStatus.FAILED
            raise
    
    async def unload(self) -> None:
        """卸载插件（模板方法）"""
        self.status = PluginStatus.UNLOADING
        try:
            await self.deactivate()
            if self.ctx:
                self.ctx.dispose()
                self.ctx = None
            self.status = PluginStatus.UNLOADED
        except Exception as e:
            self.status = PluginStatus.FAILED
            raise


class PluginRegistry:
    """
    插件注册中心
    
    管理插件的生命周期和依赖
    """
    
    def __init__(self):
        self._plugins: Dict[str, Plugin] = {}
        self._tools: Dict[str, Any] = {}
        self._hooks: Dict[str, list] = {}
    
    def register_plugin(self, plugin: Plugin) -> None:
        """注册插件"""
        self._plugins[plugin.name] = plugin
    
    def get_plugin(self, name: str) -> Optional[Plugin]:
        """获取插件"""
        return self._plugins.get(name)
    
    def list_plugins(self) -> list:
        """列出所有插件"""
        return list(self._plugins.values())
    
    async def load_plugin(self, name: str, ctx: PluginContext) -> None:
        """加载插件"""
        plugin = self.get_plugin(name)
        if not plugin:
            raise ValueError(f"Plugin not found: {name}")
        
        await plugin.load(ctx)
    
    async def unload_plugin(self, name: str) -> None:
        """卸载插件"""
        plugin = self.get_plugin(name)
        if not plugin:
            raise ValueError(f"Plugin not found: {name}")
        
        await plugin.unload()
    
    def register_tool(self, name: str, tool: Any) -> None:
        """注册工具"""
        self._tools[name] = tool
    
    def unregister_tool(self, name: str) -> None:
        """卸载工具"""
        if name in self._tools:
            del self._tools[name]
    
    def get_tool(self, name: str) -> Optional[Any]:
        """获取工具"""
        return self._tools.get(name)
    
    def list_tools(self) -> Dict[str, Any]:
        """列出所有工具"""
        return self._tools.copy()
    
    def register_hook(self, event: str, handler: callable) -> None:
        """注册事件钩子"""
        if event not in self._hooks:
            self._hooks[event] = []
        self._hooks[event].append(handler)
    
    def unregister_hook(self, event: str, handler: callable) -> None:
        """卸载事件钩子"""
        if event in self._hooks:
            try:
                self._hooks[event].remove(handler)
            except ValueError:
                pass
    
    async def emit(self, event: str, *args, **kwargs) -> None:
        """触发事件（通知模式）"""
        handlers = self._hooks.get(event, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(*args, **kwargs)
                else:
                    handler(*args, **kwargs)
            except Exception as e:
                print(f"Error in hook {event}: {e}")
    
    async def waterfall(self, event: str, payload: Any) -> Any:
        """
        触发事件（中间件模式）
        
        每个钩子可以修改 payload 并传递给下一个
        """
        handlers = self._hooks.get(event, [])
        result = payload
        
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(result)
                else:
                    result = handler(result)
            except Exception as e:
                print(f"Error in waterfall hook {event}: {e}")
                raise
        
        return result


__all__ = [
    "PluginStatus",
    "PluginContext",
    "Plugin",
    "PluginRegistry",
]
