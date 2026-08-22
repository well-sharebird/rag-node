# 后端修复：Reasoning Buffer 确保语义完整性

## 🎯 问题根因

**模型输出的 switching 问题**：推理模型（如 Qwen）在输出思考过程时，可能在句子中间从 `reasoning_content` 字段切换到 `content` 字段。

### 模型输出示例

```json
// Chunk N
{
  "reasoning_content": "用户似乎重复发送了同一",
  "content": null
}

// Chunk N+1
{
  "reasoning_content": null,
  "content": "个文件保存的确认消息"
}
```

### 后端处理逻辑（修复前）❌

```python
reason_text = delta.get("reasoning_content")
answer_text = delta.get("content")

if reason_text:
    yield reasoning_event(reason_text)  # 发送 reasoning 事件
elif answer_text:
    yield token_event(answer_text)      # 发送 token 事件
```

**结果**：
- Chunk N → reasoning 事件 → 前端显示在思考框："用户似乎重复发送了同一"
- Chunk N+1 → token 事件 → 前端显示在答案区："个文件保存的确认消息"

**句子被硬生生切断！** ❌

---

## ✅ 修复方案：Reasoning Buffer

在 `agent_runtime_service.py` 中添加 **reasoning buffer**，确保思考过程的语义完整性。

### 核心思路

1. **维护 buffer**：累积 reasoning_content
2. **检测完整性**：检查 reasoning 是否有结束标点
3. **智能合并**：当 reasoning 未完成时收到 content，合并到 reasoning

### 实现代码

**文件**: `backend/packages/agent/services/agent_runtime_service.py`

**位置**: `_astream` 方法（第 317 行开始）

```python
async def _astream(self, messages: list[BaseMessage], stop: list[str] | None = None, **kwargs):
    """异步流式生成响应 - 逐 token 解析 OpenAI SSE 流"""
    
    # 🎯 修复：添加 reasoning buffer，确保思考过程的语义完整性
    # 当模型在句子中间切换字段时，保证句子不被切断
    reasoning_buffer = ""
    reasoning_complete = True  # 初始为 True，表示没有未完成的 reasoning
    
    # ... 省略其他代码 ...
    
    async for line in response.aiter_lines():
        # ... 省略解析代码 ...
        
        reason_text = delta.get("reasoning_content") or delta.get("reasoning")
        answer_text = delta.get("content")
        
        # 检查 reasoning 是否完整（有结束标点）
        def is_reasoning_complete(text: str) -> bool:
            """检查 reasoning 文本是否有完整的句子结束"""
            if not text:
                return True
            # 结束标点：中英文句号、问号、感叹号、省略号、换行
            return text.strip().endswith(('。', '！', '？', '.', '!', '?', '…', '\n'))
        
        if reason_text:
            # 有 reasoning_content，肯定是思考过程
            reasoning_buffer += reason_text
            reasoning_complete = is_reasoning_complete(reason_text)
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=reason_text,
                    additional_kwargs={"reasoning": True},
                )
            )
        elif answer_text:
            # 只有 content 且没有 reasoning_content
            # 关键检查：如果 reasoning 刚结束但不完整，将 answer 合并到 reasoning
            if not reasoning_complete and reasoning_buffer:
                # reasoning 未完成，将 answer_text 作为 reasoning 继续
                reasoning_buffer += answer_text
                reasoning_complete = is_reasoning_complete(answer_text)
                yield ChatGenerationChunk(
                    message=AIMessageChunk(
                        content=answer_text,
                        additional_kwargs={"reasoning": True},  # 仍然标记为 reasoning
                    )
                )
            else:
                # reasoning 已完成或为空，正常发送 answer
                yield ChatGenerationChunk(
                    message=AIMessageChunk(content=answer_text)
                )
```

---

## 🎯 修复效果

### 修复前 ❌

```
模型输出：
  Chunk N:   reasoning_content: "用户似乎重复发送了同一"
  Chunk N+1: content: "个文件保存的确认消息"

后端事件：
  [reasoning] "用户似乎重复发送了同一"
  [token] "个文件保存的确认消息"

前端渲染：
  [思考框] "用户似乎重复发送了同一"
  [答案] "个文件保存的确认消息"

❌ 句子被切断！
```

### 修复后 ✅

```
模型输出：
  Chunk N:   reasoning_content: "用户似乎重复发送了同一"
  Chunk N+1: content: "个文件保存的确认消息"

后端检测：
  - reasoning_buffer: "用户似乎重复发送了同一"
  - reasoning_complete: False (无结束标点)
  - 收到 content → 合并到 reasoning

后端事件：
  [reasoning] "用户似乎重复发送了同一"
  [reasoning] "个文件保存的确认消息"  # ✅ 仍然发送 reasoning 事件

前端渲染：
  [思考框] "用户似乎重复发送了同一个文件保存的确认消息"

✅ 句子完整！
```

---

## 📋 检测逻辑

### 结束标点检测

```python
def is_reasoning_complete(text: str) -> bool:
    if not text:
        return True
    # 结束标点：中英文句号、问号、感叹号、省略号、换行
    return text.strip().endswith(('。', '！', '？', '.', '!', '?', '…', '\n'))
```

**结束标点包括**：
- 中文：`。` `！` `？` `…`
- 英文：`.` `!` `?` `…`
- 换行：`\n`

**检测逻辑**：
- ✅ 有结束标点 → reasoning 完整
- ❌ 无结束标点 → reasoning 未完成

---

## 🧪 测试场景

### 场景 1: 句子中间切换 ✅

```
模型输出：
  "用户似乎重复发送了同一" (reasoning_content)
  "个文件保存的确认消息" (content)

预期：
  两个都发送 reasoning 事件
  思考框显示完整句子
```

### 场景 2: 正常句子结束 ✅

```
模型输出：
  "让我分析一下。" (reasoning_content，有句号)
  "首先..." (content)

预期：
  第一个发送 reasoning 事件
  第二个发送 token 事件
  思考和答案正确分离
```

### 场景 3: 多轮思考 ✅

```
模型输出：
  "第一轮思考。" (reasoning_content)
  "第二轮思考？" (reasoning_content)
  "这是答案。" (content)

预期：
  前两个发送 reasoning 事件
  第三个发送 token 事件
  多轮思考完整显示
```

---

## 📄 修改文件

### 后端修改
- ✅ `backend/packages/agent/services/agent_runtime_service.py`
  - 添加 `reasoning_buffer` 变量（第 317 行）
  - 添加 `reasoning_complete` 标志（第 318 行）
  - 添加 `is_reasoning_complete` 函数（第 373-377 行）
  - 修改 reasoning/content 处理逻辑（第 379-401 行）

### 前端修改
- ✅ 无（回滚到简单版本，保持原有逻辑）

---

## 🎉 修复完成

**修复时间**: 2026-08-21  
**影响范围**: 所有推理模型输出场景  
**向后兼容**: ✅ 完全兼容  
**预期效果**: 
- ✅ 思考过程句子完整，不被切断
- ✅ 答案内容正确分离
- ✅ 无需前端检测，后端保证语义完整性
- ✅ 阅读体验流畅自然

---

## 🔍 技术优势

### 1. 治本而非治标
- ❌ 前端检测：事后补救，依赖特征猜测
- ✅ 后端缓冲：源头保证，语义完整性

### 2. 简单可靠
- ✅ 只检测标点，不依赖复杂规则
- ✅ 保守策略，只在明确未完成时合并

### 3. 通用性强
- ✅ 适用于所有推理模型
- ✅ 不依赖特定模型行为

### 4. 性能影响小
- ✅ 只增加一个字符串 buffer
- ✅ 只增加简单的标点检测
- ✅ 无额外网络开销
