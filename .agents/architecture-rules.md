# 架构约束规则

> 这些规则定义了 Agent 的行为边界。违反规则的操作将被拒绝。

---

## 规则 1：禁止直接数据库访问

**规则**：Agent 不能直接执行 SQL 或访问数据库连接。

**为什么**：所有数据访问必须通过服务层，确保：
- 数据验证
- 权限检查
- 审计日志

**机械化检查**：
```bash
# .harness/linters/no-direct-db.py
grep -r "execute.*SELECT\|execute.*INSERT\|execute.*UPDATE\|execute.*DELETE" --include="*.py"
```

**正确做法**：
```python
# ❌ 错误：直接数据库访问
result = await db.execute("SELECT * FROM users WHERE id = 1")

# ✅ 正确：通过服务层
user = await user_service.get_user_by_id(1)
```

---

## 规则 2：工作区边界

**规则**：Agent 只能访问所属用户的工作区文件。

**为什么**：防止越权访问其他用户的数据。

**机械化检查**：
```python
# .harness/linters/check-workspace.py
from packages.agent.services.workspace_service import WorkspaceService

async def check_access(user_id: int, requested_path: str):
    workspace = await workspace_service.get_workspace(user_id)
    if not requested_path.startswith(workspace.root_path):
        raise SecurityError("越权访问")
```

**正确做法**：
```python
# ✅ 使用服务层验证路径
safe_path = workspace_service.resolve_path(workspace, user_request)
```

---

## 规则 3：审计日志

**规则**：所有文件操作必须记录审计日志。

**为什么**：可追溯性是安全的基础。

**机械化检查**：
```python
# .harness/linters/check-audit.py
# 检查文件操作后是否有 log_action 调用
```

**正确做法**：
```python
# ✅ 文件操作 + 审计
await workspace_service.upload_file(...)
await workspace_service.log_action(
    workspace=workspace,
    action="upload",
    file_path=relative_path,
    user_id=user.id,
)
```

---

## 规则 4：沙箱执行

**规则**：所有代码执行必须在沙箱中进行。

**为什么**：防止恶意代码危害系统。

**机械化检查**：
```python
# .harness/linters/check-sandbox.py
# 检查代码执行是否调用了 execute_code_in_sandbox
```

**正确做法**：
```python
# ✅ 沙箱执行
from packages.agent.sandbox.nsjail import execute_code_in_sandbox

result = await execute_code_in_sandbox(
    code=user_code,
    language="python",
    timeout_seconds=30,
)
```

---

## 规则 5：工具白名单

**规则**：Agent 只能调用配置中允许的工具。

**为什么**：防止权限放大攻击。

**机械化检查**：
```python
# .harness/rules/tool-whitelist.json
{
  "rule": "tool_call",
  "check": "allowed_tools",
  "action": "reject_if_not_in_list"
}
```

**正确做法**：
```python
# ✅ 验证工具在白名单内
if tool_name not in allowed_tools:
    raise PermissionError(f"Tool {tool_name} not allowed")
```

---

## 规则 6：记忆注入防护

**规则**：必须检测并拒绝记忆注入攻击。

**为什么**：防止恶意用户通过记忆覆盖系统指令。

**机械化检查**：
```python
# .harness/linters/check-injection.py
INJECTION_PATTERNS = [
    "ignore previous instructions",
    "forget all previous",
    "system instruction:",
]
```

**正确做法**：
```python
# ✅ 注入检测
from packages.agent.runtime_engine.memory import MemoryEngine

if await memory.detect_injection(content):
    raise SecurityError("Memory injection detected")
```

---

## 违规处理

违反以上规则的操作将：
1. 被拒绝执行
2. 记录审计日志
3. 可选：触发告警
