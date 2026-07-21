"""
Stage 3.5 - Document Enrichment Service
NER 实体抽取、实体链接、关系抽取、自动标签、文档摘要
"""
from __future__ import annotations
import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

logger = logging.getLogger("app.services.enrichment")


@dataclass
class Entity:
    """Named entity extracted from text"""
    text: str
    entity_type: str  # PERSON, ORG, LOC, DATE, etc.
    start_idx: int
    end_idx: int
    confidence: float = 1.0
    linked_id: Optional[str] = None  # Linked knowledge graph ID
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Relation:
    """Relation between two entities"""
    subject: Entity
    predicate: str
    object: Entity
    confidence: float = 1.0


@dataclass
class EnrichmentResult:
    """Result of document enrichment"""
    original_text: str
    entities: List[Entity] = field(default_factory=list)
    relations: List[Relation] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    summary: str = ""
    language: str = "zh"
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseNERService(ABC):
    """Base class for Named Entity Recognition"""

    @abstractmethod
    async def extract_entities(self, text: str) -> List[Entity]:
        pass


class BaseTaggingService(ABC):
    """Base class for automatic tagging"""

    @abstractmethod
    async def generate_tags(self, text: str, entities: List[Entity]) -> List[str]:
        pass


class BaseSummarizationService(ABC):
    """Base class for document summarization"""

    @abstractmethod
    async def summarize(self, text: str, max_length: int = 200) -> str:
        pass


class SpacyNERService(BaseNERService):
    """
    NER using spaCy (good for English).
    For Chinese, use HanLP or LTP.
    """

    def __init__(self, model_name: str = "zh_core_web_sm"):
        self.model_name = model_name
        self._nlp = None

    def _load_model(self):
        if self._nlp is None:
            try:
                import spacy
                self._nlp = spacy.load(self.model_name)
            except ImportError:
                logger.warning("spaCy not installed, NER disabled")
                return None
            except OSError:
                logger.warning(f"spaCy model '{self.model_name}' not found")
                return None
        return self._nlp

    async def extract_entities(self, text: str) -> List[Entity]:
        nlp = self._load_model()
        if nlp is None:
            return []

        # Run NER
        doc = nlp(text[:10000])  # Limit length for performance

        entities = []
        for ent in doc.ents:
            entities.append(Entity(
                text=ent.text,
                entity_type=ent.label_,
                start_idx=ent.start_char,
                end_idx=ent.end_char,
                confidence=1.0,
            ))

        return entities


class HanLPNERService(BaseNERService):
    """
    NER using HanLP (excellent for Chinese).
    """

    def __init__(self):
        self._hanlp = None

    def _load_model(self):
        if self._hanlp is None:
            try:
                import hanlp
                # Load pretrained NER model
                self._hanlp = hanlp.load(hanlp.pretrained.ner.MSRA_NER_TAGGER_BIG_BERT)
            except ImportError:
                logger.warning("HanLP not installed, Chinese NER disabled")
                return None
            except Exception as e:
                logger.warning(f"HanLP failed to load: {e}")
                return None
        return self._hanlp

    async def extract_entities(self, text: str) -> List[Entity]:
        model = self._load_model()
        if model is None:
            return []

        try:
            # HanLP returns list of (text, label) tuples
            result = model(text[:10000])

            entities = []
            char_idx = 0
            for word, label in result:
                entities.append(Entity(
                    text=word,
                    entity_type=label,
                    start_idx=char_idx,
                    end_idx=char_idx + len(word),
                    confidence=1.0,
                ))
                char_idx += len(word)

            return entities
        except Exception as e:
            logger.warning(f"HanLP NER failed: {e}")
            return []


class LLMNERService(BaseNERService):
    """
    NER using LLM (most flexible, supports custom entity types).
    """

    def __init__(self, llm_service=None, custom_types: Optional[List[str]] = None):
        self.llm_service = llm_service
        self.custom_types = custom_types or ["产品", "技术", "项目", "文档"]

    async def extract_entities(self, text: str) -> List[Entity]:
        if self.llm_service is None:
            logger.warning("LLM service not available, cannot perform LLM-based NER")
            return []

        # Build prompt
        types_str = ", ".join(self.custom_types)
        prompt = f"""请从以下文本中提取命名实体，识别以下类型：PERSON, ORG, LOC, DATE, TIME, MONEY, PERCENT, {types_str}

文本：
{text[:2000]}

请以 JSON 格式返回，格式为：[{{"text": "...", "type": "...", "start": 0, "end": 10}}, ...]
只返回 JSON 数组，不要其他内容。"""

        try:
            import json
            import asyncio

            async def generate():
                return await self.llm_service.generate(prompt)

            result = await asyncio.get_event_loop().run_until_complete(generate())

            # Parse JSON response
            entities_data = json.loads(result.strip())
            entities = []
            for item in entities_data:
                entities.append(Entity(
                    text=item.get("text", ""),
                    entity_type=item.get("type", "UNKNOWN"),
                    start_idx=item.get("start", 0),
                    end_idx=item.get("end", 0),
                    confidence=item.get("confidence", 1.0),
                ))
            return entities

        except Exception as e:
            logger.warning(f"LLM NER failed: {e}")
            return []


class BERTopicTaggingService(BaseTaggingService):
    """
    Automatic tagging using BERTopic.
    Requires bertopic + sentence-transformers (optional dependency).
    """

    def __init__(self, language: str = "zh"):
        self.language = language
        self._model = None

    def _load_model(self):
        if self._model is None:
            try:
                from bertopic import BERTopic

                self._model = BERTopic(language=self.language)
            except ImportError:
                logger.warning("BERTopic not installed, auto-tagging disabled")
                return None
        return self._model

    async def generate_tags(self, text: str, entities: List[Entity]) -> List[str]:
        model = self._load_model()
        if model is None:
            return []

        try:
            # BERTopic needs multiple documents for training
            # For single document, use entity-based tagging
            if len(text) < 500:
                # Short text: use entity types as tags
                return list(set(e.entity_type for e in entities[:10]))

            # Fit and predict on single document (not ideal but works)
            topics, probs = model.fit_transform([text])

            # Get topic terms
            topic = topics[0]
            if topic == -1:
                return []

            # Get topic representation
            topic_terms = model.get_topic(topic)[:5]
            return [term for term, score in topic_terms if score > 0.3]

        except Exception as e:
            logger.warning(f"BERTopic tagging failed: {e}")
            return []


class LLMTaggingService(BaseTaggingService):
    """
    Automatic tagging using LLM.
    """

    def __init__(self, llm_service=None):
        self.llm_service = llm_service

    async def generate_tags(self, text: str, entities: List[Entity]) -> List[str]:
        if self.llm_service is None:
            # Fallback: use entity types
            return list(set(e.entity_type for e in entities[:10]))

        # Extract entity texts for context
        entity_texts = [e.text for e in entities[:10]]
        entity_context = ", ".join(entity_texts) if entity_texts else "无"

        prompt = f"""请为以下文档生成 5-10 个标签。
文档中提到的关键实体：{entity_context}

文档摘要（前 500 字）：
{text[:500]}

请返回逗号分隔的标签列表，如：技术，API，数据库，微服务
只返回标签，不要其他内容。"""

        try:
            import asyncio

            async def generate():
                return await self.llm_service.generate(prompt)

            result = await asyncio.get_event_loop().run_until_complete(generate())

            # Parse comma-separated tags
            tags = [t.strip() for t in result.split(",") if t.strip()]
            return tags[:10]

        except Exception as e:
            logger.warning(f"LLM tagging failed: {e}")
            return entity_texts if entity_texts else []


class LLMSummarizationService(BaseSummarizationService):
    """
    Document summarization using LLM.
    """

    def __init__(self, llm_service=None):
        self.llm_service = llm_service

    async def summarize(self, text: str, max_length: int = 200) -> str:
        if self.llm_service is None:
            # Fallback: return first paragraph
            paragraphs = text.split("\n\n")
            return paragraphs[0][:max_length] + "..." if paragraphs else ""

        prompt = f"""请用简洁的语言总结以下文档，控制在{max_length}字以内。

文档：
{text[:3000]}

总结："""

        try:
            import asyncio

            async def generate():
                return await self.llm_service.generate(prompt)

            result = await asyncio.get_event_loop().run_until_complete(generate())
            return result.strip()[:max_length]

        except Exception as e:
            logger.warning(f"LLM summarization failed: {e}")
            paragraphs = text.split("\n\n")
            return paragraphs[0][:max_length] + "..." if paragraphs else ""


class TextRankSummarizationService(BaseSummarizationService):
    """
    Extractive summarization using TextRank algorithm.
    Works without LLM.
    """

    def __init__(self):
        pass

    async def summarize(self, text: str, max_length: int = 200) -> str:
        try:
            # Simple extractive summarization
            sentences = re.split(r"[.!?。.！？]", text)
            sentences = [s.strip() for s in sentences if s.strip()]

            if len(sentences) <= 2:
                return text[:max_length]

            # Score sentences by word frequency
            word_freq: Dict[str, int] = {}
            for sent in sentences:
                words = sent.split()
                for word in words:
                    if len(word) > 1:  # Skip single characters
                        word_freq[word] = word_freq.get(word, 0) + 1

            # Normalize frequencies
            if word_freq:
                max_freq = max(word_freq.values())
                for word in word_freq:
                    word_freq[word] /= max_freq

            # Score sentences
            scored_sentences = []
            for sent in sentences:
                words = sent.split()
                score = sum(word_freq.get(w, 0) for w in words) / max(len(words), 1)
                scored_sentences.append((sent, score))

            # Get top sentences
            scored_sentences.sort(key=lambda x: x[1], reverse=True)
            summary_sentences = [s for s, _ in scored_sentences[:3]]

            summary = ". ".join(summary_sentences)
            if len(summary) > max_length:
                summary = summary[:max_length] + "..."

            return summary

        except Exception as e:
            logger.warning(f"TextRank summarization failed: {e}")
            return text[:max_length]


# Import re for TextRank
import re


class EntityLinker:
    """
    Link extracted entities to knowledge graph.
    """

    def __init__(self, kg_service=None):
        self.kg_service = kg_service

    async def link_entities(self, entities: List[Entity], context: str) -> List[Entity]:
        """
        Link entities to knowledge graph nodes.
        """
        if self.kg_service is None:
            # No KG available, return entities as-is
            return entities

        linked_entities = []
        for entity in entities:
            # Try to find matching node in KG
            linked_id = await self.kg_service.find_node(entity.text, entity.entity_type)
            if linked_id:
                entity.linked_id = linked_id
            linked_entities.append(entity)

        return linked_entities


class RelationExtractor:
    """
    Extract relations between entities.
    """

    def __init__(self, llm_service=None):
        self.llm_service = llm_service

    async def extract_relations(
        self,
        entities: List[Entity],
        text: str
    ) -> List[Relation]:
        """
        Extract relations between entities from text.
        """
        if self.llm_service is None or len(entities) < 2:
            return []

        # Build entity list for prompt
        entity_list = ", ".join(f"{e.text}({e.entity_type})" for e in entities[:20])

        prompt = f"""请识别以下文本中实体之间的关系。

实体列表：{entity_list}

文本：
{text[:2000]}

请返回 JSON 格式的关系列表：
[{{"subject": "实体 A", "predicate": "关系", "object": "实体 B"}}, ...]

只返回 JSON 数组。"""

        try:
            import json
            import asyncio

            async def generate():
                return await self.llm_service.generate(prompt)

            result = await asyncio.get_event_loop().run_until_complete(generate())
            relations_data = json.loads(result.strip())

            # Build entity lookup
            entity_map = {e.text: e for e in entities}

            relations = []
            for item in relations_data:
                subj_text = item.get("subject", "")
                obj_text = item.get("object", "")
                subj = entity_map.get(subj_text)
                obj = entity_map.get(obj_text)
                if subj and obj:
                    relations.append(Relation(
                        subject=subj,
                        predicate=item.get("predicate", "相关"),
                        object=obj,
                    ))

            return relations

        except Exception as e:
            logger.warning(f"Relation extraction failed: {e}")
            return []


# ============================================================
# Main Enrichment Service
# ============================================================

class DocumentEnrichmentService:
    """
    Main service for document enrichment.
    Combines NER, entity linking, relation extraction, tagging, and summarization.
    """

    def __init__(
        self,
        llm_service=None,
        kg_service=None,
        use_hanlp: bool = True,
        use_bertopic: bool = False,
    ):
        self.llm_service = llm_service
        self.kg_service = kg_service

        # Initialize NER service
        if use_hanlp:
            self.ner_service = HanLPNERService()
        else:
            self.ner_service = LLMNERService(llm_service)

        # Initialize tagging service
        if use_bertopic:
            self.tagging_service = BERTopicTaggingService()
        else:
            self.tagging_service = LLMTaggingService(llm_service)

        # Initialize summarization service
        if llm_service:
            self.summarization_service = LLMSummarizationService(llm_service)
        else:
            self.summarization_service = TextRankSummarizationService()

        # Initialize entity linker and relation extractor
        self.entity_linker = EntityLinker(kg_service)
        self.relation_extractor = RelationExtractor(llm_service)

    async def enrich(self, text: str) -> EnrichmentResult:
        """
        Perform full document enrichment.
        """
        result = EnrichmentResult(original_text=text)

        # 1. Extract entities
        result.entities = await self.ner_service.extract_entities(text)
        logger.info("Extracted %d entities", len(result.entities))

        # 2. Link entities to KG
        result.entities = await self.entity_linker.link_entities(
            result.entities, text
        )
        linked_count = sum(1 for e in result.entities if e.linked_id)
        logger.info("Linked %d entities to KG", linked_count)

        # 3. Generate tags
        result.tags = await self.tagging_service.generate_tags(
            text, result.entities
        )
        logger.info("Generated %d tags", len(result.tags))

        # 4. Extract relations
        result.relations = await self.relation_extractor.extract_relations(
            result.entities, text
        )
        logger.info("Extracted %d relations", len(result.relations))

        # 5. Generate summary
        result.summary = await self.summarization_service.summarize(text, 300)
        logger.info("Generated summary (%d chars)", len(result.summary))

        return result


# Global instance
_enrichment_service: Optional[DocumentEnrichmentService] = None


def get_document_enrichment_service(
    llm_service=None,
    kg_service=None,
    use_hanlp: bool = True,
    use_bertopic: bool = False,
) -> DocumentEnrichmentService:
    """Get or create document enrichment service"""
    global _enrichment_service
    if _enrichment_service is None:
        _enrichment_service = DocumentEnrichmentService(
            llm_service=llm_service,
            kg_service=kg_service,
            use_hanlp=use_hanlp,
            use_bertopic=use_bertopic,
        )
    return _enrichment_service


def reset_document_enrichment_service():
    """Reset the global service instance"""
    global _enrichment_service
    _enrichment_service = None
