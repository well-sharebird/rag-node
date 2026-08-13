"""主从编排 State 与结构化 Schema

State 使用 TypedDict，与之对齐 LangGraph；plan 输出用 Pydantic 结构化。
"""
from typing import Any, Dict, List, Optional, TypedDict

from pydantic import BaseModel, Field


class SubTask(BaseModel):
    """主 Agent 派发的单个子任务"""
    sub_agent_id: str = Field(description="子 Agent 的唯一标识")
    task_prompt: str = Field(description="分配给该子 Agent 的任务描述")


class OrchestrationPlan(BaseModel):
    """主 Agent 决策输出（结构化）"""
    need_sub_agents: bool = Field(description="是否需要调用子 Agent")
    run_mode: str = Field(
        default="serial",
        description="子任务执行方式：serial 串行 / parallel 并行",
    )
    plan: List[SubTask] = Field(default_factory=list, description="子任务列表")
    direct_answer: Optional[str] = Field(
        default=None, description="无需子 Agent 时，主 Agent 直接给出的回答"
    )


class SubAgentResult(BaseModel):
    """单个子 Agent 的执行结果"""
    sub_agent_id: str
    success: bool = True
    content: str = ""
    error: Optional[str] = None
    approvals: List[Dict[str, Any]] = Field(default_factory=list, description="需要的审批请求（HITL）")


class OrchestratorState(TypedDict):
    """主从编排运行 State"""
    messages: List[Dict[str, str]]            # 用户会话消息
    session_id: Optional[str]
    trace_id: Optional[str]
    main_agent_config: Optional[Dict[str, Any]]  # 主 Agent 配置
    temp_sub_config: Optional[Dict[str, Any]]    # 子 Agent 临时配置（子图内使用）
    sub_tasks: List[Dict[str, Any]]              # 主 Agent 派发的子任务
    sub_agent_results: List[Dict[str, Any]]      # 各子 Agent 结果
    final_answer: Optional[str]                  # 聚合后的最终回答
    error: Optional[str]                         # 顶层错误
