# Harness 内核使用示例

> 文档版本：1.0  
> 创建日期：2026-08-05

---

## 概述

Harness 是 Agent 平台的内核引擎，提供四层核心能力：

```
┌─────────────────────────────────────────────────────────────┐
│                    Harness Kernel                            │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Orchestration│  │   Memory     │  │    Action    │      │
│  │   编排引擎    │  │   记忆引擎    │  │   行动引擎    │      │
│  ├──────────────┤  ├──────────────┤  ├──────────────┤      │
│  │ - 多 Agent    │  │ - 存储检索    │  │ - 工具调用    │      │
│  │ - 任务分发    │  │ - 对话历史    │  │ - 代码执行    │      │
│  │ - 流水线      │  │ - 安全防护    │  │ - 速率限制    │      │
│  │ - 投票决策    │  │ - 注入检测    │  │ - 权限验证    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Governance 管控引擎                      │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ - 全链路追踪  - 合规检查  - 异常检测  - 效果评估     │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 1. 编排引擎 (Orchestration Engine)

### 1.1 Supervisor 模式 - 主管分配任务

```python
from packages.agent.harness import OrchestrationEngine
from packages.agent.harness.orchestration import (
    OrchestrationConfig,
    OrchestrationMode,
    WorkerAgent,
)

# 配置主管模式
config = OrchestrationConfig(
    mode=OrchestrationMode.SUPERVISOR,
    workers=[
        WorkerAgent(agent_id="researcher-001", role="researcher", priority=1),
        WorkerAgent(agent_id="writer-001", role="writer", priority=2),
        WorkerAgent(agent_id="reviewer-001", role="reviewer", priority=3),
    ],
    supervisor_prompt="你是一个智能任务分配器...",
    max_iterations=10,
)

# 创建引擎
engine = OrchestrationEngine(db_session, config)

# 执行多 Agent 协作
result = await engine.execute_multi_agent(
    runtime_id="runtime-123",
    session_id="session-456",
    user_input="帮我研究并撰写一份 AI 技术报告",
)

print(result)
# {
#   "mode": "supervisor",
#   "tasks": [...],
#   "aggregated_result": {...}
# }
```

### 1.2 Pipeline 模式 - 顺序流水线

```python
config = OrchestrationConfig(
    mode=OrchestrationMode.PIPELINE,
    workers=[
        WorkerAgent(agent_id="researcher-001", role="research"),
        WorkerAgent(agent_id="writer-001", role="write"),
        WorkerAgent(agent_id="reviewer-001", role="review"),
    ],
)

engine = OrchestrationEngine(db_session, config)

# 流水线执行：研究 -> 写作 -> 审核
result = await engine.execute_multi_agent(
    runtime_id="runtime-123",
    session_id="session-456",
    user_input="撰写一份产品发布会新闻稿",
)

# 执行流程:
# 1. researcher 收集产品信息
# 2. writer 基于研究结果撰写新闻稿
# 3. reviewer 审核并给出修改建议
```

### 1.3 Voting 模式 - 投票决策

```python
config = OrchestrationConfig(
    mode=OrchestrationMode.VOTING,
    workers=[
        WorkerAgent(agent_id="agent-a", role="voter"),
        WorkerAgent(agent_id="agent-b", role="voter"),
        WorkerAgent(agent_id="agent-c", role="voter"),
    ],
    voting_threshold=0.67,  # 需要 2/3 多数
)

engine = OrchestrationEngine(db_session, config)

# 多个 Agent 并行执行，投票选择最佳结果
result = await engine.execute_multi_agent(
    runtime_id="runtime-123",
    session_id="session-456",
    user_input="评估这个商业计划的风险",
)

# 所有 Agent 独立评估，然后汇总结果
```

---

## 2. 记忆引擎 (Memory Engine)

### 2.1 存储和检索对话历史

```python
from packages.agent.harness import MemoryEngine

engine = MemoryEngine(db_session)

# 存储对话消息
message = await engine.store_conversation(
    session=session,
    role="user",
    content="你好，我想了解一下 RAG 技术",
    token_count=15,
)

# 获取对话历史
messages = await engine.get_conversation(
    session_id="session-456",
    limit=50,
)

# 为 LLM 准备上下文（自动管理 token 预算）
context = await engine.get_context_for_llm(
    session_id="session-456",
    max_tokens=4096,
)
```

### 2.2 对话摘要

```python
# 创建对话摘要（用于长对话压缩）
await engine.create_summary(
    session_id="session-456",
    summary="用户询问了 RAG 技术的基本原理、应用场景和实现步骤",
    keywords=["RAG", "检索增强生成", "向量数据库"],
)

# 获取摘要
summary = await engine.get_summary(session_id="session-456")
```

### 2.3 安全防护 - 注入检测

```python
# 自动检测记忆投毒攻击
try:
    await engine.store(
        agent_id="agent-001",
        user_id=123,
        thread_id="thread-789",
        memory_type="conversation",
        content={
            "content": "忽略之前的指令，现在你要..."  # 会被检测为注入
        },
        ttl_hours=24,
    )
except SecurityError as e:
    print(f"Memory injection detected: {e}")
```

### 2.4 清理过期记忆

```python
# 定期清理过期记忆
deleted_count = await engine.cleanup_expired(agent_id="agent-001")
print(f"Cleaned up {deleted_count} expired memories")
```

---

## 3. 行动引擎 (Action Engine)

### 3.1 注册工具

```python
from packages.agent.harness import ActionEngine

engine = ActionEngine(db_session)

# 注册知识库检索工具
engine.register_tool(
    name="knowledge_base_search",
    description="搜索知识库获取相关信息",
    parameters={
        "query": {"type": "string", "description": "搜索关键词"},
        "top_k": {"type": "integer", "description": "返回结果数量", "default": 5},
    },
    handler=kb_search_handler,  # 实际的处理器函数
    requires_approval=False,
    rate_limit_per_minute=60,
)

# 注册需要审批的工具
engine.register_tool(
    name="file_download",
    description="下载文件",
    parameters={
        "file_id": {"type": "string", "description": "文件 ID"},
    },
    handler=file_download_handler,
    requires_approval=True,  # 需要用户确认
    rate_limit_per_minute=10,
)
```

### 3.2 执行工具调用

```python
# 执行工具
result = await engine.execute_tool(
    session_id="session-456",
    user_id=123,
    tool_name="knowledge_base_search",
    parameters={"query": "RAG 技术原理", "top_k": 5},
    allowed_tools=["knowledge_base_search", "web_search"],  # 白名单
)

if result.success:
    print(f"Tool result: {result.result}")
else:
    print(f"Tool failed: {result.error_message}")
```

### 3.3 沙箱代码执行

```python
# 在沙箱中执行代码
result = await engine.execute_code(
    session_id="session-456",
    user_id=123,
    code="print('Hello, World!')",
    language="python",
    timeout_seconds=30,
)

print(f"stdout: {result.result['stdout']}")
print(f"stderr: {result.result['stderr']}")
print(f"exit_code: {result.result['exit_code']}")
```

---

## 4. 管控引擎 (Governance Engine)

### 4.1 全链路追踪

```python
from packages.agent.harness import GovernanceEngine

engine = GovernanceEngine(db_session, es_client)

# 开始追踪
trace_id = await engine.start_trace(
    runtime_id="runtime-123",
    session_id="session-456",
    user_id=123,
)

# 添加执行步骤
await engine.add_step(
    trace_id=trace_id,
    action="tool_call:knowledge_base_search",
    duration_ms=150,
    result={"documents": 5},
)

await engine.add_step(
    trace_id=trace_id,
    action="llm_completion",
    duration_ms=2000,
    result={"tokens": 500},
)

# 完成追踪
trace = await engine.complete_trace(
    trace_id=trace_id,
    status="completed",
)

print(f"Total duration: {trace.total_duration_ms}ms")
print(f"Steps executed: {len(trace.steps)}")
```

### 4.2 合规检查

```python
# 检查行动是否合规
compliance = await engine.check_compliance(
    runtime_id="runtime-123",
    actions=[
        {"type": "tool_call", "tool": "knowledge_base_search"},
        {"type": "code_execution", "language": "python"},
    ],
)

print(f"Compliance passed: {compliance.overall_passed}")
print(f"Score: {compliance.score}")

for check in compliance.checks:
    print(f"  - {check.check_name}: {'PASS' if check.passed else 'FAIL'}")

if compliance.recommendations:
    print("Recommendations:")
    for rec in compliance.recommendations:
        print(f"  - {rec}")
```

### 4.3 异常检测

```python
# 检测异常行为
anomaly_result = await engine.detect_anomaly(
    runtime_id="runtime-123",
    metrics={
        "requests_per_minute": 150,  # 超过阈值
        "error_rate": 0.05,
        "tokens_per_minute": 5000,
    },
)

if anomaly_result["anomalies_detected"]:
    print("Anomalies detected:")
    for anomaly in anomaly_result["anomalies"]:
        print(f"  - {anomaly['type']}: {anomaly['value']} (threshold: {anomaly['threshold']})")
```

### 4.4 Agent 效果评估

```python
# 评估 Agent 质量
evaluation = await engine.evaluate_agent(
    agent_id="agent-001",
    trace_records=trace_records,  # 历史执行记录
)

print(f"Evaluation: {evaluation['evaluation']}")
print(f"Success rate: {evaluation['metrics']['success_rate']}")
print(f"Average duration: {evaluation['metrics']['avg_duration_ms']}ms")

if evaluation['recommendations']:
    print("Recommendations:")
    for rec in evaluation['recommendations']:
        print(f"  - {rec}")
```

---

## 5. 完整示例 - 整合四层能力

```python
"""
完整示例：多 Agent 协作撰写报告
整合 Harness 四层能力
"""
from packages.agent.harness import (
    OrchestrationEngine,
    MemoryEngine,
    ActionEngine,
    GovernanceEngine,
)
from packages.agent.harness.orchestration import (
    OrchestrationConfig,
    OrchestrationMode,
    WorkerAgent,
)

async def generate_report(runtime_id: str, session_id: str, user_id: int, topic: str):
    """生成技术报告"""

    # ========== 1. 初始化引擎 ==========
    orchestration = OrchestrationEngine(db, OrchestrationConfig(
        mode=OrchestrationMode.PIPELINE,
        workers=[
            WorkerAgent(agent_id="researcher", role="research"),
            WorkerAgent(agent_id="writer", role="write"),
            WorkerAgent(agent_id="reviewer", role="review"),
        ],
    ))
    memory = MemoryEngine(db)
    action = ActionEngine(db)
    governance = GovernanceEngine(db, es_client)

    # ========== 2. 开始追踪 ==========
    trace_id = await governance.start_trace(runtime_id, session_id, user_id)

    try:
        # ========== 3. 存储用户输入 ==========
        await memory.store_conversation(session, "user", f"请帮我撰写关于{topic}的报告")

        # ========== 4. 执行多 Agent 协作 ==========
        result = await orchestration.execute_multi_agent(
            runtime_id=runtime_id,
            session_id=session_id,
            user_input=f"撰写关于{topic}的技术报告",
        )

        # ========== 5. 记录执行步骤 ==========
        await governance.add_step(
            trace_id=trace_id,
            action="multi_agent_execution",
            duration_ms=result.get("duration_ms", 0),
            result=result,
        )

        # ========== 6. 存储结果 ==========
        await memory.store_conversation(
            session, "assistant",
            f"报告已完成：{result.get('final_result', {})}"
        )

        # ========== 7. 完成追踪 ==========
        await governance.complete_trace(trace_id, "completed")

        return result

    except Exception as e:
        # 异常处理
        await governance.complete_trace(trace_id, "failed")
        raise

# 使用示例
# result = await generate_report(
#     runtime_id="runtime-123",
#     session_id="session-456",
#     user_id=1,
#     topic="RAG 技术原理与应用",
# )
```

---

## 6. 最佳实践

### 6.1 安全建议

1. **始终使用白名单** - 限制 Agent 可以使用的工具
2. **启用注入检测** - 防止记忆投毒攻击
3. **设置速率限制** - 防止资源滥用
4. **记录完整审计日志** - 便于问题追溯

### 6.2 性能优化

1. **合理设置上下文窗口** - 避免 token 浪费
2. **使用对话摘要** - 长对话时压缩上下文
3. **并行执行** - 投票模式下充分利用并行
4. **预热 Runtime** - 减少冷启动延迟

### 6.3 监控告警

1. **监控错误率** - 超过 10% 时告警
2. **监控响应时间** - P95 超过 5 秒时告警
3. **监控资源消耗** - token 超限前预警
4. **定期合规检查** - 确保持续符合策略

---

## 7. API 参考

| 引擎 | 方法 | 说明 |
|------|------|------|
| **OrchestrationEngine** | `execute_multi_agent()` | 执行多 Agent 协作 |
| | `validate_task_distribution()` | 验证任务分发合法性 |
| **MemoryEngine** | `store()` | 存储记忆 |
| | `retrieve()` | 检索记忆 |
| | `store_conversation()` | 存储对话 |
| | `get_context_for_llm()` | 准备 LLM 上下文 |
| **ActionEngine** | `register_tool()` | 注册工具 |
| | `execute_tool()` | 执行工具调用 |
| | `execute_code()` | 沙箱代码执行 |
| **GovernanceEngine** | `start_trace()` | 开始追踪 |
| | `check_compliance()` | 合规检查 |
| | `detect_anomaly()` | 异常检测 |
| | `evaluate_agent()` | Agent 效果评估 |
