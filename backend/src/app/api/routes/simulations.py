"""統一 Simulation API エンドポイント"""

import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from src.app.api.deps import get_session
from src.app.config import settings
from src.app.models.graph_state import GraphState
from src.app.models.report import Report
from src.app.models.simulation import Simulation, normalize_mode
from src.app.models.timeline_event import TimelineEvent
from src.app.models.world_state import WorldState
from src.app.models.followup import Followup
from src.app.services.decision_briefing import (
    build_single_decision_brief,
)
from src.app.services.followup_handler import handle_followup
from src.app.services.society.backtest import (
    build_empty_backtest_result,
    overlay_observed_intervention_comparison,
    prepare_backtest_payload,
)
from src.app.services.society.issue_miner import build_intervention_comparison
from src.app.services.quality import (
    build_quality_summary,
    collect_simulation_evidence_refs,
    extract_run_config,
    extract_quality,
    get_evidence_mode,
    normalize_scenarios,
    normalize_evidence_mode,
    supports_evidence_mode,
)
from src.app.services.simulation_dispatcher import spawn_simulation
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)

router = APIRouter()


class SimulationCreate(BaseModel):
    project_id: str | None = None
    template_name: str = ""
    execution_profile: str = "standard"
    mode: str = "standard"  # quick | standard | deep | research | baseline (旧モード名も受付)
    prompt_text: str = ""
    evidence_mode: str = "prefer"  # strict | prefer | off (legacy aliases accepted)


class HistoricalOutcome(BaseModel):
    issue_label: str | None = None
    summary: str = ""
    actual_scenario: str = ""
    metrics: dict[str, float] = {}
    tags: list[str] = []


class HistoricalIntervention(BaseModel):
    intervention_id: str
    label: str = ""
    baseline_metrics: dict[str, float] = {}
    outcome_metrics: dict[str, float] = {}
    evidence: list[str] = []


class HistoricalCase(BaseModel):
    case_id: str | None = None
    title: str
    observed_at: str | None = None
    linked_simulation_id: str | None = None
    linked_report_id: str | None = None
    baseline_metrics: dict[str, float] = {}
    outcome: HistoricalOutcome
    interventions: list[HistoricalIntervention] = []


class BacktestCreate(BaseModel):
    historical_cases: list[HistoricalCase]


@router.post("")
async def create_simulation(
    body: SimulationCreate,
    session: AsyncSession = Depends(get_session),
):
    """Simulation を作成して実行を開始する。"""
    try:
        normalized_mode = normalize_mode(body.mode)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid mode: {body.mode}")
    if not supports_evidence_mode(body.evidence_mode):
        raise HTTPException(status_code=400, detail=f"Invalid evidence_mode: {body.evidence_mode}")
    normalized_evidence_mode = normalize_evidence_mode(body.evidence_mode)
    if not settings.live_simulation_available():
        raise HTTPException(status_code=400, detail=settings.live_simulation_message())

    sim = Simulation(
        id=str(uuid.uuid4()),
        project_id=body.project_id,
        mode=normalized_mode,
        prompt_text=body.prompt_text,
        template_name=body.template_name,
        execution_profile=body.execution_profile,
        status="queued",
        metadata_json={
            "run_config": {
                "evidence_mode": normalized_evidence_mode,
                "trust_mode": "strict",
            }
        },
    )
    session.add(sim)
    await session.commit()
    await session.refresh(sim)

    spawn_simulation(sim.id)

    return {
        "id": sim.id,
        "mode": sim.mode,
        "status": sim.status,
        "prompt_text": sim.prompt_text[:100],
        "template_name": sim.template_name,
        "execution_profile": sim.execution_profile,
        "evidence_mode": normalized_evidence_mode,
        "created_at": sim.created_at.isoformat(),
    }


@router.get("")
async def list_simulations(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1),
    session: AsyncSession = Depends(get_session),
):
    """Simulation 一覧を取得する。"""
    result = await session.execute(
        select(Simulation).order_by(Simulation.created_at.desc()).offset(skip).limit(min(limit, 100))
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
            "pipeline_stage": s.pipeline_stage,
            "created_at": s.created_at.isoformat(),
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        }
        for s in sims
    ]


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
        "status": sim.status,
        "error_message": sim.error_message,
        "pipeline_stage": sim.pipeline_stage,
        "stage_progress": sim.stage_progress,
        "seed": sim.seed,
        "metadata": sim.metadata_json,
        "created_at": sim.created_at.isoformat(),
        "started_at": sim.started_at.isoformat() if sim.started_at else None,
        "completed_at": sim.completed_at.isoformat() if sim.completed_at else None,
    }


def _get_society_first_payload(sim: Simulation) -> dict:
    return dict((sim.metadata_json or {}).get("society_first_result") or {})


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
    """シミュレーション結果レポートを返す。"""
    sim = await session.get(Simulation, sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation が見つかりません")

    evidence_refs = await collect_simulation_evidence_refs(
        session, sim.project_id, sim.prompt_text,
    )
    evidence_mode = get_evidence_mode(sim.metadata_json)
    run_config = extract_run_config(sim.metadata_json)
    quality = build_quality_summary(
        fallback_used=False,
        evidence_refs=evidence_refs,
        evidence_mode=evidence_mode,
    )

    # 新プリセット方式: unified_result に全結果を格納
    unified_result = dict((sim.metadata_json or {}).get("unified_result") or {})
    if unified_result:
        return {
            **unified_result,
            "type": unified_result.get("type", sim.mode),
            "evidence_refs": evidence_refs,
            "run_config": run_config,
            "quality": quality,
        }

    # レガシー: society_first 結果
    society_first = dict((sim.metadata_json or {}).get("society_first_result") or {})
    if society_first:
        return {
            "type": "society_first",
            "content": society_first.get("content", ""),
            "sections": society_first.get("sections", {}),
            "society_summary": society_first.get("society_summary", {}),
            "issue_candidates": society_first.get("issue_candidates", []),
            "selected_issues": society_first.get("selected_issues", []),
            "issue_colonies": society_first.get("issue_colonies", []),
            "intervention_comparison": society_first.get("intervention_comparison", []),
            "backtest": society_first.get("backtest") or build_empty_backtest_result(),
            "scenarios": normalize_scenarios(
                society_first.get("scenarios", []),
                evidence_refs=evidence_refs,
                evidence_mode=evidence_mode,
            ),
            "verification": society_first.get("verification"),
            "evidence_refs": evidence_refs,
            "run_config": run_config,
            "quality": quality,
        }

    # レガシー: meta_simulation 結果
    meta_report = dict((sim.metadata_json or {}).get("meta_simulation_result") or {})
    if meta_report:
        response = {
            **meta_report,
            "evidence_refs": evidence_refs,
            "run_config": run_config,
            "quality": quality,
        }
        if "content" not in response and response.get("summary_markdown"):
            response["content"] = response["summary_markdown"]
        return response

    # レガシー: single モード (Report テーブル)
    if sim.run_id:
        result = await session.execute(select(Report).where(Report.run_id == sim.run_id))
        report = result.scalar_one_or_none()
        if report:
            report_quality = extract_quality(report.sections)
            response_quality = build_quality_summary(
                fallback_used=bool(report_quality.get("fallback_used", False)),
                evidence_refs=evidence_refs,
                fallback_reason=str(report_quality.get("fallback_reason", "") or ""),
                evidence_mode=evidence_mode,
            )
            decision_brief = (
                dict(report.sections.get("decision_brief"))
                if isinstance(report.sections, dict) and isinstance(report.sections.get("decision_brief"), dict)
                else build_single_decision_brief(
                    prompt_text=sim.prompt_text,
                    report_content=str(report.content or ""),
                    sections=dict(report.sections or {}),
                    quality=response_quality,
                )
            )
            return {
                "type": "single",
                "id": report.id,
                "run_id": report.run_id,
                "content": report.content,
                "sections": report.sections,
                "status": report.status,
                "decision_brief": decision_brief,
                "evidence_refs": evidence_refs,
                "run_config": run_config,
                "verification": (
                    dict(report.sections.get("verification"))
                    if isinstance(report.sections, dict) and isinstance(report.sections.get("verification"), dict)
                    else None
                ),
                "quality": response_quality,
            }

    # レガシー: PM Board 結果 (metadata_json 直接)
    if sim.metadata_json and sim.metadata_json.get("pm_analyses"):
        return {
            **sim.metadata_json,
            "evidence_refs": evidence_refs,
            "run_config": run_config,
            "quality": quality,
        }

    raise HTTPException(status_code=404, detail="レポートが見つかりません")


@router.get("/{sim_id}/backtest")
async def get_simulation_backtest(sim_id: str, session: AsyncSession = Depends(get_session)):
    """society_first の backtest 結果を返す。"""
    sim = await session.get(Simulation, sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation が見つかりません")
    if sim.mode != "society_first":
        raise HTTPException(status_code=400, detail="backtest は society_first モードのみ対応")

    society_first = _get_society_first_payload(sim)
    if not society_first:
        raise HTTPException(status_code=404, detail="society_first 結果が見つかりません")

    return society_first.get("backtest") or build_empty_backtest_result()


@router.post("/{sim_id}/backtest")
async def create_simulation_backtest(
    sim_id: str,
    body: BacktestCreate,
    session: AsyncSession = Depends(get_session),
):
    """society_first の historical case を保存し backtest を計算する。"""
    sim = await session.get(Simulation, sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation が見つかりません")
    if sim.mode != "society_first":
        raise HTTPException(status_code=400, detail="backtest は society_first モードのみ対応")

    society_first = _get_society_first_payload(sim)
    if not society_first:
        raise HTTPException(status_code=404, detail="society_first 結果が見つかりません")

    normalized_cases = [case.model_dump() for case in body.historical_cases]
    backtest = prepare_backtest_payload(society_first, normalized_cases)

    base_interventions = build_intervention_comparison(
        society_first.get("selected_issues", []),
        society_first.get("issue_colonies", []),
    )
    updated_interventions = overlay_observed_intervention_comparison(base_interventions, backtest)

    updated_society_first = {
        **society_first,
        "backtest": backtest,
        "intervention_comparison": updated_interventions,
        "sections": {
            **dict(society_first.get("sections") or {}),
            "intervention_comparison": updated_interventions,
            "backtest": backtest,
        },
    }
    sim.metadata_json = {
        **dict(sim.metadata_json or {}),
        "society_first_result": updated_society_first,
    }
    await session.commit()

    return backtest



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
            "created_at": e.created_at.isoformat() if e.created_at else None,
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
            evidence_refs = await collect_simulation_evidence_refs(
                session,
                sim.project_id,
                sim.prompt_text,
                query_text=question,
            )
            followup.answer = answer
            followup.status = "completed"
            await session.commit()
            return {
                "id": followup.id,
                "status": "completed",
                "answer": answer,
                "evidence_refs": evidence_refs,
                "run_config": extract_run_config(sim.metadata_json),
                "quality": build_quality_summary(
                    fallback_used=False,
                    evidence_refs=evidence_refs,
                    evidence_mode=get_evidence_mode(sim.metadata_json),
                ),
            }
    except Exception as e:
        logger.error(f"Followup generation failed: {e}")

    return {
        "id": followup.id,
        "status": "pending",
        "evidence_refs": [],
        "run_config": extract_run_config(sim.metadata_json),
        "quality": build_quality_summary(
            fallback_used=True,
            evidence_refs=[],
            fallback_reason="followup_generation_pending",
            evidence_mode=get_evidence_mode(sim.metadata_json),
        ),
    }



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
        metadata_json=dict(original.metadata_json or {}),
    )
    session.add(new_sim)
    await session.commit()

    spawn_simulation(new_sim.id)

    return {"id": new_sim.id, "status": "queued"}
