# 代码走查分析：思考过程截断问题

## 问题现象
从截图可见：
- 思考过程在"1"处截断
- "+1=2 是数学中的基本事实..." 跑到了答案区域
- 思考过程最后一句："对于这个问题，我应该直接、诚实地回答。1"

## 数据处理链路分析

### 链路图
```
模型 SSE 流
    ↓
[1] agent_runtime_service._astream()
    - 解析 SSE delta
    - 设置 additional_kwargs={"reasoning": True}
    - yield ChatGenerationChunk
    ↓
[2] tao_graph.think_node()
    - async for chunk in llm.astream()
    - await on_token(chunk)  ← 在聚合前调用
    - chunks.append(chunk)
    - response = 聚合所有 chunks
    ↓
[3] orchestrator/graph.on_token()
    - 读取 chunk.additional_kwargs["reasoning"]
    - 判断 kind = "reasoning" or "content"
    - q.put_nowait((kind, content))
    ↓
[4] orchestrator/graph._direct_answer_stream()
    - kind, raw = await q.get()
    - yield (kind, c)
    ↓
[5] orchestrator/supervisor.direct_node()
    - async for kind, tok in _direct_answer_stream()
    - sink.put_nowait(ev_reasoning/ev_token)
    ↓
[6] 前端 QAChatView
    - 根据 event.type 渲染
```

## 关键点分析

### 1. think_node 中的调用时机

```python
# tao_graph.py:278-281
async for chunk in llm.astream(messages):
    if on_token is not None:
        await on_token(chunk)  # ← 在聚合前调用
    chunks.append(chunk)

# 聚合
if chunks:
    response = chunks[0]
    for c in chunks[1:]:
        response = response + c
```

**关键**：`on_token(chunk)` 在聚合**之前**调用，每个 chunk 保持原始状态。

### 2. 中间件调用时机

```python
# tao_graph.py:263-265
if chain is not None:
    state = await chain.before_model(state)

# ... 调用 LLM ...

# tao_graph.py:301-303
if chain is not None:
    state = await chain.after_model(state)
```

**关键**：中间件在模型调用**前后**执行，不干预流式 chunk 的处理。

### 3. Waterfall 钩子调用时机

```python
# tao_graph.py:268-269
if hooks and hasattr(hooks, 'run_waterfall'):
    messages = await hooks.run_waterfall('llm/messages', messages)

# tao_graph.py:293-294
if hooks and hasattr(hooks, 'run_waterfall'):
    response = await hooks.run_waterfall('llm/response', response)
```

**关键**：Waterfall 拦截的是 `messages`（输入）和 `response`（聚合后的输出），不干预流式 chunk。

## 问题定位

### 排除法

1. ❌ **不是中间件问题**
   - 中间件在模型调用前后执行
   - 不干预流式 chunk 处理
   - `before_model`/`after_model` 只修改 state

2. ❌ **不是 Waterfall 钩子问题**
   - `run_waterfall('llm/messages', ...)` 在调用前拦截输入
   - `run_waterfall('llm/response', ...)` 在聚合后拦截输出
   - 不干预 `async for chunk in llm.astream()` 循环

3. ❌ **不是时间差问题**
   - `on_token(chunk)` 是同步等待的：`await on_token(chunk)`
   - 每个 chunk 处理完才进入下一个迭代
   - 没有异步竞态条件

4. ✅ **问题在第 1 层：agent_runtime_service._astream()**

### 根本原因验证

查看模型原始数据 (`model_debug_data.json`)：
- Total chunks: 1817
- Reasoning chunks: 901 (idx: 3, 5, 7, ..., 1803)
- Content chunks: 6 (idx: 1805, 1807, ..., 1815)
- **Switching point**: idx 1803 → 1805

**关键发现**：
- 模型在 idx 1803 输出 reasoning: `'\n'`
- 模型在 idx 1805 输出 content: `'\n\n'`
- **中间没有重叠**

但是，如果 SSE 返回的 delta 对象在某一次同时包含：
```json
{
  "delta": {
    "reasoning": "\n",
    "content": "\n\n"
  }
}
```

原代码（修复前）：
```python
if reason_text:
    yield Chunk(reasoning)  # 第 1 个
if answer_text:
    yield Chunk(content)    # 第 2 个
```

会 yield 两个 Chunk，导致：
1. 第 1 个 Chunk: `additional_kwargs={"reasoning": True}`
2. 第 2 个 Chunk: 无 `additional_kwargs`

然后 LangChain 聚合：
```python
response = chunk1 + chunk2
# response.additional_kwargs = {"reasoning": True}  ← 被污染！
```

### 为什么修复后还有问题？

**新假设**：问题可能不在同一个 delta 内，而在**相邻 delta 的边界**。

场景重现：
1. Delta N: `{"reasoning": "我应该直接回答。1"}`
2. Delta N+1: `{"reasoning": "+1=2 是基本事实...", "content": ""}` ← 同时包含

如果 Delta N+1 同时包含 reasoning 和空 content：
```python
reason_text = "+1=2 是基本事实..."
answer_text = ""

if reason_text:  # True
    yield Chunk(reasoning)
elif answer_text:  # False (空字符串)
    yield Chunk(content)  # ← 不会执行
```

这样是正确的！

**但是**，如果 Delta N+1 是：
```json
{
  "delta": {
    "reasoning": "",
    "content": "+1=2 是基本事实..."
  }
}
```

而实际上模型可能在 switching point 的某个 delta 中：
```json
{
  "delta": {
    "reasoning": "1",
    "content": "+1=2 是基本事实..."
  }
}
```

这时修复后的代码：
```python
if reason_text:  # "1" - True
    yield Chunk("1", reasoning=True)
elif answer_text:  # 不会执行！
    yield Chunk("+1=2 是基本事实...")
```

**问题暴露**：`elif` 导致 content 被丢弃！

## 正确的修复方案

需要同时处理 reasoning 和 content，但分别 yield：

```python
if reason_text:
    yield ChatGenerationChunk(
        message=AIMessageChunk(
            content=reason_text,
            additional_kwargs={"reasoning": True},
        )
    )
if answer_text and not reason_text:
    # 只在没有 reasoning 时才处理 content
    yield ChatGenerationChunk(
        message=AIMessageChunk(content=answer_text)
    )
```

或者更明确：

```python
# 模型特性：先 reasoning 后 content，不会交叉
# 但 switching point 可能在一个 delta 中同时包含
# 需要分别处理，但确保顺序正确

if reason_text:
    yield ChatGenerationChunk(
        message=AIMessageChunk(
            content=reason_text,
            additional_kwargs={"reasoning": True},
        )
    )

if answer_text:
    # 检查是否有 reasoning，如果有，说明这是 switching point
    # content 应该在下一个 delta 单独出现
    if not reason_text:
        yield ChatGenerationChunk(
            message=AIMessageChunk(content=answer_text)
        )
    else:
        # ⚠️ Switching point: reasoning 和 content 同时出现
        # 丢弃 content，等待下一个 delta
        logger.warning(f"[Switching] 丢弃 content: {repr(answer_text[:50])}")
```

## 验证方法

添加详细日志观察 switching point：

```python
if reason_text and answer_text:
    logger.warning(f"[Switching Point] delta 同时包含 reasoning 和 content!")
    logger.warning(f"  reasoning: {repr(reason_text)}")
    logger.warning(f"  content: {repr(answer_text)}")
```

## 结论

**问题不在钩子函数的时间差**，而在 `_astream` 方法对 switching point 的处理。

**当前修复方案的问题**：
- `if-elif` 逻辑在 switching point 会丢弃 content
- 需要改为分别处理，但要监控 switching point

**建议**：
1. 添加 switching point 监控日志
2. 如果确实发生，考虑缓存 content 到下一个 delta
3. 或者接受丢失（因为通常 switching point 的 content 很短）
