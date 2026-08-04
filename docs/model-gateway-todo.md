# 模型网关 TODO 需求清单

> 文档版本：1.0  
> 创建时间：2026-07-30  
> 最后更新：2026-07-30

---

## 一、核心能力现状

### ✅ 已实现

| 能力 | 实现状态 | 说明 |
|------|----------|------|
| 多模型统一接口 | ✅ 完成 | `/chat/completions` 支持 LLM/Embedding/Rerank |
| API Key 集中管理 | ✅ 完成 | 供应商统一管理，Key 掩码展示 |
| Token 配额检查 | ⚠️ 部分实现 | 有检查接口但未实际拦截 |
| 成本追踪 | ⚠️ 部分实现 | 记录 token 用量但缺少服务维度 |

---

## 二、缺失能力清单

### P0 - 必须补充（影响核心功能）

#### P0-1: 配额实际拦截

**问题描述**  
当前 `check_quota()` 仅提供检查接口，不会实际阻止超额调用。

**需求**  
- 在 `call_llm()` 调用前执行配额检查
- 超额时抛出 `QuotaExceededError` 并返回 429 状态码
- 支持临时提升配额（紧急情况）

**涉及文件**  
- `backend/app/services/model_gateway_service.py` - `call_llm()` 方法
- `backend/app/api/v1/model_gateway.py` - 错误处理

**验收标准**  
- [ ] 配额用尽后调用被拒绝
- [ ] 返回明确的错误信息（剩余配额/重置时间）
- [ ] 支持管理员临时提升配额

---

#### P0-2: 服务维度追踪

**问题描述**  
`ModelCallLog` 只记录 `user_id` 和 `kb_id`，无法按服务/项目统计成本。

**需求**  
- 增加 `service_name` 字段（如：`qa-bot`, `doc-search`, `agent-chat`）
- 增加 `project_id` 字段（可选，用于多项目管理）
- 调用时自动记录服务标识

**涉及文件**  
- `backend/app/models/model_gateway.py` - `ModelCallLog` 模型
- `backend/app/api/v1/model_gateway.py` - 调用接口增加 `service_name` 参数
- Alembic 迁移脚本

**验收标准**  
- [ ] 可按服务名称查询调用日志
- [ ] 可按服务名称统计 token 用量
- [ ] 向后兼容（不传 service_name 时为空）

---

#### P0-3: 限流实际执行

**问题描述**  
`check_rate_limit()` 仅检查，不拦截。

**需求**  
- 在调用前执行限流检查
- 超限时抛出 `RateLimitExceededError` 并返回 429 状态码
- 支持不同用户等级不同限流策略

**涉及文件**  
- `backend/app/services/model_gateway_service.py` - `call_llm()` 方法

**验收标准**  
- [ ] 超限请求被拒绝
- [ ] 返回 `Retry-After` 头
- [ ] 支持白名单（内部服务不限流）

---

### P1 - 强烈建议（企业级功能）

#### P1-1: 配额预警通知

**问题描述**  
用户配额用到 80% 时无感知，突然被拦截影响业务。

**需求**  
- 用量达 80% 时发送预警通知
- 用量达 100% 时发送告警通知
- 支持多种通知渠道（邮件/钉钉/企业微信）

**涉及文件**  
- `backend/app/services/quota_alert_service.py` (新建)
- `backend/app/workers/quota_alert_worker.py` (新建)
- 定时任务：每日检查配额使用情况

**验收标准**  
- [ ] 支持配置预警阈值（默认 80%）
- [ ] 支持配置通知渠道
- [ ] 同一周期内不重复通知

---

#### P1-2: 成本报表 API

**问题描述**  
无法回答"哪个服务最烧钱"、"本月 token 花费多少"等问题。

**需求**  
- 按服务聚合的月度成本报表
- 按团队聚合的成本分摊
- Token → 法币估算（支持配置单价）

**接口设计**  
```
GET /api/v1/model-gateway/costs/by-service?month=2026-07
GET /api/v1/model-gateway/costs/by-team?month=2026-07
GET /api/v1/model-gateway/costs/trend?days=30
```

**涉及文件**  
- `backend/app/api/v1/model_gateway.py` - 新增成本接口
- `backend/app/services/model_gateway_service.py` - 成本聚合方法

**验收标准**  
- [ ] 支持按月查询
- [ ] 支持按服务/团队聚合
- [ ] 支持导出 CSV

---

#### P1-3: 管理审计日志

**问题描述**  
配额被谁修改了、供应商配置何时变更，无法追溯。

**需求**  
- 记录所有管理操作（配额修改/供应商增删改/路由规则变更）
- 记录操作人/操作时间/变更前后值
- 提供审计日志查询接口

**涉及文件**  
- `backend/app/models/audit_log.py` (新建)
- `backend/app/middleware/audit_log_middleware.py` (新建)

**验收标准**  
- [ ] 所有管理操作可追溯
- [ ] 支持按操作人/时间范围查询
- [ ] 审计日志不可篡改

---

#### P1-4: 供应商故障告警

**问题描述**  
供应商挂了无人知晓，直到用户投诉。

**需求**  
- 健康检查连续失败 N 次后发送告警
- 支持告警分级（Warning/Error/Critical）
- 支持告警静默（维护期间不通知）

**涉及文件**  
- `backend/app/services/model_health_monitor.py` - 集成告警
- `backend/app/config.py` - 告警配置

**验收标准**  
- [ ] 连续失败 3 次发送 Warning
- [ ] 连续失败 5 次发送 Error
- [ ] 支持配置告警接收人

---

### P2 - 可选（锦上添花）

#### P2-1: 审批流集成

**需求**  
- 新模型接入需要审批
- 大额配额调整需要审批
- 对接企业审批系统（钉钉/飞书）

**涉及文件**  
- `backend/app/models/approval_request.py` (新建)
- `backend/app/services/approval_service.py` (新建)

---

#### P2-2: SLA 分级保障

**需求**  
- VIP 客户优先队列
- 普通客户标准队列
- 高峰期降级策略

**涉及文件**  
- `backend/app/services/model_gateway_service.py` - 队列管理

---

#### P2-3: 智能路由优化

**需求**  
- 根据历史延迟选择最优供应商
- 根据成本自动切换便宜供应商
- 支持 A/B 测试分流

---

#### P2-4: Token 预算功能

**需求**  
- 按团队设置月度预算
- 预算快耗尽时自动降速
- 预算报表

---

## 三、实施建议

### 阶段一：补齐核心能力（2-3 周）

| 任务 | 优先级 | 预计工时 | 依赖 |
|------|--------|----------|------|
| P0-1 配额实际拦截 | P0 | 3 天 | - |
| P0-2 服务维度追踪 | P0 | 2 天 | - |
| P0-3 限流实际执行 | P0 | 2 天 | - |

### 阶段二：企业级功能（3-4 周）

| 任务 | 优先级 | 预计工时 | 依赖 |
|------|--------|----------|------|
| P1-1 配额预警通知 | P1 | 3 天 | P0-1 |
| P1-2 成本报表 API | P1 | 4 天 | P0-2 |
| P1-3 管理审计日志 | P1 | 3 天 | - |
| P1-4 供应商故障告警 | P1 | 2 天 | 健康监控 |

### 阶段三：高级功能（按需）

| 任务 | 优先级 | 预计工时 |
|------|--------|----------|
| P2-1 审批流集成 | P2 | 5 天 |
| P2-2 SLA 分级保障 | P2 | 4 天 |
| P2-3 智能路由优化 | P2 | 5 天 |
| P2-4 Token 预算功能 | P2 | 3 天 |

---

## 四、技术债务

| 问题 | 影响 | 建议 |
|------|------|------|
| 模型配置与供应商配置耦合 | 代码可读性差 | 考虑拆分服务层 |
| 健康监控事务冲突 | 并发检测时可能失败 | 已修复为独立 session |
| 缺少单元测试 | 重构风险高 | 建议补充核心逻辑测试 |

---

## 五、相关文档

- [模型网关 API 文档](../backend/app/api/v1/model_gateway.py)
- [模型网关服务实现](../backend/app/services/model_gateway_service.py)
- [熔断器实现](../backend/app/services/model_gateway_service.py#L41-L104)
- [健康监控服务](../backend/app/services/model_health_monitor.py)

---

## 六、变更记录

| 日期 | 变更内容 | 作者 |
|------|----------|------|
| 2026-07-30 | 初始版本，梳理 TODO 清单 | - |
