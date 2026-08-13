"""上下文压缩 - Harness 上下文工程（设计文档 2.1）

在有限上下文窗口下，当对话消息超出 Token 预算时压缩历史。
适配 langchain_core 的 BaseMessage，自带 Token 估算，原子、无状态编排、易单测。
供编排层 `_prepare_state` 在每次 `execute` 前触发。
"""
import logging
from typing import List, Optional

from langchain_core.messages import BaseMessage

logger = logging.getLogger(__name__)

def _estimate_fn(text: str) -> int:
    """估算文本 Token 数：中文按 ~2 字/token，英文按 ~4 字符/token。"""
    if not text:
        return 0
    chinese = sum(1 for c in text if '一' <= c <= '鿿')
    english = len(text) - chinese
    return (chinese // 2) + (english // 4)


class ContextCompressor:
    """基于 Token 预算的上下文压缩器。"""

    def __init__(
        self,
        max_tokens: Optional[int] = None,
        reserve_tokens: int = 512,
    ):
        self._max_tokens = max_tokens or 4096
        self._reserve_tokens = reserve_tokens or 0

    def estimate(self, messages: List[BaseMessage]) -> int:
        """估算消息列表的总 Token 数"""
        return sum(_estimate_fn(self._text(m)) for m in messages)

    def should_compress(self, messages: List[BaseMessage]) -> bool:
        """是否需要压缩（超预算阈值）"""
        budget = self._max_tokens - self._reserve_tokens
        if budget <= 0:
            return True
        return self.estimate(messages) > budget

    def compress(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """压缩超出的上下文，保留 system 消息与最近 N 条消息。

        压缩不可用（依赖缺失）时原样返回。
        """
        # 保护 system 消息（提示词/约束）
        system_msgs = [m for m in messages if getattr(m, "type", "") == "system"]
        non_system = [m for m in messages if getattr(m, "type", "") != "system"]

        # 循环压缩直到满足预算
        while self.estimate(non_system) > (self._max_tokens - self._reserve_tokens):
            if len(non_system) <= 2:
                break
            # 压缩最旧的非系统消息：截断其内容
            oldest = non_system[0]
            content = getattr(oldest, "content", "")
            if isinstance(content, str) and len(content) > 24:
                try:
                    oldest.content = content[:16] + "...[已压缩]"
                except Exception:
                    # BaseMessage 不可变时跳过该条
                    non_system.pop(0)
                    continue
            else:
                non_system.pop(0)

        return system_msgs + non_system

    @staticmethod
    def _text(message: BaseMessage) -> str:
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return " ".join(
                str(c.get("text", c)) if isinstance(c, dict) else str(c)
                for c in content
            )
        return str(content)
