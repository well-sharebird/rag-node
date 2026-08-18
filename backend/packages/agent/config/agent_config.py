"""
Agent 配置 Schema

定义配置驱动架构的核心数据结构
"""
from enum import Enum
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, field_validator


# ========== 枚举类型 ==========

class AgentType(str, Enum):
    """Agent 类型"""
    SINGLE = "single"
    SUPERVISOR = "supervisor"
    ROUND_ROBIN = "round_robin"
    VOTING = "voting"
    PIPELINE = "pipeline"
    PARALLEL = "parallel"


class RunMode(str, Enum):
    """运行模式"""
    SERIAL = "serial"
    PARALLEL = "parallel"


class SandboxType(str, Enum):
    """沙箱类型"""
    NSJAIL = "nsjail"
    FIRECRACKER = "firecracker"
    DOCKER = "docker"
    PROCESS = "process"  # 开发模式


class PermissionMode(str, Enum):
    """权限模式"""
    AUTO = "auto"  # 自动放行
    HITL = "hitl"  # 人工审批
    BLOCKED = "blocked"  # 完全禁止


# ========== 模型配置 ==========

class ModelConfig(BaseModel):
    """LLM 模型配置"""
    provider: str = Field(..., description="模型提供商", examples=["openai", "anthropic", "deepseek"])
    model: str = Field(..., description="模型名称", examples=["gpt-4", "claude-3", "deepseek-v4"])
    temperature: float = Field(default=0.7, ge=0, le=2, description="温度参数")
    max_tokens: Optional[int] = Field(default=None, gt=0, description="最大 token 数")
    top_p: Optional[float] = Field(default=None, ge=0, le=1, description="Top-p 采样")
    frequency_penalty: Optional[float] = Field(default=None, ge=-2, le=2)
    presence_penalty: Optional[float] = Field(default=None, ge=-2, le=2)


# ========== 工具配置 ==========

class ToolConfig(BaseModel):
    """工具配置"""
    name: str = Field(..., description="工具名称")
    enabled: bool = Field(default=True, description="是否启用")
    config: dict[str, Any] = Field(default_factory=dict, description="工具特定配置")
    permission_mode: PermissionMode = Field(default=PermissionMode.AUTO, description="权限模式")


# ========== 安全策略 ==========

class SecurityPolicy(BaseModel):
    """安全策略配置"""
    sandbox_type: SandboxType = Field(default=SandboxType.NSJAIL, description="沙箱类型")
    network_enabled: bool = Field(default=False, description="是否启用网络")
    file_read_paths: list[str] = Field(default_factory=list, description="允许读取的路径")
    file_write_paths: list[str] = Field(default_factory=list, description="允许写入的路径")
    max_memory_mb: int = Field(default=512, gt=0, description="最大内存 (MB)")
    max_disk_mb: int = Field(default=100, gt=0, description="最大磁盘 (MB)")
    timeout_seconds: int = Field(default=30, gt=0, description="超时时间 (秒)")


# ========== TAO 循环配置 ==========

class TAOLoopConfig(BaseModel):
    """TAO 循环配置"""
    max_iterations: int = Field(default=10, gt=0, description="最大迭代次数")
    enable_think: bool = Field(default=True, description="是否启用思考")
    enable_act: bool = Field(default=True, description="是否启用行动")
    enable_observe: bool = Field(default=True, description="是否启用观察")
    think_system_prompt: Optional[str] = Field(default=None, description="思考系统提示")


# ========== 子 Agent 配置 ==========

class SubAgentConfig(BaseModel):
    """子 Agent 配置"""
    id: str = Field(..., description="子 Agent ID")
    task_prompt: str = Field(..., description="任务描述")
    tools_whitelist: list[str] = Field(default_factory=list, description="工具白名单")
    timeout_seconds: int = Field(default=60, gt=0, description="超时时间")


# ========== 主 Agent 配置 ==========

class MainAgentConfig(BaseModel):
    """主 Agent 配置"""
    orchestrator_prompt: str = Field(
        default="""你是任务编排主 Agent。根据用户的请求，判断是否需要派发给子 Agent 执行。

如果需要子 Agent，输出 JSON（严格键名）：
{
  "need_sub_agents": true,
  "run_mode": "serial" 或 "parallel",
  "plan": [
    {"sub_agent_id": "<子 agent 的 id>", "task_prompt": "<给该子 agent 的任务描述>"}
  ]
}

如果无需子 Agent，输出：
{
  "need_sub_agents": false,
  "plan": [],
  "direct_answer": "<你直接给出的回答>"
}

只输出 JSON，不要额外文字。
""",
        description="编排器提示词"
    )
    aggregate_prompt: str = Field(
        default="""你根据以下多个子 Agent 的执行结果，综合整理成一份面向用户的最终回答。

子 Agent 结果：
{results}

请给出清晰、完整的最终回答。
""",
        description="聚合提示词"
    )
    sub_agents: list[SubAgentConfig] = Field(default_factory=list, description="子 Agent 列表")


# ========== 运行时配置 ==========

class RuntimeConfig(BaseModel):
    """运行时配置"""
    timeout_seconds: int = Field(default=300, gt=0, description="总超时时间 (秒)")
    recursion_limit: int = Field(default=25, gt=0, description="递归限制")
    token_budget: Optional[int] = Field(default=None, gt=0, description="Token 预算")
    enable_streaming: bool = Field(default=True, description="是否启用流式")
    enable_checkpointer: bool = Field(default=False, description="是否启用检查点")
    redact_pii: bool = Field(default=True, description="是否脱敏 PII")


# ========== 完整 Agent 配置 ==========

class AgentConfig(BaseModel):
    """
    Agent 完整配置
    
    配置驱动架构的核心数据结构
    """
    # 基础信息
    id: str = Field(..., description="Agent ID")
    name: str = Field(..., description="Agent 名称")
    version: str = Field(default="1.0.0", description="版本号")
    description: Optional[str] = Field(default=None, description="描述")
    
    # 类型和模式
    agent_type: AgentType = Field(default=AgentType.SINGLE, description="Agent 类型")
    run_mode: RunMode = Field(default=RunMode.SERIAL, description="运行模式")
    
    # 模型配置
    model: ModelConfig = Field(..., description="LLM 模型配置")
    
    # 系统提示
    system_prompt: str = Field(..., description="系统提示词")
    
    # 工具配置
    tools: list[ToolConfig] = Field(default_factory=list, description="工具列表")
    
    # TAO 循环配置
    tao_loop: TAOLoopConfig = Field(default_factory=TAOLoopConfig, description="TAO 循环配置")
    
    # 主 Agent 配置（多 Agent 场景）
    main_agent: Optional[MainAgentConfig] = Field(default=None, description="主 Agent 配置")
    
    # 安全策略
    security: SecurityPolicy = Field(default_factory=SecurityPolicy, description="安全策略")
    
    # 运行时配置
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig, description="运行时配置")
    
    # 元数据
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")
    
    @field_validator('tools')
    @classmethod
    def validate_tools_unique(cls, v):
        """验证工具名称唯一性"""
        names = [t.name for t in v]
        if len(names) != len(set(names)):
            raise ValueError("工具名称必须唯一")
        return v


# ========== 配置加载器 ==========

class AgentConfigLoader:
    """
    Agent 配置加载器
    
    支持从多种来源加载配置：
    - YAML 文件
    - JSON 文件
    - 数据库
    - 环境变量
    """
    
    @staticmethod
    def from_yaml(yaml_str: str) -> AgentConfig:
        """从 YAML 字符串加载配置"""
        import yaml
        data = yaml.safe_load(yaml_str)
        return AgentConfig(**data)
    
    @staticmethod
    def from_json(json_str: str) -> AgentConfig:
        """从 JSON 字符串加载配置"""
        import json
        data = json.loads(json_str)
        return AgentConfig(**data)
    
    @staticmethod
    def from_file(file_path: str) -> AgentConfig:
        """从文件加载配置"""
        import json
        import yaml
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if file_path.endswith('.yaml') or file_path.endswith('.yml'):
            data = yaml.safe_load(content)
        elif file_path.endswith('.json'):
            data = json.loads(content)
        else:
            raise ValueError(f"Unsupported file format: {file_path}")
        
        return AgentConfig(**data)
    
    @staticmethod
    def from_dict(data: dict) -> AgentConfig:
        """从字典加载配置"""
        return AgentConfig(**data)
    
    @staticmethod
    def to_yaml(config: AgentConfig) -> str:
        """导出为 YAML"""
        import yaml
        return yaml.dump(config.model_dump(), allow_unicode=True, default_flow_style=False)
    
    @staticmethod
    def to_json(config: AgentConfig, indent: int = 2) -> str:
        """导出为 JSON"""
        import json
        return json.dumps(config.model_dump(), indent=indent, ensure_ascii=False)
