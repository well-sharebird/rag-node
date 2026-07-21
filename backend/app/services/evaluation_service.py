"""
Evaluation service - RAG 评估服务
集成 RAGAS 指标、Golden Dataset、评估运行
"""
from __future__ import annotations
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("app.services.evaluation")


@dataclass
class RAGASEvalResult:
    """RAGAS 评估结果"""
    answer_relevancy: float = 0.0  # 答案相关性 (0-1)
    faithfulness: float = 0.0  # 忠实度 (0-1)
    answer_correctness: float = 0.0  # 答案正确性 (0-1)
    context_precision: float = 0.0  # 上下文精确度 (0-1)
    context_recall: float = 0.0  # 上下文召回率 (0-1)
    answer_similarity: float = 0.0  # 答案相似度 (0-1)

    @property
    def overall_score(self) -> float:
        """计算总体分数（加权平均）"""
        weights = {
            'answer_relevancy': 0.2,
            'faithfulness': 0.2,
            'answer_correctness': 0.25,
            'context_precision': 0.15,
            'context_recall': 0.2,
        }
        return sum(getattr(self, k) * v for k, v in weights.items())


@dataclass
class GoldenSample:
    """Golden Sample 测试样本"""
    id: str
    question: str
    expected_answer: str
    expected_context: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class EvaluationService:
    """RAG 评估服务"""

    def __init__(self, llm_service=None, embedding_service=None):
        self.llm_service = llm_service
        self.embedding_service = embedding_service

    async def evaluate_answer(
        self,
        question: str,
        answer: str,
        contexts: List[str],
        ground_truth: Optional[str] = None,
    ) -> RAGASEvalResult:
        """
        评估 RAG 答案质量（简化版 RAGAS 指标）

        使用 LLM 进行启发式评估，无需安装 ragas 库
        """
        result = RAGASEvalResult()

        if not self.llm_service:
            logger.warning("LLM service not available, using default scores")
            return result

        # 1. Answer Relevancy (答案相关性)
        relevancy_prompt = f"""
请评估以下答案与问题的相关性（0-1 分）：

问题：{question}
答案：{answer}

评分标准：
- 1.0: 答案完全相关，直接回答问题
- 0.5: 答案部分相关
- 0.0: 答案完全不相关

只返回 0-1 之间的数字："""

        try:
            relevancy_text = await self.llm_service.generate(relevancy_prompt, max_tokens=10)
            result.answer_relevancy = float(relevancy_text.strip())
        except:
            result.answer_relevancy = 0.5

        # 2. Faithfulness (忠实度) - 答案是否基于上下文
        faithfulness_prompt = f"""
请评估答案是否忠实于提供的上下文（0-1 分）：

上下文：
{" ".join(contexts[:3])}

答案：{answer}

评分标准：
- 1.0: 答案完全基于上下文，无幻觉
- 0.5: 答案部分基于上下文
- 0.0: 答案包含大量上下文未提及的信息

只返回 0-1 之间的数字："""

        try:
            faithfulness_text = await self.llm_service.generate(faithfulness_prompt, max_tokens=10)
            result.faithfulness = float(faithfulness_text.strip())
        except:
            result.faithfulness = 0.5

        # 3. Context Precision (上下文精确度)
        if contexts:
            precision_prompt = f"""
请评估检索到的上下文对回答问题的有用程度（0-1 分）：

问题：{question}
上下文：{" ".join(contexts[:3])}

评分标准：
- 1.0: 所有上下文都有用
- 0.5: 部分上下文有用
- 0.0: 上下文都无用

只返回 0-1 之间的数字："""

            try:
                precision_text = await self.llm_service.generate(precision_prompt, max_tokens=10)
                result.context_precision = float(precision_text.strip())
            except:
                result.context_precision = 0.5

        # 4. Answer Correctness (如果有 ground truth)
        if ground_truth:
            correctness_prompt = f"""
请比较答案与正确答案的相似度（0-1 分）：

问题：{question}
正确答案：{ground_truth}
模型答案：{answer}

评分标准：
- 1.0: 答案与正确答案语义等价
- 0.5: 答案部分正确
- 0.0: 答案错误

只返回 0-1 之间的数字："""

            try:
                correctness_text = await self.llm_service.generate(correctness_prompt, max_tokens=10)
                result.answer_correctness = float(correctness_text.strip())
            except:
                result.answer_correctness = 0.5

        return result

    async def batch_evaluate(
        self,
        samples: List[GoldenSample],
        rag_function: callable,
    ) -> Dict[str, Any]:
        """
        批量评估 Golden Samples

        Args:
            samples: Golden Sample 列表
            rag_function: RAG 函数，接收 question 返回 (answer, contexts)

        Returns:
            评估统计信息
        """
        results = []
        scores_by_metric = {
            'answer_relevancy': [],
            'faithfulness': [],
            'answer_correctness': [],
            'context_precision': [],
        }

        for sample in samples:
            try:
                answer, contexts = await rag_function(sample.question)

                eval_result = await self.evaluate_answer(
                    sample.question,
                    answer,
                    contexts,
                    sample.expected_answer,
                )

                results.append({
                    'sample_id': sample.id,
                    'question': sample.question,
                    'expected': sample.expected_answer,
                    'predicted': answer,
                    'eval': eval_result,
                })

                # 收集分数
                for metric in scores_by_metric:
                    scores_by_metric[metric].append(getattr(eval_result, metric))

            except Exception as e:
                logger.warning("Evaluation failed for sample %s: %s", sample.id, e)

        # 计算平均分
        avg_scores = {
            metric: sum(scores) / len(scores) if scores else 0.0
            for metric, scores in scores_by_metric.items()
        }

        return {
            'total_samples': len(samples),
            'evaluated': len(results),
            'avg_scores': avg_scores,
            'overall_score': sum(avg_scores.values()) / len(avg_scores),
            'details': results,
        }


# ============================================================
# Golden Dataset 管理
# ============================================================

class GoldenDatasetService:
    """Golden Dataset 管理服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_golden_sample(
        self,
        kb_id: str,
        question: str,
        expected_answer: str,
        expected_context_ids: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """创建 Golden Sample"""
        from app.models.evaluation import GoldenSample as GoldenSampleModel
        import uuid
        import json

        sample = GoldenSampleModel(
            id=str(uuid.uuid4()),
            kb_id=kb_id,
            question=question,
            expected_answer=expected_answer,
            expected_context_ids=json.dumps(expected_context_ids) if expected_context_ids else None,
            metadata_json=json.dumps(metadata) if metadata else None,
        )

        self.db.add(sample)
        await self.db.commit()

        return sample.id

    async def list_golden_samples(
        self,
        kb_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[GoldenSample]:
        """获取 Golden Samples"""
        from app.models.evaluation import GoldenSample as GoldenSampleModel
        import json

        query = select(GoldenSampleModel).order_by(GoldenSampleModel.created_at.desc()).limit(limit)
        if kb_id:
            query = query.where(GoldenSampleModel.kb_id == kb_id)

        result = await self.db.execute(query)
        samples = result.scalars().all()

        return [
            GoldenSample(
                id=s.id,
                question=s.question,
                expected_answer=s.expected_answer,
                expected_context=json.loads(s.expected_context_ids) if s.expected_context_ids else [],
                metadata=json.loads(s.metadata_json) if s.metadata_json else {},
            )
            for s in samples
        ]

    async def delete_golden_sample(self, sample_id: str) -> bool:
        """删除 Golden Sample"""
        from app.models.evaluation import GoldenSample as GoldenSampleModel
        from sqlalchemy import delete

        await self.db.execute(delete(GoldenSampleModel).where(GoldenSampleModel.id == sample_id))
        await self.db.commit()
        return True


# ============================================================
# Evaluation Run 管理
# ============================================================

class EvaluationRunService:
    """评估运行管理服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_run(
        self,
        kb_id: str,
        name: str,
        evaluation_type: str,  # golden_dataset, manual, production
        metrics: List[str],
        config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """创建评估运行记录"""
        from app.models.evaluation import EvaluationRun
        import uuid
        import json

        run = EvaluationRun(
            id=str(uuid.uuid4()),
            kb_id=kb_id,
            name=name,
            evaluation_type=evaluation_type,
            metrics=json.dumps(metrics),
            config_json=json.dumps(config) if config else None,
            status='pending',
        )

        self.db.add(run)
        await self.db.commit()

        return run.id

    async def update_run_status(
        self,
        run_id: str,
        status: str,  # pending, running, completed, failed
        results: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ):
        """更新评估运行状态"""
        from app.models.evaluation import EvaluationRun
        from sqlalchemy import update
        import json

        values = {
            'status': status,
            'completed_at': datetime.utcnow() if status in ('completed', 'failed') else None,
        }

        if results:
            values['results_json'] = json.dumps(results)
        if error_message:
            values['error_message'] = error_message

        await self.db.execute(
            update(EvaluationRun)
            .where(EvaluationRun.id == run_id)
            .values(**values)
        )
        await self.db.commit()


# Global instances
_evaluation_service: Optional[EvaluationService] = None


def get_evaluation_service(llm_service=None, embedding_service=None) -> EvaluationService:
    """Get or create evaluation service"""
    global _evaluation_service
    if _evaluation_service is None:
        _evaluation_service = EvaluationService(llm_service, embedding_service)
    return _evaluation_service
