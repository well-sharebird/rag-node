# Agent Runtime 实现总结

> 文档版本：1.0  
> 创建日期：2026-08-05  
> 状态：完成

---

## 实现概览

本次实现完成了 Agent Runtime 的完整架构，包括：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Agent Runtime 架构                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  API Layer                                                           │   │
│  │  - /workspaces/*    工作区管理                                        │   │
│  │  - /runtimes/*      Runtime 生命周期                                  │   │
│  │  - /sessions/*      会话管理                                          │   │
│  │  - /code-execution  沙箱代码执行                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                     │                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Harness Engine Service (统一引擎)                                   │   │
│  │  - 整合编排/记忆/行动/管控四层能力                                    │   │
│  │  - 提供 execute() 和 execute_stream() 接口                            │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                     │                                       │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐            │
│  │ Orchestration   │  │    Memory       │  │    Action       │            │
│  │ 编排引擎         │  │    记忆引擎      │  │    行动引擎      │            │
│  │ - 5 种模式       │  │ - 存储检索       │  │ - 工具调用       │            │
│  │ - 任务分发       │  │ - 注入检测       │  │ - 代码执行       │            │
│  │ - 权限控制       │  │ - 过期清理       │  │ - 速率限制       │            │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘            │
│                                     │                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              Governance 管控引擎                                      │   │
│  │  - 全链路追踪  - 合规检查  - 异常检测  - 效果评估                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                     │                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Sandbox Layer                                                       │   │
│  │  - NsJailSandboxManager: 轻量级进程隔离                               │   │
│  │  - FirecrackerSandboxManager: MicroVM 完全隔离                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                     │                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Runtime Preheat Pool                                                │   │
│  │  - 预热池管理  - 快速启动  - CoW Fork  - 自动扩缩容                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 已完成的功能

### 1. 数据模型 (8 个表)

| 表名 | 说明 | 关键字段 |
|------|------|---------|
| `workspaces` | 用户工作区 | root_path, storage_quota, status |
| `workspace_files` | 文件索引 | relative_path, file_size, scan_status |
| `workspace_audit_logs` | 审计日志 | action, file_path, success |
| `agent_runtimes` | Runtime 实例 | manifest, sandbox_id, status |
| `agent_runtime_events` | 事件日志 | event_type, event_data |
| `agent_sessions` | 会话实例 | session_token, context_tokens |
| `agent_session_messages` | 会话消息 | role, content, tool_calls |
| `agent_session_checkpoints` | 检查点 | checkpoint_data |

**迁移文件**: `012_add_agent_runtime_workspace.py`

---

### 2. Schema (Pydantic)

| Schema | 说明 |
|--------|------|
| `AgentManifest` | Agent 声明式配置 |
| `ManifestSecurityPolicy` | 安全策略 (工具白名单/命令限制/速率限制) |
| `ManifestWorkspaceConfig` | 工作区配置 |
| `ManifestMemoryConfig` | 记忆配置 |
| `ManifestModelConfig` | LLM 模型配置 |

---

### 3. 服务层

| 服务 | 文件 | 核心功能 |
|------|------|---------|
| `WorkspaceService` | `workspace_service.py` | 工作区管理、路径验证、配额检查、审计日志 |
| `RuntimeService` | `runtime_service.py` | Runtime 生命周期 (创建/启动/停止/休眠/唤醒) |
| `RuntimePreheatPool` | `runtime_preheat_pool.py` | 预热池、快速启动、CoW Fork、自动扩缩容 |
| `HarnessEngineService` | `harness_engine_service.py` | 统一引擎接口、整合四层能力 |

---

### 4. Harness 四层引擎

| 引擎 | 文件 | 核心能力 |
|------|------|---------|
| **Orchestration** | `orchestration.py` | 5 种模式：Supervisor/Round Robin/Voting/Pipeline/Parallel |
| **Memory** | `memory.py` | 存储/检索、对话历史、摘要、注入检测 |
| **Action** | `action.py` | 工具注册/调用、速率限制、沙箱代码执行 |
| **Governance** | `governance.py` | 全链路追踪、合规检查、异常检测、效果评估 |

---

### 5. 沙箱实现

| 沙箱 | 文件 | 隔离级别 | 启动时间 | 适用场景 |
|------|------|---------|---------|---------|
| **NsJail** | `nsjail.py` | 进程级 | 50-100ms | 轻量级代码执行 |
| **Firecracker** | `firecracker.py` | VM 级 | 100-500ms | 高安全需求 |

**NsJail 安全特性**:
- seccomp 系统调用过滤
- 用户/组映射到 nobody
- 网络命名空间隔离
- 资源限制 (CPU/内存/文件)

**Firecracker 安全特性**:
- 完整的内核级隔离
- 独立的文件系统
- 网络隔离 (可选)
- 与宿主机完全隔离

---

### 6. API 端点

#### Workspaces
```
GET    /api/v1/workspaces/me          # 获取我的工作区
GET    /api/v1/workspaces/{id}        # 获取工作区详情
GET    /api/v1/workspaces/{id}/files  # 列出文件
POST   /api/v1/workspaces/{id}/files  # 上传文件
GET    /api/v1/workspaces/{id}/files/{file_id}  # 下载文件
DELETE /api/v1/workspaces/{id}/files/{file_id}  # 删除文件
GET    /api/v1/workspaces/{id}/audit-logs       # 审计日志
```

#### Runtimes
```
POST   /api/v1/runtimes             # 创建 Runtime
GET    /api/v1/runtimes/{id}        # 获取详情
POST   /api/v1/runtimes/{id}/start  # 启动
POST   /api/v1/runtimes/{id}/stop   # 停止
POST   /api/v1/runtimes/{id}/sleep  # 休眠
POST   /api/v1/runtimes/{id}/wake   # 唤醒
GET    /api/v1/runtimes/{id}/sessions  # 列出会话
GET    /api/v1/runtimes/{id}/events    # 事件日志
DELETE /api/v1/runtimes/{id}         # 删除
```

#### Sessions
```
POST   /api/v1/sessions             # 创建会话
GET    /api/v1/sessions/{id}        # 获取详情
GET    /api/v1/sessions/{id}/messages  # 消息历史
POST   /api/v1/sessions/{id}/messages  # 创建消息
POST   /api/v1/sessions/{id}/archive   # 归档
POST   /api/v1/sessions/{id}/clear     # 清空消息
DELETE /api/v1/sessions/{id}          # 删除
```

#### Code Execution
```
POST   /api/v1/code-execution/execute  # 沙箱代码执行
```

---

## 使用示例

### 1. 创建 Runtime 并执行代码

```python
# 1. 创建工作区
workspace = await workspace_service.get_or_create_workspace(user)

# 2. 创建 Runtime
runtime = await runtime_service.create_runtime(agent, workspace)

# 3. 启动 Runtime
await runtime_service.start_runtime(runtime.id)

# 4. 创建会话
session = await create_session(runtime.id)

# 5. 执行代码
result = await execute_code_in_sandbox(
    code="print('Hello, World!')",
    language="python",
    workspace_path=workspace.root_path,
    timeout_seconds=30,
)
```

### 2. 使用 Harness 引擎

```python
from packages.agent.services.harness_engine_service import (
    HarnessEngineService,
    HarnessExecutionRequest,
)
from packages.agent.harness.orchestration import (
    OrchestrationConfig,
    OrchestrationMode,
    WorkerAgent,
)

# 配置多 Agent 协作
config = OrchestrationConfig(
    mode=OrchestrationMode.PIPELINE,
    workers=[
        WorkerAgent(agent_id="researcher", role="research"),
        WorkerAgent(agent_id="writer", role="write"),
        WorkerAgent(agent_id="reviewer", role="review"),
    ],
)

# 执行
service = HarnessEngineService(db)
request = HarnessExecutionRequest(
    runtime_id="runtime-123",
    session_id="session-456",
    user_id=1,
    user_input="撰写一份 AI 技术报告",
)

response = await service.execute(request, config)
print(f"Output: {response.output}")
```

### 3. 使用预热池

```python
from packages.agent.services.runtime_preheat_pool import (
    RuntimePreheatPool,
    PoolConfig,
    PoolStrategy,
)

# 配置预热池
config = PoolConfig(
    min_size=2,
    max_size=10,
    strategy=PoolStrategy.LRU,
    preheat_on_startup=True,
)

pool = RuntimePreheatPool(db, config)
await pool.initialize()

# 快速获取 Runtime
runtime = await pool.acquire(agent_id, workspace)

# 使用完毕释放
await pool.release(runtime.id)

# 查看统计
stats = await pool.get_stats()
print(f"Pool: {stats.available}/{stats.total_size} available")
```

---

## 安全特性

### 文件系统隔离
- 每用户独立工作区 `/workspace/users/{user_id}/`
- 路径验证防止 `../` 遍历
- 符号链接检测

### 代码执行隔离
- NsJail: seccomp 系统调用过滤
- Firecracker: VM 级完全隔离
- 网络访问默认禁止

### 记忆安全
- 注入检测 (防止记忆投毒)
- 内容过滤 (移除危险标记)
- 过期自动清理

### 行动控制
- 工具白名单
- 速率限制
- 需要审批的工具

### 审计追踪
- 完整的文件访问日志
- 代码执行日志
- 全链路执行追踪

---

## 性能优化

### 预热池
- 预创建 Runtime 减少冷启动
- LRU 策略回收空闲资源
- 自动扩缩容

### Copy-on-Write Fork
- 秒级复制 Runtime
- 文件系统级别优化

### 记忆管理
- Token 预算管理
- 对话摘要压缩上下文
- 向量检索 (可选)

---

## 文件结构

```
backend/packages/agent/
├── models/
│   ├── workspace.py          # 工作区模型
│   ├── runtime.py            # Runtime 模型
│   └── session.py            # Session 模型
├── schemas/
│   └── manifest.py           # Manifest Schema
├── services/
│   ├── workspace_service.py  # 工作区服务
│   ├── runtime_service.py    # Runtime 服务
│   ├── runtime_preheat_pool.py  # 预热池
│   └── harness_engine_service.py  # Harness 引擎
├── sandbox/
│   ├── nsjail.py             # NsJail 沙箱
│   └── firecracker.py        # Firecracker 沙箱
├── harness/
│   ├── orchestration.py      # 编排引擎
│   ├── memory.py             # 记忆引擎
│   ├── action.py             # 行动引擎
│   └── governance.py         # 管控引擎
├── api/
│   ├── workspaces.py         # 工作区 API
│   ├── runtimes.py           # Runtime API
│   ├── sessions.py           # Session API
│   └── code_execution.py     # 代码执行 API
└── models/__init__.py        # 模型导出
```

---

## 下一步建议

1. **集成测试** - 编写端到端测试验证完整流程
2. **性能基准** - 测试沙箱启动时间、执行延迟
3. **监控告警** - 集成 Prometheus/Grafana
4. **文档完善** - API 文档、用户指南
5. **生产部署** - Kubernetes 配置、 Helm Chart

---

## 参考资料

- [共享 Runtime 安全分析](./shared-runtime-security-analysis.md)
- [Harness 使用示例](./harness-usage-example.md)
- [Agent Runtime 能力扩展](./agent-runtime-capabilities.md)
