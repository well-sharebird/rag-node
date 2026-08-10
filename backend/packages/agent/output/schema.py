"""输出 Schema 定义"""
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class OutputFormat(str, Enum):
    TEXT = "text"
    MARKDOWN = "markdown"
    JSON = "json"
    STRUCTURED = "structured"


class AgentOutput(BaseModel):
    """标准化 Agent 输出 Schema"""
    answer: str = Field(description="给用户的最终回答")
    format: OutputFormat = OutputFormat.TEXT
    sources: list[str] = Field(default=[], description="引用来源")
    confidence: float = Field(ge=0, le=1, default=1.0)
    metadata: dict = Field(default={}, description="额外元数据")


class GovernanceResult(BaseModel):
    """输出治理结果"""
    output: AgentOutput
    filtered: bool = False
    filtered_content: list[str] = []
    warnings: list[str] = []
    passed: bool = True
