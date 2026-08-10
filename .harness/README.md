# Harness 约束系统

> Harness 不是执行引擎，而是约束系统。
> 
> 工程师的产出从代码变成了约束系统。

---

## 目录结构

```
.harness/
├── rules/              # 机械化规则 (JSON)
│   └── workspace-boundary.json
├── linters/            # Lint 检查脚本
│   ├── check-workspace.py
│   └── check-audit.py
└── feedback/           # 反馈回路
    ├── pre-commit.sh
    └── post-execution-check.py

.agents/
├── AGENTS.md                    # 导航地图
├── architecture-rules.md        # 架构约束
└── tools/
    ├── knowledge-base.json
    └── code-executor.json
```

---

## 与 Runtime Engine 的关系

```
┌─────────────────────────────────────────────────────────────┐
│                    Harness 约束层                             │
│  - AGENTS.md (导航)                                         │
│  - architecture-rules.md (规则)                              │
│  - tools/*.json (工具 Schema)                               │
│  - .harness/rules/*.json (机械化规则)                       │
│  - .harness/linters/*.py (Lint 检查)                        │
└─────────────────────────────────────────────────────────────┘
                            │ 约束
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              Runtime Engine (执行引擎)                        │
│  - Orchestration (编排)                                     │
│  - Memory (记忆)                                            │
│  - Action (行动)                                            │
│  - Governance (管控)                                        │
└─────────────────────────────────────────────────────────────┘
```

**Harness 约束层**定义了什么不能做，**Runtime Engine** 负责执行。

---

## 运行检查

### Pre-commit 检查

```bash
.harness/feedback/pre-commit.sh
```

### Post-execution 检查

```bash
.harness/feedback/post-execution-check.py result.json
```

### 工作区边界检查

```bash
.harness/linters/check-workspace.py /workspace/users/123 /workspace/users/123/file.txt
```

---

## 添加新规则

1. 在 `.harness/rules/` 创建 JSON 规则文件
2. 在 `.harness/linters/` 创建对应的检查脚本
3. 在 `pre-commit.sh` 中添加检查调用

示例规则：

```json
{
  "name": "require-auth",
  "description": "所有 API 请求必须认证",
  "check": {
    "type": "header_exists",
    "field": "Authorization"
  },
  "action": {
    "on_violation": "reject"
  }
}
```
