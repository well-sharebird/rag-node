"""Skill registry: publish, versioning, tagging, dependency resolution, user locks."""
from __future__ import annotations
import json
import logging
import semver
from typing import Optional
from sqlalchemy import select, update, delete, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skill import (
    Skill, SkillVersion, SkillTag, SkillUserLock,
    SkillDeclaredDep, SkillLockedDep,
)

logger = logging.getLogger("app.services.skill_registry")


# ============================================================
# RegistryService
# ============================================================

class RegistryService:
    """Publish, query, and manage skill packages."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def publish(
        self,
        skill_name: str,
        version_str: str,
        manifest: dict,
        package_hash: str,
        changelog: str | None = None,
        released_by: str | None = None,
        dependencies: list[dict] | None = None,
    ) -> SkillVersion:
        # Parse semver
        try:
            v = semver.Version.parse(version_str)
        except ValueError as e:
            raise ValueError(f"Invalid semver: {version_str}") from e

        # Get or create skill
        skill = await self._get_or_create_skill(skill_name, released_by)

        # Check version uniqueness
        existing = await self.db.execute(
            select(SkillVersion).where(
                and_(SkillVersion.skill_id == skill.id, SkillVersion.version == version_str)
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Version {version_str} already exists for {skill_name}")

        # Create version
        ver = SkillVersion(
            skill_id=skill.id,
            version=version_str,
            semver_major=v.major,
            semver_minor=v.minor,
            semver_patch=v.patch,
            semver_prerelease=v.prerelease or None,
            manifest_json=json.dumps(manifest, ensure_ascii=False),
            package_hash=package_hash,
            changelog=changelog,
            released_by=released_by,
            status="released",
        )
        self.db.add(ver)
        await self.db.flush()

        # Save declared dependencies
        if dependencies:
            for dep in dependencies:
                dd = SkillDeclaredDep(
                    from_version_id=ver.id,
                    dep_skill_name=dep["dep_skill_name"],
                    version_constraint=dep.get("version_constraint", ">=0.1.0"),
                )
                self.db.add(dd)
            await self.db.flush()

        # Resolve and lock dependencies
        resolver = DependencyResolver(self.db)
        await resolver.resolve(ver.id)

        await self.db.commit()
        await self.db.refresh(ver)
        logger.info("Published | %s@%s hash=%s deps=%d",
                    skill_name, version_str, package_hash[:16], len(dependencies or []))
        return ver

    async def list_skills(
        self, search: str | None = None, category: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[dict], int]:
        query = select(Skill)
        count_q = select(func.count(Skill.id))

        if search:
            filter_expr = Skill.name.ilike(f"%{search}%")
            query = query.where(filter_expr)
            count_q = count_q.where(filter_expr)
        if category:
            query = query.where(Skill.category == category)
            count_q = count_q.where(Skill.category == category)

        query = query.order_by(Skill.name).limit(limit).offset(offset)

        total_result = await self.db.execute(count_q)
        total = total_result.scalar() or 0

        result = await self.db.execute(query)
        skills = list(result.scalars().all())

        items = []
        for s in skills:
            items.append(await self._enrich_skill(s))
        return items, total

    async def get_skill(self, skill_name: str) -> dict | None:
        result = await self.db.execute(
            select(Skill).where(Skill.name == skill_name)
        )
        skill = result.scalar_one_or_none()
        if not skill:
            return None
        return await self._enrich_skill(skill)

    async def list_versions(self, skill_name: str) -> list[SkillVersion] | None:
        skill = await self._get_skill_by_name(skill_name)
        if not skill:
            return None
        result = await self.db.execute(
            select(SkillVersion)
            .where(SkillVersion.skill_id == skill.id)
            .order_by(
                SkillVersion.semver_major.desc(),
                SkillVersion.semver_minor.desc(),
                SkillVersion.semver_patch.desc(),
            )
        )
        versions = list(result.scalars().all())
        return versions

    async def get_version(self, skill_name: str, version_str: str) -> SkillVersion | None:
        skill = await self._get_skill_by_name(skill_name)
        if not skill:
            return None
        result = await self.db.execute(
            select(SkillVersion).where(
                and_(SkillVersion.skill_id == skill.id, SkillVersion.version == version_str)
            )
        )
        return result.scalar_one_or_none()

    async def get_version_by_id(self, version_id: int) -> SkillVersion | None:
        result = await self.db.execute(
            select(SkillVersion).where(SkillVersion.id == version_id)
        )
        return result.scalar_one_or_none()

    async def _get_or_create_skill(self, name: str, owner: str | None = None) -> Skill:
        result = await self.db.execute(select(Skill).where(Skill.name == name))
        skill = result.scalar_one_or_none()
        if skill:
            return skill
        skill = Skill(name=name, owner=owner)
        self.db.add(skill)
        await self.db.flush()
        return skill

    async def _get_skill_by_name(self, name: str) -> Skill | None:
        result = await self.db.execute(select(Skill).where(Skill.name == name))
        return result.scalar_one_or_none()

    async def _enrich_skill(self, skill: Skill) -> dict:
        """Add latest version, stable tag version, and version count."""
        # Version count
        count_result = await self.db.execute(
            select(func.count(SkillVersion.id)).where(SkillVersion.skill_id == skill.id)
        )
        version_count = count_result.scalar() or 0

        # Latest version
        latest_result = await self.db.execute(
            select(SkillVersion.version)
            .where(SkillVersion.skill_id == skill.id)
            .order_by(
                SkillVersion.semver_major.desc(),
                SkillVersion.semver_minor.desc(),
                SkillVersion.semver_patch.desc(),
            )
            .limit(1)
        )
        latest = latest_result.scalar_one_or_none()
        latest_version = latest if latest else None

        # Stable tag
        tag_result = await self.db.execute(
            select(SkillTag).where(
                and_(SkillTag.skill_id == skill.id, SkillTag.tag_name == "stable")
            )
        )
        tag = tag_result.scalar_one_or_none()
        if tag:
            ver_result = await self.db.execute(
                select(SkillVersion.version).where(SkillVersion.id == tag.version_id)
            )
            stable_ver = ver_result.scalar_one_or_none()
            stable_version = stable_ver if stable_ver else None
        else:
            stable_version = None

        return {
            "id": skill.id,
            "name": skill.name,
            "description": skill.description,
            "category": skill.category,
            "owner": skill.owner,
            "status": skill.status,
            "latest_version": latest_version,
            "stable_version": stable_version,
            "version_count": version_count,
            "created_at": skill.created_at,
            "updated_at": skill.updated_at,
        }


# ============================================================
# TagService
# ============================================================

class TagService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def set_tag(self, skill_name: str, tag_name: str, version_str: str) -> SkillTag:
        registry = RegistryService(self.db)
        skill = await registry._get_skill_by_name(skill_name)
        if not skill:
            raise ValueError(f"Skill not found: {skill_name}")

        ver = await registry.get_version(skill_name, version_str)
        if not ver:
            raise ValueError(f"Version not found: {skill_name}@{version_str}")

        # Upsert tag
        result = await self.db.execute(
            select(SkillTag).where(
                and_(SkillTag.skill_id == skill.id, SkillTag.tag_name == tag_name)
            )
        )
        tag = result.scalar_one_or_none()
        if tag:
            tag.version_id = ver.id
        else:
            tag = SkillTag(skill_id=skill.id, tag_name=tag_name, version_id=ver.id)
            self.db.add(tag)

        await self.db.commit()
        await self.db.refresh(tag)
        logger.info("Tag set | %s:%s -> %s", skill_name, tag_name, version_str)
        return tag

    async def resolve_tag(self, skill_name: str, tag_name: str = "stable") -> str | None:
        registry = RegistryService(self.db)
        skill = await registry._get_skill_by_name(skill_name)
        if not skill:
            return None

        result = await self.db.execute(
            select(SkillTag).where(
                and_(SkillTag.skill_id == skill.id, SkillTag.tag_name == tag_name)
            )
        )
        tag = result.scalar_one_or_none()
        if not tag:
            return None

        ver = await registry.get_version_by_id(tag.version_id)
        return ver.version if ver else None

    async def list_tags(self, skill_name: str) -> list[SkillTag]:
        registry = RegistryService(self.db)
        skill = await registry._get_skill_by_name(skill_name)
        if not skill:
            return []
        result = await self.db.execute(
            select(SkillTag).where(SkillTag.skill_id == skill.id)
        )
        return list(result.scalars().all())


# ============================================================
# DependencyResolver
# ============================================================

class DependencyResolver:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def resolve(self, version_id: int) -> dict[str, str]:
        """Resolve dependencies for a version and save locked_deps."""
        result = await self.db.execute(
            select(SkillDeclaredDep).where(SkillDeclaredDep.from_version_id == version_id)
        )
        declared = list(result.scalars().all())

        if not declared:
            return {}

        # Clear previous lock results
        await self.db.execute(
            delete(SkillLockedDep).where(SkillLockedDep.from_version_id == version_id)
        )

        resolved = {}
        to_process = list(declared)

        while to_process:
            dep = to_process.pop(0)
            dep_name = dep.dep_skill_name
            constraint = dep.version_constraint

            if dep_name in resolved:
                continue

            # Find all versions of the dependency
            skill_result = await self.db.execute(
                select(Skill).where(Skill.name == dep_name)
            )
            dep_skill = skill_result.scalar_one_or_none()
            if not dep_skill:
                raise ValueError(f"Dependency skill not found: {dep_name}")

            ver_result = await self.db.execute(
                select(SkillVersion).where(SkillVersion.skill_id == dep_skill.id)
            )
            all_versions = list(ver_result.scalars().all())

            # Filter by semver constraint
            candidates = []
            for v in all_versions:
                try:
                    sver = semver.Version.parse(v.version)
                    if constraint == "*" or self._satisfies(sver, constraint):
                        candidates.append(v)
                except ValueError:
                    continue

            if not candidates:
                raise ValueError(
                    f"No version of {dep_name} satisfies constraint {constraint}"
                )

            # Pick highest version
            candidates.sort(
                key=lambda v: (v.semver_major, v.semver_minor, v.semver_patch),
                reverse=True,
            )
            best = candidates[0]
            resolved[dep_name] = best.version

            # Save locked dep
            ld = SkillLockedDep(
                from_version_id=version_id,
                dep_skill_name=dep_name,
                resolved_version_id=best.id,
            )
            self.db.add(ld)

            # Add sub-dependencies to queue
            sub_result = await self.db.execute(
                select(SkillDeclaredDep).where(SkillDeclaredDep.from_version_id == best.id)
            )
            sub_deps = list(sub_result.scalars().all())
            for sd in sub_deps:
                if sd.dep_skill_name not in resolved:
                    to_process.append(sd)

        await self.db.flush()
        return resolved

    async def get_resolved_deps(self, version_id: int) -> list[dict]:
        """Get the resolved dependency tree for display."""
        result = await self.db.execute(
            select(SkillLockedDep).where(SkillLockedDep.from_version_id == version_id)
        )
        locked = list(result.scalars().all())

        deps = []
        for ld in locked:
            ver = await self.db.execute(
                select(SkillVersion.version).where(SkillVersion.id == ld.resolved_version_id)
            )
            resolved_ver = ver.scalar_one_or_none()

            # Get original constraint
            const_result = await self.db.execute(
                select(SkillDeclaredDep.version_constraint).where(
                    and_(
                        SkillDeclaredDep.from_version_id == version_id,
                        SkillDeclaredDep.dep_skill_name == ld.dep_skill_name,
                    )
                )
            )
            constraint = const_result.scalar_one_or_none() or "?"

            deps.append({
                "dep_skill_name": ld.dep_skill_name,
                "constraint": constraint,
                "resolved_version": resolved_ver or "?",
            })
        return deps

    def _satisfies(self, version: semver.Version, constraint: str) -> bool:
        """Check if a version satisfies a semver constraint string."""
        try:
            return semver.match(str(version), constraint)
        except (ValueError, TypeError):
            return False


# ============================================================
# LockService
# ============================================================

class LockService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def set_user_lock(
        self, skill_name: str, user_id: str, version_str: str, reason: str | None = None,
    ) -> SkillUserLock:
        registry = RegistryService(self.db)
        skill = await registry._get_skill_by_name(skill_name)
        if not skill:
            raise ValueError(f"Skill not found: {skill_name}")

        ver = await registry.get_version(skill_name, version_str)
        if not ver:
            raise ValueError(f"Version not found: {skill_name}@{version_str}")

        # Upsert
        result = await self.db.execute(
            select(SkillUserLock).where(
                and_(SkillUserLock.user_id == user_id, SkillUserLock.skill_id == skill.id)
            )
        )
        lock = result.scalar_one_or_none()
        if lock:
            lock.version_id = ver.id
            lock.reason = reason
        else:
            lock = SkillUserLock(
                user_id=user_id, skill_id=skill.id,
                version_id=ver.id, reason=reason,
            )
            self.db.add(lock)

        await self.db.commit()
        await self.db.refresh(lock)
        logger.info("User lock | %s -> %s@%s", user_id, skill_name, version_str)
        return lock

    async def remove_user_lock(self, skill_name: str, user_id: str) -> bool:
        registry = RegistryService(self.db)
        skill = await registry._get_skill_by_name(skill_name)
        if not skill:
            return False

        result = await self.db.execute(
            select(SkillUserLock).where(
                and_(SkillUserLock.user_id == user_id, SkillUserLock.skill_id == skill.id)
            )
        )
        lock = result.scalar_one_or_none()
        if lock:
            await self.db.delete(lock)
            await self.db.commit()
            return True
        return False

    async def get_effective_version(
        self, skill_name: str, user_id: str | None = None, tag: str | None = None,
    ) -> dict:
        """Resolve effective version with priority: User Lock > Tag > Latest."""
        registry = RegistryService(self.db)
        tag_svc = TagService(self.db)

        # Priority 1: User lock
        if user_id:
            skill = await registry._get_skill_by_name(skill_name)
            if skill:
                result = await self.db.execute(
                    select(SkillUserLock).where(
                        and_(SkillUserLock.user_id == user_id, SkillUserLock.skill_id == skill.id)
                    )
                )
                lock = result.scalar_one_or_none()
                if lock:
                    ver = await registry.get_version_by_id(lock.version_id)
                    if ver:
                        return {
                            "skill_name": skill_name,
                            "resolved_version": ver.version,
                            "version_id": ver.id,
                            "resolved_by": "user_lock",
                        }

        # Priority 2: Tag
        tag_name = tag or "stable"
        tag_version = await tag_svc.resolve_tag(skill_name, tag_name)
        if tag_version:
            ver = await registry.get_version(skill_name, tag_version)
            if ver:
                return {
                    "skill_name": skill_name,
                    "resolved_version": ver.version,
                    "version_id": ver.id,
                    "resolved_by": f"tag:{tag_name}",
                }

        # Priority 3: Latest released version
        versions = await registry.list_versions(skill_name)
        if versions and len(versions) > 0:
            latest = versions[0]
            return {
                "skill_name": skill_name,
                "resolved_version": latest.version,
                "version_id": latest.id,
                "resolved_by": "latest",
            }

        raise ValueError(f"No version found for skill: {skill_name}")


# ============================================================
# SkillRegistry (Sync version for Agent Runtime)
# ============================================================

class SkillRegistry:
    """
    同步版本的 Skill 注册表，用于 Agent Runtime

    提供简单的工具获取接口
    """

    def __init__(self, db):
        self.db = db

    def get_tool(self, skill_id: str):
        """
        根据 skill ID 获取工具

        TODO: 实现完整的工具加载逻辑
        目前返回 None，后续可扩展支持：
        - 从 Skill 配置加载 Python 函数
        - MCP 工具
        - API 工具
        """
        # 临时实现：返回 None
        # 后续可根据 skill_id 查询数据库，加载对应的工具函数
        logger.debug("get_tool called for skill_id=%s (not implemented yet)", skill_id)
        return None

    def list_available_skills(self) -> list[dict]:
        """列出可用的 Skill"""
        from app.models.skill import Skill
        result = self.db.execute(select(Skill).where(Skill.status == "active"))
        skills = result.scalars().all()
        return [
            {
                "id": str(s.id),
                "name": s.name,
                "description": s.description,
                "category": s.category,
            }
            for s in skills
        ]
