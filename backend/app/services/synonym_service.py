"""
同义词映射与关键词扩展服务

功能：
1. 同义词/缩写映射（如 apple→苹果、AI→人工智能）
2. 检索时关键词扩展
3. 支持自定义词库
"""
import json
import logging
from typing import Dict, List, Set, Optional
from dataclasses import dataclass, field
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("app.services.synonym")


@dataclass
class SynonymEntry:
    """同义词条目"""
    id: Optional[int] = None
    standard_term: str = ""  # 标准词（如"苹果"）
    synonyms: List[str] = field(default_factory=list)  # 同义词列表（如["apple", "苹果手机"]）
    category: str = ""  # 分类（如"品牌"、"技术术语"）
    kb_id: Optional[str] = None  # 所属知识库 ID（None 表示全局）
    is_enabled: bool = True


class SynonymService:
    """同义词服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._cache: Dict[str, SynonymEntry] = {}
        self._synonym_map: Dict[str, str] = {}  # 同义词→标准词

    async def load_synonyms(self, kb_id: Optional[str] = None) -> Dict[str, str]:
        """
        加载同义词映射

        Args:
            kb_id: 知识库 ID，None 表示加载全局同义词

        Returns:
            同义词→标准词 的映射字典
        """
        from app.models.synonym import Synonym

        stmt = select(Synonym).where(Synonym.is_enabled == True)
        if kb_id:
            stmt = stmt.where(
                (Synonym.kb_id == kb_id) | (Synonym.kb_id.is_(None))
            )

        result = await self.db.execute(stmt)
        entries = result.scalars().all()

        synonym_map = {}
        for entry in entries:
            # 标准词本身也映射到自己
            synonym_map[entry.standard_term] = entry.standard_term
            # 所有同义词映射到标准词
            for synonym in entry.synonyms_list:
                synonym_map[synonym.lower()] = entry.standard_term

        self._synonym_map = synonym_map
        return synonym_map

    async def expand_query(self, query: str, kb_id: Optional[str] = None) -> List[str]:
        """
        扩展查询关键词

        Args:
            query: 原始查询词
            kb_id: 知识库 ID

        Returns:
            扩展后的关键词列表（包含原词和同义词）
        """
        # 确保加载了同义词
        if not self._synonym_map:
            await self.load_synonyms(kb_id)

        # 查找该词是否是某个标准词的同义词
        standard_term = self._synonym_map.get(query.lower(), query)

        # 找到所有映射到这个标准词的词
        expanded = {standard_term}
        for synonym, std in self._synonym_map.items():
            if std == standard_term:
                expanded.add(synonym)

        # 也包含原始查询
        expanded.add(query)

        return list(expanded)

    async def add_synonym(
        self,
        standard_term: str,
        synonyms: List[str],
        category: str = "",
        kb_id: Optional[str] = None,
    ) -> SynonymEntry:
        """添加同义词条目"""
        from app.models.synonym import Synonym

        entry = Synonym(
            standard_term=standard_term,
            synonyms_json=json.dumps(synonyms, ensure_ascii=False),
            category=category,
            kb_id=kb_id,
            is_enabled=True,
        )
        self.db.add(entry)
        await self.db.commit()
        await self.db.refresh(entry)

        # 更新缓存
        await self.load_synonyms(kb_id)

        return SynonymEntry(
            id=entry.id,
            standard_term=entry.standard_term,
            synonyms=synonyms,
            category=entry.category,
            kb_id=entry.kb_id,
            is_enabled=entry.is_enabled,
        )

    async def remove_synonym(self, synonym_id: int) -> bool:
        """删除同义词条目"""
        from app.models.synonym import Synonym
        from sqlalchemy import delete

        await self.db.execute(
            delete(Synonym).where(Synonym.id == synonym_id)
        )
        await self.db.commit()

        # 重新加载缓存
        self._synonym_map.clear()
        await self.load_synonyms()

        return True

    async def list_synonyms(
        self,
        kb_id: Optional[str] = None,
        category: Optional[str] = None,
    ) -> List[SynonymEntry]:
        """列出同义词条目"""
        from app.models.synonym import Synonym

        stmt = select(Synonym).where(Synonym.is_enabled == True)
        if kb_id:
            stmt = stmt.where(
                (Synonym.kb_id == kb_id) | (Synonym.kb_id.is_(None))
            )
        if category:
            stmt = stmt.where(Synonym.category == category)

        result = await self.db.execute(stmt)
        entries = result.scalars().all()

        return [
            SynonymEntry(
                id=e.id,
                standard_term=e.standard_term,
                synonyms=e.synonyms_list,
                category=e.category,
                kb_id=e.kb_id,
                is_enabled=e.is_enabled,
            )
            for e in entries
        ]


# ============================================================
# 默认同义词库（系统初始化时加载）
# ============================================================

DEFAULT_SYNONYMS = [
    # 科技/IT 术语
    {
        "standard_term": "人工智能",
        "synonyms": ["AI", "机器智能", "智能"],
        "category": "技术术语",
    },
    {
        "standard_term": "大语言模型",
        "synonyms": ["LLM", "语言模型", "大模型"],
        "category": "技术术语",
    },
    {
        "standard_term": "检索增强生成",
        "synonyms": ["RAG", "检索生成"],
        "category": "技术术语",
    },
    {
        "standard_term": "向量数据库",
        "synonyms": ["向量库", "矢量数据库", "Embedding 数据库"],
        "category": "技术术语",
    },
    # 常见品牌/产品
    {
        "standard_term": "苹果",
        "synonyms": ["Apple", "苹果手机", "苹果公司"],
        "category": "品牌",
    },
    {
        "standard_term": "微软",
        "synonyms": ["Microsoft", "微软公司"],
        "category": "品牌",
    },
    {
        "standard_term": "华为",
        "synonyms": ["Huawei", "华为公司", "华为技术"],
        "category": "品牌",
    },
    # 职位/角色
    {
        "standard_term": "首席执行官",
        "synonyms": ["CEO", "行政总裁", "总经理"],
        "category": "职位",
    },
    {
        "standard_term": "首席技术官",
        "synonyms": ["CTO", "技术总监"],
        "category": "职位",
    },
    {
        "standard_term": "产品经理",
        "synonyms": ["PM", "产品负责人"],
        "category": "职位",
    },
]


async def init_default_synonyms(db: AsyncSession):
    """初始化默认同义词库"""
    from app.models.synonym import Synonym
    from sqlalchemy import select, func

    # 检查是否已有数据
    result = await db.execute(select(func.count(Synonym.id)))
    if result.scalar() > 0:
        logger.info("Synonyms already exist, skipping initialization")
        return

    # 添加默认同义词
    for item in DEFAULT_SYNONYMS:
        entry = Synonym(
            standard_term=item["standard_term"],
            synonyms_json=json.dumps(item["synonyms"], ensure_ascii=False),
            category=item.get("category", ""),
            kb_id=None,  # 全局同义词
            is_enabled=True,
        )
        db.add(entry)
        logger.info(f"Adding default synonym: {item['standard_term']} → {item['synonyms']}")

    await db.commit()
    logger.info("Default synonyms initialized")
