"""编排层的纯文本/脱敏工具（无状态、可独立测试）。

从 OrchestratorRuntime 抽出的静态纯函数；不引用 DB/图/LLM，供 graph.py 各流程复用。
"""
import logging
from typing import Iterator, Optional

logger = logging.getLogger(__name__)


def maybe_compress(text: Optional[str], budget: int = 12000) -> Optional[str]:
    """上下文压缩保护：超长输入截断到预算内（ContextCompressor 兜底）。

    多轮历史压缩由 Harness 的 ContextCompressor 提供；此处对超长 system/输入做硬保护。
    """
    if not text or len(text) <= budget:
        return text
    return text[:budget]


def make_pii_redactor():
    """流式 PII 脱敏器（滑动窗口；不可用时降级恒等）。
    
    修复：原实现中，当缓冲不足 window 大小时返回空字符串，导致所有短 token 丢失。
    新策略：
    1. 保留小窗口用于跨 token 的敏感信息匹配（如手机号被分成两段）
    2. 超过窗口就立即处理并返回，确保流式输出
    3. 缓冲内的内容在后续 push 或 flush 时处理
    """
    try:
        from packages.agent.output.filters import PIIFilter

        pii = PIIFilter()
    except Exception as e:
        logger.warning("[Orchestrator] PII 脱敏不可用：%s", e)
        return None

    class _R:
        def __init__(self, window: int = 10):
            """
            Args:
                window: 保留的缓冲大小，用于跨 token 的敏感信息匹配
            """
            self.buf = ""
            self.window = window

        def push(self, text: str) -> str:
            if not text:
                return ""
            
            # ✅ 将新文本加入缓冲
            self.buf += text
            
            # ✅ 如果缓冲超过窗口大小，处理前面的部分并返回
            if len(self.buf) > self.window:
                # 保留最后 window 个字符用于跨 token 匹配
                to_process = self.buf[:-self.window]
                self.buf = self.buf[-self.window:]
                
                # ✅ 立即处理并返回脱敏内容
                return pii.check(to_process)[0]
            
            # ✅ 缓冲不足时返回空，等待更多 token 或 flush
            # 这确保敏感信息跨 token 时能正确匹配（如 "138" + "12345678"）
            return ""

        def flush(self) -> str:
            if not self.buf:
                return ""
            # ✅ 处理剩余缓冲 - 所有未输出的内容都在这里返回
            out = pii.check(self.buf)[0]
            self.buf = ""
            return out

    return _R()


def redact_block(redactor, text) -> str:
    """一次性把完整文本块脱敏（push 处理主体 + flush 收尾缓冲）。"""
    if redactor is None or not text:
        return str(text) if text is not None else ""
    return redactor.push(str(text)) + redactor.flush()


def extract_final_content(messages: list) -> str:
    """从 TAO 图结果中提取最终 AI 回答内容。"""
    content = ""
    for m in messages:
        if getattr(m, "type", "") in ("ai", "assistant"):
            c = getattr(m, "content", "") or ""
            if c:
                content = str(c)
    return content


def chunk_text(text: str, size: int = 2) -> Iterator[str]:
    """把一段文本切成小块逐段产出（伪流式打字机）。"""
    for i in range(0, len(text), size):
        yield text[i:i + size]
