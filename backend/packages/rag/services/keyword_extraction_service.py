"""
关键词自动提取服务

功能：
1. 从文档中自动提取关键词
2. 支持 TF-IDF、TextRank 等算法
3. 支持自定义词库和停用词
"""
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("app.services.keyword_extraction")


@dataclass
class KeywordResult:
    """关键词提取结果"""
    keyword: str
    score: float
    category: Optional[str] = None
    occurrences: int = 1


class KeywordExtractionService:
    """关键词提取服务"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._stopwords: set = self._load_stopwords()
        self._custom_dict: set = self._load_custom_dictionary()

    def _load_stopwords(self) -> set:
        """加载停用词表"""
        # 中文常用停用词
        stopwords = {
            "的", "了", "和", "是", "就", "都", "而", "及", "与", "着",
            "或", "一个", "没有", "我们", "你们", "他们", "它", "她",
            "他", "这", "那", "你", "我", "他", "是", "在", "有",
            "就", "不", "人", "都", "一", "一个", "上", "也", "很",
            "到", "说", "要", "去", "你", "会", "着", "没有", "看",
            "好", "自己", "这", "那", "因为", "所以", "但是", "如果",
            "虽然", "可是", "而且", "或者", "以及", "然而", "则",
            "之", "乎", "者", "也", "矣", "焉", "哉",
            # 英文停用词
            "the", "a", "an", "and", "or", "but", "in", "on", "at",
            "to", "for", "of", "with", "by", "from", "is", "are",
            "was", "were", "be", "been", "being", "have", "has", "had",
            "do", "does", "did", "will", "would", "could", "should",
            "this", "that", "these", "those", "it", "its",
        }
        return stopwords

    def _load_custom_dictionary(self) -> set:
        """加载自定义词典（可扩展）"""
        # 默认添加一些常见技术术语
        return {
            "人工智能", "机器学习", "深度学习", "神经网络",
            "自然语言处理", "计算机视觉", "知识图谱",
            "RAG", "向量数据库", "Embedding", "大语言模型",
        }

    def extract_keywords(
        self,
        text: str,
        top_k: int = 10,
        method: str = "tfidf",
        min_word_length: int = 2,
        max_word_length: int = 10,
    ) -> List[KeywordResult]:
        """
        提取关键词

        Args:
            text: 输入文本
            top_k: 返回的关键词数量
            method: 提取方法 ("tfidf", "textrank", "frequency")
            min_word_length: 最小词长
            max_word_length: 最大词长

        Returns:
            关键词列表
        """
        if not text or len(text.strip()) < 10:
            return []

        try:
            # 尝试使用 jieba 进行中文分词
            import jieba
            import jieba.analyse

            # 加载自定义词典
            for word in self._custom_dict:
                jieba.add_word(word)

            if method == "tfidf":
                keywords = jieba.analyse.extract_tags(
                    text,
                    topK=top_k,
                    withWeight=True,
                    allowPOS=('n', 'nz', 'vn', 'v', 'x')  # 名词、动词等
                )
            elif method == "textrank":
                keywords = jieba.analyse.textrank(
                    text,
                    topK=top_k,
                    withWeight=True,
                    allowPOS=('n', 'nz', 'vn', 'v', 'x')
                )
            else:
                # 简单的词频统计
                keywords = self._extract_by_frequency(text, top_k)

            return [
                KeywordResult(
                    keyword=word,
                    score=weight,
                    occurrences=1,  # TODO: 统计实际出现次数
                )
                for word, weight in keywords
                if min_word_length <= len(word) <= max_word_length
                and word not in self._stopwords
            ]

        except ImportError:
            # jieba 未安装，回退到简单方法
            logger.warning("jieba not installed, using simple keyword extraction")
            return self._extract_by_frequency(text, top_k)

    def _extract_by_frequency(self, text: str, top_k: int) -> List[tuple]:
        """简单的词频统计方法"""
        import re
        from collections import Counter

        # 中文分词（简单按标点和空格分割）
        words = re.split(r'[,\s.!?;:，。！？；：、\n\r\t]+', text)

        # 过滤停用词和短词
        filtered_words = [
            w for w in words
            if len(w) >= 2
            and w not in self._stopwords
            and not re.match(r'^[^一-龥a-zA-Z]+$', w)
        ]

        # 统计词频
        counter = Counter(filtered_words)
        most_common = counter.most_common(top_k)

        # 归一化权重
        if most_common:
            max_count = most_common[0][1]
            return [(word, count / max_count) for word, count in most_common]
        return []

    def add_custom_word(self, word: str):
        """添加自定义词语到词典"""
        self._custom_dict.add(word)
        logger.info(f"Added custom word: {word}")

    def add_stopword(self, word: str):
        """添加停用词"""
        self._stopwords.add(word)

    def batch_extract(
        self,
        texts: List[str],
        top_k: int = 5,
    ) -> Dict[int, List[KeywordResult]]:
        """
        批量提取关键词

        Args:
            texts: 文本列表
            top_k: 每个文本的关键词数量

        Returns:
            {索引：关键词列表}
        """
        results = {}
        for i, text in enumerate(texts):
            results[i] = self.extract_keywords(text, top_k=top_k)
        return results


# ============================================================
# 服务创建工厂
# ============================================================

_keyword_service: Optional[KeywordExtractionService] = None


def get_keyword_service() -> KeywordExtractionService:
    """获取关键词提取服务单例"""
    global _keyword_service
    if _keyword_service is None:
        _keyword_service = KeywordExtractionService()
    return _keyword_service
