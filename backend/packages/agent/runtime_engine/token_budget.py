"""
Token Budget Manager - Token 预算管理

在有限上下文窗口下实现：
1. 动态 Token 调度
2. 上下文压缩
3. 记忆分级存储
4. 预算告警

核心策略：
- 工作记忆（最近 N 轮对话）- 始终保留
- 短期记忆（会话摘要）- 按需压缩
- 长期记忆（向量检索）- 外部存储
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from pydantic import BaseModel, Field
from enum import Enum

logger = logging.getLogger(__name__)


class CompressionStrategy(str, Enum):
    """压缩策略"""
    NONE = "none"              # 不压缩
    TRUNCATE = "truncate"      # 截断最旧消息
    SUMMARIZE = "summarize"    # 摘要压缩
    SLIDING_WINDOW = "sliding_window"  # 滑动窗口


class TokenAlert(BaseModel):
    """Token 告警"""
    threshold_percent: float  # 触发阈值（百分比）
    action: str  # warn, compress, stop
    message: str


class TokenBudgetConfig(BaseModel):
    """Token 预算配置"""
    max_tokens: int = Field(default=4096, ge=1024, le=128000)
    warning_threshold: float = Field(default=0.8, ge=0.5, le=0.95)  # 80% 告警
    compression_strategy: CompressionStrategy = CompressionStrategy.SLIDING_WINDOW
    reserve_tokens: int = Field(default=512)  # 保留 Token 用于系统消息
    alerts: List[TokenAlert] = Field(default_factory=list)


class MessageEntry(BaseModel):
    """消息条目"""
    id: str
    role: str  # user, assistant, system, tool
    content: str
    token_count: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    is_compressed: bool = False
    summary: Optional[str] = None  # 压缩后的摘要


class TokenBudgetManager:
    """
    Token 预算管理器

    管理上下文窗口的 Token 使用，支持：
    1. 实时 Token 计数
    2. 预算告警
    3. 自动压缩
    4. 分级记忆
    """

    def __init__(self, config: Optional[TokenBudgetConfig] = None):
        self.config = config or TokenBudgetConfig()
        self.messages: List[MessageEntry] = []
        self.total_tokens_used = 0
        self.compression_count = 0

        # 默认告警
        if not self.config.alerts:
            self.config.alerts = [
                TokenAlert(threshold_percent=0.8, action="warn", message="Token usage at 80%"),
                TokenAlert(threshold_percent=0.9, action="compress", message="Token usage at 90%, compressing..."),
                TokenAlert(threshold_percent=0.95, action="stop", message="Token usage at 95%, stopping..."),
            ]

    def add_message(
        self,
        role: str,
        content: str,
        message_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        添加消息

        Returns:
            (success, warning_message)
        """
        # 估算 Token 数（简单按字符/4 计算）
        token_count = len(content) // 4

        # 检查是否需要压缩
        if self._would_exceed_budget(token_count):
            compressed = self._compress_if_needed()
            if not compressed:
                return False, "Token budget exhausted, cannot add message"

        # 添加消息
        entry = MessageEntry(
            id=message_id or f"msg_{len(self.messages)}",
            role=role,
            content=content,
            token_count=token_count,
        )
        self.messages.append(entry)
        self.total_tokens_used += token_count

        # 检查告警
        alert = self._check_alerts()
        return True, alert

    def add_message_with_tokens(
        self,
        role: str,
        content: str,
        token_count: int,
        message_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """添加消息（已知 Token 数）"""
        if self._would_exceed_budget(token_count):
            compressed = self._compress_if_needed()
            if not compressed:
                return False, "Token budget exhausted"

        entry = MessageEntry(
            id=message_id or f"msg_{len(self.messages)}",
            role=role,
            content=content,
            token_count=token_count,
        )
        self.messages.append(entry)
        self.total_tokens_used += token_count

        alert = self._check_alerts()
        return True, alert

    def get_context_messages(self) -> List[MessageEntry]:
        """获取当前上下文中的消息（用于发送给 LLM）"""
        # 返回所有未压缩的消息
        return self.messages

    def get_context_summary(self) -> Dict[str, Any]:
        """获取上下文摘要"""
        return {
            "total_messages": len(self.messages),
            "total_tokens": self.total_tokens_used,
            "available_tokens": self.config.max_tokens - self.total_tokens_used,
            "usage_percent": (self.total_tokens_used / self.config.max_tokens) * 100,
            "compression_count": self.compression_count,
        }

    def clear(self):
        """清空上下文"""
        self.messages = []
        self.total_tokens_used = 0
        self.compression_count = 0

    def _would_exceed_budget(self, new_tokens: int) -> bool:
        """检查添加新 Token 是否会超出预算"""
        return (self.total_tokens_used + new_tokens) > (self.config.max_tokens - self.config.reserve_tokens)

    def _check_alerts(self) -> Optional[str]:
        """检查是否触发告警"""
        usage_percent = self.total_tokens_used / self.config.max_tokens

        for alert in self.config.alerts:
            if usage_percent >= alert.threshold_percent:
                logger.warning(f"Token budget alert: {alert.message}")
                return alert.message

        return None

    def _compress_if_needed(self) -> bool:
        """
        压缩上下文

        Returns:
            是否成功压缩
        """
        strategy = self.config.compression_strategy

        if strategy == CompressionStrategy.NONE:
            return False

        if strategy == CompressionStrategy.TRUNCATE:
            return self._truncate_oldest()

        if strategy == CompressionStrategy.SUMMARIZE:
            return self._summarize_oldest()

        if strategy == CompressionStrategy.SLIDING_WINDOW:
            return self._sliding_window_compress()

        return False

    def _truncate_oldest(self) -> bool:
        """截断最旧的消息"""
        if len(self.messages) <= 2:  # 至少保留 2 条消息
            return False

        # 移除最旧的非系统消息
        for i, msg in enumerate(self.messages):
            if msg.role != "system":
                removed = self.messages.pop(i)
                self.total_tokens_used -= removed.token_count
                self.compression_count += 1
                logger.info(f"Truncated oldest message: {removed.id}")
                return True

        return False

    def _summarize_oldest(self) -> bool:
        """
        摘要压缩最旧的消息

        实际实现需要调用 LLM 生成摘要
        """
        if len(self.messages) <= 3:
            return False

        # 找到最早的可压缩消息
        for i, msg in enumerate(self.messages):
            if msg.role in ["user", "assistant"] and not msg.is_compressed:
                # 简化实现：直接截断内容
                # 实际应该调用 LLM 生成摘要
                original_tokens = msg.token_count
                msg.summary = msg.content[:100] + "..."
                msg.content = msg.summary
                msg.is_compressed = True
                msg.token_count = len(msg.content) // 4

                self.total_tokens_used -= (original_tokens - msg.token_count)
                self.compression_count += 1
                logger.info(f"Summarized message: {msg.id}")
                return True

        return False

    def _sliding_window_compress(self) -> bool:
        """
        滑动窗口压缩

        保留最近 N 轮对话，压缩更早的内容
        """
        # 保留最近 10 轮对话（20 条消息）
        keep_count = 20

        if len(self.messages) <= keep_count:
            return False

        # 计算需要移除的消息
        to_remove = self.messages[:-keep_count]
        removed_tokens = sum(m.token_count for m in to_remove)

        # 保留系统消息
        system_messages = [m for m in to_remove if m.role == "system"]
        actual_remove = [m for m in to_remove if m.role != "system"]

        for msg in actual_remove:
            self.messages.remove(msg)

        self.total_tokens_used -= removed_tokens
        self.compression_count += 1
        logger.info(f"Sliding window compression: removed {len(actual_remove)} messages")

        return True

    def estimate_tokens(self, text: str) -> int:
        """估算文本的 Token 数"""
        # 简单估算：英文按字符/4，中文按字符/1.5
        chinese_chars = sum(1 for c in text if '一' <= c <= '鿿')
        english_chars = len(text) - chinese_chars

        return (chinese_chars // 2) + (english_chars // 4)

    def get_available_tokens(self) -> int:
        """获取可用 Token 数"""
        return self.config.max_tokens - self.total_tokens_used - self.config.reserve_tokens

    def get_usage_percent(self) -> float:
        """获取使用百分比"""
        return (self.total_tokens_used / self.config.max_tokens) * 100
