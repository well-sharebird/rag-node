"""Skill registry Pydantic schemas."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ============================================================
# Skill CRUD
# ============================================================

class SkillCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    category: str = "L1"
    owner: Optional[str] = None


class SkillResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    category: str
    owner: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime
    latest_version: Optional[str] = None
    stable_version: Optional[str] = None
    version_count: int = 0

    model_config = {"from_attributes": True}


class SkillListResponse(BaseModel):
    items: list[SkillResponse]
    total: int


# ============================================================
# Version
# ============================================================

class VersionResponse(BaseModel):
    id: int
    skill_id: int
    version: str
    semver_major: int
    semver_minor: int
    semver_patch: int
    semver_prerelease: Optional[str] = None
    package_hash: str
    changelog: Optional[str] = None
    released_by: Optional[str] = None
    released_at: Optional[datetime] = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class VersionListResponse(BaseModel):
    skill_name: str
    items: list[VersionResponse]
    total: int


class DependencyInfo(BaseModel):
    dep_skill_name: str
    version_constraint: str


class VersionPublishRequest(BaseModel):
    version: str = Field(..., description="SemVer version, e.g. 1.2.0 or 1.2.0-beta.1")
    changelog: Optional[str] = None
    dependencies: list[DependencyInfo] = Field(default_factory=list)


# ============================================================
# Tag
# ============================================================

class TagSetRequest(BaseModel):
    tag_name: str = Field(..., min_length=1, max_length=50)
    version: str = Field(..., description="Target version, e.g. 1.2.0")


class TagResponse(BaseModel):
    id: int
    skill_id: int
    tag_name: str
    version_id: int
    version: Optional[str] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TagListResponse(BaseModel):
    items: list[TagResponse]


# ============================================================
# Resolution
# ============================================================

class ResolveRequest(BaseModel):
    tag: Optional[str] = None
    version: Optional[str] = None
    user_id: Optional[str] = None


class ResolveResponse(BaseModel):
    skill_name: str
    resolved_version: str
    version_id: int
    resolved_by: str  # "user_lock", "tag", "latest"


# ============================================================
# User Lock
# ============================================================

class UserLockRequest(BaseModel):
    user_id: str = Field(...)
    version: str = Field(...)
    reason: Optional[str] = None


class UserLockResponse(BaseModel):
    id: int
    user_id: str
    skill_id: int
    version_id: int
    reason: Optional[str] = None
    locked_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ============================================================
# Dependency Resolution
# ============================================================

class ResolvedDepInfo(BaseModel):
    dep_skill_name: str
    constraint: str
    resolved_version: str


class DependencyTreeResponse(BaseModel):
    skill_name: str
    version: str
    dependencies: list[ResolvedDepInfo]
