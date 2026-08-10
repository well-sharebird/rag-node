"""
Harness 配置
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Union, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    from packages.agent.runtime.config import RuntimeConfig


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

    # 运行时配置 (延迟解析)
    runtime: Optional[Union["RuntimeConfig", dict]] = None

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
                "collaboration_modes": ["supervisor"],
                "enable_planning_tools": True,
                "enable_rag_tools": True,
            }
        }
    }

    def __init__(self, **kwargs):
        # 延迟导入 RuntimeConfig 避免循环依赖
        if "runtime" not in kwargs or kwargs["runtime"] is None:
            from packages.agent.runtime.config import RuntimeConfig
            kwargs["runtime"] = RuntimeConfig()
        # 如果是 dict，转换为 RuntimeConfig
        elif isinstance(kwargs["runtime"], dict):
            from packages.agent.runtime.config import RuntimeConfig
            kwargs["runtime"] = RuntimeConfig(**kwargs["runtime"])
        super().__init__(**kwargs)
