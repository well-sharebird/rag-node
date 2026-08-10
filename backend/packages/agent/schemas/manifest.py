"""
Agent Manifest 声明式配置 Schema

Manifest 是 Runtime 的核心配置文件，定义了 Agent 的身份、能力和边界
"""
from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator


class ManifestSecurityPolicy(BaseModel):
    """
    Manifest 安全策略配置

    定义 Agent 可以使用的工具、访问的资源、执行的操作
    """

    # 工具访问控制
    allowed_tools: list[str] = Field(
        default_factory=list,
        description="允许使用的工具白名单"
    )
    blocked_tools: list[str] = Field(
        default_factory=list,
        description="禁止使用的工具黑名单"
    )
    require_approval_tools: list[str] = Field(
        default_factory=list,
        description="需要用户确认才能使用的工具"
    )

    # 代码执行限制
    max_code_execution_time_seconds: int = Field(
        default=30,
        ge=1,
        le=300,
        description="代码执行最大时间 (秒)"
    )
    allow_network_access: bool = Field(
        default=False,
        description="是否允许网络访问"
    )
    allowed_external_domains: list[str] = Field(
        default_factory=list,
        description="允许访问的外部域名白名单"
    )

    # 文件操作限制
    max_file_upload_size_bytes: int = Field(
        default=50 * 1024 * 1024,  # 50MB
        ge=1,
        le=1024 * 1024 * 1024,  # 最大 1GB
        description="文件上传最大大小"
    )
    allowed_file_extensions: list[str] = Field(
        default=[".txt", ".md", ".csv", ".json", ".py"],
        description="允许的文件扩展名白名单"
    )
    allow_file_download: bool = Field(
        default=True,
        description="是否允许文件下载"
    )

    # 命令执行限制
    allowed_commands: list[str] = Field(
        default_factory=list,
        description="允许执行的系统命令白名单"
    )
    blocked_commands: list[str] = Field(
        default_factory=["rm", "sudo", "chmod", "chown"],
        description="禁止执行的系统命令黑名单"
    )

    # 速率限制
    max_requests_per_minute: int = Field(
        default=60,
        ge=1,
        le=1000,
        description="每分钟最大请求数"
    )
    max_tokens_per_minute: int = Field(
        default=100000,
        ge=1000,
        le=10000000,
        description="每分钟最大 token 数"
    )


class ManifestWorkspaceConfig(BaseModel):
    """
    Manifest 工作区配置

    定义 Agent 的工作区隔离策略
    """

    root_path: str = Field(
        ...,
        description="工作区根路径",
        min_length=1,
        max_length=500
    )
    session_isolation: bool = Field(
        default=True,
        description="是否启用 Session 级别隔离"
    )
    # True = 每个 session 有独立目录

    max_storage_bytes: int = Field(
        default=1024 * 1024 * 1024,  # 1GB
        ge=1,
        le=100 * 1024 * 1024 * 1024,  # 最大 100GB
        description="最大存储空间"
    )

    cleanup_on_destroy: bool = Field(
        default=True,
        description="Runtime 销毁时是否清理工作区"
    )


class ManifestMemoryConfig(BaseModel):
    """
    Manifest 记忆配置

    定义 Agent 的记忆存储策略
    """

    memory_type: Literal["conversation", "vector", "hybrid"] = Field(
        default="hybrid",
        description="记忆类型"
    )
    # conversation: 仅对话历史
    # vector: 向量记忆 (Milvus)
    # hybrid: 混合记忆

    ttl_hours: int = Field(
        default=24,
        ge=1,
        le=720,  # 最大 30 天
        description="记忆存活时间 (小时)"
    )

    max_turns: int = Field(
        default=50,
        ge=1,
        le=1000,
        description="最大对话轮数"
    )

    max_tokens: int = Field(
        default=4096,
        ge=512,
        le=32768,
        description="最大 token 数"
    )

    enable_summary: bool = Field(
        default=True,
        description="是否启用对话摘要"
    )


class ManifestModelConfig(BaseModel):
    """
    Manifest 模型配置

    定义 Agent 使用的默认模型配置
    """

    provider: str = Field(
        default="anthropic",
        description="模型提供商"
    )
    model: str = Field(
        default="claude-sonnet-4-6",
        description="模型名称"
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="温度参数"
    )
    max_tokens: int = Field(
        default=4096,
        ge=1,
        le=32768,
        description="最大输出 token 数"
    )
    top_p: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Top-p 采样参数"
    )


class AgentManifest(BaseModel):
    """
    Agent 声明式配置 (Manifest)

    这是 Runtime 的核心配置文件，定义了 Agent 的身份、能力和边界
    """

    # 基本信息
    agent_id: str = Field(..., description="关联的 Agent ID")
    name: str = Field(..., min_length=1, max_length=200, description="Agent 名称")
    version: str = Field(default="1.0.0", description="版本号")
    description: Optional[str] = Field(default=None, max_length=2000)

    # 模型配置
    llm_config: ManifestModelConfig = Field(
        default_factory=ManifestModelConfig,
        description="LLM 模型配置"
    )

    # 核心配置
    system_prompt: str = Field(
        ...,
        min_length=1,
        max_length=50000,
        description="系统提示词"
    )

    # 启用的能力
    enabled_tools: list[str] = Field(
        default_factory=list,
        description="启用的工具列表"
    )
    mcp_servers: list[str] = Field(
        default_factory=list,
        description="启用的 MCP 服务器列表"
    )

    # 工作区配置
    workspace: ManifestWorkspaceConfig

    # 安全策略
    security_policy: ManifestSecurityPolicy = Field(
        default_factory=ManifestSecurityPolicy,
        description="安全策略配置"
    )

    # 记忆配置
    memory: ManifestMemoryConfig = Field(
        default_factory=ManifestMemoryConfig,
        description="记忆配置"
    )

    # 沙箱配置
    sandbox_config: Optional[dict] = Field(
        default=None,
        description="沙箱具体配置"
    )
    # {
    #   "type": "nsjail" | "firecracker" | "docker",
    #   "memory_mb": 128,
    #   "vcpu_count": 1,
    #   "timeout_seconds": 30,
    #   ...
    # }

    # 扩展配置
    extensions: dict = Field(
        default_factory=dict,
        description="扩展配置"
    )
    # 用于存储自定义配置项

    @field_validator('enabled_tools')
    @classmethod
    def validate_tools(cls, v):
        """验证工具列表"""
        # 检查是否有冲突
        if any(tool in v for tool in ['admin_access', 'system_config']):
            raise ValueError("高危工具不能直接启用，需要特殊审批")
        return v
