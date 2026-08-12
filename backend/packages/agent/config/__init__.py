"""Agent 配置加载器 - 主 Agent 静态配置（设计文档 8）

从 config/default_main_agent/ 加载主 Agent 配置：
- soul.md: 人格与底线
- claude.md: 任务规则与工作流
- agent.yaml: 工具、沙箱、内存策略
"""
from packages.agent.config.agent_config_loader import AgentConfigLoader, LoadedAgentConfig, get_default_agent_config, get_system_prompt

__all__ = [
    "AgentConfigLoader",
    "LoadedAgentConfig",
    "get_default_agent_config",
    "get_system_prompt",
]
