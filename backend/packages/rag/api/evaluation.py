"""
Evaluation API - RAG 评估接口
"""
import logging
from fastapi import APIRouter, Query, HTTPException, Depends
from typing import Optional, List, Dict, Any

from packages.core.deps import DBSession
from packages.rag.schemas.evaluation import (
    GoldenSampleCreate,
    GoldenSampleResponse,
    EvaluationRunCreate,
    EvaluationRunResponse,
    EvaluationResult,
)
from packages.rag.services.evaluation_service import (
    EvaluationService,
    GoldenDatasetService,
    EvaluationRunService,
    get_evaluation_service,
)

logger = logging.getLogger("app.api.evaluation")
router = APIRouter(prefix="/evaluation", tags=["Evaluation"])


def get_golden_dataset_service(db: DBSession) -> GoldenDatasetService:
    return GoldenDatasetService(db)


def get_run_service(db: DBSession) -> EvaluationRunService:
    return EvaluationRunService(db)


@router.post("/golden-samples", response_model=GoldenSampleResponse, status_code=201)
async def create_golden_sample(
    db: DBSession,
    data: GoldenSampleCreate,
):
    """创建 Golden Sample 测试样本"""
    service = get_golden_dataset_service(db)
    sample_id = await service.create_golden_sample(
        kb_id=data.kb_id,
        question=data.question,
        expected_answer=data.expected_answer,
        expected_context_ids=data.expected_context_ids,
        metadata=data.metadata,
    )
    return GoldenSampleResponse(id=sample_id, **data.model_dump())


@router.get("/golden-samples", response_model=List[GoldenSampleResponse])
async def list_golden_samples(
    db: DBSession,
    kb_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """获取 Golden Samples"""
    service = get_golden_dataset_service(db)
    samples = await service.list_golden_samples(kb_id, limit)

    return [
        GoldenSampleResponse(
            id=s.id,
            kb_id="",  # Not stored in sample object
            question=s.question,
            expected_answer=s.expected_answer,
            expected_context_ids=s.expected_context,
            metadata=s.metadata,
        )
        for s in samples
    ]


@router.delete("/golden-samples/{sample_id}")
async def delete_golden_sample(db: DBSession, sample_id: str):
    """删除 Golden Sample"""
    service = get_golden_dataset_service(db)
    success = await service.delete_golden_sample(sample_id)
    if not success:
        raise HTTPException(status_code=404, detail="Sample not found")
    return {"status": "deleted", "id": sample_id}


@router.post("/runs", response_model=EvaluationRunResponse, status_code=201)
async def create_evaluation_run(
    db: DBSession,
    data: EvaluationRunCreate,
):
    """创建评估运行"""
    service = get_run_service(db)
    run_id = await service.create_run(
        kb_id=data.kb_id,
        name=data.name,
        evaluation_type=data.evaluation_type,
        metrics=data.metrics,
        config=data.config,
    )
    return EvaluationRunResponse(
        id=run_id,
        **data.model_dump(),
        status="pending",
        results=None,
    )


@router.get("/runs/{run_id}", response_model=EvaluationRunResponse)
async def get_evaluation_run(db: DBSession, run_id: str):
    """获取评估运行状态"""
    from packages.rag.models.evaluation import EvaluationRun
    from sqlalchemy import select

    result = await db.execute(select(EvaluationRun).where(EvaluationRun.id == run_id))
    run = result.scalar_one_or_none()

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    import json
    return EvaluationRunResponse(
        id=run.id,
        kb_id=run.kb_id,
        name=run.name,
        evaluation_type=run.evaluation_type,
        metrics=json.loads(run.metrics) if run.metrics else [],
        config=json.loads(run.config_json) if run.config_json else None,
        status=run.status,
        results=json.loads(run.results_json) if run.results_json else None,
    )


@router.post("/runs/{run_id}/execute")
async def execute_evaluation_run(
    db: DBSession,
    run_id: str,
    llm_service=Depends(get_evaluation_service),
):
    """执行评估运行"""
    from packages.rag.models.evaluation import EvaluationRun
    from sqlalchemy import select
    import json

    # Get run
    result = await db.execute(select(EvaluationRun).where(EvaluationRun.id == run_id))
    run = result.scalar_one_or_none()

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Update status to running
    await get_run_service(db).update_run_status(run_id, "running")

    try:
        # Get golden samples
        golden_service = get_golden_dataset_service(db)
        samples = await golden_service.list_golden_samples(run.kb_id)

        if not samples:
            raise HTTPException(status_code=400, detail="No golden samples found for this KB")

        # Mock RAG function (replace with actual RAG pipeline)
        async def mock_rag(question: str):
            return ("Mock answer based on retrieved context.", ["context 1", "context 2"])

        # Run evaluation
        eval_service = get_evaluation_service()
        results = await eval_service.batch_evaluate(samples, mock_rag)

        # Update run with results
        await get_run_service(db).update_run_status(
            run_id,
            "completed",
            results=results,
        )

        return {"status": "completed", "results": results}

    except Exception as e:
        logger.exception("Evaluation run failed")
        await get_run_service(db).update_run_status(
            run_id,
            "failed",
            error_message=str(e),
        )
        raise


@router.get("/summary", response_model=Dict[str, Any])
async def get_evaluation_summary(
    db: DBSession,
    kb_id: Optional[str] = Query(None),
):
    """获取评估摘要"""
    from packages.rag.models.evaluation import EvaluationRun, GoldenSample
    from sqlalchemy import select, func

    # Count golden samples
    sample_query = select(func.count(GoldenSample.id))
    if kb_id:
        sample_query = sample_query.where(GoldenSample.kb_id == kb_id)

    sample_result = await db.execute(sample_query)
    total_samples = sample_result.scalar() or 0

    # Count runs
    run_query = select(func.count(EvaluationRun.id))
    if kb_id:
        run_query = run_query.where(EvaluationRun.kb_id == kb_id)

    run_result = await db.execute(run_query)
    total_runs = run_result.scalar() or 0

    # Get average score from completed runs
    avg_score_query = select(func.avg(EvaluationRun.avg_score)).where(
        EvaluationRun.status == "completed"
    )
    if kb_id:
        avg_score_query = avg_score_query.where(EvaluationRun.kb_id == kb_id)

    avg_result = await db.execute(avg_score_query)
    avg_score = avg_result.scalar() or 0.0

    return {
        "total_golden_samples": total_samples,
        "total_runs": total_runs,
        "average_score": avg_score,
    }
