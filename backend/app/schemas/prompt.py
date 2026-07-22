"""提示词模块 - Pydantic Schemas"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


# ==================== 请求 Schema ====================


class PromptTemplateCreate(BaseModel):
    """创建提示词模板"""

    name: str = Field(..., min_length=1, max_length=255, description="唯一标识名")
    description: Optional[str] = Field(None, description="描述用途")
    category: str = Field("system", description="分类：system | user | instruction")
    owner: Optional[str] = Field(None, description="负责人")


class PromptTemplateUpdate(BaseModel):
    """更新提示词模板（元数据）"""

    description: Optional[str] = None
    category: Optional[str] = None
    owner: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(active|archived)$")


class PromptVersionCreate(BaseModel):
    """创建新版本"""

    version: str = Field(
        ...,
        pattern=r"^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$",
        description="语义化版本号，如 1.0.0, 2.0.0-beta",
    )
    content: str = Field(..., min_length=1, description="提示词模板内容")
    variables_schema: List[Dict[str, Any]] = Field(
        default_factory=list, description="变量定义 [{name, type, required, default}]"
    )
    system_role: Optional[str] = Field(None, description="系统角色设定")
    changelog: Optional[str] = Field(None, description="变更说明")
    released_by: Optional[str] = Field(None, description="发布人")


class PromptVersionRelease(BaseModel):
    """发布版本（将 draft 改为 released）"""

    released_by: Optional[str] = None


class TagCreate(BaseModel):
    """创建/更新标签"""

    tag_name: str = Field(
        ..., pattern=r"^[a-z]+$", description="标签名：stable | beta | dev | canary"
    )
    version_id: int = Field(..., description="指向的版本 ID")
    meta_config: Dict[str, Any] = Field(
        default_factory=dict, description="灰度配置 {gray_percent, target_users}"
    )
    updated_by: Optional[str] = Field(None, description="操作人")


class TagUpdate(BaseModel):
    """更新标签配置"""

    meta_config: Optional[Dict[str, Any]] = None
    updated_by: Optional[str] = None


class EvalRequest(BaseModel):
    """运行评估请求"""

    candidate_version_id: int = Field(..., description="候选版本 ID")
    baseline_version_id: Optional[int] = Field(
        None, description="基线版本 ID（默认使用 stable）"
    )
    test_case_ids: Optional[List[int]] = Field(
        None, description="测试用例 ID 列表（默认使用全部 active 用例）"
    )
    judge_model: str = Field("gpt-4o", description="裁判模型")
    triggered_by: str = Field("manual", description="触发来源：manual | ci | pre_release")


class TestCaseCreate(BaseModel):
    """创建测试用例"""

    input_context: Dict[str, Any] = Field(..., description="输入上下文变量")
    expected_output: Optional[str] = Field(None, description="期望输出（精确匹配）")
    expected_behavior: Optional[str] = Field(None, description="期望行为描述")
    tags: List[str] = Field(default_factory=list, description="分类标签")
    priority: int = Field(1, ge=1, le=5, description="优先级 1-5")
    created_by: Optional[str] = Field(None, description="创建人")


class RenderRequest(BaseModel):
    """渲染请求"""

    version_id: Optional[int] = Field(None, description="版本 ID（不传则使用 stable）")
    variables: Dict[str, Any] = Field(..., description="变量值")


class RollbackRequest(BaseModel):
    """回滚请求"""

    target_version_id: int = Field(..., description="回滚目标版本 ID")
    tag_name: str = Field("stable", description="要回滚的标签")
    actor: str = Field(..., description="操作人")


# ==================== 响应 Schema ====================


class PromptTemplateResponse(BaseModel):
    """提示词模板响应"""

    id: int
    name: str
    description: Optional[str]
    category: str
    owner: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
    current_tags: Dict[str, str] = Field(
        default_factory=dict, description="当前标签 {tag_name: version}"
    )

    model_config = {"from_attributes": True}


class PromptVersionResponse(BaseModel):
    """提示词版本响应"""

    id: int
    template_id: int
    version: str
    content: str
    variables_schema: List[Dict[str, Any]]
    system_role: Optional[str]
    changelog: Optional[str]
    released_by: Optional[str]
    released_at: Optional[datetime]
    status: str
    latest_eval_score: Optional[float]
    eval_dataset_hash: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PromptTagResponse(BaseModel):
    """提示词标签响应"""

    id: int
    template_id: int
    tag_name: str
    version_id: int
    version: str = Field(..., description="版本号（冗余字段，方便查询）")
    meta_config: Dict[str, Any]
    updated_by: Optional[str]
    updated_at: datetime

    model_config = {"from_attributes": True}


class TestCaseResponse(BaseModel):
    """测试用例响应"""

    id: int
    template_id: int
    input_context: Dict[str, Any]
    expected_output: Optional[str]
    expected_behavior: Optional[str]
    tags: List[str]
    priority: int
    is_active: bool
    created_by: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class EvalResultItem(BaseModel):
    """评估结果单项"""

    case_id: int
    score: float
    llm_output: str
    reasoning: str
    passed: bool


class EvalReportResponse(BaseModel):
    """评估报告响应"""

    run_id: int
    version_id: int
    baseline_version_id: Optional[int]
    avg_score: Optional[float]
    delta: Optional[float] = Field(None, description="相对基线的提升")
    pass_count: Optional[int]
    fail_count: Optional[int]
    total_count: Optional[int]
    passed: bool = Field(..., description="整体是否通过")
    detailed_results: List[EvalResultItem]
    run_at: datetime
    triggered_by: str

    model_config = {"from_attributes": True}


class AuditLogResponse(BaseModel):
    """审计日志响应"""

    id: int
    actor: str
    action: str
    resource_type: str
    resource_id: int
    old_value: Optional[Dict[str, Any]]
    new_value: Optional[Dict[str, Any]]
    created_at: datetime

    model_config = {"from_attributes": True}


class RenderResponse(BaseModel):
    """渲染响应"""

    rendered_content: str
    version_id: int
    version: str
    warnings: List[str] = Field(default_factory=list)


# ==================== 列表响应 ====================


class TemplateListResponse(BaseModel):
    """模板列表响应"""

    items: List[PromptTemplateResponse]
    total: int


class VersionListResponse(BaseModel):
    """版本列表响应"""

    items: List[PromptVersionResponse]
    total: int


class TagListResponse(BaseModel):
    """标签列表响应"""

    items: List[PromptTagResponse]
    total: int


class TestCaseListResponse(BaseModel):
    """测试用例列表响应"""

    items: List[TestCaseResponse]
    total: int


class AuditLogListResponse(BaseModel):
    """审计日志列表响应"""

    items: List[AuditLogResponse]
    total: int
