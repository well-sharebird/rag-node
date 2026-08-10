"""内容过滤器"""
import re
from typing import Callable


class ContentFilter:
    """内容过滤器基类"""
    name: str = "base"

    def check(self, text: str) -> tuple[str, list[str]]:
        """返回 (过滤后文本，被过滤的内容列表)"""
        raise NotImplementedError


class SensitiveWordFilter(ContentFilter):
    """敏感词过滤"""
    name = "sensitive_word"

    def __init__(self, words: list[str] = None):
        self.words = words or []
        self._pattern = re.compile(
            "|".join(re.escape(w) for w in self.words),
            re.IGNORECASE
        ) if self.words else None

    def check(self, text: str) -> tuple[str, list[str]]:
        if not self._pattern:
            return text, []
        filtered = []

        def replace(match):
            word = match.group()
            filtered.append(word)
            return "*" * len(word)

        return self._pattern.sub(replace, text), filtered


class PIIFilter(ContentFilter):
    """个人隐私信息过滤"""
    name = "pii"

    PATTERNS = {
        "phone": re.compile(r"1[3-9]\d{9}"),
        "email": re.compile(r"[\w.-]+@[\w.-]+\.\w+"),
        "id_card": re.compile(r"\d{17}[\dXx]"),
    }

    def check(self, text: str) -> tuple[str, list[str]]:
        filtered = []
        for name, pattern in self.PATTERNS.items():
            def replace(match, n=name):
                filtered.append(f"{n}: {match.group()}")
                return f"[{n}_REDACTED]"
            text = pattern.sub(replace, text)
        return text, filtered


# 过滤器注册表
_FILTERS: list[ContentFilter] = []


def register_filter(f: ContentFilter):
    _FILTERS.append(f)


def get_filters() -> list[ContentFilter]:
    return list(_FILTERS)


# 默认注册
register_filter(PIIFilter())
