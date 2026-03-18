"""トークン使用量の追跡"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.token_usage import TokenUsage

# 概算コスト（USD per 1M tokens）
COST_TABLE = {
    "gpt-4o": {"input": 2.5, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6},
    "gpt-5-nano-2025-08-07": {"input": 0.10, "output": 0.40},
}


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
