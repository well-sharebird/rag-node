"""
Agent 管理 API

执行逻辑统一使用 AgentExecutor：
- /api/v1/agents/{agent_id}/execute/stream - 单智能体执行
- /api/v1/agents/meta/execute/stream - Meta Agent 执行
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.agent import AgentConfig
from app.schemas.chat import (
    AgentCreate,
    AgentUpdate,
    AgentResponse,
    AgentListItem,
)
from app.services.agent_config_service import AgentConfigService
from app.services.agent_builder_service import AgentBuilderService
from app.services.model_gateway_service import ModelGatewayService
from app.services.skill_registry import RegistryService as SkillRegistryService
from app.services.agent_service import AgentService, AgentExecuteRequest, ExecutionMode, create_agent_service

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("", response_model=AgentResponse)
async def create_agent(
    data: AgentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建新的 Agent"""
    service = AgentConfigService(db)
    agent = await service.create(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        data=data,
    )
    return agent


@router.get("", response_model=list[AgentListItem])
async def list_agents(
    status: Optional[str] = Query(None),
    agent_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取用户的 Agent 列表"""
    service = AgentConfigService(db)
    agents, total = await service.list(
        user_id=current_user.id,
        status=status,
        agent_type=agent_type,
        skip=skip,
        limit=limit,
    )
    return agents


# ============================================================
# Subagent Management APIs (必须在{agent_id} 之前定义)
# ============================================================

class SubagentInfo(BaseModel):
    """子智能体信息"""
    type: str
    name: str
    description: str
    default_skills: list[str] = []


class RegisterSubagentRequest(BaseModel):
    """注册自定义子智能体请求"""
    name: str = Field(..., min_length=1)
    system_prompt: str = Field(..., min_length=10)
    skills: list[str] = Field(default_factory=list)
    model: dict = Field(..., description="模型配置 {provider, model}")


class RegisterSubagentResponse(BaseModel):
    """注册自定义子智能体响应"""
    id: str
    name: str
    type: str = "custom_subagent"


@router.get("/subagents", response_model=list[SubagentInfo])
async def list_subagents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取可用的子智能体列表"""
    model_gateway = ModelGatewayService(db)
    skill_registry = SkillRegistryService(db)
    agent_service = AgentService(
        db=db,
        model_gateway=model_gateway,
        skill_registry=skill_registry,
    )

    # TODO: 实现获取可用子智能体逻辑
    subagents = []
    return subagents


@router.post("/subagents", response_model=RegisterSubagentResponse)
async def register_subagent(
    data: RegisterSubagentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """注册自定义子智能体"""
    # TODO: 实现注册子智能体逻辑
    # 使用 AgentService 统一处理
    model_gateway = ModelGatewayService(db)
    skill_registry = SkillRegistryService(db)
    agent_service = AgentService(
        db=db,
        model_gateway=model_gateway,
        skill_registry=skill_registry,
    )

    return RegisterSubagentResponse(
        id="temp",
        name=data.name,
        type="custom_subagent",
    )


@router.get("/public", response_model=list[AgentListItem])
async def list_public_agents(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取广场公开的 Agent"""
    service = AgentConfigService(db)
    agents, total = await service.list_public(skip=skip, limit=limit)
    return agents


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取 Agent 详情"""
    service = AgentConfigService(db)
    agent = await service.get_by_id(agent_id, user_id=current_user.id)
    if not agent:
        # 尝试获取公开的 Agent
        agent = await service.get_by_id(agent_id)
        if not agent or not agent.is_public:
            raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    data: AgentUpdate,
    create_version: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新 Agent 配置"""
    service = AgentConfigService(db)
    agent = await service.update(
        agent_id=agent_id,
        user_id=current_user.id,
        data=data,
        create_version=create_version,
    )
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除 Agent"""
    service = AgentConfigService(db)
    success = await service.delete(agent_id, user_id=current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"message": "Agent deleted"}


@router.post("/{agent_id}/publish", response_model=AgentResponse)
async def publish_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """发布 Agent"""
    service = AgentConfigService(db)
    agent = await service.publish(agent_id, user_id=current_user.id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("/{agent_id}/unpublish", response_model=AgentResponse)
async def unpublish_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """取消发布 Agent"""
    service = AgentConfigService(db)
    agent = await service.unpublish(agent_id, user_id=current_user.id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("/{agent_id}/duplicate", response_model=AgentResponse)
async def duplicate_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """复制 Agent"""
    service = AgentConfigService(db)
    agent = await service.duplicate(
        agent_id=agent_id,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
    )
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


class AgentFromRequirementRequest(BaseModel):
    """根据需求创建 Agent 请求"""
    requirement: str = Field(..., min_length=10, description="用户需求描述")
    kb_ids: Optional[List[str]] = None


class AgentFromRequirementResponse(BaseModel):
    """根据需求创建 Agent 响应"""
    agent: AgentResponse
    analysis: dict


@router.post("/from-requirement", response_model=AgentFromRequirementResponse)
async def create_agent_from_requirement(
    data: AgentFromRequirementRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """根据用户需求自动创建智能体"""
    service = AgentBuilderService(db)

    agent, analysis = await service.create_agent_from_requirement(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        requirement=data.requirement,
        kb_ids=data.kb_ids,
    )

    return AgentFromRequirementResponse(
        agent=AgentResponse.model_validate(agent),
        analysis=analysis,
    )


# ============================================================
# Meta Agent APIs (自主智能体) - AI 助手超级入口
# ============================================================

class MetaAgentExecuteRequest(BaseModel):
    """Meta Agent 执行请求 - AI 助手超级入口

    Meta Agent 是系统的默认问答入口，可以：
    1. 分析用户需求，自主决策创建什么智能体
    2. 调用 create_agent 工具创建新智能体
    3. 调用 execute_agent 工具使用广场中的现有智能体
    4. 整合多个智能体的结果
    5. 支持 RAG 检索增强（绑定知识库）
    6. 支持用户选择模型

    示例：
    - "如何配置 SSL 证书？" → 调用文档检索智能体
    - "帮我分析这个项目" → 调用代码分析智能体
    - "创建产品经理和架构师两个智能体" → 创建多个智能体协作
    """
    query: str = Field(..., min_length=1, description="用户输入/任务描述")
    # RAG 相关参数
    kb_ids: Optional[list[str]] = Field(None, description="知识库 ID 列表（可选）")
    top_k: Optional[int] = Field(5, description="检索返回的文档片段数量")
    enable_rerank: Optional[bool] = Field(False, description="是否启用重排序")
    # 模型选择
    model_name: Optional[str] = Field(None, description="运行时选择的模型名称")


class MetaAgentExecuteResponse(BaseModel):
    """Meta Agent 执行响应"""
    response: str
    messages: list = []
    agents_used: list[str] = Field(default_factory=list, description="被调用的智能体 ID 列表")


@router.post("/meta/execute", response_model=MetaAgentExecuteResponse)
async def execute_meta_agent(
    data: MetaAgentExecuteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    执行 Meta Agent（自主智能体）- AI 助手超级入口

    使用统一的 AgentService 执行引擎
    """
    from app.services.agent_service import AgentExecuteRequest as ServiceAgentExecuteRequest

    model_gateway = ModelGatewayService(db)
    skill_registry = SkillRegistryService(db)
    agent_service = await create_agent_service(db, model_gateway, skill_registry)

    request = ServiceAgentExecuteRequest(
        query=data.query,
        user_id=current_user.id,
        tenant_id=str(current_user.tenant_id) if current_user.tenant_id else "default",
        agent_id=None,
        kb_ids=data.kb_ids,
        top_k=data.top_k,
        enable_rerank=data.enable_rerank,
        model_name=data.model_name,
        execution_mode=ExecutionMode.META,
    )

    result = await agent_service.execute(request)

    return MetaAgentExecuteResponse(
        response=result.response,
        messages=result.messages,
        agents_used=result.agents_used,
    )


@router.post("/meta/execute/stream")
async def execute_meta_agent_stream(
    data: MetaAgentExecuteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    流式执行 Meta Agent（SSE）- AI 助手超级入口

    使用统一的 AgentService 执行引擎

    支持：
    - 多 Agent 协作调度
    - RAG 检索增强
    - 用户选择模型
    - 实时 token 流式返回
    """
    from sse_starlette.sse import EventSourceResponse
    import json
    from app.services.model_gateway_service import ModelGatewayService
    from app.services.skill_registry import RegistryService as SkillRegistryService
    from app.services.agent_service import create_agent_service, AgentExecuteRequest as ServiceAgentExecuteRequest, ExecutionMode

    model_gateway = ModelGatewayService(db)
    skill_registry = SkillRegistryService(db)
    agent_service = await create_agent_service(db, model_gateway, skill_registry)

    request = ServiceAgentExecuteRequest(
        query=data.query,
        user_id=current_user.id,
        tenant_id=str(current_user.tenant_id) if current_user.tenant_id else "default",
        agent_id=None,
        kb_ids=data.kb_ids,
        top_k=data.top_k,
        enable_rerank=data.enable_rerank,
        model_name=data.model_name,
        execution_mode=ExecutionMode.META,
    )

    async def event_generator():
        try:
            async for chunk in agent_service.execute_stream(request):
                if chunk:
                    # chunk 已经是 JSON 字符串，直接返回
                    # EventSourceResponse 会自动添加 "data: " 前缀
                    yield chunk
            yield json.dumps({"type": "done"})
        except Exception as e:
            yield json.dumps({"type": "error", "error": str(e)})

    return EventSourceResponse(event_generator())


# ============================================================
# Agent Execution APIs (工厂模式) - 注意：这些路由在{agent_id}之后定义
# ============================================================

class AgentExecuteRequest(BaseModel):
    """执行 Agent 请求"""
    query: str = Field(..., min_length=1, description="用户输入/查询")
    model_name: Optional[str] = Field(None, description="运行时选择的模型名称")
    plan_mode: Optional[bool] = Field(False, description="是否启用计划模式")
    skills: Optional[list[str]] = Field(None, description="技能覆盖列表")
    mcp_servers: Optional[list[str]] = Field(None, description="MCP 服务器列表")
    session_id: Optional[str] = Field(None, description="会话 ID")
    # RAG 相关参数
    kb_ids: Optional[list[str]] = Field(None, description="知识库 ID 列表")
    top_k: Optional[int] = Field(5, description="检索返回的文档片段数量")
    enable_rerank: Optional[bool] = Field(False, description="是否启用重排序")


class AgentExecuteResponse(BaseModel):
    """执行 Agent 响应"""
    run_id: str
    response: str
    messages: list
    factory_mode: bool = True
    agent_type: str = "lead_agent"


class AgentExecuteStreamRequest(BaseModel):
    """流式执行 Agent 请求（支持调试模式）"""
    query: str = Field(..., min_length=1, description="用户输入/查询")
    model_name: Optional[str] = Field(None, description="运行时选择的模型名称")
    plan_mode: Optional[bool] = Field(False, description="是否启用计划模式")
    debug_mode: Optional[bool] = Field(False, description="是否启用调试模式（输出节点执行轨迹）")
    session_id: Optional[str] = Field(None, description="会话 ID")
    # RAG 相关参数
    kb_ids: Optional[list[str]] = Field(None, description="知识库 ID 列表")
    top_k: Optional[int] = Field(5, description="检索返回的文档片段数量")
    enable_rerank: Optional[bool] = Field(False, description="是否启用重排序")


@router.post("/{agent_id}/execute", response_model=AgentExecuteResponse)
async def execute_agent(
    agent_id: str,
    data: AgentExecuteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    执行 Agent（统一入口）

    使用统一的 AgentService 执行引擎
    """
    model_gateway = ModelGatewayService(db)
    skill_registry = SkillRegistryService(db)
    agent_service = await create_agent_service(db, model_gateway, skill_registry)

    request = AgentExecuteRequest(
        query=data.query,
        user_id=current_user.id,
        tenant_id=str(current_user.tenant_id) if current_user.tenant_id else "default",
        agent_id=agent_id,
        kb_ids=data.kb_ids,
        top_k=data.top_k,
        enable_rerank=data.enable_rerank,
        model_name=data.model_name,
        execution_mode=ExecutionMode.SINGLE,
    )

    result = await agent_service.execute(request)

    return AgentExecuteResponse(
        run_id=result.run_id,
        response=result.response,
        messages=result.messages,
        factory_mode=True,
        agent_type="single",
    )


@router.post("/{agent_id}/execute/stream")
async def execute_agent_stream(
    agent_id: str,
    data: AgentExecuteStreamRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """流式执行 Agent（SSE）- 支持调试模式"""
    from sse_starlette.sse import EventSourceResponse
    import json
    from app.services.agent_monitoring_service import AgentMonitoringService
    from app.services.agent_service import create_agent_service, AgentExecuteRequest, ExecutionMode

    runtime_config = {
        "model_name": data.model_name,
        "plan_mode": data.plan_mode,
        "kb_ids": data.kb_ids,
        "top_k": data.top_k,
        "enable_rerank": data.enable_rerank,
        "debug_mode": data.debug_mode,
    }

    model_gateway = ModelGatewayService(db)
    skill_registry = SkillRegistryService(db)
    agent_service = await create_agent_service(db, model_gateway, skill_registry)

    # 创建监控服务
    monitoring = AgentMonitoringService(db)

    async def event_generator():
        run_id = None
        try:
            # 开始执行轨迹追踪
            trace = monitoring.start_trace(agent_id=agent_id, user_id=current_user.id)
            run_id = trace.run_id

            # 如果启用调试模式，设置调试标记
            if data.debug_mode:
                monitoring.set_debug_mode(run_id, enabled=True)
                yield {
                    "event": "debug",
                    "data": json.dumps({"type": "debug_enabled", "run_id": run_id}),
                }

            request = AgentExecuteRequest(
                query=data.query,
                user_id=current_user.id,
                tenant_id=str(current_user.tenant_id) if current_user.tenant_id else "default",
                agent_id=agent_id,
                kb_ids=data.kb_ids,
                top_k=data.top_k,
                enable_rerank=data.enable_rerank,
                model_name=data.model_name,
                execution_mode=ExecutionMode.SINGLE,
            )

            async for chunk in agent_service.execute_stream(request):
                if chunk:
                    # chunk 已经是 JSON 字符串，直接返回
                    yield chunk

            # 结束追踪并发送统计
            completed_trace = monitoring.end_trace(run_id) if run_id else None
            yield json.dumps({
                "type": "done",
                "metrics": completed_trace.to_dict() if completed_trace else None,
            })
        except Exception as e:
            if run_id:
                trace = monitoring.get_trace(run_id)
                if trace:
                    trace.add_error(str(e))
                    monitoring.end_trace(run_id)

            yield json.dumps({"type": "error", "error": str(e)})

    return EventSourceResponse(event_generator())


# ============================================================
# Agent Model Config APIs
# ============================================================

class AgentModelConfigUpdate(BaseModel):
    """更新 Agent 模型配置请求"""
    provider: str = Field(..., description="模型供应商代码")
    model: str = Field(..., description="模型 ID")
    temperature: Optional[float] = Field(0.7, ge=0, le=2)
    max_tokens: Optional[int] = Field(4096, ge=1)
    top_p: Optional[float] = Field(0.9, ge=0, le=1)


class AgentModelConfigResponse(BaseModel):
    """Agent 模型配置响应"""
    id: str
    name: str
    default_model_config: Optional[dict]

    class Config:
        from_attributes = True
        json_encoders = {
            # UUID 自动转字符串
        }


@router.put("/{agent_id}/model-config", response_model=AgentModelConfigResponse)
async def update_agent_model_config(
    agent_id: str,
    data: AgentModelConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    保存 Agent 默认模型配置

    用户在聊天页面选择的模型配置可以保存为 Agent 的默认配置
    """
    from app.services.agent_config_service import AgentConfigService

    service = AgentConfigService(db)

    # 获取当前 Agent 配置
    agent = await service.get_by_id(agent_id, user_id=current_user.id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # 更新默认模型配置
    model_config = {
        "provider": data.provider,
        "model": data.model,
        "temperature": data.temperature,
        "max_tokens": data.max_tokens,
        "top_p": data.top_p,
    }

    # 直接更新数据库
    from sqlalchemy import update
    await db.execute(
        update(AgentConfig)
        .where(AgentConfig.id == agent_id)
        .values(default_model_config=model_config)
    )
    await db.commit()

    # 返回更新后的配置
    updated_agent = await service.get_by_id(agent_id, user_id=current_user.id)
    return AgentModelConfigResponse(
        id=str(updated_agent.id),
        name=updated_agent.name,
        default_model_config=updated_agent.default_model_config,
    )


@router.get("/{agent_id}/model-config", response_model=AgentModelConfigResponse)
async def get_agent_model_config(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取 Agent 默认模型配置
    """
    from app.services.agent_config_service import AgentConfigService

    service = AgentConfigService(db)
    agent = await service.get_by_id(agent_id, user_id=current_user.id)

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    return AgentModelConfigResponse(
        id=str(agent.id),
        name=agent.name,
        default_model_config=agent.default_model_config,
    )


