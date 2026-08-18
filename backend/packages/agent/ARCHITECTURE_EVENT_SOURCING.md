# 事件溯源架构文档

> 版本：1.0
> 日期：2026-08-14
> 参考：DeepSeek Harness Session 架构

---

## 一、什么是事件溯源

**事件溯源 (Event Sourcing)** 是一种架构模式，核心思想是：

> **状态是事件的投影，事件是唯一的真相来源**

与传统 CRUD 的区别：

| 传统 CRUD | 事件溯源 |
|----------|---------|
| 只记录当前状态 | 记录所有状态变更事件 |
| 覆盖写操作 | 追加写事件 |
| 无法回溯历史 | 可重建任意时间点状态 |
| 审计困难 | 完整审计日志 |
| 无法 Fork 会话 | 可从任意点 Fork |

---

## 二、为什么需要事件溯源

### 2.1 解决的问题

1. **状态不可追溯**
   - 问题：数据库中只有当前状态，不知道是怎么来的
   - 解决：事件流记录所有变更，可完整回溯

2. **调试困难**
   - 问题：用户报告 bug 时无法重现现场
   - 解决：通过事件回放精确重现问题

3. **无法时间旅行**
   - 问题：用户想回到某个历史状态
   - 解决：`time_travel(session_id, to_seq=42)`

4. **会话 Fork 不可能**
   - 问题：用户想从某个点尝试不同分支
   - 解决：`fork_session(from_seq=10)`

5. **审计合规**
   - 问题：需要完整操作日志
   - 解决：事件即审计日志

### 2.2 DeepSeek Harness 的启示

DeepSeek Harness 的 Session 架构核心就是事件溯源：

```typescript
class Session {
  private events: SessionEvent[] = []
  
  append<T>(type: T, data: SessionEventMap[T]): void {
    this.events.push({ type, data, seq: this.events.length })
  }
  
  deriveMessages(): Message[] {
    // 从事件派生当前状态
    return this.surface.fold().messages
  }
}
```

我们的实现完全对齐这一设计。

---

## 三、架构设计

### 3.1 核心概念

| 概念 | 说明 | 示例 |
|------|------|------|
| **Event** | 不可变的状态变更记录 | `TurnStartEvent`, `MessageCreatedEvent` |
| **Event Stream** | 同一 Session 的事件序列 | `session_123` 的所有事件 |
| **Seq** | 事件序列号，Session 内单调递增 | `0, 1, 2, ...` |
| **Correlation ID** | 关联 ID，追踪因果链 | `corr_456` |
| **Causation ID** | 前因事件 ID，指向触发此事件的上一个事件 | `event_789.id` |
| **Fold** | 折叠事件流派生状态 | `fold() → {messages: [...]}` |
| **Replay** | 回放事件流 | `replay(up_to_seq=10)` |

### 3.2 事件分类

```
AgentEventType
├── turn_* (轮次事件)
│   ├── turn_start
│   └── turn_end
├── message_* (消息事件)
│   ├── message_created
│   └── message_updated
├── think_* (思考事件)
│   ├── think_start
│   ├── think_end
│   └── think_token (流式)
├── tool_* (工具事件)
│   ├── tool_call_start
│   ├── tool_call_end
│   └── tool_result
├── observe_* (观察事件)
│   ├── observe_start
│   └── observe_end
├── session_* (会话事件)
│   ├── session_created
│   ├── session_updated
│   └── session_archived
├── error_* (错误事件)
│   ├── error_occurred
│   └── error_recovered
└── checkpoint_* (检查点事件)
    ├── checkpoint_created
    └── checkpoint_restored
```

### 3.3 数据模型

```python
class AgentEvent(Base):
    """事件模型"""
    id: UUID              # 事件 ID
    session_id: UUID      # 所属会话
    seq: int              # 序列号（单调递增）
    event_type: str       # 事件类型
    payload: dict         # 事件数据
    source: str           # 来源：system/user/tool/agent
    correlation_id: str   # 关联 ID（因果链）
    causation_id: str     # 前因事件 ID
    occurred_at: datetime # 发生时间
```

### 3.4 核心操作

#### 追加事件

```python
event_store.append_turn_start(
    session_id=session.id,
    turn=1,
    correlation_id=corr_id,
)
```

#### 状态重建

```python
state = event_store.rebuild_state(session_id)
# {
#   "session_id": "...",
#   "messages": [...],
#   "tool_calls": [...],
#   "current_turn": 1,
#   "turn_status": "running"
# }
```

#### 时间旅行

```python
historical_state = event_store.time_travel(
    session_id=session.id,
    to_seq=42,  # 回到第 43 个事件之前
)
```

#### 会话 Fork

```python
new_session = EventStore.fork_session(
    source_session_id=old_session.id,
    new_session=new_session_obj,
    from_seq=10,  # 从第 11 个事件开始复制
)
```

---

## 四、使用指南

### 4.1 在 TAO 循环中使用

```python
# backend/packages/agent/orchestrator/graph.py

async def _build_agent_graph(..., event_store: EventStore, ...):
    async def think_node(state: TAOState):
        # 记录思考开始
        event_store.append_think_start(
            session_id=session_id,
            iteration=state["iteration"],
        )
        
        # 执行思考
        result = await llm.ainvoke(...)
        
        # 记录思考结束
        event_store.append_think_end(
            session_id=session_id,
            iteration=state["iteration"],
            result=result["content"],
        )
        
        return {"think_result": result}
```

### 4.2 在流式响应中使用

```python
async def run_stream(..., event_store: EventStore, ...):
    async for token in llm.stream(...):
        # 记录每个 token
        event_store.append_think_token(
            session_id=session_id,
            token=token,
        )
        yield token
```

### 4.3 在工具调用中使用

```python
async def tool_call_node(state: TAOState):
    tool_call_id = str(uuid4())
    
    # 记录工具调用开始
    event_store.append_tool_call_start(
        session_id=session_id,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        arguments=tool_args,
    )
    
    # 执行工具
    result = await tool.invoke(tool_args)
    
    # 记录工具结果
    event_store.append_tool_result(
        session_id=session_id,
        tool_call_id=tool_call_id,
        result=result,
    )
    
    return {"tool_result": result}
```

### 4.4 在 API 层中使用

```python
# backend/packages/agent/api/agents.py

@router.post("/{agent_id}/execute/stream")
async def execute_stream(
    agent_id: UUID,
    request: ChatRequest,
    db: Session = Depends(get_db),
):
    # 创建事件存储
    event_store = EventStore(db)
    
    # 记录用户消息
    event_store.append_message_created(
        session_id=session.id,
        role="user",
        content=request.messages[-1]["content"],
    )
    
    # 执行 Agent
    async for chunk in orchestrator.run_stream(..., event_store=event_store):
        yield chunk
    
    # 记录轮次结束
    event_store.append_turn_end(
        session_id=session.id,
        turn=current_turn,
    )
```

---

## 五、最佳实践

### 5.1 事件设计原则

1. **不可变性**: 事件一旦创建永不修改
2. **完整性**: 事件 payload 包含完整的状态变更信息
3. **原子性**: 每个事件代表一个原子操作
4. **时序性**: seq 严格递增，保证因果顺序
5. **可追溯性**: 使用 correlation_id 和 causation_id 追踪因果链

### 5.2 事件命名规范

```
{领域}_{动作}

示例:
- turn_start (轮次开始)
- message_created (消息创建)
- tool_call_start (工具调用开始)
- error_occurred (错误发生)
```

### 5.3 错误处理

```python
try:
    result = await tool.invoke(args)
    event_store.append_tool_result(...)
except Exception as e:
    # 记录错误事件
    event_store.append_error(
        session_id=session_id,
        error_message=str(e),
        error_type=type(e).__name__,
        stack_trace=traceback.format_exc(),
    )
    raise
```

### 5.4 性能优化

1. **批量追加**: 多个事件一起提交
2. **异步写入**: 不阻塞主流程
3. **事件压缩**: 定期归档旧事件
4. **增量折叠**: 只处理新增事件

---

## 六、与 DeepSeek Harness 对比

| 特性 | DeepSeek Harness | 我们的实现 | 状态 |
|------|-----------------|-----------|------|
| 事件模型 | TypeScript | Python + SQLAlchemy | ✅ |
| 事件类型 | SessionEventMap | AgentEventType + Pydantic | ✅ |
| 状态重建 | surface.fold() | EventStream.fold() | ✅ |
| 时间旅行 | 支持 | 支持 | ✅ |
| 会话 Fork | 支持 | 支持 | ✅ |
| 因果追踪 | correlationId | correlation_id + causation_id | ✅ |
| 流式事件 | think/token | think_token | ✅ |
| 类型安全 | TypeScript 类型 | Pydantic v2 | ✅ |
| 数据库 | PostgreSQL | PostgreSQL | ✅ |
| 测试覆盖 | 完整 | 11 个核心测试 | ✅ |

---

## 七、下一步

### 已完成
- [x] 事件模型定义 (`models/event.py`)
- [x] 事件类型定义 (`schemas/events.py`)
- [x] 事件存储库 (`services/event_store.py`)
- [x] 核心测试 (`tests/test_event_sourcing.py`)
- [x] 类型安全测试 (`tests/test_type_safety.py`)

### 待完成
- [ ] 集成到 TAO 循环
- [ ] 集成到流式响应
- [ ] 集成到工具调用
- [ ] 性能优化（批量写入、异步）
- [ ] 事件归档策略
- [ ] 监控和告警

---

## 八、参考文档

- [DeepSeek Harness Session 架构](../../../code/deepseek-harness/packages/core/session/src/index.ts)
- [事件溯源模式](https://martinfowler.com/eaaDev/EventSourcing.html)
- [CQRS 和事件溯源](https://docs.microsoft.com/en-us/azure/architecture/patterns/cqrs)
