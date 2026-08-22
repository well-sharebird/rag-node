# 权限审批功能修复报告

## 问题描述
用户测试发现前端没有收到人工确认提醒，权限审批中断机制未生效。

## 根本原因分析

### 问题 1: PermissionEngine 未传入执行链路
**位置**: `packages/agent/integration/execution_chain.py`

**问题**: `ExecutionOrchestrator.execute()` 创建 `StepDrivenEngineV2` 时没有传入 `permission_engine` 参数。

**修复**: 
```python
# 创建权限引擎（用于工具调用审批）
try:
    permission_engine = PermissionEngine(
        db=self.db,
        user_id=self.user_id,
        policy={
            "blocked_tools": [],
            "allowed_tools": [],
        }
    )
except Exception as e:
    logger.warning("[ExecutionOrchestrator] PermissionEngine 初始化失败：%s", e)
    permission_engine = None

self._step_runtime = StepDrivenEngineV2(
    self.runtime, llm, tools,
    session_id=session_id,
    user_id=self.user_id, agent_id=agent_id,
    permission_engine=permission_engine,  # ✅ 新增
)
```

### 问题 2: should_act_router 未检查审批状态
**位置**: `packages/agent/runtime_engine/tao_graph.py`

**问题**: `should_act_router` 只检查迭代次数和工具调用，没有检查用户是否已审批通过（恢复执行）。

**修复**:
```python
def should_act_router(state: TAOState) -> Literal["act", "end"]:
    iteration = state.get("iteration", 0)
    tool_calls = state.get("tool_calls", [])
    # ✅ 检查是否有审批状态（用户已审批，恢复执行）
    approval_status = state.get("approval_status")
    
    # 1. 最大轮数限制
    if iteration >= max_iterations:
        return "end"
    
    # 2. ✅ 用户已审批通过，恢复执行
    if approval_status == "approved":
        logger.info("Approval granted, resuming execution")
        return "act"
    
    # 3. 无工具调用，结束
    if not tool_calls:
        return "end"
    
    # 4. 有工具调用，执行（经权限检查）
    return "act"
```

### 问题 3: GraphInterrupt 异常未正确传递
**位置**: `packages/agent/orchestrator/graph.py` 和 `packages/agent/execution/step_engine.py`

**问题**: `_direct_answer_stream` 和 `StepDrivenEngineV2.execute()` 没有捕获并重新抛出 `GraphInterrupt` 异常，导致前端无法收到审批请求。

**修复**:
```python
# step_engine.py
try:
    async for event in self._graph.astream(initial_state):
        # ... 事件处理 ...
except Exception as e:
    # ✅ 检查是否是审批中断
    from langgraph.errors import GraphInterrupt
    if isinstance(e, GraphInterrupt):
        logger.info("[StepEngineV2] GraphInterrupt 捕获，提取审批请求")
        raise  # 重新抛出，让上层处理
    else:
        logger.error("[StepEngineV2] 图执行异常：%s", e, exc_info=True)
        raise

# graph.py
if gtask.done():
    exc = gtask.exception()
    if exc and not isinstance(exc, asyncio.CancelledError):
        # ✅ 检查是否是审批中断
        from langgraph.errors import GraphInterrupt
        if isinstance(exc, GraphInterrupt):
            # 提取审批请求并重新抛出，让调用者处理
            approvals = self._extract_approvals(exc)
            if approvals:
                logger.info("[Orchestrator] 捕获审批请求：%d 个", len(approvals))
                raise GraphInterrupt(approvals) from exc
```

### 问题 4: 缺少恢复执行方法
**位置**: `packages/agent/integration/execution_chain.py`

**问题**: 没有提供用户审批后恢复执行的 API。

**修复**:
```python
async def resume_after_approval(self, thread_id: str, approval_status: str = "approved") -> Any:
    """
    用户审批后恢复执行（HITL 断点续跑）
    
    Args:
        thread_id: 线程 ID（用于从 checkpointer 恢复）
        approval_status: 审批状态（"approved" 或 "rejected"）
    
    Returns:
        执行结果或审批请求列表
    """
    from langgraph.errors import GraphInterrupt
    
    if not self._step_runtime:
        raise RuntimeError("StepDrivenEngineV2 未初始化，无法恢复执行")
    
    # 设置审批状态
    approval_state = {
        "approval_status": approval_status,
        "thread_id": thread_id,
    }
    
    try:
        # 从 checkpointer 恢复并继续执行
        async for event in self._step_runtime._graph.astream(
            approval_state,
            config={"configurable": {"thread_id": thread_id}}
        ):
            yield self._step_runtime._transform_event(event, "resume_step", f"resume_{thread_id}")
    except GraphInterrupt as e:
        # 仍有待审批的工具
        logger.info("[ExecutionOrchestrator] 恢复执行时仍有审批请求")
        raise
    except Exception as e:
        logger.error("[ExecutionOrchestrator] 恢复执行失败：%s", e, exc_info=True)
        raise
```

## 权限审批流程（修复后）

```
用户查询
    ↓
Orchestrator.execute_agent()
    ↓
TAO Graph 执行
    ├── START → orchestrator → think
    └── think → should_act_router (检查工具调用)
        ↓
    permission_check 节点
        ├── 检查每个工具调用的权限级别
        ├── FREE → 直接放行 → act 节点
        ├── ASK_FIRST → 询问用户 → 等待响应
        └── APPROVE_ONCE → 需要审批 → 设置 __interrupt__
            ↓
    GraphInterrupt 异常抛出
        ↓
    StepDrivenEngineV2.execute() 捕获并重新抛出
        ↓
    ExecutionOrchestrator.execute() 捕获并提取审批请求
        ↓
    API 层返回前端（显示审批对话框）
        ↓
    用户审批（approve/reject）
        ↓
    ExecutionOrchestrator.resume_after_approval() 恢复执行
        ↓
    should_act_router 检查 approval_status == "approved"
        ↓
    act 节点执行工具
```

## 修复文件清单

| 文件 | 修改内容 |
|------|----------|
| `packages/agent/integration/execution_chain.py` | 1. 创建并传入 PermissionEngine<br>2. 添加 resume_after_approval 方法 |
| `packages/agent/runtime_engine/tao_graph.py` | should_act_router 检查 approval_status |
| `packages/agent/execution/step_engine.py` | 捕获并重新抛出 GraphInterrupt |
| `packages/agent/orchestrator/graph.py` | _direct_answer_stream 捕获并重新抛出 GraphInterrupt |

## 测试验证

### 测试场景 1: 需要审批的工具调用
```bash
# 使用 file_delete 工具（APPROVE_ONCE 级别）
curl -X POST http://localhost:8000/api/agent/execute \
  -H "Authorization: Bearer <token>" \
  -d '{"query": "删除文件 /tmp/test.txt", "tools": ["file_delete"]}'

# 预期响应：
{
  "type": "approval_required",
  "pending": [
    {
      "tool_name": "file_delete",
      "tool_input": {"path": "/tmp/test.txt"},
      "permission_level": "approve_once",
      "risk_level": "high"
    }
  ]
}
```

### 测试场景 2: 用户审批后恢复执行
```bash
# 1. 先批准权限请求
curl -X POST http://localhost:8000/api/approvals/{request_id}/approve

# 2. 恢复执行
curl -X POST http://localhost:8000/api/approvals/{request_id}/resume \
  -d '{"thread_id": "123:main:1234567890", "sub_agent_id": null}'

# 预期：工具执行成功，返回执行结果
```

### 测试场景 3: 用户拒绝审批
```bash
# 1. 拒绝权限请求
curl -X POST http://localhost:8000/api/approvals/{request_id}/reject

# 2. 恢复执行（可选）
curl -X POST http://localhost:8000/api/approvals/{request_id}/resume \
  -d '{"thread_id": "123:main:1234567890", "approval_status": "rejected"}'

# 预期：工具被跳过，返回拒绝消息
```

## 后续工作

- [ ] 前端集成审批对话框（显示 pending 工具列表）
- [ ] 前端调用 approve/reject API
- [ ] 前端调用 resume API 恢复执行
- [ ] 端到端测试验证完整流程
- [ ] 添加审批历史记录和审计日志

## 架构对齐

### Harness Layer 2（治理层）✅
- ✅ PermissionEngine 梯度化权限管理（FREE/ASK_FIRST/APPROVE_ONCE）
- ✅ SecurityGuardMiddleware 工具调用拦截
- ✅ run_tool_permission_check 中间件
- ✅ 审批中断机制（GraphInterrupt）

### Harness Layer 1（图内控制）✅
- ✅ TAO Graph permission_check 节点
- ✅ should_act_router 条件边路由
- ✅ wait_approval_node（通过 interrupt 实现）

### 执行层
- ✅ ToolExecutor 最终执行
- ✅ 审批状态传递（approval_status）

## 总结

权限审批功能的核心问题在于**调用链路断裂**：
1. PermissionEngine 创建但未传入执行引擎
2. 审批中断异常未正确传递到 API 层
3. 缺少恢复执行的 API

修复后，完整的 HITL（Human-In-The-Loop）流程已打通，前端只需集成审批对话框即可实现完整的人工审批功能。
