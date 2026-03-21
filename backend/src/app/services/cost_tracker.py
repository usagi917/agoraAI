"""トークン使用量の追跡"""

import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.log import Log
from src.app.models.token_usage import TokenUsage

# 概算コスト（USD per 1M tokens）
COST_TABLE = {
    "gpt-4o": {"input": 2.5, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6},
    "gpt-5-nano-2025-08-07": {"input": 0.10, "output": 0.40},
}


def classify_task_phase(task_name: str) -> str:
    if task_name in {"world_build", "world_build_graphrag"}:
        return "world_build"
    if task_name.startswith("round_"):
        return "simulation_round"
    if task_name.startswith("report_") or task_name in {"report_generate", "final_report"}:
        return "report"
    if task_name.startswith("pm_board_"):
        return "pm_board"
    if task_name.startswith("swarm") or task_name.startswith("claim_extract"):
        return "swarm"
    if task_name.startswith("bdi_") or task_name in {
        "gm_action_resolve",
        "gm_consistency_check",
        "reflection",
        "self_critique",
        "tom_infer",
    }:
        return "cognition"
    if task_name in {"followup", "evaluation"}:
        return task_name
    return "other"


async def record_usage(
    session: AsyncSession,
    run_id: str,
    task_name: str,
    usage: dict,
) -> None:
    model = usage.get("model", "unknown")
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    total_tokens = usage.get("total_tokens", 0)

    costs = COST_TABLE.get(model, {"input": 5.0, "output": 15.0})
    estimated_cost = (
        prompt_tokens * costs["input"] / 1_000_000
        + completion_tokens * costs["output"] / 1_000_000
    )

    token_usage = TokenUsage(
        id=str(uuid.uuid4()),
        run_id=run_id,
        task_name=task_name,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost=estimated_cost,
    )
    session.add(token_usage)

    retry_count = int(usage.get("retry_count", 0) or 0)
    validation_failures = int(usage.get("validation_failures", 0) or 0)
    json_retries = int(usage.get("json_retries", 0) or 0)
    last_validation_error = str(usage.get("last_validation_error", "") or "")

    if retry_count or validation_failures or json_retries:
        session.add(
            Log(
                id=str(uuid.uuid4()),
                run_id=run_id,
                level="warning" if validation_failures or json_retries else "info",
                message=f"llm_observation:{task_name}",
                details=json.dumps(
                    {
                        "phase": classify_task_phase(task_name),
                        "model": model,
                        "retry_count": retry_count,
                        "validation_failures": validation_failures,
                        "json_retries": json_retries,
                        "last_validation_error": last_validation_error,
                    },
                    ensure_ascii=False,
                ),
            )
        )
