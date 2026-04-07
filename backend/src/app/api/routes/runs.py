import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import get_session
from src.app.models.followup import Followup
from src.app.models.graph_state import GraphState
from src.app.models.report import Report
from src.app.models.run import Run
from src.app.models.timeline_event import TimelineEvent
from src.app.models.world_state import WorldState
from src.app.services.followup_handler import handle_followup
from src.app.services.simulator import PROFILE_ROUNDS, run_simulation

logger = logging.getLogger(__name__)

router = APIRouter()

# バックグラウンドタスクの参照を保持（GC防止）
_background_tasks: set[asyncio.Task] = set()


def _spawn_simulation(run_id: str) -> None:
    task = asyncio.create_task(run_simulation(run_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


@router.get("")
async def list_runs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Run).order_by(Run.created_at.desc()).offset(skip).limit(min(limit, 100))
    )
    runs = result.scalars().all()
    return [
        {
            "id": r.id,
            "project_id": r.project_id,
            "template_name": r.template_name,
            "status": r.status,
            "execution_profile": r.execution_profile,
            "current_round": r.current_round,
            "total_rounds": r.total_rounds,
            "created_at": r.created_at.isoformat(),
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in runs
    ]


class RunCreate(BaseModel):
    project_id: str
    template_name: str
    execution_profile: str = "standard"


@router.post("")
async def create_run(body: RunCreate, session: AsyncSession = Depends(get_session)):
    total_rounds = PROFILE_ROUNDS.get(body.execution_profile, 4)
    run = Run(
        id=str(uuid.uuid4()),
        project_id=body.project_id,
        template_name=body.template_name,
        execution_profile=body.execution_profile,
        status="queued",
        total_rounds=total_rounds,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    # バックグラウンドでシミュレーション起動
    _spawn_simulation(run.id)

    return {
        "id": run.id,
        "project_id": run.project_id,
        "status": run.status,
        "execution_profile": run.execution_profile,
        "total_rounds": run.total_rounds,
        "created_at": run.created_at.isoformat(),
    }


@router.get("/{run_id}")
async def get_run(run_id: str, session: AsyncSession = Depends(get_session)):
    run = await session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="ランが見つかりません")
    return {
        "id": run.id,
        "project_id": run.project_id,
        "status": run.status,
        "execution_profile": run.execution_profile,
        "current_round": run.current_round,
        "total_rounds": run.total_rounds,
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


@router.get("/{run_id}/report")
async def get_report(run_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Report).where(Report.run_id == run_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="レポートが見つかりません")
    return {
        "id": report.id,
        "run_id": report.run_id,
        "content": report.content,
        "sections": report.sections,
        "status": report.status,
    }


@router.get("/{run_id}/timeline")
async def get_timeline(run_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(TimelineEvent)
        .where(TimelineEvent.run_id == run_id)
        .order_by(TimelineEvent.round_number, TimelineEvent.created_at)
    )
    events = result.scalars().all()
    return [
        {
            "id": e.id,
            "round_number": e.round_number,
            "event_type": e.event_type,
            "title": e.title,
            "description": e.description,
            "severity": e.severity,
            "involved_entities": e.involved_entities,
        }
        for e in events
    ]


@router.get("/{run_id}/events")
async def get_events(run_id: str, session: AsyncSession = Depends(get_session)):
    return await get_timeline(run_id, session)


@router.get("/{run_id}/graph")
async def get_graph(run_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(GraphState)
        .where(GraphState.run_id == run_id)
        .order_by(GraphState.round_number.desc())
        .limit(1)
    )
    graph = result.scalar_one_or_none()
    if not graph:
        return {"nodes": [], "edges": [], "round": 0}
    return {
        "run_id": graph.run_id,
        "round": graph.round_number,
        "nodes": graph.nodes,
        "edges": graph.edges,
        "focus_entities": graph.focus_entities,
        "highlights": graph.highlights,
    }


@router.post("/{run_id}/followups")
async def create_followup(
    run_id: str,
    question: str = "",
    session: AsyncSession = Depends(get_session),
):
    followup = Followup(
        id=str(uuid.uuid4()),
        run_id=run_id,
        question=question,
    )
    session.add(followup)
    await session.commit()

    # フォローアップ回答生成
    try:
        report_result = await session.execute(select(Report).where(Report.run_id == run_id))
        report = report_result.scalar_one_or_none()

        ws_result = await session.execute(
            select(WorldState)
            .where(WorldState.run_id == run_id)
            .order_by(WorldState.round_number.desc())
        )
        ws = ws_result.scalar_one_or_none()

        if report and ws:
            answer = await handle_followup(
                session, run_id, question,
                report.content, ws.state_data,
            )
            followup.answer = answer
            followup.status = "completed"
            await session.commit()
            return {"id": followup.id, "status": "completed", "answer": answer}
    except Exception as e:
        logger.error(f"Followup generation failed for run {run_id}: {e}")

    return {"id": followup.id, "status": "pending"}


@router.post("/{run_id}/rerun")
async def rerun(run_id: str, session: AsyncSession = Depends(get_session)):
    original = await session.get(Run, run_id)
    if not original:
        raise HTTPException(status_code=404, detail="ランが見つかりません")

    new_run = Run(
        id=str(uuid.uuid4()),
        project_id=original.project_id,
        template_name=original.template_name,
        execution_profile=original.execution_profile,
        status="queued",
        total_rounds=original.total_rounds,
    )
    session.add(new_run)
    await session.commit()

    _spawn_simulation(new_run.id)

    return {"id": new_run.id, "status": "queued"}
