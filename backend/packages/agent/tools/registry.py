"""统一工具注册表"""
from typing import Callable, Any
from langchain_core.tools import BaseTool
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class ToolRegistry:
    """统一工具注册表"""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._categories: dict[str, list[str]] = defaultdict(list)
        self._error_handlers: dict[str, Callable] = {}

    def register(self, tool: BaseTool, category: str = "default"):
        """注册工具"""
        name = tool.name
        if name in self._tools:
            logger.warning(f"Tool '{name}' already registered, overwriting")
        self._tools[name] = tool
        self._categories[category].append(name)
        logger.info(f"Tool registered: {name} [{category}]")

    def register_many(self, tools: list[BaseTool], category: str = "default"):
        """批量注册"""
        for tool in tools:
            self.register(tool, category)

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def get_all(self) -> list[BaseTool]:
        return list(self._tools.values())

    def get_by_category(self, category: str) -> list[BaseTool]:
        names = self._categories.get(category, [])
        return [self._tools[n] for n in names if n in self._tools]

    def unregister(self, name: str):
        """卸载工具"""
        if name in self._tools:
            del self._tools[name]
            for cat, names in self._categories.items():
                if name in names:
                    names.remove(name)

    def register_error_handler(self, tool_name: str, handler: Callable):
        """为特定工具注册错误处理器"""
        self._error_handlers[tool_name] = handler

    async def safe_invoke(self, tool: BaseTool, input: dict) -> str:
        """安全调用工具 — 带错误降级（async 工具走 ainvoke，同步工具兜底 invoke）"""
        try:
            if hasattr(tool, "ainvoke"):
                return await tool.ainvoke(input)
            return tool.invoke(input)
        except Exception as e:
            logger.error(f"Tool '{tool.name}' failed: {e}")

            # 1. 尝试特定错误处理器
            handler = self._error_handlers.get(tool.name)
            if handler:
                try:
                    res = handler(e, input)
                    if hasattr(res, "__await__"):
                        res = await res
                    return res
                except Exception:
                    pass

            # 2. 降级：返回错误信息给 LLM
            return (
                f"[工具执行失败] {tool.name}: {e}\n"
                f"请尝试换一种方式，或使用其他工具。"
            )


# 全局单例
_registry = ToolRegistry()


def get_tool_registry() -> ToolRegistry:
    return _registry


def tool_registry_init():
    """初始化：注册所有内置工具"""
    from packages.agent.tools.builtins import get_builtin_tools
    # 注意：skills 和 mcp 工具在运行时动态加载
    _registry.register_many(get_builtin_tools(), category="builtin")
