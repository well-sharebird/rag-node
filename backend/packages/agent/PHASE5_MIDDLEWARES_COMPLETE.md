# Phase 5: Hooks 迁移到中间件完成

## 执行时间
2026-08-21

## 新增中间件

### 1. SecurityMiddleware（安全策略检查）
**职责**：
- 工具调用权限检查
- 输入参数安全性验证
- 高危操作拒绝（可配置）

**替代**：`pre-step hook` 的安全检查逻辑

**关键方法**：
- `wrap_tool_call()` - 工具调用前进行权限和参数检查
- `_validate_tool_args()` - 参数安全检查
- `_contains_dangerous_pattern()` - 危险模式检测

**危险模式示例**：
```python
dangerous_patterns = [
    "rm -rf /",
    "chmod 777",
    "sudo rm",
    "drop table",
    "delete from",
    "import os; os.system",
]
```

### 2. SessionLogMiddleware（会话日志记录）
**职责**：
- 记录 think 节点输出
- 记录 act 节点工具调用
- 记录工具执行结果

**替代**：`post-step hook` 的日志记录逻辑

**关键方法**：
- `before_agent()` - 提取 session_id
- `after_agent()` - 记录 agent 执行日志
- `wrap_tool_call()` - 记录工具调用和结果

**日志事件类型**：
- `agent/think` - think 节点输出
- `agent/act` - act 节点执行
- `tool/call` - 工具调用
- `tool/result` - 工具结果
- `tool/error` - 工具错误

### 3. CheckpointMiddleware（检查点管理）
**职责**：
- 执行前恢复检查点
- 执行后保存检查点

**替代**：检查点管理逻辑

**关键方法**：
- `before_agent()` - 恢复检查点
- `after_agent()` - 保存检查点

**懒加载优化**：
- `_restored` 标志防止重复恢复
- 仅在 `has_checkpoint()` 时恢复

## 迁移策略

### Hooks → 中间件映射

| Hooks 类型 | 中间件方法 | 迁移目标 |
|-----------|-----------|---------|
| `pre-step` (安全检查) | `SecurityMiddleware.wrap_tool_call()` | ✅ 完成 |
| `post-step` (日志记录) | `SessionLogMiddleware.after_agent()` | ✅ 完成 |
| `post-step` (检查点) | `CheckpointMiddleware.after_agent()` | ✅ 完成 |
| `waterfall` (事件拦截) | 各中间件 `wrap_tool_call()` | ✅ 完成 |

### 向后兼容

**HooksAdapterMiddleware 仍然保留**，用于兼容现有代码：
- 现有 `add_pre_step()` 调用继续有效
- 现有 `add_post_step()` 调用继续有效
- 现有 `add_waterfall()` 调用继续有效

**新代码推荐使用中间件**：
```python
from packages.agent.runtime import (
    SecurityMiddleware,
    SessionLogMiddleware,
    CheckpointMiddleware,
    make_agent,
)

agent = make_agent(
    llm=llm,
    tools=tools,
    middlewares=[
        SecurityMiddleware(permission_engine=perm_engine),
        SessionLogMiddleware(session_log=session_log),
        CheckpointMiddleware(checkpoint=checkpoint),
    ]
)
```

## 文件变更

### runtime/builtins.py
- **新增行数**：+196 行
- **总行数**：535 行（从 339 行增加）
- **新增中间件**：3 个

### runtime/__init__.py
- **新增导出**：
  - `SecurityMiddleware`
  - `SessionLogMiddleware`
  - `CheckpointMiddleware`
- **更新 __all__**：添加新中间件

## 验证结果

```
✅ builtins.py syntax OK
✅ Phase 5 middlewares import successfully
✅ All runtime exports import successfully
```

## 架构对比

### 旧 Hooks 架构
```
StepDrivenEngine
    ↓
HookRegistry
    ├── pre_step hooks (安全检查)
    ├── post_step hooks (日志/检查点)
    └── waterfall hooks (事件拦截)
    ↓
工具执行
```

### 新中间件架构
```
RuntimeEngine
    ↓
MiddlewareChain
    ├── SecurityMiddleware (安全检查)
    ├── SessionLogMiddleware (日志记录)
    ├── CheckpointMiddleware (检查点)
    └── ...
    ↓
LangGraph (Agent Loop)
```

## 优势

1. **职责清晰**：每个中间件专注单一职责
2. **可组合**：中间件链可灵活组合
3. **可测试**：中间件独立可测
4. **可扩展**：新增中间件不影响现有代码
5. **懒加载**：按需初始化，优化资源占用

## 下一步

### Phase 6: 测试验证
- [ ] 单 Agent 执行流程测试
- [ ] 多 Agent 编排流程测试
- [ ] 中间件单元测试
- [ ] 端到端测试

### Phase 7: 移除 Hooks 兼容层（未来）
- [ ] 迁移所有 `add_pre_step()` 调用
- [ ] 迁移所有 `add_post_step()` 调用
- [ ] 迁移所有 `add_waterfall()` 调用
- [ ] 移除 `HooksAdapterMiddleware`
- [ ] 移除 `HookRegistry` 类
- [ ] 删除 `execution/hooks.py`

## 总结

Phase 5 完成 Hooks 到中间件的迁移，新增 3 个生产级中间件：
- SecurityMiddleware：安全策略检查
- SessionLogMiddleware：会话日志记录
- CheckpointMiddleware：检查点管理

保留向后兼容层，现有 Hooks 代码继续有效，新代码推荐使用中间件模式。
