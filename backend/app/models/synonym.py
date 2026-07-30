"""
同义词映射模型
用于存储同义词/缩写映射关系
"""
import json
from sqlalchemy import Column, String, Boolean, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship

from app.models.base import Base


class Synonym(Base):
    """同义词映射表"""

    __tablename__ = "synonyms"

    id = Column(Integer, primary_key=True, index=True)

    # 标准词（如"苹果"）
    standard_term = Column(String(255), nullable=False, index=True, comment="标准词")

    # 同义词列表 JSON（如["apple", "苹果手机"]）
    synonyms_json = Column(Text, nullable=False, comment="同义词列表 JSON")

    # 分类（如"品牌"、"技术术语"、"职位"）
    category = Column(String(100), nullable=True, index=True, comment="分类")

    # 所属知识库 ID（None 表示全局同义词）
    kb_id = Column(String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
                   nullable=True, index=True, comment="知识库 ID")

    # 是否启用
    is_enabled = Column(Boolean, default=True, index=True, comment="是否启用")

    @property
    def synonyms_list(self) -> list:
        """获取同义词列表"""
        try:
            return json.loads(self.synonyms_json)
        except (json.JSONDecodeError, TypeError):
            return []

    @synonyms_list.setter
    def synonyms_list(self, value: list):
        """设置同义词列表"""
        self.synonyms_json = json.dumps(value, ensure_ascii=False)
