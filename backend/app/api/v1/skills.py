"""Skill registry API endpoints."""
from __future__ import annotations
import json
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.skill import (
    SkillCreate, SkillResponse, SkillListResponse,
    VersionResponse, VersionListResponse, VersionPublishRequest,
    TagSetRequest, TagResponse, TagListResponse,
    ResolveRequest, ResolveResponse,
    UserLockRequest, UserLockResponse,
    DependencyTreeResponse, DependencyInfo, ResolvedDepInfo,
)
from app.services.skill_registry import (
    RegistryService, TagService, DependencyResolver, LockService,
)
from app.services import skill_storage

logger = logging.getLogger("app.api.skills")
router = APIRouter(prefix="/skills", tags=["Skill Registry"])


# ============================================================
# Skill CRUD
# ============================================================

@router.get("", response_model=SkillListResponse)
async def list_skills(
    db: AsyncSession = Depends(get_db),
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    svc = RegistryService(db)
    items, total = await svc.list_skills(search, category, limit, offset)
    return SkillListResponse(items=[SkillResponse(**it) for it in items], total=total)


@router.get("/{skill_name}", response_model=SkillResponse)
async def get_skill(skill_name: str, db: AsyncSession = Depends(get_db)):
    svc = RegistryService(db)
    skill = await svc.get_skill(skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return SkillResponse(**skill)


@router.post("", response_model=SkillResponse, status_code=201)
async def create_skill(data: SkillCreate, db: AsyncSession = Depends(get_db)):
    svc = RegistryService(db)
    skill = await svc._get_or_create_skill(data.name, data.owner)
    if data.description:
        skill.description = data.description
    if data.category:
        skill.category = data.category
    await db.commit()
    await db.refresh(skill)
    enriched = await svc._enrich_skill(skill)
    return SkillResponse(**enriched)


# ============================================================
# Version Management
# ============================================================

@router.get("/{skill_name}/versions", response_model=VersionListResponse)
async def list_versions(skill_name: str, db: AsyncSession = Depends(get_db)):
    svc = RegistryService(db)
    versions = await svc.list_versions(skill_name)
    if versions is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return VersionListResponse(
        skill_name=skill_name,
        items=[VersionResponse.model_validate(v) for v in versions],
        total=len(versions),
    )


@router.get("/{skill_name}/versions/{version}", response_model=VersionResponse)
async def get_version(skill_name: str, version: str, db: AsyncSession = Depends(get_db)):
    svc = RegistryService(db)
    ver = await svc.get_version(skill_name, version)
    if not ver:
        raise HTTPException(status_code=404, detail="Version not found")
    return VersionResponse.model_validate(ver)


@router.post("/publish", response_model=VersionResponse, status_code=201)
async def publish_version(
    skill_name: str = Form(..., description="Skill name"),
    version: str = Form(..., description="SemVer version"),
    changelog: Optional[str] = Form(None),
    released_by: Optional[str] = Form(None),
    dependencies: Optional[str] = Form(None, description="JSON array of DependencyInfo"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    # Read uploaded file
    file_content = await file.read()

    # Parse manifest from uploaded file (expect zip or manifest.json)
    manifest = {}
    files: dict[str, bytes] = {}
    filename = file.filename or "package.zip"

    if filename.endswith(".json"):
        try:
            manifest = json.loads(file_content.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            manifest = {"name": skill_name, "version": version}
        files["manifest.json"] = file_content
    else:
        # Treat as a package file
        manifest = {"name": skill_name, "version": version, "package": filename}
        files[filename] = file_content

    # Save package to blob storage
    package_hash = skill_storage.save_package(skill_name, version, manifest, files)

    # Parse dependencies
    deps = []
    if dependencies:
        try:
            deps = json.loads(dependencies)
        except json.JSONDecodeError:
            pass

    # Publish to registry
    svc = RegistryService(db)
    try:
        ver = await svc.publish(
            skill_name=skill_name,
            version_str=version,
            manifest=manifest,
            package_hash=package_hash,
            changelog=changelog,
            released_by=released_by,
            dependencies=deps,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return VersionResponse.model_validate(ver)


# ============================================================
# Tags
# ============================================================

@router.get("/{skill_name}/tags", response_model=TagListResponse)
async def list_tags(skill_name: str, db: AsyncSession = Depends(get_db)):
    svc = TagService(db)
    tags = await svc.list_tags(skill_name)
    items = []
    for t in tags:
        ver = await RegistryService(db).get_version_by_id(t.version_id)
        items.append(TagResponse(
            id=t.id, skill_id=t.skill_id, tag_name=t.tag_name,
            version_id=t.version_id,
            version=ver.version if ver else None,
            updated_at=t.updated_at,
        ))
    return TagListResponse(items=items)


@router.post("/{skill_name}/tags", response_model=TagResponse, status_code=201)
async def set_tag(skill_name: str, data: TagSetRequest, db: AsyncSession = Depends(get_db)):
    svc = TagService(db)
    try:
        tag = await svc.set_tag(skill_name, data.tag_name, data.version)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    ver = await RegistryService(db).get_version_by_id(tag.version_id)
    return TagResponse(
        id=tag.id, skill_id=tag.skill_id, tag_name=tag.tag_name,
        version_id=tag.version_id,
        version=ver.version if ver else None,
        updated_at=tag.updated_at,
    )


# ============================================================
# Resolution
# ============================================================

@router.get("/{skill_name}/resolve", response_model=ResolveResponse)
async def resolve_version(
    skill_name: str,
    tag: Optional[str] = Query(None),
    version: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    if version:
        svc = RegistryService(db)
        ver = await svc.get_version(skill_name, version)
        if not ver:
            raise HTTPException(status_code=404, detail="Version not found")
        return ResolveResponse(
            skill_name=skill_name, resolved_version=ver.version,
            version_id=ver.id, resolved_by="explicit",
        )

    svc = LockService(db)
    try:
        return ResolveResponse(**await svc.get_effective_version(skill_name, user_id, tag))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================
# User Locks
# ============================================================

@router.post("/{skill_name}/locks", response_model=UserLockResponse, status_code=201)
async def set_user_lock(skill_name: str, data: UserLockRequest, db: AsyncSession = Depends(get_db)):
    svc = LockService(db)
    try:
        lock = await svc.set_user_lock(skill_name, data.user_id, data.version, data.reason)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return UserLockResponse.model_validate(lock)


@router.delete("/{skill_name}/locks/{user_id}")
async def remove_user_lock(skill_name: str, user_id: str, db: AsyncSession = Depends(get_db)):
    svc = LockService(db)
    removed = await svc.remove_user_lock(skill_name, user_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Lock not found")
    return {"status": "removed", "skill_name": skill_name, "user_id": user_id}


# ============================================================
# Dependencies
# ============================================================

@router.get("/{skill_name}/deps", response_model=DependencyTreeResponse)
async def get_dependency_tree(
    skill_name: str,
    version: str = Query(..., description="Version to inspect"),
    db: AsyncSession = Depends(get_db),
):
    svc = RegistryService(db)
    ver = await svc.get_version(skill_name, version)
    if not ver:
        raise HTTPException(status_code=404, detail="Version not found")

    resolver = DependencyResolver(db)
    # Resolve if not already resolved
    await resolver.resolve(ver.id)
    deps = await resolver.get_resolved_deps(ver.id)

    return DependencyTreeResponse(
        skill_name=skill_name,
        version=version,
        dependencies=[ResolvedDepInfo(**d) for d in deps],
    )


# ============================================================
# Download
# ============================================================

@router.get("/{skill_name}/download")
async def download_package(
    skill_name: str,
    version: Optional[str] = Query(None, description="Specific version or tag (stable/latest)"),
    db: AsyncSession = Depends(get_db),
):
    """Download a skill package as a zip file."""
    import io
    import zipfile

    svc = RegistryService(db)
    tag_svc = TagService(db)

    # Resolve version
    resolved_ver = version
    if not resolved_ver or resolved_ver in ("latest", "stable"):
        tag_name = resolved_ver or "stable"
        tag_ver = await tag_svc.resolve_tag(skill_name, tag_name)
        if tag_ver:
            resolved_ver = tag_ver
        else:
            versions = await svc.list_versions(skill_name)
            if not versions:
                raise HTTPException(status_code=404, detail="No versions found")
            resolved_ver = versions[0].version

    # Verify version exists
    ver = await svc.get_version(skill_name, resolved_ver)
    if not ver:
        raise HTTPException(status_code=404, detail=f"Version {resolved_ver} not found")

    # Read package files
    files = skill_storage.get_package_content(skill_name, resolved_ver)
    if not files:
        raise HTTPException(status_code=404, detail="Package files not found")

    # Create zip in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for rel_path, content in files.items():
            if isinstance(content, str):
                zf.writestr(rel_path, content)
            else:
                zf.writestr(rel_path, content)

    zip_buffer.seek(0)
    filename = f"{skill_name}-{resolved_ver}.zip"
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
