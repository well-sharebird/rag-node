"""
智能标签生成服务

功能：
1. 关键词提取（TF-IDF/TextRank）
2. LLM 语义标签生成
3. 分类体系标签（基于预定义分类树）
4. 实体识别（NER）

标签类型：
- extracted: 提取式标签（关键词）
- semantic: 语义标签（LLM 生成）
- category: 分类标签（分类树）
- entity: 实体标签（NER 识别）
"""
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("app.services.tag_generation")


class TagType(str, Enum):
    """标签类型枚举"""
    EXTRACTED = "extracted"    # 提取式（关键词）
    SEMANTIC = "semantic"      # 语义标签（LLM）
    CATEGORY = "category"      # 分类标签
    ENTITY = "entity"          # 实体标签


@dataclass
class Tag:
    """标签数据结构"""
    name: str                    # 标签名称
    tag_type: TagType            # 标签类型
    score: float = 1.0           # 置信度/权重
    source: str = ""             # 来源（如 "jieba_tfidf", "llm_qwen", "ner_spacy"）
    metadata: Dict[str, Any] = field(default_factory=dict)  # 额外元数据


class TagGenerationService:
    """智能标签生成服务"""

    def __init__(self, llm_service=None):
        self.llm_service = llm_service
        self._stopwords = self._load_stopwords()
        self._custom_dict = self._load_custom_dictionary()
        # 预定义分类体系
        self._category_tree = self._load_category_tree()
        # 实体类型映射
        self._entity_type_map = {
            "PERSON": "人名",
            "ORG": "机构",
            "GPE": "地名",
            "TIME": "时间",
            "DATE": "日期",
            "MONEY": "金额",
            "PERCENT": "百分比",
            "PRODUCT": "产品",
            "TECH": "技术",
        }

    def _load_stopwords(self) -> set:
        """加载停用词表"""
        return {
            "的", "了", "和", "是", "就", "都", "而", "及", "与", "着",
            "或", "一个", "没有", "我们", "你们", "他们", "它", "她",
            "他", "这", "那", "你", "我", "在", "有", "不", "人",
            "上", "也", "很", "到", "说", "要", "去", "会", "好", "自己",
            "the", "a", "an", "and", "or", "but", "in", "on", "at",
            "to", "for", "of", "with", "by", "from", "is", "are",
        }

    def _load_custom_dictionary(self) -> set:
        """加载自定义词典"""
        return {
            "人工智能", "机器学习", "深度学习", "神经网络",
            "自然语言处理", "计算机视觉", "知识图谱",
            "RAG", "向量数据库", "Embedding", "大语言模型",
        }

    def _load_category_tree(self) -> Dict[str, Any]:
        """加载分类体系树"""
        return {
            "技术": {
                "AI": ["机器学习", "深度学习", "NLP", "计算机视觉"],
                "大数据": ["数据处理", "数据存储", "数据分析"],
                "云计算": ["容器化", "微服务", "DevOps"],
            },
            "产品": {
                "软件": ["SaaS", "PaaS", "IaaS"],
                "硬件": ["服务器", "网络设备", "存储设备"],
            },
            "文档": {
                "手册": ["用户手册", "部署手册", "API 文档"],
                "报告": ["技术报告", "市场报告", "分析报告"],
            },
        }

    async def generate_tags(
        self,
        text: str,
        doc_name: str = "",
        category: str = "",
        top_k: int = 10,
        enable_all_types: bool = True,
        enabled_types: Optional[List[TagType]] = None,
    ) -> List[Tag]:
        """
        生成智能标签

        Args:
            text: 文档内容
            doc_name: 文档名称
            category: 文档分类
            top_k: 返回的标签数量
            enable_all_types: 是否启用所有标签类型
            enabled_types: 指定启用的标签类型

        Returns:
            标签列表
        """
        if not text or len(text.strip()) < 50:
            return []

        # 确定启用的标签类型
        if enable_all_types:
            types_to_generate = list(TagType)
        else:
            types_to_generate = enabled_types or [TagType.EXTRACTED]

        all_tags = []

        # 1. 关键词提取
        if TagType.EXTRACTED in types_to_generate:
            extracted = self._extract_keywords(text, top_k // 2)
            all_tags.extend(extracted)

        # 2. LLM 语义标签
        if TagType.SEMANTIC in types_to_generate and self.llm_service:
            semantic = await self._generate_llm_tags(text, top_k // 3)
            all_tags.extend(semantic)

        # 3. 分类标签
        if TagType.CATEGORY in types_to_generate:
            category_tags = self._classify_text(text, category)
            all_tags.extend(category_tags)

        # 4. 实体识别
        if TagType.ENTITY in types_to_generate:
            entities = self._extract_entities(text)
            all_tags.extend(entities)

        # 去重和排序
        unique_tags = self._deduplicate_tags(all_tags)
        sorted_tags = sorted(unique_tags, key=lambda t: t.score, reverse=True)

        return sorted_tags[:top_k]

    def _extract_keywords(self, text: str, top_k: int = 5) -> List[Tag]:
        """提取关键词（TF-IDF/TextRank）"""
        try:
            import jieba
            import jieba.analyse

            # 加载自定义词典
            for word in self._custom_dict:
                jieba.add_word(word)

            # TF-IDF 提取
            keywords = jieba.analyse.extract_tags(
                text,
                topK=top_k,
                withWeight=True,
                allowPOS=('n', 'nz', 'vn', 'v', 'x')
            )

            return [
                Tag(
                    name=word,
                    tag_type=TagType.EXTRACTED,
                    score=weight,
                    source="jieba_tfidf",
                )
                for word, weight in keywords
                if len(word) >= 2 and word not in self._stopwords
            ]

        except ImportError:
            logger.warning("jieba not installed, skipping keyword extraction")
            return []

    async def _generate_llm_tags(self, text: str, top_k: int = 3) -> List[Tag]:
        """使用 LLM 生成语义标签"""
        if not self.llm_service:
            return []

        prompt = f"""请分析以下文本，提取 3-5 个最能代表文档主题的关键词或短语标签。
要求：
- 标签简洁（2-6 个字）
- 能准确反映文档核心主题
- 适合用于文档检索和分类

文本内容（前 2000 字）：
{text[:2000]}

请只返回标签列表，用逗号分隔，不要其他解释。
示例格式：机器学习，向量检索，文档处理"""

        try:
            result = await self.llm_service.generate(prompt)
            tags_text = result.strip()

            # 解析标签
            tag_names = [t.strip() for t in tags_text.split(',') if t.strip()]

            return [
                Tag(
                    name=name,
                    tag_type=TagType.SEMANTIC,
                    score=0.9,  # LLM 生成的标签置信度较高
                    source="llm_semantic",
                )
                for name in tag_names[:top_k]
            ]

        except Exception as e:
            logger.warning("LLM tag generation failed: %s", e)
            return []

    def _classify_text(self, text: str, existing_category: str = "") -> List[Tag]:
        """基于分类体系生成分类标签"""
        tags = []

        # 如果已有分类，添加到标签
        if existing_category:
            tags.append(Tag(
                name=existing_category,
                tag_type=TagType.CATEGORY,
                score=1.0,
                source="existing",
            ))

            # 添加父分类
            parts = existing_category.split('/')
            for i in range(1, len(parts)):
                parent = '/'.join(parts[:i+1])
                tags.append(Tag(
                    name=parent,
                    tag_type=TagType.CATEGORY,
                    score=0.8,
                    source="parent_category",
                ))

        # 基于内容匹配分类树
        text_lower = text[:1000].lower()
        for main_cat, sub_cats in self._category_tree.items():
            if main_cat in text_lower:
                tags.append(Tag(
                    name=main_cat,
                    tag_type=TagType.CATEGORY,
                    score=0.7,
                    source="content_match",
                ))
            for sub_cat, leafs in sub_cats.items():
                if sub_cat in text_lower:
                    tags.append(Tag(
                        name=f"{main_cat}/{sub_cat}",
                        tag_type=TagType.CATEGORY,
                        score=0.75,
                        source="content_match",
                    ))

        return tags

    def _extract_entities(self, text: str) -> List[Tag]:
        """实体识别（NER）"""
        try:
            # 尝试使用 spaCy 或 HanLP 进行 NER
            import spacy
            # 中文模型：zh_core_web_sm
            nlp = spacy.load("zh_core_web_sm")
            doc = nlp(text[:5000])  # 限制长度

            tags = []
            for ent in doc.ents:
                ent_type = self._entity_type_map.get(ent.label_, ent.label_)
                tags.append(Tag(
                    name=ent.text,
                    tag_type=TagType.ENTITY,
                    score=0.85,
                    source=f"spacy_{ent.label_}",
                    metadata={"entity_type": ent_type},
                ))

            return tags[:10]  # 限制实体数量

        except ImportError:
            logger.debug("spaCy not installed, skipping NER")
            return []
        except Exception as e:
            logger.warning("NER failed: %s", e)
            return []

    def _deduplicate_tags(self, tags: List[Tag]) -> List[Tag]:
        """去重标签（保留最高分）"""
        tag_dict = {}
        for tag in tags:
            key = f"{tag.name}:{tag.tag_type}"
            if key not in tag_dict or tag.score > tag_dict[key].score:
                tag_dict[key] = tag
        return list(tag_dict.values())


# ============================================================
# 服务创建工厂
# ============================================================

_tag_service: Optional[TagGenerationService] = None


def get_tag_generation_service(llm_service=None) -> TagGenerationService:
    """获取标签生成服务单例"""
    global _tag_service
    if _tag_service is None:
        _tag_service = TagGenerationService(llm_service)
    return _tag_service
