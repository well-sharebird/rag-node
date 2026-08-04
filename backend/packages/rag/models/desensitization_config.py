"""
数据脱敏配置模型
支持不同知识库设置不同的脱敏策略
"""
from sqlalchemy import Column, String, Boolean, Integer
from sqlalchemy.orm import relationship

from packages.core.base_model import Base


class DesensitizationConfig(Base):
    """脱敏配置表"""

    __tablename__ = "desensitization_config"

    id = Column(Integer, primary_key=True, index=True)

    # 知识库 ID（None 表示全局配置）
    kb_id = Column(String(36), nullable=True, unique=True, index=True,
                   comment="知识库 ID（NULL 表示全局配置）")

    # 脱敏级别：none, low, medium, high, custom
    level = Column(String(20), default="medium", comment="脱敏级别")

    # 各类 PII 脱敏开关
    enable_email_mask = Column(Boolean, default=True, comment="启用邮箱脱敏")
    enable_phone_mask = Column(Boolean, default=True, comment="启用手机号脱敏")
    enable_id_card_mask = Column(Boolean, default=True, comment="启用身份证脱敏")
    enable_bank_card_mask = Column(Boolean, default=True, comment="启用银行卡脱敏")
    enable_address_mask = Column(Boolean, default=False, comment="启用地址脱敏")
    enable_name_mask = Column(Boolean, default=False, comment="启用姓名脱敏")

    # 自定义替换规则 JSON
    # 格式：[{"from": "apple", "to": "苹果"}, {"from": "CEO", "to": "首席执行官"}]
    custom_replacements_json = Column(String(4096), nullable=True, comment="自定义替换规则 JSON")

    # 脱敏字符
    mask_char = Column(String(10), default="*", comment="脱敏占位符")

    @property
    def custom_replacements(self) -> list:
        """获取自定义替换规则"""
        import json
        if not self.custom_replacements_json:
            return []
        try:
            return json.loads(self.custom_replacements_json)
        except (json.JSONDecodeError, TypeError):
            return []

    @custom_replacements.setter
    def custom_replacements(self, value: list):
        """设置自定义替换规则"""
        import json
        self.custom_replacements_json = json.dumps(value, ensure_ascii=False)
