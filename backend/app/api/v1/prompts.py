"""
Prompt Engineering Module API - 提示词工程化管理

提供提示词的版本控制、效果评估、灰度发布和回滚能力
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_user, require_role
from typing import Annotated, List

# Helper for multiple role checking
def require_any_role(*role_names: str):
    """Require any of the specified roles"""
    async def role_checker(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        user_roles = {r.name for r in current_user.roles}
        if not any(role in user_roles for role in role_names):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required role. Need one of: {', '.join(role_names)}",
            )
        return current_user
    return role_checker
from app.models.user import User
from app.schemas.prompt import (
    # Request
    PromptTemplateCreate,
    PromptTemplateUpdate,
    PromptVersionCreate,
    PromptVersionRelease,
    TagCreate,
    TagUpdate,
    EvalRequest,
    TestCaseCreate,
    RenderRequest,
    RollbackRequest,
    # Response
    PromptTemplateResponse,
    PromptVersionResponse,
    PromptTagResponse,
    TestCaseResponse,
    EvalReportResponse,
    AuditLogResponse,
    RenderResponse,
    TemplateListResponse,
    VersionListResponse,
    TagListResponse,
    TestCaseListResponse,
    AuditLogListResponse,
)
from app.models.prompt_template import PromptTag, PromptVersion
from app.services.prompt import (
    PromptRegistryService,
    PromptRenderer,
    PromptEvaluator,
    PromptPublisher,
    AuditService,
)

router = APIRouter(prefix="/prompts", tags=["Prompt Engineering"])


# ==================== Template Management ====================


@router.post("", response_model=PromptTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    data: PromptTemplateCreate,
    request: Request,
    current_user: User = Depends(require_any_role("Admin", "Editor")),
    db: AsyncSession = Depends(get_db),
):
    """创建提示词模板"""
    registry = PromptRegistryService(db)
    audit = AuditService(db)

    # 检查是否已存在
    existing = await registry.get_template(data.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"模板 '{data.name}' 已存在",
        )

    template = await registry.create_template(data, actor=current_user.username)

    # 审计日志
    await audit.log(
        actor=current_user.username,
        action=AuditService.ACTION_CREATE,
        resource_type=AuditService.RESOURCE_TEMPLATE,
        resource_id=template['id'],
        new_value=data.model_dump(),
        ip_address=request.client.host if request.client else None,
    )

    return template


@router.get("", response_model=TemplateListResponse)
async def list_templates(
    skip: int = 0,
    limit: int = 20,
    status_filter: Optional[str] = None,
    category: Optional[str] = None,
    current_user: User = Depends(require_any_role("Admin", "Editor", "Viewer")),
    db: AsyncSession = Depends(get_db),
):
    """获取模板列表"""
    registry = PromptRegistryService(db)
    items, total = await registry.list_templates(
        status=status_filter,
        category=category,
        offset=skip,
        limit=limit,
    )

    return TemplateListResponse(items=items, total=total)


@router.get("/{name}", response_model=PromptTemplateResponse)
async def get_template(
    name: str,
    current_user: User = Depends(require_any_role("Admin", "Editor", "Viewer")),
    db: AsyncSession = Depends(get_db),
):
    """获取模板详情"""
    registry = PromptRegistryService(db)
    template = await registry.get_template_with_tags(name)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"模板 '{name}' 不存在",
        )

    return PromptTemplateResponse(
        id=template['id'],
        name=template['name'],
        description=template['description'],
        category=template['category'],
        owner=template['owner'],
        status=template['status'],
        created_at=template['created_at'],
        updated_at=template['updated_at'],
        current_tags=template['current_tags'],
    )


@router.put("/{name}", response_model=PromptTemplateResponse)
async def update_template(
    name: str,
    data: PromptTemplateUpdate,
    request: Request,
    current_user: User = Depends(require_any_role("Admin", "Editor")),
    db: AsyncSession = Depends(get_db),
):
    """更新模板元数据"""
    registry = PromptRegistryService(db)
    audit = AuditService(db)

    template = await registry.get_template(name)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"模板 '{name}' 不存在",
        )

    old_value = {
        "description": template.description,
        "category": template.category,
        "owner": template.owner,
        "status": template.status,
    }

    updated = await registry.update_template(name, data, actor=current_user.username)

    # 审计日志
    await audit.log(
        actor=current_user.username,
        action=AuditService.ACTION_UPDATE,
        resource_type=AuditService.RESOURCE_TEMPLATE,
        resource_id=template.id,
        old_value=old_value,
        new_value=data.model_dump(exclude_unset=True),
        ip_address=request.client.host if request.client else None,
    )

    return updated


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_template(
    name: str,
    request: Request,
    current_user: User = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
):
    """归档模板（软删除）"""
    registry = PromptRegistryService(db)
    audit = AuditService(db)

    template = await registry.get_template(name)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"模板 '{name}' 不存在",
        )

    await registry.archive_template(name, actor=current_user.username)

    # 审计日志
    await audit.log(
        actor=current_user.username,
        action=AuditService.ACTION_ARCHIVE,
        resource_type=AuditService.RESOURCE_TEMPLATE,
        resource_id=template.id,
        ip_address=request.client.host if request.client else None,
    )


# ==================== Version Management ====================


@router.post("/{name}/versions", response_model=PromptVersionResponse, status_code=status.HTTP_201_CREATED)
async def create_version(
    name: str,
    data: PromptVersionCreate,
    request: Request,
    current_user: User = Depends(require_any_role("Admin", "Editor")),
    db: AsyncSession = Depends(get_db),
):
    """创建新版本"""
    registry = PromptRegistryService(db)
    audit = AuditService(db)

    template = await registry.get_template(name)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"模板 '{name}' 不存在",
        )

    # 检查版本是否已存在
    existing = await registry.get_version(name, data.version)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"版本 '{data.version}' 已存在",
        )

    version = await registry.create_version(name, data, actor=current_user.username)

    # 审计日志
    await audit.log(
        actor=current_user.username,
        action=AuditService.ACTION_CREATE,
        resource_type=AuditService.RESOURCE_VERSION,
        resource_id=version.id,
        new_value=data.model_dump(),
        ip_address=request.client.host if request.client else None,
    )

    return version


@router.get("/{name}/versions", response_model=VersionListResponse)
async def list_versions(
    name: str,
    skip: int = 0,
    limit: int = 20,
    status_filter: Optional[str] = None,
    current_user: User = Depends(require_any_role("Admin", "Editor", "Viewer")),
    db: AsyncSession = Depends(get_db),
):
    """获取版本列表"""
    registry = PromptRegistryService(db)
    versions, total = await registry.list_versions(
        name, status=status_filter, offset=skip, limit=limit
    )

    items = [
        PromptVersionResponse(
            id=v.id,
            template_id=v.template_id,
            version=v.version,
            content=v.content,
            variables_schema=v.variables_schema,
            system_role=v.system_role,
            changelog=v.changelog,
            released_by=v.released_by,
            released_at=v.released_at,
            status=v.status,
            latest_eval_score=v.latest_eval_score,
            eval_dataset_hash=v.eval_dataset_hash,
            created_at=v.created_at,
            updated_at=v.updated_at,
        )
        for v in versions
    ]

    return VersionListResponse(items=items, total=total)


@router.get("/{name}/versions/{version}", response_model=PromptVersionResponse)
async def get_version(
    name: str,
    version: str,
    current_user: User = Depends(require_any_role("Admin", "Editor", "Viewer")),
    db: AsyncSession = Depends(get_db),
):
    """获取指定版本详情"""
    registry = PromptRegistryService(db)
    v = await registry.get_version(name, version)

    if not v:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"版本 '{version}' 不存在",
        )

    return PromptVersionResponse(
        id=v.id,
        template_id=v.template_id,
        version=v.version,
        content=v.content,
        variables_schema=v.variables_schema,
        system_role=v.system_role,
        changelog=v.changelog,
        released_by=v.released_by,
        released_at=v.released_at,
        status=v.status,
        latest_eval_score=v.latest_eval_score,
        eval_dataset_hash=v.eval_dataset_hash,
        created_at=v.created_at,
        updated_at=v.updated_at,
    )


@router.post("/{name}/versions/{version_id}/release", response_model=PromptVersionResponse)
async def release_version(
    name: str,
    version_id: int,
    request: Request,
    data: Optional[PromptVersionRelease] = None,
    current_user: User = Depends(require_any_role("Admin", "Editor")),
    db: AsyncSession = Depends(get_db),
):
    """发布版本（draft -> released）"""
    registry = PromptRegistryService(db)
    audit = AuditService(db)

    released_by = data.released_by if data else current_user.username
    version = await registry.release_version(version_id, released_by=released_by)

    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"版本 {version_id} 不存在",
        )

    # 审计日志
    await audit.log(
        actor=current_user.username,
        action=AuditService.ACTION_RELEASE,
        resource_type=AuditService.RESOURCE_VERSION,
        resource_id=version.id,
        ip_address=request.client.host if request.client else None,
    )

    return version


# ==================== Tag Management ====================


@router.get("/{name}/tags", response_model=TagListResponse)
async def list_tags(
    name: str,
    current_user: User = Depends(require_any_role("Admin", "Editor", "Viewer")),
    db: AsyncSession = Depends(get_db),
):
    """获取所有标签"""
    registry = PromptRegistryService(db)
    tags = await registry.list_tags(name)

    items = [
        PromptTagResponse(
            id=t.id,
            template_id=t.template_id,
            tag_name=t.tag_name,
            version_id=t.version_id,
            version=t.version.version if t.version else None,
            meta_config=t.meta_config,
            updated_by=t.updated_by,
            updated_at=t.updated_at,
        )
        for t in tags
    ]

    return TagListResponse(items=items, total=len(items))


@router.post("/{name}/tags", response_model=PromptTagResponse)
async def set_tag(
    name: str,
    data: TagCreate,
    request: Request,
    current_user: User = Depends(require_any_role("Admin", "Editor")),
    db: AsyncSession = Depends(get_db),
):
    """设置标签（创建或更新）"""
    registry = PromptRegistryService(db)
    audit = AuditService(db)

    old_tag = await registry.get_tag(name, data.tag_name)
    old_value = {"version_id": old_tag.version_id, "meta_config": old_tag.meta_config} if old_tag else None

    tag = await registry.set_tag(name, data, actor=current_user.username)

    if not tag:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="设置标签失败，请检查模板和版本是否存在",
        )

    # 审计日志
    await audit.log(
        actor=current_user.username,
        action=AuditService.ACTION_TAG,
        resource_type=AuditService.RESOURCE_TAG,
        resource_id=tag.id,
        old_value=old_value,
        new_value=data.model_dump(),
        ip_address=request.client.host if request.client else None,
    )

    return PromptTagResponse(
        id=tag.id,
        template_id=tag.template_id,
        tag_name=tag.tag_name,
        version_id=tag.version_id,
        version=tag.version.version if tag.version else None,
        meta_config=tag.meta_config,
        updated_by=tag.updated_by,
        updated_at=tag.updated_at,
    )


@router.delete("/{name}/tags/{tag_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    name: str,
    tag_name: str,
    request: Request,
    current_user: User = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
):
    """删除标签"""
    registry = PromptRegistryService(db)
    audit = AuditService(db)

    tag = await registry.get_tag(name, tag_name)
    if not tag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"标签 '{tag_name}' 不存在",
        )

    await registry.delete_tag(name, tag_name)

    # 审计日志
    await audit.log(
        actor=current_user.username,
        action=AuditService.ACTION_DELETE,
        resource_type=AuditService.RESOURCE_TAG,
        resource_id=tag.id,
        ip_address=request.client.host if request.client else None,
    )


@router.post("/{name}/rollback", response_model=PromptTagResponse)
async def rollback(
    name: str,
    data: RollbackRequest,
    request: Request,
    current_user: User = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
):
    """回滚：将标签指向旧版本"""
    publisher = PromptPublisher(db)
    audit = AuditService(db)

    old_tag = await registry.get_tag(name, data.tag_name)
    old_value = {"version_id": old_tag.version_id} if old_tag else None

    success = await publisher.rollback(
        name,
        target_version_id=data.target_version_id,
        tag_name=data.tag_name,
        actor=data.actor or current_user.username,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="回滚失败，请检查版本是否存在",
        )

    # 审计日志
    await audit.log(
        actor=current_user.username,
        action=AuditService.ACTION_ROLLBACK,
        resource_type=AuditService.RESOURCE_TAG,
        resource_id=old_tag.id if old_tag else 0,
        old_value=old_value,
        new_value={"version_id": data.target_version_id, "tag_name": data.tag_name},
        ip_address=request.client.host if request.client else None,
    )

    tag = await registry.get_tag(name, data.tag_name)
    return PromptTagResponse(
        id=tag.id,
        template_id=tag.template_id,
        tag_name=tag.tag_name,
        version_id=tag.version_id,
        version=tag.version.version if tag.version else None,
        meta_config=tag.meta_config,
        updated_by=tag.updated_by,
        updated_at=tag.updated_at,
    )


# ==================== Evaluation ====================


@router.post("/{name}/eval", response_model=EvalReportResponse)
async def run_evaluation(
    name: str,
    data: EvalRequest,
    request: Request,
    current_user: User = Depends(require_any_role("Admin", "Editor")),
    db: AsyncSession = Depends(get_db),
):
    """运行离线评估（LLM-as-Judge）"""
    audit = AuditService(db)

    evaluator = PromptEvaluator(db)

    try:
        report = await evaluator.evaluate(
            candidate_version_id=data.candidate_version_id,
            baseline_version_id=data.baseline_version_id,
            test_case_ids=data.test_case_ids,
            judge_model=data.judge_model,
            triggered_by=data.triggered_by,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # 审计日志
    await audit.log(
        actor=current_user.username,
        action=AuditService.ACTION_EVAL,
        resource_type=AuditService.RESOURCE_VERSION,
        resource_id=data.candidate_version_id,
        new_value={
            "candidate_version_id": data.candidate_version_id,
            "baseline_version_id": data.baseline_version_id,
            "avg_score": report.avg_score,
            "passed": report.passed,
        },
        ip_address=request.client.host if request.client else None,
    )

    return EvalReportResponse(
        run_id=0,  # TODO: get from report
        version_id=report.version_id,
        baseline_version_id=report.baseline_version_id,
        avg_score=report.avg_score,
        delta=report.delta,
        pass_count=report.pass_count if hasattr(report, "pass_count") else None,
        fail_count=report.fail_count if hasattr(report, "fail_count") else None,
        total_count=len(report.results),
        passed=report.passed,
        detailed_results=[
            {
                "case_id": r.case_id,
                "score": r.score,
                "llm_output": r.llm_output,
                "reasoning": r.reasoning,
                "passed": r.passed,
            }
            for r in report.results
        ],
        run_at=datetime.utcnow(),
        triggered_by=data.triggered_by,
    )


# ==================== Test Cases ====================


@router.get("/{name}/test-cases", response_model=TestCaseListResponse)
async def list_test_cases(
    name: str,
    is_active: Optional[bool] = None,
    priority: Optional[int] = None,
    current_user: User = Depends(require_any_role("Admin", "Editor", "Viewer")),
    db: AsyncSession = Depends(get_db),
):
    """获取测试用例列表"""
    registry = PromptRegistryService(db)
    cases = await registry.list_test_cases(name, is_active=is_active, priority=priority)

    items = [
        TestCaseResponse(
            id=c.id,
            template_id=c.template_id,
            input_context=c.input_context,
            expected_output=c.expected_output,
            expected_behavior=c.expected_behavior,
            tags=c.tags,
            priority=c.priority,
            is_active=bool(c.is_active),
            created_by=c.created_by,
            created_at=c.created_at,
        )
        for c in cases
    ]

    return TestCaseListResponse(items=items, total=len(items))


@router.post("/{name}/test-cases", response_model=TestCaseResponse, status_code=status.HTTP_201_CREATED)
async def create_test_case(
    name: str,
    data: TestCaseCreate,
    request: Request,
    current_user: User = Depends(require_any_role("Admin", "Editor")),
    db: AsyncSession = Depends(get_db),
):
    """创建测试用例"""
    registry = PromptRegistryService(db)
    audit = AuditService(db)

    case = await registry.create_test_case(name, data, actor=current_user.username)

    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"模板 '{name}' 不存在",
        )

    # 审计日志
    await audit.log(
        actor=current_user.username,
        action=AuditService.ACTION_CREATE,
        resource_type=AuditService.RESOURCE_TEST_CASE,
        resource_id=case.id,
        new_value=data.model_dump(),
        ip_address=request.client.host if request.client else None,
    )

    return TestCaseResponse(
        id=case.id,
        template_id=case.template_id,
        input_context=case.input_context,
        expected_output=case.expected_output,
        expected_behavior=case.expected_behavior,
        tags=case.tags,
        priority=case.priority,
        is_active=bool(case.is_active),
        created_by=case.created_by,
        created_at=case.created_at,
    )


# ==================== Rendering ====================


@router.post("/{name}/render", response_model=RenderResponse)
async def render_prompt(
    name: str,
    data: RenderRequest,
    current_user: User = Depends(require_any_role("Admin", "Editor", "Viewer")),
    db: AsyncSession = Depends(get_db),
):
    """渲染提示词模板

    根据版本 ID 或标签（默认 stable）获取模板，并渲染变量
    """
    registry = PromptRegistryService(db)
    publisher = PromptPublisher(db)
    renderer = PromptRenderer()

    # 获取版本
    if data.version_id:
        version = await registry.get_version_by_id(data.version_id)
    else:
        version = await publisher.resolve_effective_version(name, user_id=current_user.username)

    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"模板 '{name}' 不存在或无可用版本",
        )

    # 渲染
    rendered, warnings = renderer.render(
        version.content, data.variables, version.variables_schema
    )

    return RenderResponse(
        rendered_content=rendered,
        version_id=version.id,
        version=version.version,
        warnings=warnings,
    )


# ==================== Audit Logs ====================


@router.get("/{name}/audit-logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    name: str,
    skip: int = 0,
    limit: int = 50,
    action: Optional[str] = None,
    current_user: User = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
):
    """获取模板相关的审计日志"""
    registry = PromptRegistryService(db)
    audit = AuditService(db)

    template = await registry.get_template(name)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"模板 '{name}' 不存在",
        )

    # 查询该模板相关的审计日志
    logs, total = await audit.list_logs(
        resource_type=AuditService.RESOURCE_TEMPLATE,
        resource_id=template.id,
        action=action,
        offset=skip,
        limit=limit,
    )

    items = [
        AuditLogResponse(
            id=log.id,
            actor=log.actor,
            action=log.action,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            old_value=log.old_value,
            new_value=log.new_value,
            created_at=log.created_at,
        )
        for log in logs
    ]

    return AuditLogListResponse(items=items, total=total)


from datetime import datetime
