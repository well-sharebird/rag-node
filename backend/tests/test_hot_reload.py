"""
测试热更新系统
"""
import pytest
import asyncio
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from packages.agent.hotreload.watcher import (
    HotReloadService,
    HotReloadConfig,
    FileWatcher,
    ConfigHotReloader,
    PluginHotSwapper,
    create_hot_reload_service,
    ChangeType,
    ReloadStrategy,
    FileChange,
)


class TestChangeType:
    """测试变更类型"""
    
    def test_change_type_values(self):
        """测试变更类型值"""
        assert ChangeType.MODIFIED.value == "modified"
        assert ChangeType.CREATED.value == "created"
        assert ChangeType.DELETED.value == "deleted"
        assert ChangeType.MOVED.value == "moved"


class TestReloadStrategy:
    """测试重载策略"""
    
    def test_strategy_values(self):
        """测试策略值"""
        assert ReloadStrategy.IMMEDIATE.value == "immediate"
        assert ReloadStrategy.DEBOUNCE.value == "debounce"
        assert ReloadStrategy.BATCH.value == "batch"


class TestFileChange:
    """测试文件变更事件"""
    
    def test_file_change_creation(self):
        """测试文件变更创建"""
        change = FileChange(
            path="/test/config.yaml",
            change_type=ChangeType.MODIFIED,
            content_hash="abc123"
        )
        
        assert change.path == "/test/config.yaml"
        assert change.change_type == ChangeType.MODIFIED
        assert change.content_hash == "abc123"
        assert change.old_path is None
    
    def test_file_change_with_old_path(self):
        """测试带旧路径的文件变更"""
        change = FileChange(
            path="/test/new.yaml",
            change_type=ChangeType.MOVED,
            old_path="/test/old.yaml"
        )
        
        assert change.old_path == "/test/old.yaml"
        assert change.change_type == ChangeType.MOVED


class TestHotReloadConfig:
    """测试热更新配置"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = HotReloadConfig()
        
        assert config.watch_dirs == []
        assert config.watch_patterns == []
        assert config.ignore_patterns == []
        assert config.debounce_seconds == 0.5
        assert config.strategy == ReloadStrategy.DEBOUNCE
        assert config.enabled is True
    
    def test_custom_config(self):
        """测试自定义配置"""
        config = HotReloadConfig(
            watch_dirs=["/config", "/plugins"],
            watch_patterns=["*.yaml", "*.json"],
            ignore_patterns=["__pycache__", "*.log"],
            debounce_seconds=1.0,
            strategy=ReloadStrategy.IMMEDIATE,
            enabled=False
        )
        
        assert config.watch_dirs == ["/config", "/plugins"]
        assert config.watch_patterns == ["*.yaml", "*.json"]
        assert config.ignore_patterns == ["__pycache__", "*.log"]
        assert config.debounce_seconds == 1.0
        assert config.strategy == ReloadStrategy.IMMEDIATE
        assert config.enabled is False


class TestFileWatcher:
    """测试文件监听器"""
    
    def test_watcher_creation(self):
        """测试监听器创建"""
        config = HotReloadConfig()
        watcher = FileWatcher(config)
        
        assert watcher.config == config
        assert watcher._callbacks == {}
        assert watcher._content_hashes == {}
    
    def test_compute_hash(self, tmp_path):
        """测试计算文件哈希"""
        config = HotReloadConfig()
        watcher = FileWatcher(config)
        
        # 创建测试文件
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")
        
        content_hash = watcher._compute_hash(str(test_file))
        assert content_hash is not None
        assert len(content_hash) == 32  # MD5 hex length
        
        # 相同内容应该有相同哈希
        hash2 = watcher._compute_hash(str(test_file))
        assert content_hash == hash2
        
        # 不同内容应该有不同的哈希
        test_file.write_text("Different content")
        hash3 = watcher._compute_hash(str(test_file))
        assert content_hash != hash3
    
    def test_should_watch_with_ignore_patterns(self):
        """测试忽略模式"""
        config = HotReloadConfig(
            ignore_patterns=["__pycache__", "*.pyc", ".git"]
        )
        watcher = FileWatcher(config)
        
        assert not watcher._should_watch("/project/__pycache__/module.pyc")
        assert not watcher._should_watch("/project/module.pyc")
        assert not watcher._should_watch("/project/.git/config")
        assert watcher._should_watch("/project/config.yaml")
    
    def test_should_watch_with_watch_patterns(self):
        """测试监听模式"""
        config = HotReloadConfig(
            watch_patterns=["*.yaml", "*.json"],
            ignore_patterns=[]
        )
        watcher = FileWatcher(config)
        
        assert watcher._should_watch("/config/test.yaml")
        assert watcher._should_watch("/config/test.json")
        assert not watcher._should_watch("/config/test.py")
        assert not watcher._should_watch("/config/test.txt")
    
    def test_add_watch_callback(self):
        """测试添加监听回调"""
        config = HotReloadConfig()
        watcher = FileWatcher(config)
        
        callback = Mock()
        watcher.add_watch("*.yaml", callback)
        
        assert "*.yaml" in watcher._callbacks
        assert callback in watcher._callbacks["*.yaml"]
    
    def test_remove_watch_callback(self):
        """测试移除监听回调"""
        config = HotReloadConfig()
        watcher = FileWatcher(config)
        
        callback = Mock()
        watcher.add_watch("*.yaml", callback)
        watcher.remove_watch("*.yaml", callback)
        
        assert callback not in watcher._callbacks["*.yaml"]


class TestConfigHotReloader:
    """测试配置热重载"""
    
    def test_config_reloader_creation(self):
        """测试配置重载器创建"""
        config = HotReloadConfig()
        watcher = FileWatcher(config)
        reloader = ConfigHotReloader(watcher)
        
        assert reloader.watcher == watcher
        assert reloader._configs == {}
        assert reloader._reload_callbacks == []
    
    def test_load_yaml_config(self, tmp_path):
        """测试加载 YAML 配置"""
        config = HotReloadConfig()
        watcher = FileWatcher(config)
        reloader = ConfigHotReloader(watcher)
        
        # 创建测试 YAML 文件
        test_file = tmp_path / "config.yaml"
        test_file.write_text("name: test\nvalue: 123")
        
        loaded = reloader._load_config(str(test_file))
        
        assert loaded["name"] == "test"
        assert loaded["value"] == 123
    
    def test_load_json_config(self, tmp_path):
        """测试加载 JSON 配置"""
        config = HotReloadConfig()
        watcher = FileWatcher(config)
        reloader = ConfigHotReloader(watcher)
        
        # 创建测试 JSON 文件
        test_file = tmp_path / "config.json"
        test_file.write_text('{"name": "test", "value": 123}')
        
        loaded = reloader._load_config(str(test_file))
        
        assert loaded["name"] == "test"
        assert loaded["value"] == 123
    
    def test_get_config(self):
        """测试获取配置"""
        config = HotReloadConfig()
        watcher = FileWatcher(config)
        reloader = ConfigHotReloader(watcher)
        
        # 模拟已加载的配置
        reloader._configs["/test/config.yaml"] = {"key": "value"}
        
        result = reloader.get_config("/test/config.yaml")
        assert result == {"key": "value"}
        
        # 不存在的配置
        result = reloader.get_config("/nonexistent.yaml")
        assert result is None
    
    def test_on_reload_callback(self):
        """测试重载回调注册"""
        config = HotReloadConfig()
        watcher = FileWatcher(config)
        reloader = ConfigHotReloader(watcher)
        
        callback1 = Mock()
        callback2 = Mock()
        
        reloader.on_reload(callback1)
        reloader.on_reload(callback2)
        
        assert len(reloader._reload_callbacks) == 2
        assert callback1 in reloader._reload_callbacks
        assert callback2 in reloader._reload_callbacks
    
    @pytest.mark.asyncio
    async def test_notify_reload(self):
        """测试通知重载"""
        config = HotReloadConfig()
        watcher = FileWatcher(config)
        reloader = ConfigHotReloader(watcher)
        
        call_args = []
        
        async def callback(config, path):
            call_args.append((config, path))
        
        reloader.on_reload(callback)
        
        config_data = {"key": "new_value"}
        await reloader._notify_reload(config_data, "/test/config.yaml")
        
        assert len(call_args) == 1
        assert call_args[0] == (config_data, "/test/config.yaml")


class TestPluginHotSwapper:
    """测试插件热插拔"""
    
    def test_plugin_swapper_creation(self, tmp_path):
        """测试插件热插拔创建"""
        config = HotReloadConfig()
        watcher = FileWatcher(config)
        swapper = PluginHotSwapper(watcher, str(tmp_path))
        
        assert swapper.watcher == watcher
        assert swapper.plugin_dir == tmp_path
        assert swapper._loaded_plugins == {}
        assert swapper._plugin_registry is None
    
    def test_set_registry(self, tmp_path):
        """测试设置注册中心"""
        config = HotReloadConfig()
        watcher = FileWatcher(config)
        swapper = PluginHotSwapper(watcher, str(tmp_path))
        
        registry = Mock()
        swapper.set_registry(registry)
        
        assert swapper._plugin_registry == registry


class TestHotReloadService:
    """测试热更新服务"""
    
    def test_service_creation(self):
        """测试服务创建"""
        config = HotReloadConfig()
        service = HotReloadService(config)
        
        assert service.config == config
        assert service.watcher is not None
        assert service.config_reloader is not None
        assert service.plugin_swapper is None
        assert service._started is False
    
    def test_setup_plugin_hotswap(self, tmp_path):
        """测试设置插件热插拔"""
        config = HotReloadConfig()
        service = HotReloadService(config)
        
        swapper = service.setup_plugin_hotswap(str(tmp_path))
        
        assert service.plugin_swapper is not None
        assert swapper == service.plugin_swapper
        assert swapper.plugin_dir == tmp_path
    
    def test_watch_config(self):
        """测试监听配置"""
        config = HotReloadConfig()
        service = HotReloadService(config)
        
        callback = Mock()
        service.watch_config(callback)
        
        assert callback in service.config_reloader._reload_callbacks
    
    def test_get_config(self):
        """测试获取配置"""
        config = HotReloadConfig()
        service = HotReloadService(config)
        
        # 模拟已加载的配置
        service.config_reloader._configs["/test.yaml"] = {"key": "value"}
        
        result = service.get_config("/test.yaml")
        assert result == {"key": "value"}
    
    @patch('packages.agent.hotreload.watcher.WATCHDOG_AVAILABLE', False)
    def test_start_without_watchdog(self):
        """测试没有 watchdog 时启动"""
        config = HotReloadConfig()
        service = HotReloadService(config)
        
        service.start()
        
        assert service._started is False
    
    def test_start_disabled(self):
        """测试启动禁用的服务"""
        config = HotReloadConfig(enabled=False)
        service = HotReloadService(config)
        
        service.start()
        
        assert service._started is False


class TestCreateHotReloadService:
    """测试创建热更新服务"""
    
    def test_create_with_defaults(self):
        """测试使用默认值创建"""
        service = create_hot_reload_service(
            watch_dirs=["/config", "/plugins"]
        )
        
        assert service.config.watch_dirs == ["/config", "/plugins"]
        assert service.config.watch_patterns == ["*.yaml", "*.yml", "*.json", "*.py"]
        assert service.config.ignore_patterns == ["__pycache__", "*.pyc", "*.pyo", ".git", "*.log"]
        assert service.config.enabled is True
    
    def test_create_with_custom_patterns(self):
        """测试使用自定义模式创建"""
        service = create_hot_reload_service(
            watch_dirs=["/config"],
            watch_patterns=["*.yaml"],
            ignore_patterns=["*.log"],
            enabled=False
        )
        
        assert service.config.watch_dirs == ["/config"]
        assert service.config.watch_patterns == ["*.yaml"]
        assert service.config.ignore_patterns == ["*.log"]
        assert service.config.enabled is False


class TestHotReloadIntegration:
    """热更新集成测试"""
    
    def test_full_config_reload_flow(self, tmp_path):
        """测试完整的配置重载流程"""
        # 创建测试配置文件
        config_file = tmp_path / "test.yaml"
        config_file.write_text("initial: value")
        
        # 创建热更新服务
        service = create_hot_reload_service(
            watch_dirs=[str(tmp_path)],
            watch_patterns=["*.yaml"],
            ignore_patterns=[]
        )
        
        # 注册重载回调
        reload_events = []
        
        def on_reload(config, path):
            reload_events.append((config, path))
        
        service.watch_config(on_reload)
        
        # 手动触发配置加载
        config_data = service.config_reloader._load_config(str(config_file))
        service.config_reloader._configs[str(config_file)] = config_data
        
        # 验证配置已加载
        assert service.get_config(str(config_file)) == {"initial": "value"}
    
    def test_multiple_config_files(self, tmp_path):
        """测试多个配置文件"""
        # 创建多个测试配置文件
        config1 = tmp_path / "config1.yaml"
        config2 = tmp_path / "config2.yaml"
        config1.write_text("name: config1")
        config2.write_text("name: config2")
        
        # 创建热更新服务
        service = create_hot_reload_service(
            watch_dirs=[str(tmp_path)],
            ignore_patterns=[]
        )
        
        # 加载两个配置
        data1 = service.config_reloader._load_config(str(config1))
        data2 = service.config_reloader._load_config(str(config2))
        service.config_reloader._configs[str(config1)] = data1
        service.config_reloader._configs[str(config2)] = data2
        
        # 验证两个配置都能获取
        assert service.get_config(str(config1))["name"] == "config1"
        assert service.get_config(str(config2))["name"] == "config2"


# Helper for async tests
class AsyncMock(Mock):
    async def __call__(self, *args, **kwargs):
        return super().__call__(*args, **kwargs)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
