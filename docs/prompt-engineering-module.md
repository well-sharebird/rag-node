# 提示词工程模块设计文档

> **版本**: 1.0.0  
> **状态**: Design  
> **最后更新**: 2026-07-21

---

## 一、模块概述

### 1.1 核心目标

**对提示词进行工业化管理**：像管理代码一样管理提示词，实现版本控制、效果评估、灰度发布和回滚。

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| **不可变性** | 版本一旦创建不可修改，只能新增版本 |
| **语义化版本** | 采用 SemVer 2.0.0 规范（major.minor.patch） |
| **标签指针** | 标签（stable/beta/dev）是指向版本的可变指针 |
| **评估驱动** | 发布前必须通过 LLM-as-Judge 评估 |
| **灰度安全** | 支持小流量验证，问题秒级回滚 |

### 1.3 与技能模块的关系

| 维度 | 技能版本管理 | 提示词工程管理 | 共享设施 |
|------|-------------|---------------|----------|
| **管理对象** | Python 代码 + 配置 | 提示词模板 | - |
| **存储介质** | 文件系统 | PostgreSQL | - |
| **验证方式** | 单元测试 + 集成测试 | LLM-as-Judge | - |
| **标签体系** | ✅ 共享 | ✅ 共享 | `artifact_tags` 表 |
| **灰度逻辑** | ✅ 共享 | ✅ 共享 | `resolve_effective_version()` |

---

## 二、功能性需求

### 2.1 需求清单（优先级排序）

| ID | 需求 | 优先级 | 验收标准 |
|----|------|--------|----------|
| **PR-01** | 多版本存储（不可变） | P0 | 每次修改生成新版本，旧版本内容不可篡改 |
| **PR-02** | 语义化版本 + 标签 | P0 | 支持 `1.2.0` 和 `stable`/`beta`/`dev` 标签 |
| **PR-03** | 模板变量渲染 | P0 | 支持 `{{user_name}}` 语法，渲染延迟 < 5ms |
| **PR-04** | 提示词 CRUD API | P0 | 创建、读取、更新（新增版本）、删除（软删除） |
| **PR-05** | 标签管理 API | P0 | 创建/修改/删除标签，标签指向指定版本 |
| **PR-06** | 回滚能力 | P0 | 一键将标签指向旧版本 |
| **PR-07** | 变更历史与 Changelog | P0 | 可查询所有版本及变更说明 |
| **PR-08** | 测试用例集管理 | P1 | 支持录入输入 + 期望输出/行为 |
| **PR-09** | 离线评估（LLM-as-Judge） | P1 | 对比新旧版本，输出 0-100 分报告 |
| **PR-10** | 灰度发布策略 | P1 | 支持按用户 ID 哈希分流（如 5% 流量） |
| **PR-11** | 提示词依赖/引用 | P2 | 支持引用其他提示词片段（可复用） |
| **PR-12** | 审计日志 | P1 | 记录所有发布、回滚、标签变更操作 |

---

## 三、非功能性需求

| ID | 需求 | 指标 |
|----|------|------|
| **NFR-01** | 渲染延迟 | P99 < 5ms（不含 LLM 调用） |
| **NFR-02** | 版本检索 | P99 < 50ms（按标签查询） |
| **NFR-03** | 热加载 | 标签切换后立即可用，无需重启 |
| **NFR-04** | 审计完整性 | 100% 记录发布/回滚/标签操作 |
| **NFR-05** | 安全性 | 模板注入防护，用户输入转义 |
| **NFR-06** | 可用性 | 评估支持抽样，控制成本 |

---

## 四、数据模型设计

### 4.1 ER 图

```
┌─────────────────────┐     ┌─────────────────────┐
│  prompt_templates   │────▶│   prompt_versions   │
├─────────────────────┤  1:N ├─────────────────────┤
│ id (PK)             │     │ id (PK)             │
│ name (UNIQUE)       │     │ template_id (FK)    │
│ description         │     │ version             │
│ category            │     │ semver_major/minor  │
│ owner               │     │ semver_prerelease   │
│ status              │     │ content             │
│ created_at          │     │ variables_schema    │
└─────────────────────┘     │ system_role         │
                            │ changelog           │
┌─────────────────────┐     │ released_at         │
│    prompt_tags      │     │ released_by         │
├─────────────────────┤     │ status              │
│ id (PK)             │     │ latest_eval_score   │
│ template_id (FK)    │     │ eval_dataset_hash   │
│ tag_name            │     └─────────────────────┘
│ version_id (FK)     │
│ meta_config (JSON)  │     ┌─────────────────────┐
│ updated_at          │     │    test_cases       │
└─────────────────────┘     ├─────────────────────┤
                            │ id (PK)             │
┌─────────────────────┐     │ template_id (FK)    │
│    eval_runs        │     │ input_context (JSON)│
├─────────────────────┤     │ expected_output     │
│ id (PK)             │     │ expected_behavior   │
│ version_id (FK)     │     │ tags                │
│ test_case_ids (JSON)│     │ created_at          │
│ avg_score           │     └─────────────────────┘
│ detailed_results    │
│ run_at              │     ┌─────────────────────┐
│ triggered_by        │     │  audit_logs         │
└─────────────────────┘     ├─────────────────────┤
                            │ id (PK)             │
                            │ actor               │
                            │ action              │
                            │ resource_type       │
                            │ resource_id         │
                            │ old_value (JSON)    │
                            │ new_value (JSON)    │
                            │ created_at          │
                            └─────────────────────┘
```

---

### 4.2 表结构定义（PostgreSQL）

#### 表 1: `prompt_templates`（模板主表）

```sql
CREATE TABLE prompt_templates (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    category VARCHAR(50) NOT NULL DEFAULT 'system',  -- system | user | instruction
    owner VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'active',    -- active | archived
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_pt_name ON prompt_templates(name);
CREATE INDEX idx_pt_status ON prompt_templates(status);
```

#### 表 2: `prompt_versions`（版本表 —— 核心）

```sql
CREATE TABLE prompt_versions (
    id SERIAL PRIMARY KEY,
    template_id INTEGER NOT NULL REFERENCES prompt_templates(id) ON DELETE CASCADE,
    
    -- 语义化版本
    version VARCHAR(50) NOT NULL,
    semver_major INTEGER NOT NULL DEFAULT 0,
    semver_minor INTEGER NOT NULL DEFAULT 0,
    semver_patch INTEGER NOT NULL DEFAULT 0,
    semver_prerelease VARCHAR(50),  -- beta.1, rc.2
    
    -- 核心内容
    content TEXT NOT NULL,
    variables_schema JSONB NOT NULL DEFAULT '[]',  -- [{name, type, required, default}]
    system_role TEXT,
    
    -- 元数据
    changelog TEXT,
    released_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    released_by VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'draft',  -- draft | released | archived
    
    -- 评测
    latest_eval_score DECIMAL(5,2),  -- 0-100
    eval_dataset_hash VARCHAR(64),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT unique_template_version UNIQUE (template_id, version)
);

CREATE INDEX idx_pv_template ON prompt_versions(template_id);
CREATE INDEX idx_pv_semver ON prompt_versions(semver_major, semver_minor, semver_patch);
CREATE INDEX idx_pv_status ON prompt_versions(status);
```

#### 表 3: `prompt_tags`（标签指针）

```sql
CREATE TABLE prompt_tags (
    id SERIAL PRIMARY KEY,
    template_id INTEGER NOT NULL REFERENCES prompt_templates(id) ON DELETE CASCADE,
    tag_name VARCHAR(50) NOT NULL,  -- stable | beta | dev | canary
    version_id INTEGER NOT NULL REFERENCES prompt_versions(id) ON DELETE CASCADE,
    
    -- 灰度配置
    meta_config JSONB NOT NULL DEFAULT '{}',  -- {gray_percent: 5, target_users: []}
    
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_by VARCHAR(255),
    
    CONSTRAINT unique_template_tag UNIQUE (template_id, tag_name)
);

CREATE INDEX idx_ptag_template ON prompt_tags(template_id);
CREATE INDEX idx_ptag_name ON prompt_tags(tag_name);

COMMENT ON COLUMN prompt_tags.meta_config IS '灰度配置：gray_percent(0-100), target_users(array)';
```

#### 表 4: `test_cases`（测试用例集）

```sql
CREATE TABLE test_cases (
    id SERIAL PRIMARY KEY,
    template_id INTEGER NOT NULL REFERENCES prompt_templates(id) ON DELETE CASCADE,
    
    input_context JSONB NOT NULL,  -- 渲染变量：{"user_name": "Alice", "context": "..."}
    expected_output TEXT,          -- 期望输出（精确匹配）
    expected_behavior TEXT,        -- 期望行为描述（LLM-as-Judge 用）
    
    tags JSONB NOT NULL DEFAULT '[]',  -- ["边界条件", "正常场景", "安全测试"]
    priority INTEGER NOT NULL DEFAULT 1,  -- 1-5, 1 最高
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by VARCHAR(255),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX idx_tc_template ON test_cases(template_id);
CREATE INDEX idx_tc_tags ON test_cases USING GIN(tags);
CREATE INDEX idx_tc_priority ON test_cases(priority);
```

#### 表 5: `eval_runs`（评估运行记录）

```sql
CREATE TABLE eval_runs (
    id SERIAL PRIMARY KEY,
    version_id INTEGER NOT NULL REFERENCES prompt_versions(id) ON DELETE CASCADE,
    baseline_version_id INTEGER REFERENCES prompt_versions(id),  -- 对比基准
    
    test_case_ids JSONB NOT NULL,  -- [1, 2, 3, ...]
    
    -- 汇总结果
    avg_score DECIMAL(5,2),
    pass_count INTEGER,
    fail_count INTEGER,
    total_count INTEGER,
    
    -- 详细结果
    detailed_results JSONB NOT NULL,  -- [{case_id, score, llm_output, reasoning}]
    
    run_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    triggered_by VARCHAR(50) NOT NULL,  -- manual | ci | pre_release
    run_duration_ms INTEGER,
    
    CONSTRAINT chk_score_range CHECK (avg_score >= 0 AND avg_score <= 100)
);

CREATE INDEX idx_er_version ON eval_runs(version_id);
CREATE INDEX idx_er_run_at ON eval_runs(run_at);
```

#### 表 6: `audit_logs`（审计日志）

```sql
CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    actor VARCHAR(255) NOT NULL,
    action VARCHAR(50) NOT NULL,  -- create | update | tag | rollback | eval
    resource_type VARCHAR(50) NOT NULL,  -- template | version | tag
    resource_id INTEGER NOT NULL,
    
    old_value JSONB,
    new_value JSONB,
    
    ip_address INET,
    user_agent TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_audit_actor ON audit_logs(actor);
CREATE INDEX idx_audit_action ON audit_logs(action);
CREATE INDEX idx_audit_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX idx_audit_time ON audit_logs(created_at);
```

---

## 五、核心服务设计

### 5.1 服务分层

```
services/
└── prompt/
    ├── __init__.py
    ├── models.py           # SQLAlchemy 模型
    ├── schemas.py          # Pydantic  schemas
    ├── registry.py         # 注册中心（CRUD）
    ├── renderer.py         # 渲染引擎（Jinja2 沙箱）
    ├── evaluator.py        # 评估引擎（LLM-as-Judge）
    ├── publisher.py        # 发布控制（标签 + 灰度）
    └── audit.py            # 审计日志
```

---

### 5.2 渲染引擎（Renderer）

**文件**: `services/prompt/renderer.py`

```python
from jinja2 import Template, UndefinedError, SecurityError
from jinja2.sandbox import SandboxedEnvironment

class PromptRenderer:
    """提示词渲染引擎 - 带沙箱防护"""
    
    # 沙箱环境：禁止危险操作
    _env = SandboxedEnvironment(
        autoescape=False,  # 输出为纯文本，非 HTML
        undefined=lambda: ""  # 缺失变量返回空串，不报错
    )
    
    @staticmethod
    def render(content: str, variables: dict, schema: list) -> tuple[str, list[str]]:
        """
        渲染提示词模板
        
        Args:
            content: 原始模板内容（含 {{var}}）
            variables: 变量字典
            schema: 变量 schema 定义 [{name, type, required, default}]
        
        Returns:
            (rendered_text, warnings)
        
        Raises:
            SecurityError: 检测到模板注入尝试
        """
        warnings = []
        
        # 1. 变量校验与默认值填充
        validated_vars = PromptRenderer._validate_variables(variables, schema, warnings)
        
        # 2. 沙箱渲染
        try:
            template = PromptRenderer._env.from_string(content)
            rendered = template.render(**validated_vars)
        except SecurityError as e:
            raise SecurityError(f"模板注入检测：{str(e)}")
        except UndefinedError as e:
            warnings.append(f"变量未定义：{str(e)}")
            rendered = content  # 返回原始内容
        
        return rendered, warnings
    
    @staticmethod
    def _validate_variables(variables: dict, schema: list, warnings: list) -> dict:
        """校验变量并填充默认值"""
        result = {}
        schema_map = {s["name"]: s for s in schema}
        
        for var_def in schema:
            name = var_def["name"]
            required = var_def.get("required", False)
            default = var_def.get("default")
            
            if name in variables:
                # 类型校验
                expected_type = var_def.get("type", "string")
                value = variables[name]
                if not PromptRenderer._check_type(value, expected_type):
                    warnings.append(f"变量 {name} 类型不符，期望 {expected_type}")
                result[name] = value
            elif required:
                warnings.append(f"必需变量缺失：{name}")
                result[name] = f"__MISSING:{name}__"
            else:
                result[name] = default or ""
        
        return result
    
    @staticmethod
    def _check_type(value: any, expected_type: str) -> bool:
        """简单的类型检查"""
        type_map = {
            "string": str,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict
        }
        expected = type_map.get(expected_type)
        if expected is None:
            return True
        return isinstance(value, expected)
```

---

### 5.3 评估引擎（Evaluator）

**文件**: `services/prompt/evaluator.py`

```python
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class EvalResult:
    case_id: int
    score: float  # 0-100
    llm_output: str
    reasoning: str
    passed: bool

@dataclass
class EvalReport:
    version_id: int
    baseline_version_id: int
    avg_score: float
    delta: float  # 相对 baseline 的变化
    results: List[EvalResult]
    passed: bool  # 整体是否通过

class PromptEvaluator:
    """提示词评估引擎 - LLM-as-Judge"""
    
    # Judge Prompt 模板
    JUDGE_PROMPT = """
你是一位专业的提示词评估专家。请对比两个版本的提示词在相同输入下的输出质量。

## 评估维度
1. **准确性**: 输出是否正确、无幻觉
2. **完整性**: 是否覆盖了所有要点
3. **格式**: 是否符合要求的输出格式
4. **语气/风格**: 是否符合预期的语气

## 输入
- **测试用例**: {{test_case_description}}
- **期望行为**: {{expected_behavior}}
- **版本 A 输出**: {{output_a}}
- **版本 B 输出**: {{output_b}}

## 输出要求
请严格按照以下 JSON 格式输出：
{
    "score_a": <0-100 的整数>,
    "score_b": <0-100 的整数>,
    "winner": "A" | "B" | "tie",
    "reasoning": "<50 字以内的评估理由>"
}

## 评分标准
- 90-100: 完美符合期望
- 70-89:  基本符合，有小瑕疵
- 50-69:  部分符合，有明显问题
- 0-49:   严重偏离或错误
"""

    async def evaluate(
        self,
        candidate_version_id: int,
        baseline_version_id: int,
        test_case_ids: List[int],
        judge_model: str = "gpt-4o"
    ) -> EvalReport:
        """
        离线评估：对比候选版本与基线版本
        
        Args:
            candidate_version_id: 候选版本 ID
            baseline_version_id: 基线版本 ID（通常为 stable）
            test_case_ids: 测试用例 ID 列表
            judge_model: 裁判模型名称
        
        Returns:
            EvalReport: 评估报告
        """
        results = []
        
        for case_id in test_case_ids:
            # 1. 获取测试用例
            case = await self._get_test_case(case_id)
            
            # 2. 渲染两个版本的提示词
            candidate_prompt = await self._render_version(candidate_version_id, case.input_context)
            baseline_prompt = await self._render_version(baseline_version_id, case.input_context)
            
            # 3. 调用 LLM 获取输出
            output_a = await self._call_llm(baseline_prompt)
            output_b = await self._call_llm(candidate_prompt)
            
            # 4. LLM-as-Judge 打分
            judge_input = self._build_judge_input(case, output_a, output_b)
            judge_output = await self._call_judge(judge_input, judge_model)
            
            # 5. 解析结果
            result = self._parse_judge_output(case_id, judge_output, output_b)
            results.append(result)
        
        # 6. 汇总报告
        avg_score = sum(r.score for r in results) / len(results)
        baseline_avg = sum(r.score for r in results) / len(results)  # 简化：实际应单独计算
        delta = avg_score - baseline_avg
        
        return EvalReport(
            version_id=candidate_version_id,
            baseline_version_id=baseline_version_id,
            avg_score=avg_score,
            delta=delta,
            results=results,
            passed=delta >= 3.0  # 提升 >= 3 分才算通过
        )
    
    def _build_judge_input(self, case, output_a: str, output_b: str) -> dict:
        """构建 Judge 输入"""
        return {
            "test_case_description": case.expected_behavior or case.expected_output,
            "expected_behavior": case.expected_behavior,
            "output_a": output_a,
            "output_b": output_b
        }
```

---

### 5.4 发布控制（Publisher）

**文件**: `services/prompt/publisher.py`

```python
class PromptPublisher:
    """发布控制中心 - 标签管理 + 灰度策略"""
    
    async def resolve_effective_version(
        self,
        template_name: str,
        user_id: Optional[str] = None
    ) -> int:
        """
        解析生效版本（决策链）
        
        决策优先级:
        1. 用户级锁定（如有）
        2. 灰度规则（Canary）
        3. 全局默认（stable）
        """
        template = await self._get_template(template_name)
        
        # 1. 用户锁定
        if user_id:
            locked = await self._get_user_lock(template.id, user_id)
            if locked:
                return locked.version_id
        
        # 2. 灰度（Canary）
        canary_tag = await self._get_tag(template.id, "canary")
        if canary_tag:
            gray_percent = canary_tag.meta_config.get("gray_percent", 0)
            if self._hit_gray(user_id, gray_percent):
                return canary_tag.version_id
        
        # 3. 默认稳定版
        stable_tag = await self._get_tag(template.id, "stable")
        if stable_tag:
            return stable_tag.version_id
        
        # 4. 回退：最新 released 版本
        return await self._get_latest_released(template.id)
    
    def _hit_gray(self, user_id: Optional[str], percent: int) -> bool:
        """灰度命中判断 - 基于用户 ID 哈希"""
        if not user_id:
            return False
        hash_val = hash(user_id) % 100
        return hash_val < percent
    
    async def tag_version(
        self,
        template_id: int,
        version_id: int,
        tag_name: str,
        meta_config: dict = None,
        actor: str = "system"
    ):
        """
        给版本打标签
        
        预检查:
        - 版本必须存在且状态为 released
        - 评估分数必须达标（如果是 stable 标签）
        """
        version = await self._get_version(version_id)
        
        # 预检查：stable 标签必须通过评估
        if tag_name == "stable":
            if version.latest_eval_score is None:
                raise ValueError("stable 标签必须先通过评估")
            if version.latest_eval_score < 70:
                raise ValueError(f"评估分数 {version.latest_eval_score} < 70，禁止发布")
        
        # 更新或创建标签
        await self._upsert_tag(template_id, tag_name, version_id, meta_config, actor)
    
    async def rollback(
        self,
        template_id: int,
        target_version_id: int,
        tag_name: str = "stable",
        actor: str = "system"
    ):
        """
        回滚：将标签指向旧版本
        
        注意：不删除任何版本，只移动标签指针
        """
        await self._upsert_tag(template_id, tag_name, target_version_id, {}, actor)
```

---

## 六、API 设计

### 6.1 RESTful API 路由

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| **模板管理** |
| POST | `/api/v1/prompts` | 创建新提示词模板 | Editor+ |
| GET | `/api/v1/prompts` | 获取模板列表 | Viewer+ |
| GET | `/api/v1/prompts/{name}` | 获取模板详情 | Viewer+ |
| GET | `/api/v1/prompts/{name}/versions` | 获取版本列表 | Viewer+ |
| GET | `/api/v1/prompts/{name}/tags` | 获取标签列表 | Viewer+ |
| **版本操作** |
| POST | `/api/v1/prompts/{name}/versions` | 创建新版本 | Editor+ |
| GET | `/api/v1/prompts/{name}/versions/{version}` | 获取版本详情 | Viewer+ |
| DELETE | `/api/v1/prompts/{name}/versions/{version}` | 归档版本 | Editor+ |
| **标签管理** |
| POST | `/api/v1/prompts/{name}/tags` | 创建/更新标签 | Admin+ |
| DELETE | `/api/v1/prompts/{name}/tags/{tag}` | 删除标签 | Admin+ |
| POST | `/api/v1/prompts/{name}/rollback` | 回滚到指定版本 | Admin+ |
| **评估** |
| POST | `/api/v1/prompts/{name}/eval` | 运行离线评估 | Editor+ |
| GET | `/api/v1/prompts/{name}/eval/{run_id}` | 获取评估报告 | Viewer+ |
| **运行时** |
| POST | `/api/v1/prompts/{name}/render` | 渲染提示词 | 内部调用 |
| GET | `/api/v1/prompts/{name}/resolve` | 获取生效版本 | 内部调用 |

---

### 6.2 核心 Schema 定义

**文件**: `schemas/prompt.py`

```python
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

# --- 请求 Schema ---

class PromptTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    category: str = "system"
    owner: Optional[str] = None

class PromptVersionCreate(BaseModel):
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$")
    content: str = Field(..., min_length=1)
    variables_schema: List[Dict[str, Any]] = []
    system_role: Optional[str] = None
    changelog: Optional[str] = None

class TagCreate(BaseModel):
    tag_name: str = Field(..., pattern=r"^[a-z]+$")  # stable, beta, dev, canary
    version_id: int
    meta_config: Dict[str, Any] = {}

class EvalRequest(BaseModel):
    candidate_version_id: int
    baseline_version_id: Optional[int] = None  # 默认使用 stable
    test_case_ids: Optional[List[int]] = None  # 默认使用全部 active 用例
    judge_model: str = "gpt-4o"

# --- 响应 Schema ---

class PromptTemplateResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    category: str
    owner: Optional[str]
    status: str
    created_at: datetime
    current_tags: Dict[str, str]  # {tag_name: version}

class PromptVersionResponse(BaseModel):
    id: int
    version: str
    content: str
    variables_schema: List[Dict[str, Any]]
    system_role: Optional[str]
    changelog: Optional[str]
    released_by: Optional[str]
    released_at: datetime
    status: str
    latest_eval_score: Optional[float]

class EvalReportResponse(BaseModel):
    run_id: int
    avg_score: float
    delta: float
    passed: bool
    total_count: int
    pass_count: int
    results: List[Dict[str, Any]]
    run_at: datetime
```

---

## 七、CLI 工具设计

### 7.1 命令结构

```bash
# 提交新版本（草稿）
uv run python -m app.cli prompt commit <template_name> \
    --file ./prompt.md \
    --version 2.0.0-beta \
    --changelog "优化了格式要求"

# 运行离线评估（对比 stable）
uv run python -m app.cli prompt eval <template_name> \
    --candidate 2.0.0-beta \
    --baseline stable \
    --dataset full \
    --sample 10  # 抽样 10 条

# 提升为 canary（灰度 5%）
uv run python -m app.cli prompt tag <template_name> \
    --version 2.0.0-beta \
    --tag canary \
    --gray-percent 5

# 提升为 stable（全量）
uv run python -m app.cli prompt tag <template_name> \
    --version 2.0.0-beta \
    --tag stable

# 紧急回滚
uv run python -m app.cli prompt rollback <template_name> \
    --to 1.5.0 \
    --tag stable \
    --force

# 查看评估报告
uv run python -m app.cli prompt report <template_name> \
    --version 2.0.0-beta \
    --baseline 1.5.0
```

---

## 八、实施计划

### 8.1 阶段划分

| 阶段 | 内容 | 预计工时 |
|------|------|----------|
| **Phase 1** | 数据库迁移 + 基础模型 | 2h |
| **Phase 2** | 注册中心 CRUD API | 3h |
| **Phase 3** | 渲染引擎（Jinja2 沙箱） | 2h |
| **Phase 4** | 标签管理 + 回滚 | 2h |
| **Phase 5** | 评估引擎（LLM-as-Judge） | 4h |
| **Phase 6** | 审计日志 + CLI 工具 | 2h |
| **Phase 7** | 集成测试 + 文档 | 2h |

**总计**: ~17 小时

---

### 8.2 依赖项

| 依赖 | 用途 | 是否已有 |
|------|------|----------|
| `jinja2` | 模板渲染 | ❌ 需安装 |
| `jinja2-sandbox` | 沙箱防护 | ❌ 需安装（jinja2 内置） |
| `pydantic` | Schema 校验 | ✅ 已有 |
| `sqlalchemy` | ORM | ✅ 已有 |
| `alembic` | 数据库迁移 | ✅ 已有 |

---

## 九、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 模板注入攻击 | 高 | 使用 SandboxedEnvironment，禁止危险语法 |
| 评估成本过高 | 中 | 支持抽样评估，限制测试集大小 |
| 标签竞争条件 | 中 | 数据库唯一约束 + 事务 |
| 灰度逻辑复杂 | 低 | 与技能模块共享实现，复用代码 |

---

## 十、后续扩展

1. **Web 管理界面**: 可视化编辑、评估报告展示、一键发布
2. **A/B 测试**: 在线分流，收集真实用户反馈
3. **自动评估**: CI 集成，PR 检查卡评估分数
4. **提示词市场**: 跨团队共享优质提示词模板

---

## 附录 A: LLM-as-Judge Prompt 模板

```
你是一位专业的提示词评估专家。请对比两个版本的提示词在相同输入下的输出质量。

## 评估维度
1. **准确性**: 输出是否正确、无幻觉
2. **完整性**: 是否覆盖了所有要点
3. **格式**: 是否符合要求的输出格式
4. **语气/风格**: 是否符合预期的语气

## 输入
- **测试用例描述**: {{test_case_description}}
- **期望行为**: {{expected_behavior}}
- **版本 A（基线）输出**: 
```
{{output_a}}
```
- **版本 B（候选）输出**: 
```
{{output_b}}
```

## 输出要求
请严格按照以下 JSON 格式输出（不要输出其他内容）：
```json
{
    "score_a": <0-100 的整数>,
    "score_b": <0-100 的整数>,
    "winner": "A" | "B" | "tie",
    "reasoning": "<50 字以内的评估理由>"
}
```

## 评分标准
| 分数段 | 描述 |
|--------|------|
| 90-100 | 完美符合期望，无明显问题 |
| 70-89  | 基本符合，有小瑕疵但不影响使用 |
| 50-69  | 部分符合，有明显问题需要改进 |
| 0-49   | 严重偏离或错误，不可接受 |

## 注意事项
- 请客观公正，不要偏向新版本或旧版本
- 如果两个输出质量相近，请选择 "tie"
- 理由请具体说明哪个版本在哪方面更好
```
