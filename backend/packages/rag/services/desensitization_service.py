"""
可配置的数据脱敏服务

功能：
1. 企业可自定义脱敏规则
2. 不同知识库不同的脱敏级别
3. 支持多种脱敏方式（替换、加密、模糊）
"""
import json
import re
import hashlib
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("app.services.desensitization")


class DesensitizationLevel(Enum):
    """脱敏级别"""
    NONE = "none"           # 不脱敏
    LOW = "low"             # 轻度脱敏（保留部分信息）
    MEDIUM = "medium"       # 中度脱敏（模糊处理）
    HIGH = "high"           # 高度脱敏（完全替换）
    CUSTOM = "custom"       # 自定义规则


class DesensitizationMethod(Enum):
    """脱敏方法"""
    REPLACE = "replace"         # 字符替换（如 ****）
    MASK = "mask"               # 掩码（如 138****1234）
    HASH = "hash"               # 哈希加密
    TRUNCATE = "truncate"       # 截断
    KEEP_FIRST = "keep_first"   # 保留首字符
    KEEP_LAST = "keep_last"     # 保留尾字符
    CUSTOM = "custom"           # 自定义


@dataclass
class PIIRule:
    """PII 脱敏规则"""
    name: str  # 规则名称（如"手机号"）
    pattern: str  # 正则表达式
    method: DesensitizationMethod = DesensitizationMethod.MASK
    replace_char: str = "*"  # 替换字符
    keep_prefix: int = 0  # 保留前缀长度
    keep_suffix: int = 0  # 保留后缀长度
    is_enabled: bool = True


@dataclass
class DesensitizationConfig:
    """脱敏配置"""
    kb_id: Optional[str] = None  # 知识库 ID（None 表示全局）
    level: DesensitizationLevel = DesensitizationLevel.MEDIUM
    custom_rules: List[dict] = field(default_factory=list)  # [{"from": "apple", "to": "苹果"}, ...]
    enable_email_mask: bool = True
    enable_phone_mask: bool = True
    enable_id_card_mask: bool = True
    enable_bank_card_mask: bool = True
    enable_address_mask: bool = False
    enable_name_mask: bool = False


# 默认 PII 规则库
DEFAULT_PII_RULES = {
    "email": PIIRule(
        name="邮箱",
        pattern=r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        method=DesensitizationMethod.MASK,
        keep_prefix=2,
        keep_suffix=5,
    ),
    "phone_cn": PIIRule(
        name="中国手机号",
        pattern=r"\b1[3-9]\d{9}\b",
        method=DesensitizationMethod.MASK,
        keep_prefix=3,
        keep_suffix=4,
    ),
    "phone": PIIRule(
        name="电话号码",
        pattern=r"\b(?:\+?\d{1,3}[-.]?)?\(?\d{3}\)?[-.]?\d{3}[-.]?\d{4}\b",
        method=DesensitizationMethod.MASK,
        keep_prefix=3,
        keep_suffix=4,
    ),
    "id_card_cn": PIIRule(
        name="中国身份证",
        pattern=r"\b\d{17}[\dXx]\b",
        method=DesensitizationMethod.MASK,
        keep_prefix=1,
        keep_suffix=2,
    ),
    "bank_card": PIIRule(
        name="银行卡号",
        pattern=r"\b\d{4}[-.]?\d{4}[-.]?\d{4}[-.]?\d{4}\b",
        method=DesensitizationMethod.MASK,
        keep_prefix=4,
        keep_suffix=4,
    ),
    "id_card_partial": PIIRule(
        name="部分身份证号",
        pattern=r"\b\d{6}\s*\d{4,8}\b",
        method=DesensitizationMethod.REPLACE,
        replace_char="****",
    ),
}


class DesensitizationService:
    """脱敏服务"""

    def __init__(self, db: AsyncSession, config: Optional[DesensitizationConfig] = None):
        self.db = db
        self.config = config or DesensitizationConfig()
        self._rules: Dict[str, PIIRule] = DEFAULT_PII_RULES.copy()

    def apply(self, text: str) -> str:
        """
        应用脱敏规则到文本

        Args:
            text: 原始文本

        Returns:
            脱敏后的文本
        """
        if self.config.level == DesensitizationLevel.NONE:
            return text

        result = text

        # 应用启用的规则
        for rule_name, rule in self._rules.items():
            if not rule.is_enabled:
                continue

            # 检查是否启用该类型脱敏
            if not self._is_rule_enabled(rule_name):
                continue

            result = self._apply_rule(result, rule)

        # 应用自定义替换规则（关键词转换，如 apple→苹果）
        for custom_rule in self.config.custom_rules:
            if isinstance(custom_rule, dict):
                from_text = custom_rule.get('from', '')
                to_text = custom_rule.get('to', '')
                is_enabled = custom_rule.get('is_enabled', True)
            elif hasattr(custom_rule, 'from_term') and hasattr(custom_rule, 'to_term'):
                from_text = custom_rule.from_term
                to_text = custom_rule.to_term
                is_enabled = getattr(custom_rule, 'is_enabled', True)
            else:
                continue

            if is_enabled and from_text:
                # 不区分大小写替换
                pattern = re.compile(re.escape(from_text), re.IGNORECASE)
                result = pattern.sub(to_text, result)

        return result

    def _is_rule_enabled(self, rule_name: str) -> bool:
        """检查规则是否启用"""
        rule_enabled_map = {
            "email": self.config.enable_email_mask,
            "phone": self.config.enable_phone_mask or self.config.enable_phone_mask,
            "phone_cn": self.config.enable_phone_mask,
            "id_card_cn": self.config.enable_id_card_mask,
            "bank_card": self.config.enable_bank_card_mask,
            "id_card_partial": self.config.enable_id_card_mask,
        }
        return rule_enabled_map.get(rule_name, True)

    def _apply_rule(self, text: str, rule: PIIRule) -> str:
        """应用单条规则"""
        pattern = re.compile(rule.pattern)

        def replace_match(match):
            original = match.group(0)
            return self._desensitize_value(original, rule)

        return pattern.sub(replace_match, text)

    def _desensitize_value(self, value: str, rule: PIIRule) -> str:
        """对单个值进行脱敏"""
        if rule.method == DesensitizationMethod.REPLACE:
            return rule.replace_char * len(value)

        elif rule.method == DesensitizationMethod.MASK:
            # 掩码处理：保留前后，中间替换
            if len(value) <= rule.keep_prefix + rule.keep_suffix:
                return rule.replace_char * len(value)

            masked = (
                value[:rule.keep_prefix] +
                rule.replace_char * (len(value) - rule.keep_prefix - rule.keep_suffix) +
                value[-rule.keep_suffix:] if rule.keep_suffix > 0 else ""
            )
            return masked

        elif rule.method == DesensitizationMethod.HASH:
            # 哈希加密
            return hashlib.sha256(value.encode()).hexdigest()[:16]

        elif rule.method == DesensitizationMethod.TRUNCATE:
            # 截断
            return value[:10] + "..."

        elif rule.method == DesensitizationMethod.KEEP_FIRST:
            return value[0] + rule.replace_char * (len(value) - 1)

        elif rule.method == DesensitizationMethod.KEEP_LAST:
            return rule.replace_char * (len(value) - 1) + value[-1]

        elif rule.method == DesensitizationMethod.CUSTOM:
            # 自定义处理
            return rule.replace_char

        return value

    def detect_pii(self, text: str) -> Dict[str, int]:
        """
        检测文本中的 PII 类型和数量

        Returns:
            {"email": 2, "phone_cn": 1, ...}
        """
        detected = {}
        for rule_name, rule in self._rules.items():
            matches = re.findall(rule.pattern, text)
            if matches:
                detected[rule_name] = len(matches)
        return detected

    def get_pii_statistics(self, text: str) -> Dict[str, Any]:
        """
        获取 PII 检测统计信息

        Returns:
            {
                "total_count": 5,
                "types": {"email": 2, "phone_cn": 1, ...},
                "risk_level": "high"
            }
        """
        detected = self.detect_pii(text)
        total = sum(detected.values())

        # 风险评估
        if total == 0:
            risk_level = "low"
        elif total <= 3:
            risk_level = "medium"
        else:
            risk_level = "high"

        return {
            "total_count": total,
            "types": detected,
            "risk_level": risk_level,
        }

    def update_config(self, config: DesensitizationConfig):
        """更新配置"""
        self.config = config

    def add_custom_rule(self, rule: PIIRule):
        """添加自定义规则"""
        self._rules[f"custom_{rule.name}"] = rule


# ============================================================
# 知识库脱敏配置管理
# ============================================================

async def get_kb_desensitization_config(
    db: AsyncSession,
    kb_id: Optional[str] = None,
) -> DesensitizationConfig:
    """
    获取知识库脱敏配置

    优先级：
    1. 知识库特定配置
    2. 全局默认配置
    """
    from packages.rag.models.desensitization_config import DesensitizationConfig as ConfigModel

    # 尝试获取知识库特定配置
    if kb_id:
        result = await db.execute(
            select(ConfigModel).where(ConfigModel.kb_id == kb_id)
        )
        config_model = result.scalar_one_or_none()
        if config_model:
            return _model_to_config(config_model)

    # 获取全局配置
    result = await db.execute(
        select(ConfigModel).where(ConfigModel.kb_id.is_(None))
    )
    config_model = result.scalar_one_or_none()

    if config_model:
        return _model_to_config(config_model)

    # 返回默认配置
    return DesensitizationConfig(
        kb_id=kb_id,
        level=DesensitizationLevel.MEDIUM,
    )


def _model_to_config(model) -> DesensitizationConfig:
    """将数据库模型转换为配置对象"""
    config = DesensitizationConfig(
        kb_id=model.kb_id,
        level=DesensitizationLevel(model.level),
        enable_email_mask=model.enable_email_mask,
        enable_phone_mask=model.enable_phone_mask,
        enable_id_card_mask=model.enable_id_card_mask,
        enable_bank_card_mask=model.enable_bank_card_mask,
        enable_address_mask=model.enable_address_mask,
        custom_rules=[],
    )
    # 加载自定义替换规则
    if hasattr(model, 'custom_replacements_json') and model.custom_replacements_json:
        try:
            import json
            config.custom_rules = json.loads(model.custom_replacements_json)
        except (json.JSONDecodeError, TypeError):
            pass
    return config


async def save_kb_desensitization_config(
    db: AsyncSession,
    kb_id: Optional[str],
    config: DesensitizationConfig,
) -> DesensitizationConfig:
    """保存知识库脱敏配置"""
    from packages.rag.models.desensitization_config import DesensitizationConfig as ConfigModel
    from sqlalchemy import update

    # 检查是否已有配置
    result = await db.execute(
        select(ConfigModel).where(
            ConfigModel.kb_id == kb_id if kb_id else ConfigModel.kb_id.is_(None)
        )
    )
    existing = result.scalar_one_or_none()

    import json

    if existing:
        # 更新
        await db.execute(
            update(ConfigModel)
            .where(ConfigModel.id == existing.id)
            .values(
                level=config.level.value,
                enable_email_mask=config.enable_email_mask,
                enable_phone_mask=config.enable_phone_mask,
                enable_id_card_mask=config.enable_id_card_mask,
                enable_bank_card_mask=config.enable_bank_card_mask,
                enable_address_mask=config.enable_address_mask,
                custom_replacements_json=json.dumps(config.custom_rules, ensure_ascii=False) if config.custom_rules else None,
            )
        )
    else:
        # 新建
        new_config = ConfigModel(
            kb_id=kb_id,
            level=config.level.value,
            enable_email_mask=config.enable_email_mask,
            enable_phone_mask=config.enable_phone_mask,
            enable_id_card_mask=config.enable_id_card_mask,
            enable_bank_card_mask=config.enable_bank_card_mask,
            enable_address_mask=config.enable_address_mask,
            custom_replacements_json=json.dumps(config.custom_rules, ensure_ascii=False) if config.custom_rules else None,
        )
        db.add(new_config)

    await db.commit()
    return config
