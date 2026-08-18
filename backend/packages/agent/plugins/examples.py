"""
示例插件：计算器

演示插件系统的基本用法
"""
from typing import Any, Dict
from .base import Plugin, PluginContext


class CalculatorPlugin(Plugin):
    """
    计算器插件
    
    提供基本的数学运算工具
    """
    
    name = "calculator"
    version = "1.0.0"
    description = "Basic calculator plugin"
    author = "KnowRAG Team"
    
    def __init__(self):
        super().__init__()
        self._tools = {}
    
    async def activate(self, ctx: PluginContext) -> None:
        """激活插件，注册工具"""
        
        # 注册加法工具
        def add(a: float, b: float) -> float:
            """Add two numbers"""
            return a + b
        
        # 注册减法工具
        def subtract(a: float, b: float) -> float:
            """Subtract b from a"""
            return a - b
        
        # 注册乘法工具
        def multiply(a: float, b: float) -> float:
            """Multiply two numbers"""
            return a * b
        
        # 注册除法工具
        def divide(a: float, b: float) -> float:
            """Divide a by b"""
            if b == 0:
                raise ValueError("Division by zero")
            return a / b
        
        # 注册到上下文
        self._tools["add"] = ctx.register_tool("add", add)
        self._tools["subtract"] = ctx.register_tool("subtract", subtract)
        self._tools["multiply"] = ctx.register_tool("multiply", multiply)
        self._tools["divide"] = ctx.register_tool("divide", divide)
        
        # 注册事件钩子
        async def on_tool_call(event):
            """工具调用前的钩子"""
            print(f"Tool called: {event.get('tool_name')}")
        
        self._hook_unregister = ctx.register_hook("tool.call", on_tool_call)
    
    async def deactivate(self) -> None:
        """停用插件，清理资源"""
        # 卸载工具（通过效果函数）
        for unregister in self._tools.values():
            try:
                unregister()
            except Exception as e:
                print(f"Error unregistering tool: {e}")
        
        self._tools.clear()


class LoggerPlugin(Plugin):
    """
    日志插件
    
    提供日志记录功能
    """
    
    name = "logger"
    version = "1.0.0"
    description = "Logging plugin"
    author = "KnowRAG Team"
    
    def __init__(self):
        super().__init__()
        self._log_buffer = []
    
    async def activate(self, ctx: PluginContext) -> None:
        """激活插件，注册钩子"""
        
        async def on_message(event):
            """记录消息事件"""
            self._log_buffer.append({
                "type": "message",
                "content": event.get("content"),
                "timestamp": event.get("timestamp")
            })
            print(f"[LOG] Message: {event.get('content')}")
        
        async def on_tool_call(event):
            """记录工具调用"""
            self._log_buffer.append({
                "type": "tool_call",
                "tool": event.get("tool_name"),
                "timestamp": event.get("timestamp")
            })
            print(f"[LOG] Tool: {event.get('tool_name')}")
        
        # 注册钩子
        ctx.register_hook("message.user", on_message)
        ctx.register_hook("tool.call", on_tool_call)
    
    async def deactivate(self) -> None:
        """停用插件，清空缓冲"""
        self._log_buffer.clear()
    
    def get_logs(self) -> list:
        """获取日志"""
        return self._log_buffer.copy()


__all__ = [
    "CalculatorPlugin",
    "LoggerPlugin",
]
