"""提示词注册中心服务 - CRUD + 元数据管理"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload

from app.models.prompt_template import (
    PromptTemplate,
    PromptVersion,
    PromptTag,
    PromptTestCase,
    PromptEvalRun,
)
from app.schemas.prompt import (
    PromptTemplateCreate,
    PromptTemplateUpdate,
    PromptVersionCreate,
    TagCreate,
    TestCaseCreate,
)


class PromptRegistryService:
    """提示词注册中心服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== Template CRUD ====================

    async def create_template(
        self, data: PromptTemplateCreate, actor: str
    ) -> PromptTemplate:
        """创建提示词模板"""
        template = PromptTemplate(
            name=data.name,
            description=data.description,
            category=data.category,
            owner=data.owner,
            status="active",
        )
        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)
        return template

    async def get_template(self, name: str) -> Optional[PromptTemplate]:
        """获取模板详情"""
        result = await self.db.execute(
            select(PromptTemplate)
            .where(PromptTemplate.name == name)
        )
        return result.scalar_one_or_none()

    async def get_template_with_tags(self, name: str) -> Optional[dict]:
        """获取模板详情（包含标签）"""
        result = await self.db.execute(
            select(PromptTemplate)
            .where(PromptTemplate.name == name)
        )
        template = result.scalar_one_or_none()
        if not template:
            return None

        # 同时加载标签
        tags_result = await self.db.execute(
            select(PromptTag, PromptVersion)
            .join(PromptVersion, PromptTag.version_id == PromptVersion.id)
            .where(PromptTag.template_id == template.id)
        )
        tags_data = tags_result.all()
        current_tags = {tag.tag_name: ver.version for tag, ver in tags_data}

        return {
            'id': template.id,
            'name': template.name,
            'description': template.description,
            'category': template.category,
            'owner': template.owner,
            'status': template.status,
            'created_at': template.created_at,
            'updated_at': template.updated_at,
            'current_tags': current_tags,
        }

    async def list_templates(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[List[dict], int]:
        """获取模板列表"""
        # 获取模板列表
        query = select(PromptTemplate)
        if status:
            query = query.where(PromptTemplate.status == status)
        if category:
            query = query.where(PromptTemplate.category == category)

        # 获取总数
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # 获取数据
        query = query.order_by(desc(PromptTemplate.created_at))
        query = query.offset(offset).limit(limit)
        result = await self.db.execute(query)
        templates = result.scalars().all()
        template_ids = [t.id for t in templates]

        # 一次性获取所有标签
        tags_query = select(PromptTag, PromptVersion).join(
            PromptVersion, PromptTag.version_id == PromptVersion.id
        ).where(PromptTag.template_id.in_(template_ids))
        tags_result = await self.db.execute(tags_query)
        tags_data = tags_result.all()

        # 构建模板 ID 到标签的映射
        tags_map = {}
        for tag, ver in tags_data:
            if tag.template_id not in tags_map:
                tags_map[tag.template_id] = {}
            tags_map[tag.template_id][tag.tag_name] = ver.version

        # 构建返回结果
        items = []
        for t in templates:
            items.append({
                'id': t.id,
                'name': t.name,
                'description': t.description,
                'category': t.category,
                'owner': t.owner,
                'status': t.status,
                'created_at': t.created_at,
                'updated_at': t.updated_at,
                'current_tags': tags_map.get(t.id, {}),
            })

        return items, total

    async def update_template(
        self, name: str, data: PromptTemplateUpdate, actor: str
    ) -> Optional[PromptTemplate]:
        """更新模板元数据"""
        template = await self.get_template(name)
        if not template:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(template, field, value)

        await self.db.commit()
        await self.db.refresh(template)
        return template

    async def archive_template(self, name: str, actor: str) -> bool:
        """归档模板（软删除）"""
        template = await self.get_template(name)
        if not template:
            return False

        template.status = "archived"
        await self.db.commit()
        return True

    # ==================== Version Management ====================

    async def create_version(
        self, template_name: str, data: PromptVersionCreate, actor: str
    ) -> Optional[PromptVersion]:
        """创建新版本"""
        template = await self.get_template(name=template_name)
        if not template:
            return None

        # 解析语义化版本号
        version_parts = data.version.split("-")
        semver_main = version_parts[0]
        semver_prerelease = version_parts[1] if len(version_parts) > 1 else None

        major, minor, patch = map(int, semver_main.split("."))

        version = PromptVersion(
            template_id=template.id,
            version=data.version,
            semver_major=major,
            semver_minor=minor,
            semver_patch=patch,
            semver_prerelease=semver_prerelease,
            content=data.content,
            variables_schema=data.variables_schema or [],
            system_role=data.system_role,
            changelog=data.changelog,
            released_by=actor,
            status="draft",
        )
        self.db.add(version)
        await self.db.commit()
        await self.db.refresh(version)
        return version

    async def get_version(
        self, template_name: str, version: str
    ) -> Optional[PromptVersion]:
        """获取指定版本"""
        template = await self.get_template(name=template_name)
        if not template:
            return None

        result = await self.db.execute(
            select(PromptVersion).where(
                PromptVersion.template_id == template.id,
                PromptVersion.version == version,
            )
        )
        return result.scalar_one_or_none()

    async def get_version_by_id(self, version_id: int) -> Optional[PromptVersion]:
        """通过 ID 获取版本"""
        result = await self.db.execute(
            select(PromptVersion).where(PromptVersion.id == version_id)
        )
        return result.scalar_one_or_none()

    async def list_versions(
        self,
        template_name: str,
        status: Optional[str] = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[List[PromptVersion], int]:
        """获取版本列表"""
        template = await self.get_template(name=template_name)
        if not template:
            return [], 0

        query = select(PromptVersion).where(
            PromptVersion.template_id == template.id
        )

        if status:
            query = query.where(PromptVersion.status == status)

        # 总数
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # 数据
        query = query.order_by(
            desc(PromptVersion.semver_major),
            desc(PromptVersion.semver_minor),
            desc(PromptVersion.semver_patch),
        )
        query = query.offset(offset).limit(limit)

        result = await self.db.execute(query)
        versions = result.scalars().all()
        return list(versions), total

    async def release_version(
        self, version_id: int, released_by: str
    ) -> Optional[PromptVersion]:
        """发布版本（draft -> released）"""
        version = await self.get_version_by_id(version_id)
        if not version:
            return None

        version.status = "released"
        version.released_at = datetime.utcnow()
        version.released_by = released_by
        await self.db.commit()
        await self.db.refresh(version)
        return version

    async def archive_version(self, version_id: int) -> bool:
        """归档版本"""
        version = await self.get_version_by_id(version_id)
        if not version:
            return False

        version.status = "archived"
        await self.db.commit()
        return True

    # ==================== Tag Management ====================

    async def get_tag(
        self, template_name: str, tag_name: str
    ) -> Optional[PromptTag]:
        """获取标签"""
        template = await self.get_template(name=template_name)
        if not template:
            return None

        result = await self.db.execute(
            select(PromptTag).where(
                PromptTag.template_id == template.id,
                PromptTag.tag_name == tag_name,
            )
        )
        return result.scalar_one_or_none()

    async def set_tag(
        self, template_name: str, data: TagCreate, actor: str
    ) -> Optional[PromptTag]:
        """设置标签（创建或更新）"""
        template = await self.get_template(name=template_name)
        if not template:
            return None

        # 验证版本存在且属于该模板
        version = await self.get_version_by_id(data.version_id)
        if not version or version.template_id != template.id:
            return None

        # 查找现有标签
        existing_tag = await self.get_tag(template_name, data.tag_name)

        if existing_tag:
            existing_tag.version_id = data.version_id
            existing_tag.meta_config = data.meta_config or {}
            existing_tag.updated_by = actor
            existing_tag.updated_at = datetime.utcnow()
            await self.db.commit()
            await self.db.refresh(existing_tag)
            return existing_tag
        else:
            tag = PromptTag(
                template_id=template.id,
                tag_name=data.tag_name,
                version_id=data.version_id,
                meta_config=data.meta_config or {},
                updated_by=actor,
            )
            self.db.add(tag)
            await self.db.commit()
            await self.db.refresh(tag)
            return tag

    async def delete_tag(self, template_name: str, tag_name: str) -> bool:
        """删除标签"""
        tag = await self.get_tag(template_name, tag_name)
        if not tag:
            return False

        await self.db.delete(tag)
        await self.db.commit()
        return True

    async def list_tags(self, template_name: str) -> List[PromptTag]:
        """获取所有标签"""
        template = await self.get_template(name=template_name)
        if not template:
            return []

        result = await self.db.execute(
            select(PromptTag)
            .where(PromptTag.template_id == template.id)
            .options(selectinload(PromptTag.version))
        )
        return list(result.scalars().all())

    # ==================== Test Case Management ====================

    async def create_test_case(
        self, template_name: str, data: TestCaseCreate, actor: str
    ) -> Optional[PromptTestCase]:
        """创建测试用例"""
        template = await self.get_template(name=template_name)
        if not template:
            return None

        test_case = PromptTestCase(
            template_id=template.id,
            input_context=data.input_context,
            expected_output=data.expected_output,
            expected_behavior=data.expected_behavior,
            tags=data.tags or [],
            priority=data.priority,
            is_active=True,
            created_by=actor,
        )
        self.db.add(test_case)
        await self.db.commit()
        await self.db.refresh(test_case)
        return test_case

    async def get_test_case(self, case_id: int) -> Optional[PromptTestCase]:
        """获取测试用例"""
        result = await self.db.execute(
            select(PromptTestCase).where(PromptTestCase.id == case_id)
        )
        return result.scalar_one_or_none()

    async def list_test_cases(
        self,
        template_name: str,
        is_active: Optional[bool] = None,
        priority: Optional[int] = None,
    ) -> List[PromptTestCase]:
        """获取测试用例列表"""
        template = await self.get_template(name=template_name)
        if not template:
            return []

        query = select(PromptTestCase).where(
            PromptTestCase.template_id == template.id
        )

        if is_active is not None:
            query = query.where(PromptTestCase.is_active == is_active)
        if priority is not None:
            query = query.where(PromptTestCase.priority == priority)

        query = query.order_by(PromptTestCase.priority)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def delete_test_case(self, case_id: int) -> bool:
        """删除测试用例"""
        case = await self.get_test_case(case_id)
        if not case:
            return False

        await self.db.delete(case)
        await self.db.commit()
        return True

    # ==================== Eval Run Management ====================

    async def save_eval_run(
        self,
        version_id: int,
        baseline_version_id: Optional[int],
        test_case_ids: List[int],
        avg_score: Optional[float],
        pass_count: Optional[int],
        fail_count: Optional[int],
        detailed_results: Dict[str, Any],
        triggered_by: str,
        run_duration_ms: Optional[int],
    ) -> PromptEvalRun:
        """保存评估运行记录"""
        eval_run = PromptEvalRun(
            version_id=version_id,
            baseline_version_id=baseline_version_id,
            test_case_ids=test_case_ids,
            avg_score=avg_score,
            pass_count=pass_count,
            fail_count=fail_count,
            total_count=len(test_case_ids),
            detailed_results=detailed_results,
            run_at=datetime.utcnow(),
            triggered_by=triggered_by,
            run_duration_ms=run_duration_ms,
        )
        self.db.add(eval_run)

        # 更新版本的评估分数
        if avg_score is not None:
            version = await self.get_version_by_id(version_id)
            if version:
                version.latest_eval_score = avg_score

        await self.db.commit()
        await self.db.refresh(eval_run)
        return eval_run

    async def get_eval_run(self, run_id: int) -> Optional[PromptEvalRun]:
        """获取评估运行记录"""
        result = await self.db.execute(
            select(PromptEvalRun).where(PromptEvalRun.id == run_id)
        )
        return result.scalar_one_or_none()
