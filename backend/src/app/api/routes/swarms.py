"""Swarm API エンドポイント"""

import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import get_session
from src.app.models.aggregation_result import AggregationResult
from src.app.models.colony import Colony
from src.app.models.swarm import Swarm
from src.app.services.calibrator import record_feedback
from src.app.services.colony_factory import generate_colony_configs
from src.app.services.swarm_orchestrator import run_swarm

logger = logging.getLogger(__name__)

router = APIRouter()

# バックグラウンドタスクの参照を保持（GC防止）
_swarm_tasks: set[asyncio.Task] = set()


def _spawn_swarm(swarm_id: str) -> None:
    task = asyncio.create_task(run_swarm(swarm_id))
    _swarm_tasks.add(task)
    task.add_done_callback(_swarm_tasks.discard)


class SwarmCreate(BaseModel):
    project_id: str
    template_name: str
    execution_profile: str = "standard"


@router.post("")
async def create_swarm(body: SwarmCreate, session: AsyncSession = Depends(get_session)):
    """Swarm を作成し実行を開始する。"""
    # プロファイルからColony数・ラウンド数を取得
    try:
        configs = generate_colony_configs(
            swarm_id="temp", profile_name=body.execution_profile,
        )
        colony_count = len(configs)
        round_count = configs[0].round_count if configs else 4
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    swarm = Swarm(
        id=str(uuid.uuid4()),
        project_id=body.project_id,
        template_name=body.template_name,
        execution_profile=body.execution_profile,
        status="queued",
        colony_count=colony_count,
        total_rounds=round_count,
    )
    session.add(swarm)
    await session.commit()
    await session.refresh(swarm)

    _spawn_swarm(swarm.id)

    return {
        "id": swarm.id,
        "project_id": swarm.project_id,
        "status": swarm.status,
        "execution_profile": swarm.execution_profile,
        "colony_count": swarm.colony_count,
        "total_rounds": swarm.total_rounds,
        "created_at": swarm.created_at.isoformat(),
    }


@router.get("")
async def list_swarms(session: AsyncSession = Depends(get_session)):
    """Swarm 一覧を取得する。"""
    result = await session.execute(
        select(Swarm).order_by(Swarm.created_at.desc()).limit(50)
    )
    swarms = result.scalars().all()
    return [
        {
            "id": s.id,
            "project_id": s.project_id,
            "template_name": s.template_name,
            "status": s.status,
            "execution_profile": s.execution_profile,
            "colony_count": s.colony_count,
            "completed_colonies": s.completed_colonies,
            "total_rounds": s.total_rounds,
            "created_at": s.created_at.isoformat(),
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        }
        for s in swarms
    ]


@router.get("/{swarm_id}")
async def get_swarm(swarm_id: str, session: AsyncSession = Depends(get_session)):
    """Swarm 詳細を取得する。"""
    swarm = await session.get(Swarm, swarm_id)
    if not swarm:
        raise HTTPException(status_code=404, detail="Swarm が見つかりません")
    return {
        "id": swarm.id,
        "project_id": swarm.project_id,
        "template_name": swarm.template_name,
        "status": swarm.status,
        "execution_profile": swarm.execution_profile,
        "colony_count": swarm.colony_count,
        "completed_colonies": swarm.completed_colonies,
        "total_rounds": swarm.total_rounds,
        "diversity_mode": swarm.diversity_mode,
        "error_message": swarm.error_message,
        "created_at": swarm.created_at.isoformat(),
        "started_at": swarm.started_at.isoformat() if swarm.started_at else None,
        "completed_at": swarm.completed_at.isoformat() if swarm.completed_at else None,
    }


@router.get("/{swarm_id}/colonies")
async def get_colonies(swarm_id: str, session: AsyncSession = Depends(get_session)):
    """Swarm の Colony 一覧を取得する。"""
    result = await session.execute(
        select(Colony)
        .where(Colony.swarm_id == swarm_id)
        .order_by(Colony.colony_index)
    )
    colonies = result.scalars().all()
    return [
        {
            "id": c.id,
            "colony_index": c.colony_index,
            "perspective_id": c.perspective_id,
            "perspective_label": c.perspective_label,
            "temperature": c.temperature,
            "adversarial": c.adversarial,
            "status": c.status,
            "current_round": c.current_round,
            "total_rounds": c.total_rounds,
            "error_message": c.error_message,
            "started_at": c.started_at.isoformat() if c.started_at else None,
            "completed_at": c.completed_at.isoformat() if c.completed_at else None,
        }
        for c in colonies
    ]


@router.get("/{swarm_id}/colonies/{colony_id}")
async def get_colony(
    swarm_id: str, colony_id: str,
    session: AsyncSession = Depends(get_session),
):
    """個別 Colony の詳細を取得する。"""
    colony = await session.get(Colony, colony_id)
    if not colony or colony.swarm_id != swarm_id:
        raise HTTPException(status_code=404, detail="Colony が見つかりません")
    return {
        "id": colony.id,
        "swarm_id": colony.swarm_id,
        "run_id": colony.run_id,
        "colony_index": colony.colony_index,
        "perspective_id": colony.perspective_id,
        "perspective_label": colony.perspective_label,
        "temperature": colony.temperature,
        "adversarial": colony.adversarial,
        "status": colony.status,
        "current_round": colony.current_round,
        "total_rounds": colony.total_rounds,
        "result_summary": colony.result_summary,
        "result_data": colony.result_data,
        "error_message": colony.error_message,
    }


@router.get("/{swarm_id}/aggregation")
async def get_aggregation(
    swarm_id: str, session: AsyncSession = Depends(get_session),
):
    """集約結果を取得する。"""
    result = await session.execute(
        select(AggregationResult).where(AggregationResult.swarm_id == swarm_id)
    )
    agg = result.scalar_one_or_none()
    if not agg:
        raise HTTPException(status_code=404, detail="集約結果が見つかりません")
    return {
        "id": agg.id,
        "swarm_id": agg.swarm_id,
        "scenarios": agg.scenarios,
        "diversity_score": agg.diversity_score,
        "entropy": agg.entropy,
        "colony_agreement_matrix": agg.colony_agreement_matrix,
        "metadata": agg.metadata_json,
        "created_at": agg.created_at.isoformat(),
    }


@router.get("/{swarm_id}/scenarios")
async def get_scenarios(
    swarm_id: str, session: AsyncSession = Depends(get_session),
):
    """確率順シナリオ一覧を取得する。"""
    result = await session.execute(
        select(AggregationResult).where(AggregationResult.swarm_id == swarm_id)
    )
    agg = result.scalar_one_or_none()
    if not agg:
        raise HTTPException(status_code=404, detail="シナリオが見つかりません")
    return agg.scenarios


class FeedbackCreate(BaseModel):
    scenario_description: str
    predicted_probability: float
    actual_outcome: float
    feedback_text: str = ""


@router.post("/{swarm_id}/feedback")
async def submit_feedback(
    swarm_id: str, body: FeedbackCreate,
    session: AsyncSession = Depends(get_session),
):
    """予測結果に対するフィードバックを送信する。"""
    swarm = await session.get(Swarm, swarm_id)
    if not swarm:
        raise HTTPException(status_code=404, detail="Swarm が見つかりません")

    result = await record_feedback(
        session=session,
        swarm_id=swarm_id,
        scenario_description=body.scenario_description,
        predicted_probability=body.predicted_probability,
        actual_outcome=body.actual_outcome,
        feedback_text=body.feedback_text,
    )
    await session.commit()
    return result


@router.get("/{swarm_id}/report")
async def get_swarm_report(
    swarm_id: str, session: AsyncSession = Depends(get_session),
):
    """Swarm 統合レポートを取得する。"""
    result = await session.execute(
        select(AggregationResult).where(AggregationResult.swarm_id == swarm_id)
    )
    agg = result.scalar_one_or_none()
    if not agg:
        raise HTTPException(status_code=404, detail="レポートが見つかりません")

    # Colony 情報取得
    colony_result = await session.execute(
        select(Colony)
        .where(Colony.swarm_id == swarm_id)
        .order_by(Colony.colony_index)
    )
    colonies = colony_result.scalars().all()

    return {
        "swarm_id": swarm_id,
        "scenarios": agg.scenarios,
        "diversity_score": agg.diversity_score,
        "entropy": agg.entropy,
        "agreement_matrix": agg.colony_agreement_matrix,
        "colonies": [
            {
                "id": c.id,
                "perspective": c.perspective_label,
                "temperature": c.temperature,
                "adversarial": c.adversarial,
                "status": c.status,
            }
            for c in colonies
        ],
        "metadata": agg.metadata_json,
    }
