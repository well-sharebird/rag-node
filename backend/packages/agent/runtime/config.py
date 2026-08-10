"""
Runtime 配置
"""
from pydantic import BaseModel, Field
from typing import Optional, Literal


class RuntimeConfig(BaseModel):
    """
    Agent 运行时配置

    解决"怎么跑"的问题 - 生产环境基础设施需求
    """

    # 执行模式
    stream: bool = False                    # 是否流式输出
    recursion_limit: int = 50              # LangGraph 递归限制
    timeout_seconds: int = 300             # 执行超时

    # Token 预算
    token_budget: int = 4096               # 最大 Token 数
    reserve_tokens: int = 512              # 保留 Token 用于系统消息

    # 检查点配置
    checkpointer: Literal["database", "memory", "none"] = "database"

    # 中断配置
    interrupt_before: Optional[list[str]] = None  # 在哪些节点前中断
    interrupt_after: Optional[list[str]] = None   # 在哪些节点后中断

    # 重试配置
    max_retries: int = 3                   # 最大重试次数
    retry_delay_seconds: float = 1.0       # 重试延迟

    model_config = {
        "json_schema_extra": {
            "example": {
                "stream": True,
                "recursion_limit": 50,
                "timeout_seconds": 300,
                "token_budget": 4096,
                "checkpointer": "database",
            }
        }
    }


class HarnessConfig(BaseModel):
    """
    Harness 层配置

    解决"怎么用"的问题 - 开箱即用的业务语义
    """

    # 运行时配置
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)

    # 内置提示词模板
    system_prompt_template: Optional[str] = None

    # 启用的协作模式
    collaboration_modes: list[str] = Field(default_factory=list)
    # 支持：supervisor, round_robin, voting, pipeline, parallel

    # 内置工具
    enable_planning_tools: bool = False    # 规划工具 (Plan/Solve/Reflect)
    enable_rag_tools: bool = False         # RAG 检索工具
    enable_code_tools: bool = False        # 代码执行工具

    # 领域特定配置
    rag_config: Optional[dict] = None
    sandbox_config: Optional[dict] = None

    class Config:
        json_schema_extra = {
            "example": {
                "runtime": {"stream": True, "token_budget": 4096},
                "collaboration_modes": ["supervisor"],
                "enable_planning_tools": True,
            }
        }
