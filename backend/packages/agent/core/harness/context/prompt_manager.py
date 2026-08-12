"""分层提示词管理器 - SOUL/CLAUDE 架构（设计文档 2.1）

SOUL（人格/底线）+ CLAUDE（任务规则/工作流）
"""
from dataclasses import dataclass, field
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class PromptLayer:
    """提示词分层"""
    # SOUL 层：Agent 人格、底线、原则（不可变）
    soul: str = ""
    # CLAUDE 层：任务规则、工作流、约束（可变）
    claude: str = ""
    # 任务层：当前任务具体指令
    task: str = ""
    # 上下文层：历史对话摘要
    context_summary: str = ""

    def combine(self) -> str:
        """组合所有层为完整提示词"""
        parts = []
        if self.soul:
            parts.append(f"【人格与底线】\n{self.soul}")
        if self.claude:
            parts.append(f"【任务规则】\n{self.claude}")
        if self.task:
            parts.append(f"【当前任务】\n{self.task}")
        if self.context_summary:
            parts.append(f"【上下文摘要】\n{self.context_summary}")
        return "\n\n".join(parts)


class PromptManager:
    """分层提示词管理器

    职责：
    1. 管理 SOUL/CLAUDE 分层提示词
    2. 动态组装完整提示词
    3. 提示词模板变量替换
    """

    def __init__(
        self,
        soul: str = "",
        claude: str = "",
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None,
    ):
        self.soul = soul
        self.claude = claude
        self.agent_id = agent_id
        self.agent_name = agent_name
        self._task = ""
        self._context_summary = ""

    def set_task(self, task: str):
        """设置当前任务指令"""
        self._task = task

    def set_context_summary(self, summary: str):
        """设置上下文摘要"""
        self._context_summary = summary

    def build(self) -> PromptLayer:
        """构建分层提示词"""
        return PromptLayer(
            soul=self.soul,
            claude=self.claude,
            task=self._task,
            context_summary=self._context_summary,
        )

    def combine(self) -> str:
        """组合为完整提示词字符串"""
        return self.build().combine()

    @classmethod
    def from_config(cls, config: dict) -> "PromptManager":
        """从配置字典创建 PromptManager

        config 格式：
        {
            "soul": "...",
            "claude": "...",
            "agent_id": "...",
            "agent_name": "..."
        }
        """
        return cls(
            soul=config.get("soul", ""),
            claude=config.get("claude", ""),
            agent_id=config.get("agent_id"),
            agent_name=config.get("agent_name"),
        )
