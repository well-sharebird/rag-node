"""Prompt 组装器 - Harness 层上下文组装（设计文档 11.4）

职责：
1. 在 LangGraph 节点执行前，由 Harness 组装合法上下文
2. 注入系统提示词（SOUL + CLAUDE）
3. 上下文压缩、Token 预算控制
4. 节点只负责读取 State，不拼接 Prompt

这是 Harness 与 LangGraph 的集成边界：
- Harness：组装上下文、注入系统提示词、Token 控制
- LangGraph 节点：读取 State.messages，调用 LLM
"""
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class PromptAssembler:
    """Prompt 组装器

    将 Agent 配置、对话历史、任务指令组装为 LangChain 消息列表
    """

    def __init__(
        self,
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        reserve_tokens: int = 512,
    ):
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens
        self.reserve_tokens = reserve_tokens

    def assemble(
        self,
        messages: List[Any],
        system_prompt: Optional[str] = None,
    ) -> List[Any]:
        """组装完整的消息列表

        Args:
            messages: 当前对话消息列表（LangChain BaseMessage）
            system_prompt: 可选的系统提示词（覆盖构造函数中的值）

        Returns:
            组装后的消息列表（system 消息在最前）
        """
        from langchain_core.messages import SystemMessage

        # 使用传入的 system_prompt 或构造函数中的值
        prompt = system_prompt if system_prompt is not None else self.system_prompt

        result = []

        # 1. 注入系统提示词（如果存在且第一条消息不是 SystemMessage）
        if prompt:
            # 检查是否已有 system 消息
            has_system = any(
                getattr(m, "type", "") == "system" or m.__class__.__name__ == "SystemMessage"
                for m in messages
            )
            if not has_system:
                result.append(SystemMessage(content=prompt))

        # 2. 添加原有消息
        result.extend(messages)

        return result

    def assemble_with_budget(
        self,
        messages: List[Any],
        system_prompt: Optional[str] = None,
    ) -> List[Any]:
        """组装消息列表，带 Token 预算控制

        如果消息超出预算，自动裁剪旧消息。

        Args:
            messages: 当前对话消息列表
            system_prompt: 可选的系统提示词

        Returns:
            组装并裁剪后的消息列表
        """
        from langchain_core.messages import SystemMessage

        # 使用传入的 system_prompt 或构造函数中的值
        prompt = system_prompt if system_prompt is not None else self.system_prompt

        # 1. 估算当前 Token 数
        def estimate_tokens(msg: Any) -> int:
            content = getattr(msg, "content", "")
            if not content:
                return 0
            # 中文约 2 字/token，英文约 4 字符/token
            chinese = sum(1 for c in str(content) if '一' <= c <= '鿿')
            english = len(str(content)) - chinese
            return (chinese // 2) + (english // 4)

        total_tokens = sum(estimate_tokens(m) for m in messages)
        budget = self.max_tokens - self.reserve_tokens

        # 2. 如果需要裁剪
        if total_tokens > budget:
            logger.info(f"上下文超出预算：{total_tokens}/{budget}，开始裁剪")

            # 分离 system 消息（如果有）
            system_msgs = [
                m for m in messages
                if getattr(m, "type", "") == "system" or m.__class__.__name__ == "SystemMessage"
            ]
            non_system = [
                m for m in messages
                if getattr(m, "type", "") != "system" and m.__class__.__name__ != "SystemMessage"
            ]

            # 从后往前保留消息，直到达到预算
            result = []
            tokens = 0
            for msg in reversed(non_system):
                msg_tokens = estimate_tokens(msg)
                if tokens + msg_tokens > budget:
                    break
                result.insert(0, msg)
                tokens += msg_tokens

            # 加上 system 消息
            messages = system_msgs + result
            logger.info(f"裁剪后保留 {len(messages)} 条消息，{tokens} tokens")

        # 3. 注入系统提示词
        if prompt:
            has_system = any(
                getattr(m, "type", "") == "system" or m.__class__.__name__ == "SystemMessage"
                for m in messages
            )
            if not has_system:
                messages = [SystemMessage(content=prompt)] + messages

        return messages

    @classmethod
    def from_harness_config(
        cls,
        soul: str = "",
        claude: str = "",
        max_tokens: int = 4096,
        reserve_tokens: int = 512,
    ) -> "PromptAssembler":
        """从 Harness 配置创建组装器

        Args:
            soul: SOUL 层提示词（人格/底线）
            claude: CLAUDE 层提示词（任务规则/工作流）
            max_tokens: 最大 Token 预算
            reserve_tokens: 保留 Token（给输出预留）

        Returns:
            PromptAssembler 实例
        """
        # 组合 SOUL + CLAUDE 为系统提示词
        system_prompt = "\n\n".join(filter(None, [soul, claude]))
        return cls(
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            reserve_tokens=reserve_tokens,
        )
