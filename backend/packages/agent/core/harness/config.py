"""Harness 配置 - 统一配置面

- RuntimeConfig：执行治理配置（"怎么跑"：超时/递归上限/Token 预算/检查点/重试）
- CollaborationMode：协作模式枚举
- HarnessConfig：Harness 层业务配置（"怎么用"：协作模式/内置工具/领域配置），内嵌 RuntimeConfig
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Union, Literal
from enum import Enum

# 未显式传入 user_id 时的兜底用户（收敛分散在各处的 `or 1` 魔法数）
DEFAULT_USER_ID = 1


class RuntimeConfig(BaseModel):
    """Agent 运行时执行治理配置（生产环境基础设施需求：超时/重试/预算/检查点）。"""

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

    # LLM 默认（未显式指定模型/参数时的兜底，收敛 _create_llm 中的魔法数）
    default_model: str = "qwen3.5-397b-a17b"   # 默认模型
    llm_temperature: float = 0.3               # 默认采样温度
    llm_max_tokens: int = 2048                 # 默认最大生成长度

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


class CollaborationMode(str, Enum):
    """协作模式"""
    SUPERVISOR = "supervisor"      # 主管分配
    ROUND_ROBIN = "round_robin"    # 轮流处理
    VOTING = "voting"              # 投票决策
    PIPELINE = "pipeline"          # 顺序流水线
    PARALLEL = "parallel"          # 并行执行


class HarnessConfig(BaseModel):
    """
    Harness 层配置

    解决"怎么用"的问题 - 开箱即用的业务语义
    """

    # 运行时执行治理配置（默认注入 RuntimeConfig）
    runtime: Union[RuntimeConfig, dict] = Field(default_factory=RuntimeConfig)

    # 内置提示词模板
    system_prompt_template: Optional[str] = None

    # 启用的协作模式
    collaboration_modes: List[CollaborationMode] = Field(default_factory=list)

    # 内置工具
    enable_planning_tools: bool = False        # 规划工具 (Plan/Solve/Reflect)
    enable_rag_tools: bool = False             # RAG 检索工具
    enable_code_tools: bool = False            # 代码执行工具

    # 领域特定配置
    rag_config: Optional[dict] = None
    sandbox_config: Optional[dict] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "runtime": {"stream": True, "token_budget": 4096},
                "collaboration_modes": ["supervisor"],
                "enable_planning_tools": True,
                "enable_rag_tools": True,
            }
        }
    }

    def __init__(self, **kwargs):
        # dict 形式的 runtime 转换为 RuntimeConfig
        if kwargs.get("runtime") is None:
            kwargs["runtime"] = RuntimeConfig()
        elif isinstance(kwargs["runtime"], dict):
            kwargs["runtime"] = RuntimeConfig(**kwargs["runtime"])
        super().__init__(**kwargs)
