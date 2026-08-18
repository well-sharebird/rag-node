"""
插件加载器

支持动态加载/卸载插件
"""
import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from .base import Plugin, PluginRegistry, PluginContext, PluginStatus


class PluginLoader:
    """
    插件加载器
    
    从文件系统或模块动态加载插件
    """
    
    def __init__(self, registry: PluginRegistry):
        self._registry = registry
        self._plugin_paths: Dict[str, Path] = {}
        self._loaded_modules: Dict[str, Any] = {}
    
    def discover_plugins(self, plugin_dir: Path) -> List[str]:
        """
        扫描插件目录
        
        Returns:
            发现的插件名称列表
        """
        plugin_names = []
        
        if not plugin_dir.exists():
            return plugin_names
        
        for path in plugin_dir.iterdir():
            if path.is_file() and path.suffix == ".py" and not path.name.startswith("_"):
                # 从文件加载
                plugin_name = path.stem
                self._plugin_paths[plugin_name] = path
                plugin_names.append(plugin_name)
            elif path.is_dir() and not path.name.startswith("_"):
                # 从目录加载（包）
                if (path / "__init__.py").exists():
                    plugin_name = path.name
                    self._plugin_paths[plugin_name] = path / "__init__.py"
                    plugin_names.append(plugin_name)
        
        return plugin_names
    
    def load_from_module(self, module_name: str, plugin_dir: Optional[Path] = None) -> Optional[Plugin]:
        """
        从模块加载插件
        
        Args:
            module_name: 模块名称
            plugin_dir: 插件目录（可选）
        
        Returns:
            插件实例
        """
        try:
            # 添加插件目录到 sys.path
            if plugin_dir and str(plugin_dir.parent) not in sys.path:
                sys.path.insert(0, str(plugin_dir.parent))
            
            # 导入模块
            spec = importlib.util.spec_from_file_location(
                module_name,
                self._plugin_paths.get(module_name)
            )
            
            if not spec or not spec.loader:
                return None
            
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            
            # 查找 Plugin 子类
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and 
                    issubclass(attr, Plugin) and 
                    attr is not Plugin and
                    hasattr(attr, 'name')):
                    # 实例化插件
                    plugin = attr()
                    self._loaded_modules[module_name] = module
                    return plugin
            
            return None
            
        except Exception as e:
            print(f"Error loading plugin {module_name}: {e}")
            return None
    
    async def load_plugin(self, plugin_name: str, plugin_dir: Optional[Path] = None) -> bool:
        """
        加载单个插件
        
        Returns:
            是否成功
        """
        # 检查是否已加载
        if self._registry.get_plugin(plugin_name):
            return True
        
        # 从模块加载
        plugin = self.load_from_module(plugin_name, plugin_dir)
        if not plugin:
            return False
        
        # 注册并激活
        self._registry.register_plugin(plugin)
        ctx = PluginContext(self._registry)
        
        try:
            await self._registry.load_plugin(plugin_name, ctx)
            return True
        except Exception as e:
            print(f"Failed to activate plugin {plugin_name}: {e}")
            return False
    
    async def unload_plugin(self, plugin_name: str) -> bool:
        """
        卸载单个插件
        
        Returns:
            是否成功
        """
        plugin = self._registry.get_plugin(plugin_name)
        if not plugin:
            return False
        
        try:
            await self._registry.unload_plugin(plugin_name)
            return True
        except Exception as e:
            print(f"Failed to unload plugin {plugin_name}: {e}")
            return False
    
    async def load_all(self, plugin_dir: Path) -> Dict[str, bool]:
        """
        加载所有插件
        
        Returns:
            插件加载结果字典
        """
        plugin_names = self.discover_plugins(plugin_dir)
        results = {}
        
        for name in plugin_names:
            results[name] = await self.load_plugin(name, plugin_dir)
        
        return results
    
    async def reload_plugin(self, plugin_name: str, plugin_dir: Optional[Path] = None) -> bool:
        """
        热重载插件
        
        Returns:
            是否成功
        """
        # 先卸载
        await self.unload_plugin(plugin_name)
        
        # 从 sys.modules 中移除
        if plugin_name in self._loaded_modules:
            del sys.modules[plugin_name]
            del self._loaded_modules[plugin_name]
        
        # 重新加载
        return await self.load_plugin(plugin_name, plugin_dir)


class PluginManager:
    """
    插件管理器
    
    高层抽象，整合 Loader 和 Registry
    """
    
    def __init__(self):
        self._registry = PluginRegistry()
        self._loader = PluginLoader(self._registry)
        self._plugin_dirs: List[Path] = []
    
    @property
    def registry(self) -> PluginRegistry:
        """获取注册中心"""
        return self._registry
    
    @property
    def loader(self) -> PluginLoader:
        """获取加载器"""
        return self._loader
    
    def add_plugin_dir(self, path: Path) -> None:
        """添加插件目录"""
        self._plugin_dirs.append(path)
    
    async def initialize(self) -> Dict[str, bool]:
        """
        初始化所有插件
        
        Returns:
            加载结果
        """
        results = {}
        
        for plugin_dir in self._plugin_dirs:
            dir_results = await self._loader.load_all(plugin_dir)
            results.update(dir_results)
        
        return results
    
    async def shutdown(self) -> None:
        """关闭所有插件"""
        for plugin in self._registry.list_plugins():
            try:
                await plugin.unload()
            except Exception as e:
                print(f"Error unloading plugin {plugin.name}: {e}")
    
    def get_plugin(self, name: str) -> Optional[Plugin]:
        """获取插件"""
        return self._registry.get_plugin(name)
    
    def list_plugins(self) -> List[Plugin]:
        """列出所有插件"""
        return self._registry.list_plugins()
    
    async def hot_reload(self, plugin_name: str) -> bool:
        """
        热重载插件
        
        Returns:
            是否成功
        """
        # 查找插件所在目录
        plugin_dir = None
        for path in self._plugin_dirs:
            if (path / f"{plugin_name}.py").exists() or \
               (path / plugin_name / "__init__.py").exists():
                plugin_dir = path
                break
        
        if not plugin_dir:
            print(f"Plugin directory not found for {plugin_name}")
            return False
        
        return await self._loader.reload_plugin(plugin_name, plugin_dir)


__all__ = [
    "PluginLoader",
    "PluginManager",
]
