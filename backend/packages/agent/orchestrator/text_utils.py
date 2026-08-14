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
    """流式 PII 脱敏器（滑动窗口；不可用时降级恒等）。"""
    try:
        from packages.agent.output.filters import PIIFilter

        pii = PIIFilter()
    except Exception as e:
        logger.warning("[Orchestrator] PII 脱敏不可用: %s", e)
        return None

    class _R:
        def __init__(self, window: int = 40):
            self.buf = ""
            self.window = window

        def push(self, text: str) -> str:
            if not text:
                return ""
            self.buf += text
            if len(self.buf) > self.window:
                safe, self.buf = self.buf[:-self.window], self.buf[-self.window:]
                return pii.check(safe)[0]
            return ""

        def flush(self) -> str:
            if not self.buf:
                return ""
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
