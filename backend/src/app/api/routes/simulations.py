"""統一 Simulation API エンドポイント"""

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from src.app.api.deps import get_session
from src.app.config import settings
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
from src.app.services.decision_briefing import (
    build_pipeline_decision_brief,
    build_pm_board_decision_brief,
    build_single_decision_brief,
)
from src.app.services.followup_handler import handle_followup
from src.app.services.pipeline_fallbacks import (
    build_pipeline_report_fallback,
    build_pm_board_fallback,
    pm_board_has_substance,
)
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
    mode: str = "pipeline"  # pipeline | meta_simulation | single | swarm | hybrid | pm_board | society | society_first | unified
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
    valid_modes = ("pipeline", "meta_simulation", "single", "swarm", "hybrid", "pm_board", "society", "society_first", "unified")
    if body.mode not in valid_modes:
        raise HTTPException(status_code=400, detail=f"Invalid mode: {body.mode}")
    if not supports_evidence_mode(body.evidence_mode):
        raise HTTPException(status_code=400, detail=f"Invalid evidence_mode: {body.evidence_mode}")
    normalized_evidence_mode = normalize_evidence_mode(body.evidence_mode)
    if not settings.live_simulation_available():
        raise HTTPException(status_code=400, detail=settings.live_simulation_message())

    sim = Simulation(
        id=str(uuid.uuid4()),
        project_id=body.project_id,
        mode=body.mode,
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

    _spawn_simulation(sim.id)

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
            "pipeline_stage": s.pipeline_stage,
            "run_id": s.run_id,
            "swarm_id": s.swarm_id,
            "created_at": s.created_at.isoformat(),
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        }
        for s in sims
    ]


SAMPLE_RESULTS_DIR = settings.sample_results_dir


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
        "pipeline_stage": sim.pipeline_stage,
        "stage_progress": sim.stage_progress,
        "run_id": sim.run_id,
        "swarm_id": sim.swarm_id,
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

    evidence_refs = await collect_simulation_evidence_refs(
        session, sim.project_id, sim.prompt_text,
    )
    evidence_mode = get_evidence_mode(sim.metadata_json)
    run_config = extract_run_config(sim.metadata_json)

    # Pipeline モード: Report (統合) + AggregationResult + PM Board
    if sim.mode == "pipeline":
        response: dict = {
            "type": "pipeline",
            "evidence_refs": evidence_refs,
            "run_config": run_config,
        }
        single_report = ""
        swarm_report = ""
        scenarios: list[dict] = []
        decision_brief: dict | None = None
        fallback_used = False
        fallback_reason = ""

        if sim.run_id:
            result = await session.execute(select(Report).where(Report.run_id == sim.run_id))
            report = result.scalar_one_or_none()
            if report:
                response["id"] = report.id
                response["run_id"] = report.run_id
                response["status"] = report.status
                response["sections"] = report.sections
                response["content"] = report.content
                if isinstance(report.sections, dict) and isinstance(report.sections.get("verification"), dict):
                    response["verification"] = report.sections["verification"]
                report_quality = extract_quality(report.sections)
                if isinstance(report.sections, dict) and isinstance(report.sections.get("decision_brief"), dict):
                    decision_brief = dict(report.sections["decision_brief"])
                if report_quality.get("fallback_used"):
                    fallback_used = True
                    fallback_reason = str(report_quality.get("fallback_reason", "") or "")

                if isinstance(report.sections, dict):
                    single_report = (
                        str(report.sections.get("single_report", "") or "").strip()
                        or str(report.content or "").strip()
                    )
                else:
                    single_report = str(report.content or "").strip()

        if sim.swarm_id:
            result = await session.execute(
                select(AggregationResult).where(AggregationResult.swarm_id == sim.swarm_id)
            )
            agg = result.scalar_one_or_none()
            if agg:
                normalized_scenarios = normalize_scenarios(
                    agg.scenarios,
                    evidence_refs=evidence_refs,
                    evidence_mode=evidence_mode,
                )
                response["scenarios"] = normalized_scenarios
                response["diversity_score"] = agg.diversity_score
                response["entropy"] = agg.entropy
                response["agreement_matrix"] = agg.colony_agreement_matrix
                response["swarm_metadata"] = agg.metadata_json
                scenarios = normalized_scenarios
                if isinstance(agg.metadata_json, dict):
                    swarm_report = str(agg.metadata_json.get("integrated_report", "") or "").strip()

            colony_result = await session.execute(
                select(
                    Colony.id, Colony.perspective_label, Colony.temperature,
                    Colony.adversarial, Colony.status,
                )
                .where(Colony.swarm_id == sim.swarm_id)
                .order_by(Colony.colony_index)
            )
            response["colonies"] = [
                {
                    "id": row.id,
                    "perspective": row.perspective_label,
                    "temperature": row.temperature,
                    "adversarial": row.adversarial,
                    "status": row.status,
                }
                for row in colony_result
            ]

        pm_board = sim.metadata_json or {}
        if not pm_board_has_substance(pm_board):
            pm_board = build_pm_board_fallback(
                prompt_text=sim.prompt_text,
                scenario_candidates=scenarios,
                context_excerpt="\n\n".join(filter(None, [single_report, swarm_report])),
            )
            fallback_used = True
            fallback_reason = "pm_board_fallback_used"
        pm_quality = extract_quality(pm_board)
        if pm_quality.get("fallback_used"):
            fallback_used = True
            fallback_reason = str(pm_quality.get("fallback_reason", "") or fallback_reason)
        response["pm_board"] = pm_board
        if not decision_brief and isinstance(pm_board.get("decision_brief"), dict):
            decision_brief = dict(pm_board["decision_brief"])

        if not str(response.get("content", "") or "").strip():
            response["content"] = build_pipeline_report_fallback(
                prompt_text=sim.prompt_text,
                single_report=single_report,
                swarm_report=swarm_report,
                scenarios=scenarios,
                pm_result=pm_board,
            )
            response["sections"] = response.get("sections") or {
                "type": "pipeline_final",
                "generated_with_fallback": True,
            }
            response["status"] = response.get("status") or "completed"
            fallback_used = True
            fallback_reason = "pipeline_report_fallback_used"

        if not decision_brief:
            decision_brief = build_pipeline_decision_brief(
                prompt_text=sim.prompt_text,
                report_content=str(response.get("content", "") or ""),
                scenarios=scenarios,
                pm_result=pm_board,
            )
        response["decision_brief"] = decision_brief
        response["quality"] = build_quality_summary(
            fallback_used=fallback_used,
            evidence_refs=evidence_refs,
            fallback_reason=fallback_reason,
            evidence_mode=evidence_mode,
        )

        if response.get("content") or response.get("scenarios") or response.get("pm_board"):
            return response

    if sim.run_id:
        result = await session.execute(select(Report).where(Report.run_id == sim.run_id))
        report = result.scalar_one_or_none()
        if not report:
            raise HTTPException(status_code=404, detail="レポートが見つかりません")
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
            "scenarios": normalize_scenarios(
                agg.scenarios,
                evidence_refs=evidence_refs,
                evidence_mode=evidence_mode,
            ),
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
            "evidence_refs": evidence_refs,
            "run_config": run_config,
            "quality": build_quality_summary(
                fallback_used=False,
                evidence_refs=evidence_refs,
                evidence_mode=evidence_mode,
            ),
        }

    if sim.mode == "unified":
        unified_result = dict((sim.metadata_json or {}).get("unified_result") or {})
        if not unified_result:
            raise HTTPException(status_code=404, detail="レポートが見つかりません")

        return {
            "type": "unified",
            "content": unified_result.get("content", ""),
            "decision_brief": unified_result.get("decision_brief", {}),
            "agreement_score": unified_result.get("agreement_score", 0),
            "sections": unified_result.get("sections", {}),
            "society_summary": unified_result.get("society_summary", {}),
            "council": unified_result.get("council", {}),
            "evidence_refs": evidence_refs,
            "run_config": run_config,
            "quality": build_quality_summary(
                fallback_used=False,
                evidence_refs=evidence_refs,
                evidence_mode=evidence_mode,
            ),
        }

    if sim.mode == "society_first":
        society_first = _get_society_first_payload(sim)
        if not society_first:
            raise HTTPException(status_code=404, detail="レポートが見つかりません")

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
            "quality": build_quality_summary(
                fallback_used=False,
                evidence_refs=evidence_refs,
                evidence_mode=evidence_mode,
            ),
        }

    if sim.mode == "meta_simulation":
        meta_report = dict((sim.metadata_json or {}).get("meta_simulation_result") or {})
        if not meta_report:
            raise HTTPException(status_code=404, detail="レポートが見つかりません")

        response = {
            **meta_report,
            "evidence_refs": evidence_refs,
            "run_config": run_config,
            "quality": build_quality_summary(
                fallback_used=False,
                evidence_refs=evidence_refs,
                evidence_mode=evidence_mode,
            ),
        }
        if "content" not in response and response.get("summary_markdown"):
            response["content"] = response["summary_markdown"]
        return response

    # PM Board モード: metadata_json に結果を保存
    if sim.mode == "pm_board" and sim.metadata_json:
        pm_quality = extract_quality(sim.metadata_json)
        response = dict(sim.metadata_json)
        if not isinstance(response.get("decision_brief"), dict):
            response["decision_brief"] = build_pm_board_decision_brief(
                prompt_text=sim.prompt_text,
                pm_result=response,
            )
        response["evidence_refs"] = evidence_refs
        response["run_config"] = run_config
        response["quality"] = build_quality_summary(
            fallback_used=bool(pm_quality.get("fallback_used", False)),
            evidence_refs=evidence_refs,
            fallback_reason=str(pm_quality.get("fallback_reason", "") or ""),
            evidence_mode=evidence_mode,
        )
        return response

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
    evidence_refs = await collect_simulation_evidence_refs(
        session, sim.project_id, sim.prompt_text,
    )
    return normalize_scenarios(
        agg.scenarios,
        evidence_refs=evidence_refs,
        evidence_mode=get_evidence_mode(sim.metadata_json),
    )


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
        metadata_json=dict(original.metadata_json or {}),
    )
    session.add(new_sim)
    await session.commit()

    _spawn_simulation(new_sim.id)

    return {"id": new_sim.id, "status": "queued"}
