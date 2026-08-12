"""
Agent 管理 API - Harness 架构

=============================================================
统一执行入口
=============================================================

POST /api/v1/agents/execute
    用户只需表达需求，Harness 自主决策使用哪个 Agent

POST /api/v1/agents/execute/stream
    流式版本，实时返回 token (SSE)

示例:
    # 简单问答 (Harness 自主选择)
    {"query": "你可以做什么？"}

    # 指定 Agent
    {"query": "帮我写脚本", "agent_id": "xxx"}

    # 绑定知识库
    {"query": "查询文档", "kb_ids": ["kb1", "kb2"]}
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from packages.core.database import get_db
from packages.core.auth import get_current_user
from packages.core.system.models.user import User
from packages.agent.models.agent import AgentConfig
from packages.agent.schemas.chat import (
    AgentCreate,
    AgentUpdate,
    AgentResponse,
    AgentListItem,
)
from packages.agent.services.agent_config_service import AgentConfigService
from packages.agent.services.agent_builder_service import AgentBuilderService
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


# Subagent 相关 API 已移除，使用 HarnessEngine 统一管理


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
# Harness Unified Execution APIs (统一执行入口)
# ============================================================

class AgentExecuteUnifiedRequest(BaseModel):
    """统一执行请求 - Harness 架构入口

    用户只需表达需求，Harness 负责选择最优执行策略：
    - 不传 agent_id → Harness 自主决策使用哪个 Agent
    - 传入 agent_id → 使用指定的 Agent

    示例：
    - {"query": "你可以做什么？"} → Harness 选择默认助手
    - {"query": "帮我写脚本", "agent_id": "xxx"} → 使用指定 Agent
    """
    query: str = Field(..., min_length=1, description="用户输入/任务描述")
    agent_id: Optional[str] = Field(None, description="可选：指定 Agent ID (不传时由 Harness 自主决策)")

    # RAG 相关参数
    kb_ids: Optional[list[str]] = Field(None, description="知识库 ID 列表（可选）")
    top_k: Optional[int] = Field(5, description="检索返回的文档片段数量")
    enable_rerank: Optional[bool] = Field(False, description="是否启用重排序")

    # 模型选择
    model_name: Optional[str] = Field(None, description="运行时选择的模型名称")

    # 会话管理
    session_id: Optional[str] = Field(None, description="会话 ID (用于记忆/上下文)")

    # 执行模式
    orchestrator: Optional[bool] = Field(False, description="是否启用主从编排模式（流式）")
    main_prompt: Optional[str] = Field(None, description="主 Agent 编排提示词（orchestrator 时可选）")


class AgentExecuteUnifiedResponse(BaseModel):
    """统一执行响应"""
    run_id: str
    response: str
    messages: list = []
    agent_id: Optional[str] = Field(None, description="实际使用的 Agent ID")
    agent_type: Optional[str] = Field(None, description="Agent 类型 (single/multi/meta)")
    agents_used: Optional[list[str]] = Field(None, description="被调用的子 Agent ID 列表 (多 Agent 场景)")


@router.post("/execute", response_model=AgentExecuteUnifiedResponse)
async def execute_agent_unified(
    data: AgentExecuteUnifiedRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    统一执行入口 - 主 Agent 调度

    一切请求由主 Agent 决策调度（可派生子 Agent 或直接回答）。
    """
    from packages.agent.orchestrator.graph import OrchestratorRuntime

    rt = OrchestratorRuntime(db, model_name=data.model_name, user_id=current_user.id)
    result = await rt.run(
        query=data.query,
        main_prompt=data.main_prompt,
        user_id=current_user.id,
    )

    return AgentExecuteUnifiedResponse(
        run_id=f"run_{int(__import__('time').time() * 1000)}",
        response=result["final_answer"],
        messages=[],
        agent_id=data.agent_id,
        agent_type="main_agent",
        agents_used=[r["sub_agent_id"] for r in result.get("sub_agent_results", [])],
    )


@router.post("/execute/stream")
async def execute_agent_unified_stream(
    data: AgentExecuteUnifiedRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    流式执行入口 (SSE) - Harness 架构

    支持：
    - Harness 自主决策 (不传 agent_id)
    - 指定 Agent 执行 (传入 agent_id)
    - 多 Agent 协作调度
    - RAG 检索增强
    - 实时 token 流式返回
    """
    from sse_starlette.sse import EventSourceResponse
    import json

    async def event_generator():
        try:
            # 统一由主 Agent 调度（一切请求走 OrchestratorRuntime）
            from packages.agent.orchestrator.graph import OrchestratorRuntime

            rt = OrchestratorRuntime(db, model_name=data.model_name, user_id=current_user.id)
            # orchestrator 字段语义：是否允许主 Agent 派生子 Agent（不传=允许自主）
            allow_sub = True if data.orchestrator is None else bool(data.orchestrator)
            async for event in rt.run_stream(
                query=data.query,
                main_prompt=data.main_prompt,
                run_mode="serial",
                user_id=current_user.id,
                allow_sub_agents=allow_sub,
                session_id=data.session_id,
            ):
                if event:
                    yield json.dumps(event, ensure_ascii=False)
            yield json.dumps({"type": "done"})
        except Exception as e:
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
    from packages.agent.services.agent_config_service import AgentConfigService

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
    from packages.agent.services.agent_config_service import AgentConfigService

    service = AgentConfigService(db)
    agent = await service.get_by_id(agent_id, user_id=current_user.id)

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    return AgentModelConfigResponse(
        id=str(agent.id),
        name=agent.name,
        default_model_config=agent.default_model_config,
    )


