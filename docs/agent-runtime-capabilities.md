# Agent 运行时能力扩展方案

> 文档版本：1.0  
> 创建日期：2026-08-05  
> 状态：设计稿

---

## 1. 现状分析

### 1.1 当前架构

```
┌─────────────────────────────────────────────────────────────┐
│  当前架构                                                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  AgentConfig (配置)                                          │
│       │                                                      │
│       ├── AgentVersion (版本)                                │
│       ├── AgentMemory (记忆)                                 │
│       └── AgentCallLog (调用日志)                            │
│                                                              │
│  Conversation / ConversationMessage (对话)                    │
│                                                              │
│  ⚠️ 缺失：Runtime、Session、Workspace 概念                    │
│  ⚠️ 缺失：沙箱隔离机制                                        │
│  ⚠️ 缺失：Manifest 声明式配置                                 │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 与需求文档的差距

| 需求概念 | 当前状态 | 差距 |
|---------|---------|------|
| **Agent** | ✅ AgentConfig | 基本满足，需扩展 Manifest |
| **Runtime** | ❌ 缺失 | 需新增模型和服务 |
| **Session** | ❌ 缺失 (只有 Conversation) | 需新增模型 |
| **Workspace** | ❌ 缺失 | 需新增模型和文件系统 |
| **Harness** | ⚠️ 部分 (Memory 服务) | 需扩展四层能力 |
| **沙箱** | ❌ 缺失 | 需集成 Firecracker/nsjail |

---

## 2. 核心扩展：用户工作区 (Workspace)

### 2.1 为什么需要 Workspace？

根据安全分析文档 `shared-runtime-security-analysis.md`：

1. **文件越权防护** - 防止用户 A 访问用户 B 的文件
2. **代码执行隔离** - 代码执行限定在用户工作区内
3. **数据持久化** - 每个用户独立的存储空间
4. **审计追踪** - 按用户隔离文件访问日志

### 2.2 Workspace 数据模型

```python
# backend/packages/agent/models/workspace.py

class Workspace(Base):
    """用户工作区"""
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100))

    # 工作区根路径
    root_path: Mapped[str] = mapped_column(String(500), unique=True)
    # 示例：/workspace/users/123/

    # 配额限制
    storage_quota_bytes: Mapped[int] = mapped_column(BigInteger, default=10GB)
    storage_used_bytes: Mapped[int] = mapped_column(BigInteger, default=0)

    # 状态
    status: Mapped[str] = mapped_column(String(20), default="active")
    # active, suspended, deleted

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, onupdate=datetime.utcnow)


class WorkspaceFile(Base):
    """工作区文件索引"""
    __tablename__ = "workspace_files"

    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    runtime_id: Mapped[Optional[str]] = mapped_column(ForeignKey("agent_runtimes.id"))
    session_id: Mapped[Optional[str]] = mapped_column(ForeignKey("agent_sessions.id"))

    # 文件信息
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    # 相对于 workspace 根目录的路径

    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String(200))

    # 安全标记
    is_sandbox_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    # 是否由沙箱代码生成

    scan_status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending, clean, malicious, error

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('workspace_id', 'relative_path', name='uq_workspace_file_path'),
    )
```

### 2.3 Workspace 文件系统结构

```
/workspace/
├── users/
│   ├── 1/                          # user_id=1
│   │   ├── workspace/              # Workspace.root_path
│   │   │   ├── sessions/
│   │   │   │   ├── {session_id_1}/
│   │   │   │   │   ├── sandbox/    # 代码执行沙箱目录
│   │   │   │   │   ├── uploads/    # 用户上传文件
│   │   │   │   │   └── outputs/    # 代码执行输出
│   │   │   │   └── {session_id_2}/
│   │   │   ├── knowledge_bases/    # 知识库文件
│   │   │   └── agents/             # Agent 配置
│   │   └── audit/                  # 审计日志
│   └── 2/
├── shared/                         # 共享资源 (只读)
│   └── system_agents/
└── tmp/                            # 临时文件 (定期清理)
```

### 2.4 Workspace 安全服务

```python
# backend/packages/agent/services/workspace_security.py

class WorkspaceSecurityService:
    """工作区安全服务"""

    async def resolve_path(
        self,
        workspace: Workspace,
        requested_path: str,
        session_id: Optional[str] = None,
    ) -> str:
        """
        解析文件路径，防止越权访问

        安全措施：
        1. 规范化路径 (消除 ../)
        2. 验证路径在 workspace 根目录内
        3. 检查符号链接
        4. 可选：限定在特定 session 目录
        """
        # 实现见 shared-runtime-security-analysis.md 第 5.3 节
        pass

    async def check_quota(
        self,
        workspace: Workspace,
        required_bytes: int,
    ) -> bool:
        """检查存储配额"""
        pass

    async def scan_file(
        self,
        file: WorkspaceFile,
    ) -> ScanResult:
        """文件安全扫描 (恶意代码检测)"""
        pass
```

---

## 3. 核心扩展：Runtime 和 Session

### 3.1 Runtime 数据模型

```python
# backend/packages/agent/models/runtime.py

class AgentRuntime(Base):
    """
    Agent 运行时实例

    每个 Runtime 代表一个独立的 Agent 运行环境，包含：
    - 沙箱实例 (Firecracker VM 或 nsjail 容器)
    - Manifest 配置
    - 一个或多个 Session
    """
    __tablename__ = "agent_runtimes"

    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)

    # 关联
    agent_id: Mapped[str] = mapped_column(ForeignKey("agent_configs.id"), nullable=False)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False)

    # Manifest (声明式配置)
    manifest: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # {
    #   "agent_id": "...",
    #   "model_config": {...},
    #   "system_prompt": "...",
    #   "enabled_tools": [...],
    #   "workspace": {...},
    #   "security_policy": {...}
    # }

    # 沙箱信息
    sandbox_type: Mapped[str] = mapped_column(String(20), default="firecracker")
    # firecracker, nsjail, docker, process
    sandbox_id: Mapped[Optional[str]] = mapped_column(String(200))
    # 沙箱实例 ID (VM ID 或容器 ID)

    # 状态
    status: Mapped[str] = mapped_column(String(20), default="initializing")
    # initializing, running, sleeping, stopped, failed

    # 资源使用
    resource_usage: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {cpu_percent: 10, memory_mb: 128, disk_mb: 50}

    # 生命周期
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    idle_timeout_seconds: Mapped[int] = mapped_column(Integer, default=900)  # 15 分钟
    auto_sleep_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, onupdate=datetime.utcnow)

    # 关系
    sessions = relationship("AgentSession", back_populates="runtime", cascade="all")
    agent = relationship("AgentConfig")
    workspace = relationship("Workspace")
```

### 3.2 Session 数据模型

```python
# backend/packages/agent/models/session.py

class AgentSession(Base):
    """
    Agent 会话实例

    代表用户与 Agent 的一次完整交互过程
    """
    __tablename__ = "agent_sessions"

    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)

    # 关联
    runtime_id: Mapped[str] = mapped_column(ForeignKey("agent_runtimes.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    # 会话令牌 (安全)
    session_token_hash: Mapped[str] = mapped_column(String(64), index=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # 上下文管理
    context_window_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    context_used_tokens: Mapped[int] = mapped_column(Integer, default=0)

    # 状态
    status: Mapped[str] = mapped_column(String(20), default="active")
    # active, archived, expired

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, onupdate=datetime.utcnow)

    # 关系
    runtime = relationship("AgentRuntime", back_populates="sessions")
    messages = relationship("AgentSessionMessage", back_populates="session", cascade="all")

    # 索引
    __table_args__ = (
        Index('idx_session_user_runtime', 'user_id', 'runtime_id'),
        Index('idx_session_token', 'session_token_hash'),
    )


class AgentSessionMessage(Base):
    """会话消息"""
    __tablename__ = "agent_session_messages"

    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[str] = mapped_column(ForeignKey("agent_sessions.id"), nullable=False)

    # 消息内容
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user, assistant, system
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # 执行追踪
    tool_calls: Mapped[Optional[list[dict]]] = mapped_column(JSONB)
    # [{name: "code_interpreter", args: {...}, result: "..."}]

    # 资源引用
    referenced_files: Mapped[Optional[list[str]]] = mapped_column(JSONB)
    # [workspace_file_id, ...]

    # Token 统计
    token_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session = relationship("AgentSession", back_populates="messages")
```

### 3.3 Manifest 声明式配置

```python
# backend/packages/agent/schemas/manifest.py

from pydantic import BaseModel, Field
from typing import Optional, Literal

class ManifestSecurityPolicy(BaseModel):
    """Manifest 安全策略配置"""
    allowed_tools: list[str] = Field(default_factory=list)
    blocked_tools: list[str] = Field(default_factory=list)
    require_approval_tools: list[str] = Field(default_factory=list)

    max_code_execution_time_seconds: int = 30
    allow_network_access: bool = False
    allowed_external_domains: list[str] = Field(default_factory=list)

    max_file_upload_size_bytes: int = 50 * 1024 * 1024  # 50MB
    allowed_file_extensions: list[str] = Field(
        default=[".txt", ".md", ".csv", ".json", ".py"]
    )


class ManifestWorkspaceConfig(BaseModel):
    """Manifest 工作区配置"""
    root_path: str
    session_isolation: bool = True
    # True = 每个 session 独立目录


class AgentManifest(BaseModel):
    """
    Agent 声明式配置 (Manifest)

    这是 Runtime 的核心配置文件，定义了 Agent 的身份、能力和边界
    """
    # 基本信息
    agent_id: str
    name: str
    version: str = "1.0.0"

    # 模型配置
    model_config: dict = Field(
        default_factory=lambda: {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "temperature": 0.7,
            "max_tokens": 4096,
        }
    )

    # 核心配置
    system_prompt: str
    enabled_tools: list[str] = Field(default_factory=list)
    mcp_servers: list[str] = Field(default_factory=list)

    # 工作区配置
    workspace: ManifestWorkspaceConfig

    # 安全策略
    security_policy: ManifestSecurityPolicy

    # 记忆配置
    memory: dict = Field(
        default_factory=lambda: {
            "type": "hybrid",  # conversation, vector, hybrid
            "ttl_hours": 24,
            "max_turns": 50,
        }
    )

    # 扩展配置
    extensions: dict = Field(default_factory=dict)
```

---

## 4. Harness 四层能力扩展

### 4.1 编排引擎 (Orchestration)

```python
# backend/packages/agent/harness/orchestration.py

class OrchestrationEngine:
    """
    编排引擎

    负责多 Agent 协作、任务分发、流水线执行
    """

    async def execute_multi_agent(
        self,
        runtime: AgentRuntime,
        session: AgentSession,
        user_input: str,
    ) -> ExecutionResult:
        """
        执行多 Agent 协作

        支持模式：
        - supervisor: 主管分配任务给 Worker
        - round_robin: 轮流处理
        - voting: 多个 Agent 并行执行后投票
        - pipeline: 顺序流水线
        """
        pass

    async def validate_task_distribution(
        self,
        supervisor_agent: AgentConfig,
        worker_agent: AgentConfig,
        task: dict,
    ) -> ValidationResult:
        """
        验证任务分发合法性

        防止权限传递放大攻击
        """
        pass
```

### 4.2 记忆引擎 (Memory)

```python
# backend/packages/agent/harness/memory.py

class MemoryEngine:
    """
    记忆引擎

    负责记忆的存储、检索、清理
    """

    async def store(
        self,
        session: AgentSession,
        memory_type: Literal["conversation", "vector", "summary"],
        content: dict,
    ) -> str:
        """存储记忆"""
        pass

    async def retrieve(
        self,
        session: AgentSession,
        query: Optional[str] = None,
        limit: int = 10,
    ) -> list:
        """检索记忆"""
        pass

    async def sanitize_content(self, content: str) -> str:
        """
        记忆内容过滤

        防止记忆投毒攻击
        """
        pass

    async def detect_injection(self, content: str) -> bool:
        """检测记忆注入"""
        pass
```

### 4.3 行动引擎 (Action)

```python
# backend/packages/agent/harness/action.py

class ActionEngine:
    """
    行动引擎

    负责工具调用、外部 API 访问、代码执行
    """

    async def execute_tool(
        self,
        session: AgentSession,
        tool_name: str,
        parameters: dict,
    ) -> ToolResult:
        """
        执行工具调用

        安全措施：
        1. 验证工具在白名单内
        2. 检查参数安全
        3. 速率限制
        4. 审计日志
        """
        pass

    async def execute_code(
        self,
        session: AgentSession,
        code: str,
        language: str = "python",
    ) -> CodeExecutionResult:
        """
        在沙箱中执行代码

        使用 Firecracker 或 nsjail 隔离
        """
        pass
```

### 4.4 管控引擎 (Governance)

```python
# backend/packages/agent/harness/governance.py

class GovernanceEngine:
    """
    管控引擎

    负责全链路追踪、审计、合规检查
    """

    async def trace_execution(
        self,
        trace_id: str,
        runtime: AgentRuntime,
        session: AgentSession,
        steps: list[ExecutionStep],
    ) -> None:
        """记录执行轨迹"""
        pass

    async def check_compliance(
        self,
        runtime: AgentRuntime,
        actions: list[dict],
    ) -> ComplianceResult:
        """合规检查"""
        pass

    async def detect_anomaly(
        self,
        runtime: AgentRuntime,
        metrics: dict,
    ) -> AnomalyResult:
        """异常行为检测"""
        pass
```

---

## 5. 沙箱集成方案

### 5.1 Firecracker MicroVM

```python
# backend/packages/agent/sandbox/firecracker.py

class FirecrackerSandboxManager:
    """Firecracker MicroVM 沙箱管理器"""

    def __init__(self):
        self.vm_pool: dict[str, FirecrackerVM] = {}

    async def create_vm(
        self,
        runtime: AgentRuntime,
        workspace: Workspace,
    ) -> FirecrackerVM:
        """创建 MicroVM"""
        pass

    async def execute_code(
        self,
        vm: FirecrackerVM,
        code: str,
        timeout_seconds: int = 30,
    ) -> CodeExecutionResult:
        """在 VM 中执行代码"""
        pass

    async def cleanup_vm(self, vm: FirecrackerVM) -> None:
        """清理 VM"""
        pass
```

### 5.2 nsjail

```python
# backend/packages/agent/sandbox/nsjail.py

class NsJailSandboxManager:
    """nsjail 沙箱管理器"""

    async def execute_in_jail(
        self,
        workspace: Workspace,
        command: list[str],
        timeout_seconds: int = 30,
    ) -> ExecutionResult:
        """在 nsjail 中执行命令"""
        pass
```

---

## 6. 实施路线图

### Phase 1: 基础架构 (P0)

| 任务 | 说明 | 工作量 |
|------|------|--------|
| 数据模型设计 | Workspace、Runtime、Session 模型 | 2 天 |
| 文件系统隔离 | 用户工作区目录结构 + 路径验证 | 2 天 |
| Manifest 配置 | 声明式配置结构和验证 | 1 天 |
| 基础沙箱集成 | nsjail 集成 (轻量级) | 3 天 |

### Phase 2: Harness 核心 (P1)

| 任务 | 说明 | 工作量 |
|------|------|--------|
| 编排引擎 | 多 Agent 协作框架 | 3 天 |
| 记忆引擎 | 增强记忆服务 + 安全防护 | 2 天 |
| 行动引擎 | 工具调用安全框架 | 2 天 |
| 管控引擎 | 全链路追踪 | 2 天 |

### Phase 3: 高级沙箱 (P2)

| 任务 | 说明 | 工作量 |
|------|------|--------|
| Firecracker 集成 | MicroVM 沙箱 | 5 天 |
| 预热池管理 | Runtime 预热池 | 2 天 |
| 秒级 Fork | Copy-on-Write 支持 | 3 天 |

---

## 7. 总结

### 必须扩展的核心能力

1. **Workspace (用户工作区)** - 文件隔离的基础
2. **Runtime 模型** - 沙箱环境的抽象
3. **Session 模型** - 会话实例管理
4. **Manifest 配置** - 声明式安全策略
5. **沙箱集成** - Firecracker 或 nsjail
6. **Harness 四层** - 编排/记忆/行动/管控

### 安全优先级

```
P0 (必须):
- 用户工作区隔离
- 文件路径验证
- 基础沙箱 (nsjail)
- 工具调用白名单

P1 (重要):
- Harness 四层能力
- 全链路审计
- 记忆安全防护

P2 (增强):
- Firecracker MicroVM
- 预热池
- 高级异常检测
```
