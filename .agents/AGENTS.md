# Agent 开发导航

> Harness 范式：工程师的产出从代码变成了约束系统
> 
> 本文档是**导航地图**，不是百科全书。指向约束、工具和反馈回路。

---

## 快速导航

| 你要做什么？ | 去看这里 |
|-------------|---------|
| 添加新工具 | [tools/](tools/) - 工具 Schema 定义 |
| 修改架构规则 | [architecture-rules.md](architecture-rules.md) |
| 添加技能 | `/api/v1/skills` - 技能注册 API |
| 调试 Agent | [debugging.md](debugging.md) - 追踪和日志 |

---

## 约束系统层次

```
┌─────────────────────────────────────────────────────────────┐
│                    约束层 (Harness)                          │
├─────────────────────────────────────────────────────────────┤
│  1. AGENTS.md (本文档) - 导航地图                            │
│  2. architecture-rules.md - 架构约束（什么不能做）            │
│  3. tools/*.json - 工具 Schema（AI 知道怎么调用）            │
│  4. .harness/rules/*.json - 机械化规则                       │
│  5. .harness/linters/*.py - Lint 检查                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 核心原则

### 1. 仓库即记录系统
不在仓库里的东西，对智能体不存在。
- 所有约束必须写入文件
- 所有工具必须有 Schema
- 所有规则必须可机械化检查

### 2. 地图而非手册
本文档是目录页，不是百科全书。
- 指向约束文件，不解释细节
- 保持简洁，便于 AI 导航

### 3. 机械化执行
文档会腐烂，lint 规则不会。
- 能写成 lint 的，不写成文档
- 规则必须可自动检查

### 4. 智能体可读性
优先为智能体的推理能力优化。
- 使用清晰的 JSON Schema
- 规则命名直白

---

## 工具目录

| 工具 | Schema | 描述 |
|------|--------|------|
| knowledge_base | [tools/knowledge-base.json](tools/knowledge-base.json) | 知识库检索 |
| code_executor | [tools/code-executor.json](tools/code-executor.json) | 沙箱代码执行 |

---

## 架构规则

见 [architecture-rules.md](architecture-rules.md)

核心禁令：
- 禁止直接访问数据库（必须通过服务层）
- 禁止越权访问工作区文件
- 禁止无审计日志的文件操作

---

## 反馈回路

| 检查点 | 脚本 | 触发时机 |
|--------|------|---------|
| 代码提交 | `.harness/feedback/pre-commit.sh` | git commit |
| 执行后检查 | `.harness/feedback/post-execution-check.py` | Agent 执行后 |

---

## 相关文件

- [Runtime Engine 实现](../backend/packages/agent/runtime-engine/) - 执行引擎（不是约束）
- [Workspace 服务](../backend/packages/agent/services/workspace_service.py) - 工作区隔离
- [Sandbox 实现](../backend/packages/agent/sandbox/) - 沙箱执行
