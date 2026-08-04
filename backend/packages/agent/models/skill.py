"""Skill registry models: skills, versions, tags, user locks, dependency management."""
from typing import Optional
from datetime import datetime
from sqlalchemy import String, ForeignKey, Integer, Text, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from packages.core.base_model import Base, TimestampMixin


class Skill(Base, TimestampMixin):
    __tablename__ = "skill_skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(50), default="L1")
    owner: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")

    versions: Mapped[list["SkillVersion"]] = relationship(back_populates="skill", cascade="all, delete-orphan")
    tags: Mapped[list["SkillTag"]] = relationship(back_populates="skill", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Skill id={self.id} name={self.name}>"


class SkillVersion(Base, TimestampMixin):
    __tablename__ = "skill_versions"
    __table_args__ = (UniqueConstraint("skill_id", "version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill_id: Mapped[int] = mapped_column(Integer, ForeignKey("skill_skills.id"), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    semver_major: Mapped[int] = mapped_column(Integer, nullable=False)
    semver_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    semver_patch: Mapped[int] = mapped_column(Integer, nullable=False)
    semver_prerelease: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    manifest_json: Mapped[str] = mapped_column(Text, nullable=False)
    package_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    changelog: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    released_by: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="released")

    skill: Mapped["Skill"] = relationship(back_populates="versions")
    declared_deps: Mapped[list["SkillDeclaredDep"]] = relationship(back_populates="from_version", cascade="all, delete-orphan")
    locked_deps: Mapped[list["SkillLockedDep"]] = relationship(back_populates="from_version", cascade="all, delete-orphan", foreign_keys="SkillLockedDep.from_version_id")
    tags_pointing_here: Mapped[list["SkillTag"]] = relationship(back_populates="version_obj", foreign_keys="SkillTag.version_id")

    def __repr__(self) -> str:
        return f"<SkillVersion id={self.id} {self.version}>"


class SkillTag(Base, TimestampMixin):
    __tablename__ = "skill_tags"
    __table_args__ = (UniqueConstraint("skill_id", "tag_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill_id: Mapped[int] = mapped_column(Integer, ForeignKey("skill_skills.id"), nullable=False)
    tag_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    version_id: Mapped[int] = mapped_column(Integer, ForeignKey("skill_versions.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    skill: Mapped["Skill"] = relationship(back_populates="tags")
    version_obj: Mapped["SkillVersion"] = relationship(back_populates="tags_pointing_here", foreign_keys=[version_id])

    def __repr__(self) -> str:
        return f"<SkillTag {self.tag_name} -> {self.version_id}>"


class SkillUserLock(Base, TimestampMixin):
    __tablename__ = "skill_user_locks"
    __table_args__ = (UniqueConstraint("user_id", "skill_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    skill_id: Mapped[int] = mapped_column(Integer, ForeignKey("skill_skills.id"), nullable=False)
    version_id: Mapped[int] = mapped_column(Integer, ForeignKey("skill_versions.id"), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<SkillUserLock user={self.user_id} skill={self.skill_id} ver={self.version_id}>"


class SkillDeclaredDep(Base, TimestampMixin):
    __tablename__ = "skill_declared_deps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_version_id: Mapped[int] = mapped_column(Integer, ForeignKey("skill_versions.id"), nullable=False, index=True)
    dep_skill_name: Mapped[str] = mapped_column(String(200), nullable=False)
    version_constraint: Mapped[str] = mapped_column(String(200), nullable=False)

    from_version: Mapped["SkillVersion"] = relationship(back_populates="declared_deps")

    def __repr__(self) -> str:
        return f"<SkillDeclaredDep {self.dep_skill_name} {self.version_constraint}>"


class SkillLockedDep(Base, TimestampMixin):
    __tablename__ = "skill_locked_deps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_version_id: Mapped[int] = mapped_column(Integer, ForeignKey("skill_versions.id"), nullable=False, index=True)
    dep_skill_name: Mapped[str] = mapped_column(String(200), nullable=False)
    resolved_version_id: Mapped[int] = mapped_column(Integer, ForeignKey("skill_versions.id"), nullable=False)

    from_version: Mapped["SkillVersion"] = relationship(back_populates="locked_deps", foreign_keys=[from_version_id])
    resolved_version: Mapped["SkillVersion"] = relationship(foreign_keys=[resolved_version_id])

    def __repr__(self) -> str:
        return f"<SkillLockedDep {self.dep_skill_name} -> v{self.resolved_version_id}>"
