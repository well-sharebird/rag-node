# 思考过程内容截断修复报告

## 🐛 问题描述

从截图看，思考过程的内容被截断：
- **第 1 轮思考**：只显示"用户要求删除文件..."这一句
- **第 2 轮思考**：只显示"保正确传递 code 参数。"（明显被截断）
- **第 3 轮思考**：只显示"除命"（只有两个字）

## 🔍 根本原因

**React 状态更新的不可变性被违反**！

### 问题代码

```tsx
// ❌ 错误：直接修改数组中的对象
if (lastR && lastR.kind === 'reasoning') {
  lastR.content += ev.content;  // 直接修改，React 检测不到变化！
}
```

`lastR` 是 `steps[steps.length - 1]` 的引用，直接修改 `lastR.content` 不会触发 React 重新渲染！

### 为什么会这样

1. **后端流式输出**：每次发送一个 token/chunk
2. **前端累积逻辑**：应该累积到同一个 step
3. **React 检测机制**：通过引用比较检测变化
4. **直接修改对象**：引用没变，React 认为没有变化，不重新渲染

### 流程分析

```
第 1 个 reasoning chunk 到达
  ↓
steps.push({ kind: 'reasoning', round: 1, content: "用户要求..." })
  ↓
flushSync + setMessages → ✅ 触发渲染
  ↓
第 2 个 reasoning chunk 到达
  ↓
lastR.content += ev.content  // ❌ 直接修改，引用没变！
  ↓
flushSync + setMessages → ❌ React 检测到 steps 引用相同，跳过渲染！
  ↓
用户只看到第一个 chunk 的内容
```

---

## 🔧 修复方案

### 修复 1: Reasoning 事件累积

**文件**: `packages/agent/src/components/QAChatView.tsx`

```tsx
// ✅ 修复后：创建新对象（不可变更新）
if (lastR && lastR.kind === 'reasoning') {
  // 创建新对象，触发 React 重新渲染
  steps[steps.length - 1] = { ...lastR, content: lastR.content + ev.content };
}
```

### 修复 2: Token 事件累积

```tsx
// ✅ 修复后
if (lastA && lastA.kind === 'answer') {
  steps[steps.length - 1] = { ...lastA, content: lastA.content + ev.content };
}
```

### 修复 3: Tool 事件更新

```tsx
// ✅ 修复后
if (tIdx >= 0) {
  steps[tIdx] = toolStep;  // 已经是新对象，没问题
} else {
  steps.push(toolStep);
}
```

### 修复 4: ThinkingBlock 组件状态同步

**文件**: `packages/agent/src/components/ChatMessageList.tsx`

```tsx
// ❌ 修复前：内部状态与外部 prop 不同步
function ThinkingBlock({ show, ... }) {
  const [isExpanded, setIsExpanded] = useState(show !== false);
  // 后续 show 变化，isExpanded 不会更新！
}

// ✅ 修复后：直接使用 prop
function ThinkingBlock({ show, ... }) {
  const isExpanded = show !== false;  // 直接使用外部控制
  // 移除内部状态
}
```

---

## 📊 修复对比

| 场景 | 修复前 | 修复后 |
|------|--------|--------|
| **第 1 轮思考** | 只显示第 1 个 chunk | ✅ 显示完整思考内容 |
| **第 2 轮思考** | 只显示第 1 个 chunk | ✅ 显示完整思考内容 |
| **答案累积** | 可能丢失部分 token | ✅ 完整累积 |
| **思考块展开** | 状态可能不同步 | ✅ 完全由外部控制 |

---

## 🧪 测试验证

- [x] 前端编译通过
- [ ] 端到端测试：
  1. 提问需要多轮思考的问题
  2. 检查每轮思考内容是否完整
  3. 检查展开/收起功能是否正常

---

## 📝 修改文件

1. `packages/agent/src/components/QAChatView.tsx`
   - 修复 reasoning 事件累积（不可变更新）
   - 修复 token 事件累积（不可变更新）
   - 修复 tool 事件更新（已经是不可变，添加注释）

2. `packages/agent/src/components/ChatMessageList.tsx`
   - 移除 ThinkingBlock 内部状态
   - 直接使用外部 show prop 控制

---

## 🎯 总结

**这是典型的 React 不可变性陷阱**！

直接修改数组/对象中的元素不会触发重新渲染，必须创建新对象：

```tsx
// ❌ 错误
arr[index].prop = newValue;

// ✅ 正确
arr[index] = { ...arr[index], prop: newValue };
// 或
arr = arr.map((item, i) => i === index ? { ...item, prop: newValue } : item);
```

修复后，思考过程应该能完整显示所有内容。
