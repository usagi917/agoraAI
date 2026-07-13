"""検証モード API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import get_session
from src.app.evaluation.diagnostic import evaluate_prediction, load_eval_cases
from src.app.models.simulation import Simulation
from src.app.models.society_result import SocietyResult

router = APIRouter()


def _load_eval_cases_or_http_error(preset: str) -> list[dict]:
    try:
        return load_eval_cases(preset)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _verdict(metrics: dict) -> str:
    jsd = metrics.get("jsd")
    emd = metrics.get("emd")
    brier = metrics.get("brier")
    if jsd is not None and jsd <= 0.10 and emd is not None and emd <= 0.15:
        return "hit"
    if brier is not None and brier <= 0.30 and jsd is not None and jsd <= 0.20:
        return "partial"
    return "miss"


async def _load_sim_distribution(session: AsyncSession, sim: Simulation) -> dict | None:
    metadata = dict(sim.metadata_json or {})
    for key in ("diagnostic_result", "pulse_result"):
        payload = dict(metadata.get(key) or {})
        aggregation = dict(payload.get("aggregation") or {})
        if aggregation.get("stance_distribution"):
            return dict(aggregation["stance_distribution"])

    result = await session.execute(
        select(SocietyResult)
        .where(SocietyResult.simulation_id == sim.id, SocietyResult.layer == "activation")
        .order_by(SocietyResult.created_at.desc())
        .limit(1)
    )
    record = result.scalar_one_or_none()
    if record and record.phase_data:
        aggregation = dict(record.phase_data.get("aggregation") or {})
        if aggregation.get("stance_distribution"):
            return dict(aggregation["stance_distribution"])
    return None


async def _load_sample_reasons(session: AsyncSession, sim_id: str, limit: int = 5) -> list[dict]:
    result = await session.execute(
        select(SocietyResult)
        .where(SocietyResult.simulation_id == sim_id, SocietyResult.layer == "activation")
        .order_by(SocietyResult.created_at.desc())
        .limit(1)
    )
    record = result.scalar_one_or_none()
    if not record or not record.phase_data:
        return []
    responses = list(
        record.phase_data.get("responses")
        or record.phase_data.get("response_sample")
        or []
    )
    reasons = []
    for response in responses:
        reason = str(response.get("reason") or "").strip()
        if not reason:
            continue
        reasons.append({
            "agent_id": response.get("agent_id"),
            "stance": response.get("stance"),
            "reason": reason[:180],
        })
        if len(reasons) >= limit:
            break
    return reasons


@router.get("/validation/topics")
async def get_validation_topics(preset: str = "economy"):
    cases = _load_eval_cases_or_http_error(preset)
    return {
        "preset": preset,
        "topics": [
            {
                "survey_id": case["survey_id"],
                "theme": case["theme"],
                "question": case.get("question", ""),
                "source": case["source"],
                "survey_date": case["survey_date"],
                "sample_size": case["sample_size"],
                "quality_rank": case.get("quality_rank"),
                "source_origin": case.get("source_origin"),
            }
            for case in cases
        ],
    }


@router.get("/simulations/{sim_id}/validation-report")
async def get_validation_report(
    sim_id: str,
    preset: str = "economy",
    survey_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    sim = await session.get(Simulation, sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation が見つかりません")
    if sim.status != "completed":
        raise HTTPException(status_code=409, detail="Simulation is not completed yet")

    predicted = await _load_sim_distribution(session, sim)
    if not predicted:
        raise HTTPException(status_code=409, detail="Simulation has no stance_distribution yet")

    metadata = dict(sim.metadata_json or {})
    diagnostic = metadata.get("diagnostic") if isinstance(metadata.get("diagnostic"), dict) else {}
    requested_survey_id = survey_id or diagnostic.get("survey_id")
    cases = _load_eval_cases_or_http_error(preset)
    if requested_survey_id:
        cases = [case for case in cases if case["survey_id"] == requested_survey_id]
        if not cases:
            raise HTTPException(status_code=404, detail="Validation survey_id not found")
    else:
        same_theme = [case for case in cases if case["theme"] == sim.prompt_text]
        if same_theme:
            cases = same_theme

    evaluations = []
    for case in cases:
        metrics = evaluate_prediction(predicted, case["actual_distribution"])
        evaluations.append({
            "survey_id": case["survey_id"],
            "theme": case["theme"],
            "question": case.get("question", ""),
            "source": case["source"],
            "source_origin": case.get("source_origin"),
            "predicted": predicted,
            "actual": case["actual_distribution"],
            **metrics,
            "verdict": _verdict(metrics),
        })

    primary = evaluations[0]
    return {
        "simulation_id": sim_id,
        "preset": preset,
        "predicted": predicted,
        "actual": primary["actual"],
        "jsd": primary["jsd"],
        "emd": primary["emd"],
        "brier": primary["brier"],
        "ece": primary["ece"],
        "verdict": primary["verdict"],
        "sample_reasons": await _load_sample_reasons(session, sim_id),
        "evaluations": evaluations,
    }
