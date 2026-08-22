# 智能合并逻辑修复 - 解决模型输出 switching 问题

## 🎯 问题描述

从截图中观察到：
- 思考过程在"同一"处被硬生生切断
- 切断后的内容（"个文件保存的确认消息..."）跑到了思考框外面
- 句子不完整，阅读体验极差

---

## 🔍 根因分析

**模型输出的 switching 问题**：推理模型（如 Qwen）在输出思考过程时，可能突然从 `reasoning_content` 字段切换到 `content` 字段，导致：

### 后端事件流

```
[reasoning 事件] "测试和安全测试...用户似乎重复发送了同一"
    ↓
[token 事件] "个文件保存的确认消息。我需要继续完成..."
```

### 前端处理逻辑（修复前）

```typescript
// reasoning 事件 → 创建 thinking block（到"同一"截止）
if (isReasoning(ev)) {
  steps.push({ kind: 'reasoning', content: ev.content });
}

// token 事件 → 创建 answer block（从"个文件"开始）
if (isToken(ev)) {
  steps.push({ kind: 'answer', content: ev.content });
}
```

**结果**：思考过程被硬生生切断，后半部分跑到思考框外面！

---

## ✅ 解决方案：智能合并逻辑

在 `QAChatView.tsx` 中添加智能检测，当发现 `reasoning` 结尾无结束标点且 `token` 开头是小写/非标点时，合并到 reasoning 中：

### 检测条件

```typescript
// 1. reasoning 结尾无结束标点（。！？.!?）
const hasEndPunctuation = /[。！？.!?…]\s*$/.test(reasoningEnds);

// 2. token 开头是小写字母、中文、或非标点符号
const startsWithLowercase = /^[a-z]/.test(tokenStarts);
const startsWithChinese = /^[\u4e00-\u9fa5]/.test(tokenStarts);
const startsWithPunctuation = /^[,;.!?…]/.test(tokenStarts);

// 3. token 开头不是工具调用标记
const startsWithToolCall = /^[\n\s]*```/.test(tokenStarts);

// 合并条件
if (!hasEndPunctuation && (startsWithLowercase || startsWithChinese || startsWithPunctuation) && !startsWithToolCall) {
  // 合并到 reasoning
  steps[steps.length - 1] = { ...lastStep, content: lastStep.content + ev.content };
}
```

---

## 📝 修复代码

**文件**: `packages/agent/src/components/QAChatView.tsx`

**位置**: token 事件处理逻辑（第 528-575 行）

**修改内容**:

```typescript
// Handle Agent API stream format: {"type": "token", "content": "..."}
if (isToken(ev) && ev.content) {
  accumulatedContent += ev.content;
  const lastStep = steps[steps.length - 1];
  
  // 🎯 智能合并逻辑：检测模型输出的 switching 问题
  // 当 reasoning 刚结束就收到 token，且句子被切断时，合并到 reasoning 中
  if (lastStep && lastStep.kind === 'reasoning' && ev.content) {
    const reasoningEnds = lastStep.content.trim();
    const tokenStarts = ev.content;
    
    // 检测条件：
    // 1. reasoning 结尾无结束标点（。！？.!?）
    // 2. token 开头是小写字母、中文、或非标点符号
    // 3. token 开头不是工具调用标记
    const hasEndPunctuation = /[。！？.!?…]\s*$/.test(reasoningEnds);
    const startsWithLowercase = /^[a-z]/.test(tokenStarts);
    const startsWithChinese = /^[\u4e00-\u9fa5]/.test(tokenStarts);
    const startsWithPunctuation = /^[,;.!?…]/.test(tokenStarts);
    const startsWithToolCall = /^[\n\s]*```/.test(tokenStarts);
    
    // 如果 reasoning 没结束且 token 是句子 continuation，合并到 reasoning
    if (!hasEndPunctuation && (startsWithLowercase || startsWithChinese || startsWithPunctuation) && !startsWithToolCall) {
      // ✅ 合并到 reasoning，创建新对象
      steps[steps.length - 1] = { ...lastStep, content: lastStep.content + ev.content };
      flushSync(() => {
        setMessages(prev => prev.map(msg =>
          msg.messageId === messageId
            ? { ...msg, reasoning: accumulatedReasoning, steps: [...steps] }
            : msg
        ));
      });
      continue;
    }
  }
  
  // 正常 token 处理（答案内容）
  if (lastStep && lastStep.kind === 'answer') {
    steps[steps.length - 1] = { ...lastStep, content: lastStep.content + ev.content };
  } else {
    steps.push({ kind: 'answer', content: ev.content });
  }
  // ...
}
```

---

## 🎯 修复效果

### 修复前 ❌

```
[思考过程框]
测试和安全测试。
好的，代码文件已保存。现在让我创建详细的测试计划文档：
用户似乎重复发送了同一
[思考过程框结束]

[答案内容]
个文件保存的确认消息。我需要继续完成测试计划文档的创建。让我创
```

### 修复后 ✅

```
[思考过程框]
测试和安全测试。
好的，代码文件已保存。现在让我创建详细的测试计划文档：
用户似乎重复发送了同一个文件保存的确认消息。我需要继续完成测试计划文档的创建。让我创
[思考过程框结束]

[答案内容]
（后续正常答案内容）
```

---

## 📋 测试场景

### 场景 1: 句子连续性 ✅
- 发送需要多轮推理的复杂问题
- 观察思考过程是否完整
- 验证句子不被硬生生切断

### 场景 2: 模型 switching ✅
- 使用推理模型（如 Qwen、DeepSeek）
- 观察 reasoning_content 和 content 切换时机
- 验证智能合并逻辑生效

### 场景 3: 工具调用边界 ✅
- 发送需要工具调用的问题
- 验证工具调用标记（```）不被错误合并
- 确保工具调用正常显示

---

## ⚠️ 注意事项

### 1. 保守合并策略
- 只在明确是句子 continuation 时合并
- 避免过度合并导致思考过程过长

### 2. 标点符号检测
- 中英文结束标点都检测（。！？.!?…）
- 避免误判逗号、分号等中间标点

### 3. 工具调用保护
- 检测到工具调用标记（```）时不合并
- 确保工具调用卡片正常显示

---

## 🎉 修复完成

**修复时间**: 2026-08-21  
**影响范围**: 所有推理模型输出场景  
**向后兼容**: ✅ 完全兼容  
**预期效果**: 
- ✅ 思考过程句子完整，不被切断
- ✅ 答案内容正常分离
- ✅ 工具调用边界清晰
- ✅ 阅读体验流畅自然
