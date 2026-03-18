from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import get_session
from src.app.models.token_usage import TokenUsage

router = APIRouter()


@router.get("/costs")
async def get_costs(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(
            func.sum(TokenUsage.prompt_tokens).label("total_prompt_tokens"),
            func.sum(TokenUsage.completion_tokens).label("total_completion_tokens"),
            func.sum(TokenUsage.total_tokens).label("total_tokens"),
            func.sum(TokenUsage.estimated_cost).label("total_cost"),
            func.count(TokenUsage.id).label("total_calls"),
        )
    )
    row = result.one()
    return {
        "total_prompt_tokens": row.total_prompt_tokens or 0,
        "total_completion_tokens": row.total_completion_tokens or 0,
        "total_tokens": row.total_tokens or 0,
        "total_cost": round(row.total_cost or 0, 4),
        "total_calls": row.total_calls or 0,
    }
