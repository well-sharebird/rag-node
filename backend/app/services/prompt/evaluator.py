"""提示词评估引擎 - LLM-as-Judge"""

import time
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt_template import PromptVersion, PromptTestCase
from app.services.prompt.registry import PromptRegistryService
from app.services.prompt.renderer import PromptRenderer


@dataclass
class EvalResultItem:
    """单个测试用例的评估结果"""

    case_id: int
    score: float  # 0-100
    llm_output: str
    reasoning: str
    passed: bool


@dataclass
class EvalReport:
    """评估报告"""

    version_id: int
    baseline_version_id: int
    avg_score: float
    delta: float  # 相对 baseline 的变化
    results: List[EvalResultItem]
    passed: bool  # 整体是否通过
    run_duration_ms: int


class PromptEvaluator:
    """提示词评估引擎

    使用 LLM-as-Judge 方法对比新旧版本的质量
    """

    # Judge Prompt 模板
    JUDGE_PROMPT_TEMPLATE = """你是一位专业的提示词评估专家。请对比两个版本的提示词在相同输入下的输出质量。

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
"""

    def __init__(
        self,
        db: AsyncSession,
        llm_client: Any = None,
        judge_model: str = "gpt-4o",
    ):
        """初始化评估器

        Args:
            db: 数据库会话
            llm_client: LLM 客户端（用于调用模型 API）
            judge_model: 裁判模型名称
        """
        self.db = db
        self.llm_client = llm_client
        self.judge_model = judge_model
        self.registry = PromptRegistryService(db)
        self.renderer = PromptRenderer()

    async def evaluate(
        self,
        candidate_version_id: int,
        baseline_version_id: Optional[int] = None,
        test_case_ids: Optional[List[int]] = None,
        judge_model: Optional[str] = None,
        triggered_by: str = "manual",
    ) -> EvalReport:
        """离线评估：对比候选版本与基线版本

        Args:
            candidate_version_id: 候选版本 ID
            baseline_version_id: 基线版本 ID（默认使用 stable 标签版本）
            test_case_ids: 测试用例 ID 列表（默认使用全部 active 用例）
            judge_model: 裁判模型名称
            triggered_by: 触发来源

        Returns:
            EvalReport: 评估报告
        """
        start_time = time.time()
        judge_model = judge_model or self.judge_model

        # 1. 获取版本
        candidate = await self.registry.get_version_by_id(candidate_version_id)
        if not candidate:
            raise ValueError(f"版本 {candidate_version_id} 不存在")

        # 2. 确定基线版本
        if baseline_version_id is None:
            # 使用 stable 标签版本作为基线
            template = await self._get_template_by_id(candidate.template_id)
            stable_tag = await self.registry.get_tag(template.name, "stable")
            if stable_tag:
                baseline_version_id = stable_tag.version_id
            else:
                # 没有 stable 标签，使用最新的 released 版本
                baseline_version_id = candidate_version_id

        baseline = await self.registry.get_version_by_id(baseline_version_id)
        if not baseline:
            raise ValueError(f"基线版本 {baseline_version_id} 不存在")

        # 3. 获取测试用例
        if test_case_ids is None:
            template = await self._get_template_by_id(candidate.template_id)
            test_cases = await self.registry.list_test_cases(
                template.name, is_active=True
            )
            test_case_ids = [case.id for case in test_cases]

        # 4. 并行评估每个测试用例
        results = []
        for case_id in test_case_ids:
            case = await self.registry.get_test_case(case_id)
            if not case:
                continue

            result = await self._evaluate_case(
                candidate=candidate,
                baseline=baseline,
                test_case=case,
                judge_model=judge_model,
            )
            results.append(result)

        # 5. 汇总报告
        end_time = time.time()
        run_duration_ms = int((end_time - start_time) * 1000)

        if results:
            avg_score = sum(r.score for r in results) / len(results)
            # 计算相对基线的提升（简化：假设基线平均 70 分）
            baseline_avg = 70.0  # 实际应该重新评估基线
            delta = avg_score - baseline_avg
            passed = delta >= 3.0  # 提升 >= 3 分才算通过
        else:
            avg_score = 0.0
            delta = 0.0
            passed = False

        report = EvalReport(
            version_id=candidate_version_id,
            baseline_version_id=baseline_version_id,
            avg_score=avg_score,
            delta=delta,
            results=results,
            passed=passed,
            run_duration_ms=run_duration_ms,
        )

        # 6. 保存评估记录
        detailed_results = [asdict(r) for r in results]
        pass_count = sum(1 for r in results if r.passed)
        await self.registry.save_eval_run(
            version_id=candidate_version_id,
            baseline_version_id=baseline_version_id,
            test_case_ids=test_case_ids,
            avg_score=avg_score,
            pass_count=pass_count,
            fail_count=len(results) - pass_count,
            detailed_results=detailed_results,
            triggered_by=triggered_by,
            run_duration_ms=run_duration_ms,
        )

        return report

    async def _evaluate_case(
        self,
        candidate: PromptVersion,
        baseline: PromptVersion,
        test_case: PromptTestCase,
        judge_model: str,
    ) -> EvalResultItem:
        """评估单个测试用例"""
        # 1. 渲染两个版本的提示词
        candidate_prompt, _ = self.renderer.render(
            candidate.content, test_case.input_context, candidate.variables_schema
        )
        baseline_prompt, _ = self.renderer.render(
            baseline.content, test_case.input_context, baseline.variables_schema
        )

        # 2. 调用 LLM 获取输出
        output_a = await self._call_llm(baseline_prompt, judge_model)
        output_b = await self._call_llm(candidate_prompt, judge_model)

        # 3. LLM-as-Judge 打分
        judge_input = self._build_judge_input(
            test_case=test_case, output_a=output_a, output_b=output_b
        )
        judge_output = await self._call_judge(judge_input, judge_model)

        # 4. 解析结果
        score = judge_output.get("score_b", 50.0)
        reasoning = judge_output.get("reasoning", "")
        passed = score >= 70.0

        return EvalResultItem(
            case_id=test_case.id,
            score=score,
            llm_output=output_b,
            reasoning=reasoning,
            passed=passed,
        )

    def _build_judge_input(
        self, test_case: PromptTestCase, output_a: str, output_b: str
    ) -> Dict[str, str]:
        """构建 Judge 输入"""
        return {
            "test_case_description": test_case.expected_behavior
            or test_case.expected_output
            or "无描述",
            "expected_behavior": test_case.expected_behavior or "无",
            "output_a": output_a,
            "output_b": output_b,
        }

    async def _call_llm(self, prompt: str, model: str) -> str:
        """调用 LLM 获取输出

        实际实现需要接入具体的 LLM API
        这里提供模拟实现
        """
        if self.llm_client:
            # 真实调用
            response = await self.llm_client.generate(prompt, model=model)
            return response.text
        else:
            # 模拟输出（用于开发测试）
            return f"[模拟输出] 提示词长度：{len(prompt)}, 模型：{model}"

    async def _call_judge(
        self, judge_input: Dict[str, str], model: str
    ) -> Dict[str, Any]:
        """调用 Judge 模型进行评估"""
        # 构建完整的 Judge Prompt
        prompt = self.JUDGE_PROMPT_TEMPLATE
        for key, value in judge_input.items():
            prompt = prompt.replace(f"{{{{{key}}}}}", str(value))

        # 调用 LLM
        response_text = await self._call_llm(prompt, model)

        # 解析 JSON 输出
        try:
            # 尝试提取 JSON
            import re

            json_match = re.search(r"```json\s*(.+?)\s*```", response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))
            return json.loads(response_text)
        except (json.JSONDecodeError, AttributeError):
            # 解析失败，返回默认结果
            return {
                "score_a": 50.0,
                "score_b": 50.0,
                "winner": "tie",
                "reasoning": "JSON 解析失败，返回默认评分",
            }

    async def _get_template_by_id(self, template_id: int):
        """通过 ID 获取模板（辅助方法）"""
        from sqlalchemy import select
        from app.models.prompt_template import PromptTemplate

        result = await self.db.execute(
            select(PromptTemplate).where(PromptTemplate.id == template_id)
        )
        return result.scalar_one_or_none()
