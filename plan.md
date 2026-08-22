
## 2026-08-21: 思考过程截断问题修复

### 问题根因
在 `agent_runtime_service.py` 的 `_astream` 方法中，当同一个 SSE delta 同时包含 reasoning 和 content 字段时，原代码使用两个独立的 if 语句，导致 yield 两个独立的 Chunk。这会导致 LangChain 聚合时 additional_kwargs 被错误继承，使得 on_token 回调将 content 误判为 reasoning。

### 修复方案
将 if + if 改为 if + elif，确保一个 delta 只 yield 一个 Chunk。

### 修复文件
- ✅ backend/packages/agent/services/agent_runtime_service.py (第 377-392 行)
  - 改为 if-elif 逻辑
  - 移除循环内部的重复 import logging

### 其他已修复问题
- ✅ backend/packages/agent/orchestrator/supervisor.py - direct_node 返回 iteration: 1
- ✅ packages/agent/src/components/QAChatView.tsx - reasoning 块默认 show: true

### 调试日志
已在以下位置添加详细调试日志：
- ✅ agent_runtime_service.py - [_astream] 追踪 delta 处理
- ✅ orchestrator/graph.py - [on_token] 追踪 chunk 区分
- ✅ orchestrator/graph.py - [_direct_answer_stream] 追踪 yield
- ✅ orchestrator/supervisor.py - [direct_node] 追踪事件发送
- ✅ QAChatView.tsx - 前端追踪 event 接收

### 待测试
- [ ] 重启后端服务
- [ ] 发送测试问题："1+1 等于多少？请详细思考后回答"
- [ ] 收集各层日志验证数据流
- [ ] 验证前端渲染正确

### 走查结论
完整走查了 5 层数据处理链路：
1. ✅ agent_runtime_service.py - _astream (已修复)
2. ✅ orchestrator/graph.py - on_token (无问题)
3. ✅ orchestrator/graph.py - _direct_answer_stream (无问题)
4. ✅ orchestrator/supervisor.py - direct_node (无问题)
5. ✅ QAChatView.tsx - 事件处理 (无问题)

详细分析见：BACKEND_WALKTHROUGH_REPORT.md

## 2026-08-21 11:00: 修复方案调整

### 问题分析
根据代码走查，确认问题**不在钩子函数的时间差**，因为：
1. 中间件在模型调用前后执行，不干预流式 chunk
2. Waterfall 钩子拦截的是 messages 和聚合后的 response
3. `on_token(chunk)` 在聚合前同步调用，没有竞态条件

### 修复方案调整
改回使用两个独立的 if，确保 reasoning 和 content 都能正确输出：

```python
if reason_text:
    yield Chunk(reasoning, additional_kwargs={"reasoning": True})

if answer_text:
    yield Chunk(content)
```

**原理**：
- 模型特性：先输出 reasoning，然后切换到 content，不会交叉
- 即使同一个 delta 同时包含，也会分别 yield 两个 Chunk
- 由于 `on_token` 在聚合前调用，每个 chunk 的 additional_kwargs 是正确的
- 不会导致混淆

### 监控
添加 SWITCHING POINT 监控日志，观察是否真的发生同时包含的情况。

### 待测试
- [ ] 重启后端服务
- [ ] 观察日志中的 SWITCHING POINT 警告
- [ ] 验证前端渲染正确

## 2026-08-21 11:09: 确认调用链路

### 调用链路验证

**Agent 调用模型**：
```
tao_graph.think_node()
  → async for chunk in llm.astream(messages)
  → BaseChatModel.astream() [LangChain 基类]
  → async for chunk in self._astream(...) [基类内部调用]
  → SimpleChatHttp._astream() [子类实现] ← 修改点
```

**测试代码**：
```python
async for c in llm._astream([HumanMessage(content="hi")])
```
直接调用 `_astream()` 是为了绕过 LangChain 基类的复杂逻辑，直接测试核心数据处理。

### 结论
✅ 修改 `SimpleChatHttp._astream()` 是正确的，这就是 Agent 实际调用的数据处理方法。
