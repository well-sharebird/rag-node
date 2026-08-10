"""
Harness 层 - 基础方案引擎

解决"怎么用"的问题 - 开箱即用的完整方案：
- 内置默认提示词
- 工具调用处理
- 规划工具
- 文件系统访问
- 多 Agent 协作模式
"""
from packages.agent.harness.engine import HarnessEngine
from packages.agent.harness.config import HarnessConfig

__all__ = [
    "HarnessEngine",
    "HarnessConfig",
]
