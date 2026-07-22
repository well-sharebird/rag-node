"""发布控制中心 - 标签管理 + 灰度策略"""

import hashlib
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.prompt.registry import PromptRegistryService
from app.models.prompt_template import PromptVersion


class PromptPublisher:
    """发布控制中心

    负责：
    - 标签管理（创建/更新/删除标签）
    - 灰度策略（基于用户 ID 哈希分流）
    - 版本回滚
    - 生效版本解析
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.registry = PromptRegistryService(db)

    async def resolve_effective_version(
        self,
        template_name: str,
        user_id: Optional[str] = None,
    ) -> Optional[PromptVersion]:
        """解析生效版本

        决策优先级：
        1. 用户级锁定（如有）
        2. 灰度规则（Canary）
        3. 全局默认（stable）
        4. 最新 released 版本

        Args:
            template_name: 模板名称
            user_id: 用户 ID（用于灰度判断）

        Returns:
            生效的版本对象
        """
        template = await self.registry.get_template(template_name)
        if not template:
            return None

        # 1. 用户锁定（预留扩展）
        locked_version_id = await self._get_user_lock(template.id, user_id)
        if locked_version_id:
            return await self.registry.get_version_by_id(locked_version_id)

        # 2. 灰度（Canary）
        canary_tag = await self.registry.get_tag(template_name, "canary")
        if canary_tag:
            gray_percent = canary_tag.meta_config.get("gray_percent", 0)
            if self._hit_gray(user_id, gray_percent):
                return await self.registry.get_version_by_id(canary_tag.version_id)

        # 3. 默认稳定版
        stable_tag = await self.registry.get_tag(template_name, "stable")
        if stable_tag:
            return await self.registry.get_version_by_id(stable_tag.version_id)

        # 4. 回退：最新 released 版本
        versions, _ = await self.registry.list_versions(
            template_name, status="released", limit=1
        )
        if versions:
            return versions[0]

        return None

    async def tag_version(
        self,
        template_name: str,
        version_id: int,
        tag_name: str,
        meta_config: Optional[Dict[str, Any]] = None,
        actor: str = "system",
    ) -> bool:
        """给版本打标签

        预检查：
        - 版本必须存在且属于该模板
        - stable 标签必须通过评估（分数 >= 70）

        Args:
            template_name: 模板名称
            version_id: 版本 ID
            tag_name: 标签名
            meta_config: 元配置（灰度比例等）
            actor: 操作人

        Returns:
            是否成功
        """
        # 验证版本存在
        version = await self.registry.get_version_by_id(version_id)
        if not version:
            return False

        # 验证版本属于该模板
        template = await self.registry.get_template(template_name)
        if not template or version.template_id != template.id:
            return False

        # stable 标签特殊检查
        if tag_name == "stable":
            if version.status != "released":
                return False  # 必须先发布
            if version.latest_eval_score is None:
                return False  # 必须先评估
            if version.latest_eval_score < 70:
                return False  # 分数不够

        # 设置标签
        from app.schemas.prompt import TagCreate

        tag_data = TagCreate(
            tag_name=tag_name,
            version_id=version_id,
            meta_config=meta_config or {},
        )
        result = await self.registry.set_tag(template_name, tag_data, actor)
        return result is not None

    async def rollback(
        self,
        template_name: str,
        target_version_id: int,
        tag_name: str = "stable",
        actor: str = "system",
    ) -> bool:
        """回滚：将标签指向旧版本

        Args:
            template_name: 模板名称
            target_version_id: 回滚目标版本 ID
            tag_name: 要回滚的标签
            actor: 操作人

        Returns:
            是否成功
        """
        # 验证目标版本存在
        version = await self.registry.get_version_by_id(target_version_id)
        if not version:
            return False

        # 验证版本属于该模板
        template = await self.registry.get_template(template_name)
        if not template or version.template_id != template.id:
            return False

        # 直接设置标签（不检查评估分数，紧急回滚）
        from app.schemas.prompt import TagCreate

        tag_data = TagCreate(
            tag_name=tag_name,
            version_id=target_version_id,
            meta_config={},
        )
        result = await self.registry.set_tag(template_name, tag_data, actor)
        return result is not None

    def _hit_gray(self, user_id: Optional[str], percent: int) -> bool:
        """灰度命中判断

        基于用户 ID 的哈希值进行分流

        Args:
            user_id: 用户 ID
            percent: 灰度百分比 (0-100)

        Returns:
            是否命中灰度
        """
        if not user_id:
            return False

        # 使用 MD5 哈希的前两位作为哈希值
        hash_hex = hashlib.md5(user_id.encode()).hexdigest()[:2]
        hash_val = int(hash_hex, 16) % 100

        return hash_val < percent

    async def _get_user_lock(
        self, template_id: int, user_id: Optional[str]
    ) -> Optional[int]:
        """获取用户锁定的版本 ID

        预留扩展：允许特定用户强制使用指定版本

        Args:
            template_id: 模板 ID
            user_id: 用户 ID

        Returns:
            锁定的版本 ID，无则返回 None
        """
        # TODO: 实现用户锁定逻辑
        # 可以在 prompt_tags 表中增加 user_id 字段
        # 或者单独创建 user_prompt_locks 表
        return None

    async def get_gray_status(self, template_name: str) -> Dict[str, Any]:
        """获取灰度状态

        Args:
            template_name: 模板名称

        Returns:
            灰度状态信息
        """
        tags = await self.registry.list_tags(template_name)
        gray_info = {
            "canary": None,
            "stable": None,
            "beta": None,
            "dev": None,
        }

        for tag in tags:
            if tag.tag_name in gray_info:
                gray_info[tag.tag_name] = {
                    "version": tag.version.version if tag.version else None,
                    "version_id": tag.version_id,
                    "gray_percent": tag.meta_config.get("gray_percent", 0),
                }

        return gray_info
