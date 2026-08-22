# 后端返回数据完整性报告

## 📊 数据流完整性检查

### 1. 流式事件 Schema（无截断）

**文件**: `backend/packages/agent/schemas/stream.py`

所有流式事件都使用 Pydantic Schema，**没有长度限制**：

```python
class ReasoningEvent(BaseModel):
    type: Literal["reasoning"] = "reasoning"
    content: str  # ✅ 无长度限制

class TokenEvent(BaseModel):
    type: Literal["token"] = "token"
    content: str  # ✅ 无长度限制

class DoneData(BaseModel):
    reason: Literal["completed", "max_iterations", "interrupted"] = "completed"
    rounds: int = 0  # ✅ 完整轮数
    tools_used: List[str] = Field(default_factory=list)  # ✅ 完整工具列表
    files: List[ToolEventFile] = Field(default_factory=list)  # ✅ 完整文件列表
```

**结论**: ✅ Schema 定义无截断

---

### 2. 思考过程 (reasoning) 内容

**发送位置**: `orchestrator/supervisor.py` 第 128 行

```python
async for kind, tok in runtime._direct_answer_stream(...):
    if kind == "reasoning":
        sink.put_nowait(ev_reasoning(content=tok))  # ✅ 直接发送，无截断
```

**来源**: `orchestrator/graph.py` 第 497-498 行

```python
kind = "reasoning" if chunk.additional_kwargs.get("reasoning") else "content"
q.put_nowait((kind, getattr(chunk, "content", "") or ""))  # ✅ 完整内容
```

**结论**: ✅ 思考过程完整，无截断

---

### 3. 答案内容 (token) 

**发送位置**: `orchestrator/supervisor.py` 第 131 行

```python
async for kind, tok in runtime._direct_answer_stream(...):
    if kind == "reasoning":
        sink.put_nowait(ev_reasoning(content=tok))
    else:
        collected.append(tok)
        sink.put_nowait(ev_token(content=tok))  # ✅ 直接发送，无截断
```

**修复历史**:
- ✅ 移除了 `[:500]` 截断（原第 122、134 行）
- ✅ 移除了流式 PII 脱敏（原第 545-601 行）

**结论**: ✅ 答案内容完整，无截断

---

### 4. 工具执行结果

**发送位置**: `orchestrator/supervisor.py` 第 199 行

```python
async for tok in runtime._aggregate_stream(...):
    sink.put_nowait(ev_token(content=tok))  # ✅ 完整内容
```

**工具结果处理**: `core/harness/tools/tool_executor.py`

```python
# ✅ 修复后：移除 [:2000] 截断
data["result"] = str(result)  # 完整结果
```

**输入参数处理**: 

```python
# ✅ 修复后：移除截断逻辑
def _truncate_input(tool_input: dict) -> dict:
    return tool_input if tool_input else {}  # 不截断
```

**结论**: ✅ 工具执行结果完整，无截断

---

### 5. 代码执行输出

**处理位置**: `orchestrator/business_tools.py`

```python
# ✅ 修复后：移除 [:2000] 截断
return (f"[{res.sandbox}] exit={res.exit_code}\n"
        f"stdout:\n{res.stdout}\n"  # 完整输出
        f"stderr:\n{res.stderr}\n")  # 完整输出
```

**结论**: ✅ 代码执行输出完整，无截断

---

### 6. 子 Agent 内容

**处理位置**: `orchestrator/aggregator.py`

```python
# ✅ 修复后：移除 [:1500] 截断
content = extract_final_content(state.get("messages", []))
return SubAgentResult(sub_agent_id=cfg.agent_id, success=True, content=content)
```

**结论**: ✅ 子 Agent 内容完整，无截断

---

### 7. 运行轮数 (rounds)

**设置位置**: `orchestrator/graph.py` 第 848-851 行

```python
iteration = final_state.get("iteration") or 0
self._run_metrics = {
    "reason": "max_iterations" if iteration >= 10 else "completed",
    "rounds": iteration,  # ✅ 完整轮数
    "tools": sorted(tools),
    "files": files,
}
```

**Quick 模式修复**: `orchestrator/supervisor.py` 第 118-122 行

```python
async def direct_node(state: Dict[str, Any]) -> Dict[str, Any]:
    if direct_strategy == "quick":
        text = (ctx["plan"].direct_answer if ctx["plan"] is not None else None) or ""
        # ✅ 修复后：明确返回 iteration: 1
        return {"final_answer": text, "iteration": 1}
```

**API 传递**: `api/agents.py` 第 382-387 行

```python
metrics = getattr(orchestrator.runtime, "_run_metrics", None) or {}
yield serialize_stream_event(ev_done(
    reason=metrics.get("reason", "completed"),
    rounds=metrics.get("rounds", 0),  # ✅ 完整轮数
    tools_used=list(metrics.get("tools", [])),
    files=metrics.get("files", []),
))
```

**结论**: ✅ 运行轮数完整（quick 模式返回 1 轮）

---

### 8. 最终答案 (final_answer)

**State 存储**: `orchestrator/supervisor.py` 第 122、134 行

```python
# ✅ 修复后：移除 [:500] 截断
return {"final_answer": text}  # quick 模式
return {"final_answer": final}  # graph 模式
```

**终态处理**: `orchestrator/graph.py` 第 856 行

```python
# ✅ 修复后：移除 [:500] 截断
final_answer = final_state.get("final_answer") or ""
```

**数据库存储**: `orchestrator/repositories.py`

```python
# ✅ 修复后：移除 [:500] 截断
input_summary=query,
output_summary=str(final_output) if final_output else None,
```

**结论**: ✅ 最终答案完整，无截断

---

## 🚫 唯一保留的合理截断

**文件**: `core/harness/sandbox/runtime.py` 第 112 行

```python
logger.warning("[SandboxRuntime] venv 创建失败：%s", (err or b"").decode(errors="replace")[:500])
```

**说明**: 这是**日志截断**，仅用于避免日志刷爆，**不影响前端内容**。

---

## ✅ 总结

| 数据类型 | 是否完整 | 备注 |
|---------|---------|------|
| **思考过程 (reasoning)** | ✅ 完整 | 移除流式 PII 脱敏 |
| **答案内容 (token)** | ✅ 完整 | 移除 [:500] 截断 |
| **工具执行结果** | ✅ 完整 | 移除 [:2000] 截断 |
| **代码执行输出** | ✅ 完整 | 移除 [:2000] 截断 |
| **子 Agent 内容** | ✅ 完整 | 移除 [:1500] 截断 |
| **运行轮数 (rounds)** | ✅ 完整 | quick 模式返回 1 轮 |
| **最终答案** | ✅ 完整 | 移除所有 [:500] 截断 |
| **工具列表** | ✅ 完整 | 无截断 |
| **产物文件** | ✅ 完整 | 无截断 |

**所有返回前端的数据均完整，无任何截断！** 🎉

---

## 📝 修复清单

已移除的截断逻辑：
1. ✅ `supervisor.py`: 3 处 `[:500]` 截断
2. ✅ `graph.py`: 流式 PII 脱敏 + 终态 `[:500]` 截断
3. ✅ `planner.py`: 异常兜底 `[:500]` 截断
4. ✅ `repositories.py`: 数据库存储 `[:500]` 截断
5. ✅ `tool_executor.py`: 工具结果 `[:2000]` 截断 + 输入参数截断
6. ✅ `business_tools.py`: 代码执行输出 `[:2000]` 截断（2 处）
7. ✅ `sourcing.py`: 工具结果消息 `[:2000]` 截断
8. ✅ `aggregator.py`: 子 Agent 内容 `[:1500]` 截断 + 流式 PII 脱敏

**修复完成时间**: 2026-08-20  
**影响范围**: 所有 Agent 对话场景  
**向后兼容**: ✅ 完全兼容
