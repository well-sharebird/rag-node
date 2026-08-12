"""Agent 配置加载器 - 从文件加载主 Agent 配置"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class LoadedAgentConfig:
    """加载后的 Agent 配置"""
    # Agent 基本信息
    name: str = "main_agent"
    description: str = ""
    version: str = "1.0.0"

    # SOUL 层：人格与底线
    soul: str = ""
    # CLAUDE 层：任务规则与工作流
    claude: str = ""

    # 工具配置
    enabled_tools: List[str] = field(default_factory=list)

    # 沙箱策略
    sandbox_policy: Dict[str, Any] = field(default_factory=dict)

    # 内存策略
    memory_strategy: Dict[str, Any] = field(default_factory=dict)

    # 执行限制
    max_steps: int = 20
    token_budget: int = 8192
    max_output_tokens: int = 2048

    # 日志配置
    log_tool_calls: bool = True
    log_llm_calls: bool = False

    # 系统提示词（由 soul + claude 组合）
    @property
    def system_prompt(self) -> str:
        parts = []
        if self.soul:
            parts.append(self.soul)
        if self.claude:
            parts.append(self.claude)
        return "\n\n".join(parts)


class AgentConfigLoader:
    """Agent 配置加载器

    从 config/default_main_agent/ 目录加载配置：
    - soul.md: 人格与底线
    - claude.md: 任务规则与工作流
    - agent.yaml: 其他配置
    """

    def __init__(self, config_dir: Optional[str] = None):
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            # 默认路径
            self.config_dir = Path(__file__).parent / "default_main_agent"

    def load(self) -> LoadedAgentConfig:
        """加载主 Agent 配置

        Returns:
            LoadedAgentConfig 实例
        """
        config = LoadedAgentConfig()

        # 1. 加载 soul.md
        soul_file = self.config_dir / "soul.md"
        if soul_file.exists():
            config.soul = soul_file.read_text(encoding="utf-8")
            logger.info(f"已加载 soul.md: {len(config.soul)} 字符")
        else:
            logger.warning(f"soul.md 不存在：{soul_file}")

        # 2. 加载 claude.md
        claude_file = self.config_dir / "claude.md"
        if claude_file.exists():
            config.claude = claude_file.read_text(encoding="utf-8")
            logger.info(f"已加载 claude.md: {len(config.claude)} 字符")
        else:
            logger.warning(f"claude.md 不存在：{claude_file}")

        # 3. 加载 agent.yaml
        yaml_file = self.config_dir / "agent.yaml"
        if yaml_file.exists():
            try:
                import yaml
                yaml_config = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))

                # 解析配置
                config.name = yaml_config.get("name", config.name)
                config.description = yaml_config.get("description", config.description)
                config.version = yaml_config.get("version", config.version)

                # 工具配置
                tools_config = yaml_config.get("tools", {})
                config.enabled_tools = tools_config.get("enabled_tools", [])

                # 沙箱策略
                config.sandbox_policy = yaml_config.get("sandbox_policy", {})

                # 内存策略
                config.memory_strategy = yaml_config.get("memory_strategy", {})

                # 执行限制
                limits = yaml_config.get("limits", {})
                config.max_steps = limits.get("max_steps", config.max_steps)
                config.token_budget = limits.get("token_budget", config.token_budget)
                config.max_output_tokens = limits.get("max_output_tokens", config.max_output_tokens)

                # 日志配置
                logging_config = yaml_config.get("logging", {})
                config.log_tool_calls = logging_config.get("log_tool_calls", config.log_tool_calls)
                config.log_llm_calls = logging_config.get("log_llm_calls", config.log_llm_calls)

                logger.info(f"已加载 agent.yaml: {config.name} v{config.version}")
            except Exception as e:
                logger.error(f"加载 agent.yaml 失败：{e}")
        else:
            logger.warning(f"agent.yaml 不存在：{yaml_file}")

        return config

    @classmethod
    def load_system_prompt(cls, config_dir: Optional[str] = None) -> str:
        """直接加载系统提示词（soul + claude 组合）"""
        loader = cls(config_dir)
        config = loader.load()
        return config.system_prompt


# 全局单例
_default_loader: Optional[AgentConfigLoader] = None
_default_config: Optional[LoadedAgentConfig] = None


def get_default_agent_config() -> LoadedAgentConfig:
    """获取默认主 Agent 配置（全局单例）"""
    global _default_loader, _default_config
    if _default_config is None:
        _default_loader = AgentConfigLoader()
        _default_config = _default_loader.load()
    return _default_config


def get_system_prompt() -> str:
    """获取系统提示词（soul + claude 组合）"""
    return get_default_agent_config().system_prompt
