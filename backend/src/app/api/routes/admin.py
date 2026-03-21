import json

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import get_session
from src.app.models.log import Log
from src.app.models.report import Report
from src.app.models.simulation import Simulation
from src.app.models.token_usage import TokenUsage
from src.app.services.cost_tracker import classify_task_phase
from src.app.services.quality import extract_quality, extract_run_config

router = APIRouter()


@router.get("/costs")
async def get_costs(session: AsyncSession = Depends(get_session)):
    summary_result = await session.execute(
        select(
            func.sum(TokenUsage.prompt_tokens).label("total_prompt_tokens"),
            func.sum(TokenUsage.completion_tokens).label("total_completion_tokens"),
            func.sum(TokenUsage.total_tokens).label("total_tokens"),
            func.sum(TokenUsage.estimated_cost).label("total_cost"),
            func.count(TokenUsage.id).label("total_calls"),
        )
    )
    row = summary_result.one()

    usage_result = await session.execute(
        select(TokenUsage.task_name, TokenUsage.model, TokenUsage.total_tokens, TokenUsage.estimated_cost)
    )
    by_phase: dict[str, dict[str, float | int]] = {}
    by_model: dict[str, dict[str, float | int]] = {}

    for task_name, model, total_tokens, estimated_cost in usage_result.all():
        phase = classify_task_phase(task_name)
        phase_bucket = by_phase.setdefault(phase, {"total_tokens": 0, "total_cost": 0.0, "calls": 0})
        phase_bucket["total_tokens"] += int(total_tokens or 0)
        phase_bucket["total_cost"] += float(estimated_cost or 0.0)
        phase_bucket["calls"] += 1

        model_bucket = by_model.setdefault(model, {"total_tokens": 0, "total_cost": 0.0, "calls": 0})
        model_bucket["total_tokens"] += int(total_tokens or 0)
        model_bucket["total_cost"] += float(estimated_cost or 0.0)
        model_bucket["calls"] += 1

    response = {
        "total_prompt_tokens": row.total_prompt_tokens or 0,
        "total_completion_tokens": row.total_completion_tokens or 0,
        "total_tokens": row.total_tokens or 0,
        "total_cost": round(row.total_cost or 0, 4),
        "total_calls": row.total_calls or 0,
        "by_phase": {
            key: {
                "total_tokens": value["total_tokens"],
                "total_cost": round(float(value["total_cost"]), 4),
                "calls": value["calls"],
            }
            for key, value in by_phase.items()
        },
        "by_model": {
            key: {
                "total_tokens": value["total_tokens"],
                "total_cost": round(float(value["total_cost"]), 4),
                "calls": value["calls"],
            }
            for key, value in by_model.items()
        },
    }
    return response


@router.get("/quality-metrics")
async def get_quality_metrics(session: AsyncSession = Depends(get_session)):
    simulations = (await session.execute(select(Simulation))).scalars().all()
    reports = (await session.execute(select(Report))).scalars().all()
    logs = (await session.execute(select(Log).where(Log.message.like("llm_observation:%")))).scalars().all()

    strict_mode_runs = 0
    failed_simulations = 0
    unsupported_outputs = 0
    fallback_outputs = 0
    verification_failures = 0

    for sim in simulations:
        config = extract_run_config(sim.metadata_json)
        if config.get("evidence_mode") == "strict":
            strict_mode_runs += 1
        if sim.status == "failed":
            failed_simulations += 1

        payload_quality = extract_quality(sim.metadata_json or {})
        if payload_quality.get("status") == "unsupported":
            unsupported_outputs += 1
        if payload_quality.get("fallback_used"):
            fallback_outputs += 1

    for report in reports:
        quality = extract_quality(report.sections if isinstance(report.sections, dict) else {})
        if quality.get("status") == "unsupported":
            unsupported_outputs += 1
        if quality.get("fallback_used"):
            fallback_outputs += 1
        verification = (
            dict(report.sections or {}).get("verification")
            if isinstance(report.sections, dict)
            else None
        )
        if isinstance(verification, dict) and verification.get("status") == "failed":
            verification_failures += 1

    validation_failures = 0
    json_retry_count = 0
    retry_count = 0
    for log in logs:
        try:
            details = json.loads(log.details or "{}")
        except json.JSONDecodeError:
            continue
        validation_failures += int(details.get("validation_failures", 0) or 0)
        json_retry_count += int(details.get("json_retries", 0) or 0)
        retry_count += int(details.get("retry_count", 0) or 0)

    total_simulations = len(simulations)
    total_outputs = max(len(reports), 1)
    return {
        "total_simulations": total_simulations,
        "strict_mode_simulations": strict_mode_runs,
        "failed_simulations": failed_simulations,
        "unsupported_outputs": unsupported_outputs,
        "fallback_outputs": fallback_outputs,
        "verification_failures": verification_failures,
        "validation_failures": validation_failures,
        "json_retries": json_retry_count,
        "llm_retries": retry_count,
        "strict_failure_rate": round(failed_simulations / strict_mode_runs, 4) if strict_mode_runs else 0.0,
        "unsupported_rate": round(unsupported_outputs / total_outputs, 4) if total_outputs else 0.0,
        "fallback_rate": round(fallback_outputs / total_outputs, 4) if total_outputs else 0.0,
    }
