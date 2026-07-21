"""
意图分类器服务
识别用户查询的意图，路由到不同的处理管道
"""
from __future__ import annotations
import logging
import re
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
from dataclasses import dataclass
import asyncio

logger = logging.getLogger("app.services.intent")


class QueryIntent(Enum):
    """查询意图类型"""
    SIMPLE_QA = "simple_qa"           # 简单问答（事实性）
    COMPLEX_ANALYSIS = "complex"       # 复杂分析（推理）
    KNOWLEDGE_RETRIEVAL = "retrieval"  # 知识检索（查文档）
    SQL_QUERY = "sql"                  # SQL 查询（查数据库）
    CHITCHAT = "chitchat"              # 闲聊
    CLARIFICATION = "clarification"    # 澄清问题
    UNKNOWN = "unknown"                # 未知


@dataclass
class IntentResult:
    """意图识别结果"""
    intent: QueryIntent
    confidence: float
    keywords: List[str]
    entities: Dict[str, str]
    suggested_action: Optional[str] = None


class RuleBasedIntentClassifier:
    """
    基于规则的意图分类器
    快速、无需模型，适合冷启动
    """

    def __init__(self):
        # 意图关键词模式
        self.intent_patterns = {
            QueryIntent.SIMPLE_QA: [
                r"什么是", r"是谁", r"什么时候", r"在哪里", r"为什么",
                r"how to", r"what is", r"who is", r"when", r"where", r"why",
                r"怎么", r"如何", r"多少", r"哪些",
            ],
            QueryIntent.COMPLEX_ANALYSIS: [
                r"分析", r"比较", r"对比", r"优缺点", r"利弊",
                r"影响", r"趋势", r"原因", r"关系",
                r"analyze", r"compare", r"pros and cons", r"impact",
            ],
            QueryIntent.KNOWLEDGE_RETRIEVAL: [
                r"文档", r"手册", r"指南", r"教程", r"政策",
                r"规定", r"制度", r"流程", r"规范",
                r"document", r"manual", r"guide", r"policy",
            ],
            QueryIntent.SQL_QUERY: [
                r"查询.*数据", r"统计.*数量", r"有多少", r"占比",
                r"select", r"count", r"sum", r"average",
            ],
            QueryIntent.CHITCHAT: [
                r"你好", r"您好", r"hello", r"hi",
                r"谢谢", r"再见", r"在吗", r"是谁",
                r"今天.*天气", r"心情",
            ],
        }

        # 实体提取模式
        self.entity_patterns = {
            "date": r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}月 \d{1,2}日 | 今天 | 明天 | 昨天)",
            "time": r"(\d{1,2}[:：]\d{2}|上午 | 下午 | 早上 | 晚上)",
            "person": r"([A-Z][a-z]+\s+[A-Z][a-z]+|[A-Z]\.?\s*[A-Z][a-z]+)",
            "organization": r"([A-Z][A-Za-z]*\s+(?:Inc|Ltd|Corp|Co)\.?|[A-Z]{2,})",
            "number": r"(\d+[,.]?%?|\d+ 个|\d+ 件|\d+ 次)",
        }

    def classify(self, query: str) -> IntentResult:
        """
        基于规则分类查询意图

        Args:
            query: 用户查询

        Returns:
            IntentResult
        """
        query_lower = query.lower()

        # 计算每个意图的匹配分数
        scores: Dict[QueryIntent, float] = {}

        for intent, patterns in self.intent_patterns.items():
            match_count = 0
            for pattern in patterns:
                if re.search(pattern, query, re.IGNORECASE):
                    match_count += 1
            scores[intent] = match_count / len(patterns) if patterns else 0

        # 获取最高分意图
        if not scores:
            return IntentResult(
                intent=QueryIntent.UNKNOWN,
                confidence=0.0,
                keywords=[],
                entities={},
            )

        best_intent = max(scores.keys(), key=lambda k: scores[k])
        best_score = scores[best_intent]

        # 提取关键词
        keywords = self._extract_keywords(query)

        # 提取实体
        entities = self._extract_entities(query)

        # 生成建议动作
        suggested_action = self._get_suggested_action(best_intent, best_score)

        return IntentResult(
            intent=best_intent,
            confidence=best_score,
            keywords=keywords,
            entities=entities,
            suggested_action=suggested_action,
        )

    def _extract_keywords(self, query: str) -> List[str]:
        """提取关键词"""
        # 简单实现：去除停用词
        stopwords = {
            "的", "了", "是", "在", "和", "与", "或", "就", "都", "而",
            "a", "an", "the", "is", "are", "was", "were", "be", "been",
        }

        # 中文分词（简单按字符）
        words = []
        current_word = ""
        for char in query:
            if char.isalnum() or '一' <= char <= '鿿':
                current_word += char
            else:
                if current_word and current_word.lower() not in stopwords:
                    words.append(current_word)
                current_word = ""
        if current_word and current_word.lower() not in stopwords:
            words.append(current_word)

        return words[:10]  # 限制关键词数量

    def _extract_entities(self, query: str) -> Dict[str, str]:
        """提取实体"""
        entities = {}
        for entity_type, pattern in self.entity_patterns.items():
            match = re.search(pattern, query)
            if match:
                entities[entity_type] = match.group(1)
        return entities

    def _get_suggested_action(self, intent: QueryIntent, confidence: float) -> Optional[str]:
        """根据意图生成建议动作"""
        if confidence < 0.3:
            return "clarify"  # 置信度低，建议澄清

        action_map = {
            QueryIntent.SIMPLE_QA: "retrieve_and_answer",
            QueryIntent.COMPLEX_ANALYSIS: "retrieve_and_analyze",
            QueryIntent.KNOWLEDGE_RETRIEVAL: "search_documents",
            QueryIntent.SQL_QUERY: "generate_sql",
            QueryIntent.CHITCHAT: "casual_response",
            QueryIntent.CLARIFICATION: "ask_followup",
        }

        return action_map.get(intent)


class LLMIntentClassifier:
    """
    基于 LLM 的意图分类器
    更准确，支持自定义意图
    """

    def __init__(self, llm_service=None):
        self.llm_service = llm_service
        self._prompt_template = """
请分析用户查询的意图，从以下选项中选择：
- simple_qa: 简单事实性问题
- complex: 需要推理分析的复杂问题
- retrieval: 查找文档/资料
- sql: 查询数据库
- chitchat: 闲聊
- clarification: 需要澄清的问题

用户查询：{query}

请只返回 JSON 格式：{{"intent": "...", "confidence": 0.9, "keywords": ["..."], "entities": {{}}}}
"""

    async def classify(self, query: str) -> IntentResult:
        """使用 LLM 分类意图"""
        if self.llm_service is None:
            # Fallback 到规则分类
            logger.debug("LLM service not available, using rule-based classifier")
            rule_classifier = RuleBasedIntentClassifier()
            return rule_classifier.classify(query)

        prompt = self._prompt_template.format(query=query)

        try:
            import json

            response = await asyncio.get_event_loop().run_until_complete(
                self.llm_service.generate(prompt, max_tokens=200)
            )

            # 解析 JSON
            result = json.loads(response.strip())

            intent = QueryIntent(result.get("intent", "unknown"))
            return IntentResult(
                intent=intent,
                confidence=result.get("confidence", 0.5),
                keywords=result.get("keywords", []),
                entities=result.get("entities", {}),
                suggested_action=None,
            )

        except Exception as e:
            logger.warning(f"LLM intent classification failed: {e}")
            rule_classifier = RuleBasedIntentClassifier()
            return rule_classifier.classify(query)


class HybridIntentClassifier:
    """
    混合意图分类器
    先用规则快速分类，低置信度时用 LLM 复核
    """

    def __init__(self, llm_service=None, rule_threshold: float = 0.5):
        self.rule_classifier = RuleBasedIntentClassifier()
        self.llm_classifier = LLMIntentClassifier(llm_service)
        self.rule_threshold = rule_threshold

    async def classify(self, query: str) -> IntentResult:
        """
        混合分类策略

        1. 先用规则分类（快速）
        2. 如果置信度低于阈值，用 LLM 复核
        3. 返回最终结果
        """
        # 规则分类
        rule_result = self.rule_classifier.classify(query)

        # 高置信度直接返回
        if rule_result.confidence >= self.rule_threshold:
            logger.debug("Rule-based classification confident: %s (%.2f)",
                        rule_result.intent.value, rule_result.confidence)
            return rule_result

        # 低置信度，用 LLM 复核
        logger.debug("Low confidence (%.2f), using LLM to verify", rule_result.confidence)
        llm_result = await self.llm_classifier.classify(query)

        # 优先使用 LLM 结果
        return llm_result


# Global instance
_intent_classifier: Optional[HybridIntentClassifier] = None


def get_intent_classifier(llm_service=None) -> HybridIntentClassifier:
    """Get or create intent classifier"""
    global _intent_classifier
    if _intent_classifier is None:
        _intent_classifier = HybridIntentClassifier(llm_service)
    return _intent_classifier


def reset_intent_classifier():
    """Reset the global classifier"""
    global _intent_classifier
    _intent_classifier = None
