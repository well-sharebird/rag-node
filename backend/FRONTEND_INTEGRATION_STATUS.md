# 前端集成状态报告

## 总体评估：✅ 前端已完整实现审批功能

---

## ✅ 前端已完成（100%）

### 1. 类型定义完整

**文件**: `packages/agent/src/api/stream-events.ts`

```typescript
// ✅ 审批事件类型定义
export interface ApprovalRequiredData {
  sub_agent_id?: string;
  pending?: unknown[];
}

export type AgentStreamEvent =
  | { type: 'approval_required'; data?: ApprovalRequiredData }
  // ... 其他事件

// ✅ 类型守卫
export function isApprovalRequired(ev: AgentStreamEvent): ev is Extract<AgentStreamEvent, { type: 'approval_required' }> {
  return ev.type === 'approval_required';
}
```

### 2. 审批事件处理完整

**文件**: `packages/agent/src/components/QAChatView.tsx`

```typescript
// ✅ 状态管理（line 153-154）
const [approvalPending, setApprovalPending] = useState<any[]>([]);
const [showApprovalModal, setShowApprovalModal] = useState(false);

// ✅ 事件处理（line 444-455）
if (isApprovalRequired(ev) && ev.data?.pending) {
  const subAgentId = ev.data?.sub_agent_id;
  const next = ev.data.pending.map((p: any) => ({
    ...p,
    sub_agent_id: p?.sub_agent_id || subAgentId,
  }));
  setApprovalPending(next);
  setShowApprovalModal(true);
  continue;
}
```

### 3. 审批对话框 UI 完整

**文件**: `QAChatView.tsx` (line 1294-1327)

```tsx
<Modal
  open={showApprovalModal}
  onOpenChange={setShowApprovalModal}
  title="需要人工审批"
  description="以下敏感调用需要你的批准后才能执行"
  footer={
    <div className="flex gap-2 justify-end">
      <button onClick={() => handleApproval('reject')}>拒绝</button>
      <button onClick={() => handleApproval('approve')}>批准</button>
    </div>
  }
>
  {approvalPending.map((p: any, i: number) => (
    <div key={i}>
      <div className="font-medium">{p?.tool || p?.name || '工具调用'}</div>
      {p?.risk_level && (
        <span className={`px-1.5 py-0.5 rounded text-[10px]`}>
          {p.risk_level}
        </span>
      )}
    </div>
  ))}
</Modal>
```

### 4. 批准/拒绝逻辑完整

**文件**: `QAChatView.tsx` (line 769-830)

```typescript
const handleApproval = async (action: 'approve' | 'reject') => {
  setApproving(true);
  try {
    // ✅ 1) 逐个提交审批（approve/reject）
    for (const p of approvalPending) {
      const rid = (p as any)?.request_id;
      if (!rid) continue;
      const res = await fetch(getApiUrl(`/api/v1/approvals/${rid}/${action}`), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `******`,
        },
      });
      // ... 处理响应
    }

    if (action === 'reject') {
      toast.success('已拒绝');
      setApprovalPending([]);
      setShowApprovalModal(false);
      return;
    }

    // ✅ 2) 批准后断点续跑
    const first = approvalPending[0] as any;
    toast.success('已批准，正在从断点续跑…');
    if (first?.request_id && first?.thread_id && first?.sub_agent_id) {
      const res = await fetch(getApiUrl(`/api/v1/approvals/${first.request_id}/resume`), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `******`,
        },
        body: JSON.stringify({
          sub_agent_id: first.sub_agent_id,
          thread_id: first.thread_id,
        }),
      });
      // ... 处理续跑结果
    } else {
      toast.warning('缺少续跑定位信息（thread_id/sub_agent_id），请重新提问');
    }
  } finally {
    setApproving(false);
  }
};
```

### 5. API 路由对齐

| 前端调用 | 后端路由 | 状态 |
|----------|----------|------|
| `POST /api/v1/approvals/{id}/approve` | ✅ `/approvals/{id}/approve` | 已注册 |
| `POST /api/v1/approvals/{id}/reject` | ✅ `/approvals/{id}/reject` | 已注册 |
| `POST /api/v1/approvals/{id}/resume` | ✅ `/approvals/{id}/resume` | 已注册 |
| `GET /api/v1/approvals/pending` | ✅ `/approvals/pending` | 已注册 |

**后端注册**: `app/api/v1/router.py` (line 33)
```python
from packages.agent.api.approvals import router as approvals_router
# ...
router.include_router(approvals_router)
```

---

## ⚠️ 待修复问题：缺少 thread_id

### 问题描述

前端审批逻辑依赖 3 个关键字段：
```typescript
if (first?.request_id && first?.thread_id && first?.sub_agent_id) {
  // 调用 resume API
}
```

**现状**：
- ✅ `request_id` - 后端已生成（`PermissionRequest.id`）
- ❌ `thread_id` - **后端未生成和返回**
- ✅ `sub_agent_id` - 后端已通过 `ev.data?.sub_agent_id` 传递

### 根本原因

**文件**: `packages/agent/runtime_engine/tao_graph.py` (line 489-500)

```python
# 当前实现：只返回 pending 信息，缺少 thread_id
if pending_approvals:
    return {
        **state,
        "__interrupt__": {
            "type": "approval_required",
            "pending": pending_approvals,  # ❌ 缺少 thread_id
        },
        # ...
    }
```

### 修复方案

需要在 `permission_check` 节点中注入 `thread_id`：

```python
# 修复后
if pending_approvals:
    # ✅ 从 state 或 config 获取 thread_id
    thread_id = state.get("thread_id") or state.get("session_id", "unknown")
    
    # ✅ 为每个 pending 项添加 thread_id
    for p in pending_approvals:
        p["thread_id"] = thread_id
    
    return {
        **state,
        "__interrupt__": {
            "type": "approval_required",
            "pending": pending_approvals,
            "thread_id": thread_id,  # ✅ 同时在顶层提供
        },
        # ...
    }
```

### 修复位置

1. **`tao_graph.py`** - `create_permission_check_node` 函数
2. **`step_engine.py`** - 确保 `thread_id` 传递到 state
3. **`execution_chain.py`** - 确保 `session_id` 作为 `thread_id` 传递

---

## 📊 前后端集成矩阵

| 功能 | 前端 | 后端 | 集成状态 |
|------|------|------|----------|
| **类型定义** | ✅ | ✅ (Pydantic) | ✅ 完整 |
| **事件协议** | ✅ `approval_required` | ✅ `__interrupt__` | ✅ 完整 |
| **UI 组件** | ✅ Modal 弹窗 | N/A | ✅ 完整 |
| **批准 API** | ✅ 调用 | ✅ `/approve` | ✅ 完整 |
| **拒绝 API** | ✅ 调用 | ✅ `/reject` | ✅ 完整 |
| **续跑 API** | ✅ 调用 | ✅ `/resume` | ✅ 完整 |
| **request_id** | ✅ 读取 | ✅ 生成 | ✅ 完整 |
| **thread_id** | ✅ 需要 | ❌ 未提供 | ⚠️ **待修复** |
| **sub_agent_id** | ✅ 读取 | ✅ 传递 | ✅ 完整 |

---

## 🎯 修复优先级

### P0（阻塞性）- 1 项

**问题**: 后端未返回 `thread_id`，导致前端无法调用续跑 API

**影响**: 用户批准后无法从断点恢复执行

**修复工作量**: ~30 分钟

**修复文件**:
1. `packages/agent/runtime_engine/tao_graph.py` - 添加 thread_id 到 pending
2. `packages/agent/execution/step_engine.py` - 确保 thread_id 传递到 state

---

## 📝 总结

**前端审批功能已 100% 实现**，包括：
- ✅ 完整的类型定义和类型守卫
- ✅ 审批事件处理和状态管理
- ✅ 审批对话框 UI（Modal）
- ✅ 批准/拒绝/续跑完整逻辑
- ✅ API 调用对齐后端路由

**唯一缺失**：后端未返回 `thread_id`，导致续跑功能无法使用。

**修复建议**：
1. 在 `tao_graph.py` 的 `permission_check` 节点中添加 `thread_id` 生成和传递
2. 测试完整审批流程（提问 → 触发审批 → 批准 → 续跑）
3. 验证前端正确显示审批对话框并成功续跑
