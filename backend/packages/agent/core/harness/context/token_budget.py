"""Token 预算管理器 - 上下文窗口控制（设计文档 2.1）

职责：
1. Token 预算计算
2. 限流、防溢出
3. 智能裁剪策略
"""
from dataclasses import dataclass
from typing import Any, List, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class TokenBudget:
    """Token 预算配置"""
    # 总预算
    max_tokens: int = 4096
    # 保留预算（给 LLM 输出预留）
    reserve_tokens: int = 512
    # 可用预算 = max_tokens - reserve_tokens
    @property
    def available(self) -> int:
        return self.max_tokens - self.reserve_tokens


class TokenBudgetManager:
    """Token 预算管理器

    职责：
    1. 估算消息 Token 数
    2. 检查是否超预算
    3. 智能裁剪超预算的消息
    """

    def __init__(
        self,
        max_tokens: int = 4096,
        reserve_tokens: int = 512,
    ):
        self.budget = TokenBudget(max_tokens=max_tokens, reserve_tokens=reserve_tokens)

    def estimate(self, text: str) -> int:
        """估算文本 Token 数

        简化估算：中文约 2 字/token，英文约 4 字符/token
        """
        if not text:
            return 0
        chinese = sum(1 for c in text if '一' <= c <= '鿿')
        english = len(text) - chinese
        return (chinese // 2) + (english // 4)

    def estimate_messages(self, messages: List[dict]) -> int:
        """估算消息列表的总 Token 数"""
        return sum(self.estimate(msg.get("content", "")) for msg in messages)

    def should_trim(self, messages: List[dict]) -> bool:
        """是否需要裁剪"""
        return self.estimate_messages(messages) > self.budget.available

    def trim(
        self,
        messages: List[dict],
        preserve_system: bool = True,
        min_user_messages: int = 1,
    ) -> List[dict]:
        """裁剪消息列表以适应 Token 预算

        策略：
        1. 保留 system 消息（如果 preserve_system=True）
        2. 优先保留最近的消息
        3. 至少保留 min_user_messages 条用户消息

        Args:
            messages: 消息列表
            preserve_system: 是否保留 system 消息
            min_user_messages: 最少保留的用户消息数

        Returns:
            裁剪后的消息列表
        """
        if not messages:
            return []

        # 分离 system 消息
        system_msgs = [m for m in messages if m.get("role") == "system"] if preserve_system else []
        non_system = [m for m in messages if m.get("role") != "system"]

        # 从后往前保留消息，直到达到预算
        result = []
        user_count = 0
        tokens = 0

        for msg in reversed(non_system):
            msg_tokens = self.estimate(msg.get("content", ""))
            if tokens + msg_tokens > self.budget.available:
                # 超预算，停止
                break
            result.insert(0, msg)
            tokens += msg_tokens
            if msg.get("role") == "user":
                user_count += 1

        # 确保至少保留 min_user_messages 条用户消息
        if user_count < min_user_messages:
            # 尝试从被丢弃的消息中找回用户消息
            discarded = [m for m in non_system if m not in result]
            for msg in discarded:
                if msg.get("role") == "user" and user_count < min_user_messages:
                    result.insert(0, msg)
                    user_count += 1

        # 加上 system 消息
        return system_msgs + result

    def trim_to_fit(
        self,
        messages: List[dict],
        compression_ratio: float = 0.8,
    ) -> List[dict]:
        """裁剪消息到预算内，带压缩缓冲

        Args:
            messages: 消息列表
            compression_ratio: 压缩目标比例（默认 80%，留 20% 缓冲）

        Returns:
            裁剪后的消息列表
        """
        target = int(self.budget.available * compression_ratio)

        if not messages:
            return []

        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        result = []
        tokens = 0

        for msg in reversed(non_system):
            msg_tokens = self.estimate(msg.get("content", ""))
            if tokens + msg_tokens > target:
                break
            result.insert(0, msg)
            tokens += msg_tokens

        # 如果裁剪后为空，至少保留最后一条消息
        if not result and non_system:
            result = [non_system[-1]]

        return system_msgs + result

    def check_overflow(self, messages: List[dict]) -> Optional[str]:
        """检查是否溢出

        Returns:
            溢出错误信息，无溢出返回 None
        """
        total = self.estimate_messages(messages)
        if total > self.budget.max_tokens:
            return f"上下文超出 Token 预算：{total}/{self.budget.max_tokens}"
        return None
