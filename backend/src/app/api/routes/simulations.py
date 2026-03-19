"""統一 Simulation API エンドポイント"""

import asyncio
import json
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from src.app.api.deps import get_session
from src.app.models.aggregation_result import AggregationResult
from src.app.models.colony import Colony
from src.app.models.graph_state import GraphState
from src.app.models.report import Report
from src.app.models.run import Run
from src.app.models.simulation import Simulation
from src.app.models.swarm import Swarm
from src.app.models.timeline_event import TimelineEvent
from src.app.models.world_state import WorldState
from src.app.models.followup import Followup
from src.app.services.calibrator import record_feedback
from src.app.services.followup_handler import handle_followup
from src.app.services.simulation_dispatcher import dispatch_simulation
from src.app.services.simulator import PROFILE_ROUNDS
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)

router = APIRouter()

_background_tasks: set[asyncio.Task] = set()


def _spawn_simulation(simulation_id: str) -> None:
    task = asyncio.create_task(dispatch_simulation(simulation_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


class SimulationCreate(BaseModel):
    project_id: str | None = None
    template_name: str = ""
    execution_profile: str = "standard"
    mode: str = "single"  # single | swarm | hybrid | pm_board
    prompt_text: str = ""


@router.post("")
async def create_simulation(
    body: SimulationCreate,
    session: AsyncSession = Depends(get_session),
):
    """Simulation を作成して実行を開始する。"""
    if body.mode not in ("single", "swarm", "hybrid", "pm_board"):
        raise HTTPException(status_code=400, detail=f"Invalid mode: {body.mode}")

    sim = Simulation(
        id=str(uuid.uuid4()),
        project_id=body.project_id,
        mode=body.mode,
        prompt_text=body.prompt_text,
        template_name=body.template_name,
        execution_profile=body.execution_profile,
        status="queued",
    )
    session.add(sim)
    await session.commit()
    await session.refresh(sim)

    _spawn_simulation(sim.id)

    return {
        "id": sim.id,
        "mode": sim.mode,
        "status": sim.status,
        "prompt_text": sim.prompt_text[:100],
        "template_name": sim.template_name,
        "execution_profile": sim.execution_profile,
        "created_at": sim.created_at.isoformat(),
    }


@router.get("")
async def list_simulations(session: AsyncSession = Depends(get_session)):
    """Simulation 一覧を取得する。"""
    result = await session.execute(
        select(Simulation).order_by(Simulation.created_at.desc()).limit(50)
    )
    sims = result.scalars().all()
    return [
        {
            "id": s.id,
            "project_id": s.project_id,
            "mode": s.mode,
            "status": s.status,
            "template_name": s.template_name,
            "execution_profile": s.execution_profile,
            "colony_count": s.colony_count,
            "run_id": s.run_id,
            "swarm_id": s.swarm_id,
            "created_at": s.created_at.isoformat(),
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        }
        for s in sims
    ]


SAMPLE_RESULTS_DIR = Path(__file__).resolve().parents[5] / "sample_results"


@router.get("/samples")
async def get_sample_results():
    """API Key不要のサンプル結果を返す。"""
    samples = []
    if SAMPLE_RESULTS_DIR.is_dir():
        for filepath in sorted(SAMPLE_RESULTS_DIR.glob("*.json")):
            try:
                data = json.loads(filepath.read_text(encoding="utf-8"))
                samples.append({
                    "id": data.get("id", filepath.stem),
                    "mode": data.get("mode", "single"),
                    "status": data.get("status", "completed"),
                    "template_name": data.get("template_name", ""),
                    "execution_profile": data.get("execution_profile", "standard"),
                    "prompt_text": data.get("prompt_text", ""),
                })
            except (json.JSONDecodeError, OSError):
                continue
    return samples


@router.get("/samples/{sample_id}")
async def get_sample_result(sample_id: str):
    """個別のサンプル結果を返す。"""
    if not SAMPLE_RESULTS_DIR.is_dir():
        raise HTTPException(status_code=404, detail="サンプルが見つかりません")

    for filepath in SAMPLE_RESULTS_DIR.glob("*.json"):
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            if data.get("id") == sample_id:
                return data
        except (json.JSONDecodeError, OSError):
            continue

    raise HTTPException(status_code=404, detail="サンプルが見つかりません")


@router.get("/{sim_id}")
async def get_simulation(sim_id: str, session: AsyncSession = Depends(get_session)):
    """Simulation 詳細を取得する。"""
    sim = await session.get(Simulation, sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation が見つかりません")
    return {
        "id": sim.id,
        "project_id": sim.project_id,
        "mode": sim.mode,
        "prompt_text": sim.prompt_text,
        "template_name": sim.template_name,
        "execution_profile": sim.execution_profile,
        "colony_count": sim.colony_count,
        "deep_colony_count": sim.deep_colony_count,
        "status": sim.status,
        "error_message": sim.error_message,
        "run_id": sim.run_id,
        "swarm_id": sim.swarm_id,
        "metadata": sim.metadata_json,
        "created_at": sim.created_at.isoformat(),
        "started_at": sim.started_at.isoformat() if sim.started_at else None,
        "completed_at": sim.completed_at.isoformat() if sim.completed_at else None,
    }


@router.get("/{sim_id}/stream")
async def stream_simulation(sim_id: str):
    """Simulation の統一 SSE ストリーム。"""
    return StreamingResponse(
        sse_manager.subscribe(sim_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{sim_id}/graph")
async def get_simulation_graph(sim_id: str, session: AsyncSession = Depends(get_session)):
    """最新のグラフ状態を取得する。"""
    sim = await session.get(Simulation, sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation が見つかりません")

    run_id = sim.run_id
    if not run_id and sim.swarm_id:
        # Swarm の場合、最初の Colony の run_id を取得
        result = await session.execute(
            select(Colony.run_id)
            .where(Colony.swarm_id == sim.swarm_id)
            .order_by(Colony.colony_index)
            .limit(1)
        )
        run_id = result.scalar_one_or_none()

    if not run_id:
        return {"nodes": [], "edges": [], "round": 0}

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


@router.get("/{sim_id}/graph/history")
async def get_simulation_graph_history(sim_id: str, session: AsyncSession = Depends(get_session)):
    """全ラウンドのグラフスナップショット（テンポラルリプレイ用）。"""
    sim = await session.get(Simulation, sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation が見つかりません")

    run_id = sim.run_id
    if not run_id and sim.swarm_id:
        result = await session.execute(
            select(Colony.run_id)
            .where(Colony.swarm_id == sim.swarm_id)
            .order_by(Colony.colony_index)
            .limit(1)
        )
        run_id = result.scalar_one_or_none()

    if not run_id:
        return []

    result = await session.execute(
        select(GraphState)
        .where(GraphState.run_id == run_id)
        .order_by(GraphState.round_number)
    )
    graphs = result.scalars().all()
    return [
        {
            "round": g.round_number,
            "nodes": g.nodes,
            "edges": g.edges,
            "focus_entities": g.focus_entities,
            "highlights": g.highlights,
        }
        for g in graphs
    ]


@router.get("/{sim_id}/report")
async def get_simulation_report(sim_id: str, session: AsyncSession = Depends(get_session)):
    """レポートを取得する（single: Report テーブル、swarm: AggregationResult）。"""
    sim = await session.get(Simulation, sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation が見つかりません")

    if sim.run_id:
        result = await session.execute(select(Report).where(Report.run_id == sim.run_id))
        report = result.scalar_one_or_none()
        if not report:
            raise HTTPException(status_code=404, detail="レポートが見つかりません")
        return {
            "type": "single",
            "id": report.id,
            "run_id": report.run_id,
            "content": report.content,
            "sections": report.sections,
            "status": report.status,
        }

    if sim.swarm_id:
        result = await session.execute(
            select(AggregationResult).where(AggregationResult.swarm_id == sim.swarm_id)
        )
        agg = result.scalar_one_or_none()
        if not agg:
            raise HTTPException(status_code=404, detail="レポートが見つかりません")

        colony_result = await session.execute(
            select(Colony)
            .where(Colony.swarm_id == sim.swarm_id)
            .order_by(Colony.colony_index)
        )
        colonies = colony_result.scalars().all()

        return {
            "type": "swarm",
            "swarm_id": sim.swarm_id,
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

    # PM Board モード: metadata_json に結果を保存
    if sim.mode == "pm_board" and sim.metadata_json:
        return sim.metadata_json

    raise HTTPException(status_code=404, detail="レポートが見つかりません")


@router.get("/{sim_id}/scenarios")
async def get_simulation_scenarios(sim_id: str, session: AsyncSession = Depends(get_session)):
    """シナリオ一覧（swarm/hybrid モード用）。"""
    sim = await session.get(Simulation, sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation が見つかりません")
    if not sim.swarm_id:
        raise HTTPException(status_code=404, detail="Swarm モードではありません")

    result = await session.execute(
        select(AggregationResult).where(AggregationResult.swarm_id == sim.swarm_id)
    )
    agg = result.scalar_one_or_none()
    if not agg:
        raise HTTPException(status_code=404, detail="シナリオが見つかりません")
    return agg.scenarios


@router.get("/{sim_id}/colonies")
async def get_simulation_colonies(sim_id: str, session: AsyncSession = Depends(get_session)):
    """Colony 一覧（swarm/hybrid モード用）。"""
    sim = await session.get(Simulation, sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation が見つかりません")
    if not sim.swarm_id:
        raise HTTPException(status_code=404, detail="Swarm モードではありません")

    result = await session.execute(
        select(Colony)
        .where(Colony.swarm_id == sim.swarm_id)
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
        }
        for c in colonies
    ]


@router.get("/{sim_id}/timeline")
async def get_simulation_timeline(sim_id: str, session: AsyncSession = Depends(get_session)):
    """タイムライン取得。"""
    sim = await session.get(Simulation, sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation が見つかりません")

    run_id = sim.run_id
    if not run_id:
        return []

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


@router.post("/{sim_id}/followups")
async def create_simulation_followup(
    sim_id: str,
    question: str = "",
    session: AsyncSession = Depends(get_session),
):
    """フォローアップ質問。"""
    sim = await session.get(Simulation, sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation が見つかりません")

    run_id = sim.run_id
    if not run_id:
        raise HTTPException(status_code=400, detail="フォローアップは single モードのみ対応")

    followup = Followup(
        id=str(uuid.uuid4()),
        run_id=run_id,
        question=question,
    )
    session.add(followup)
    await session.commit()

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
        logger.error(f"Followup generation failed: {e}")

    return {"id": followup.id, "status": "pending"}


class FeedbackCreate(BaseModel):
    scenario_description: str
    predicted_probability: float
    actual_outcome: float
    feedback_text: str = ""


@router.post("/{sim_id}/feedback")
async def submit_simulation_feedback(
    sim_id: str,
    body: FeedbackCreate,
    session: AsyncSession = Depends(get_session),
):
    """キャリブレーションフィードバック。"""
    sim = await session.get(Simulation, sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation が見つかりません")
    if not sim.swarm_id:
        raise HTTPException(status_code=400, detail="フィードバックは swarm/hybrid モードのみ対応")

    result = await record_feedback(
        session=session,
        swarm_id=sim.swarm_id,
        scenario_description=body.scenario_description,
        predicted_probability=body.predicted_probability,
        actual_outcome=body.actual_outcome,
        feedback_text=body.feedback_text,
    )
    await session.commit()
    return result


@router.post("/{sim_id}/rerun")
async def rerun_simulation(sim_id: str, session: AsyncSession = Depends(get_session)):
    """シミュレーションを再実行する。"""
    original = await session.get(Simulation, sim_id)
    if not original:
        raise HTTPException(status_code=404, detail="Simulation が見つかりません")

    new_sim = Simulation(
        id=str(uuid.uuid4()),
        project_id=original.project_id,
        mode=original.mode,
        prompt_text=original.prompt_text,
        template_name=original.template_name,
        execution_profile=original.execution_profile,
        status="queued",
    )
    session.add(new_sim)
    await session.commit()

    _spawn_simulation(new_sim.id)

    return {"id": new_sim.id, "status": "queued"}
