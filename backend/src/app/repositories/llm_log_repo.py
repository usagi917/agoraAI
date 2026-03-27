"""LLM Call Log リポジトリ"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.llm_call_log import LLMCallLog


class LLMCallLogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def log_call(self, **kwargs) -> LLMCallLog:
        entry = LLMCallLog(**kwargs)
        self.session.add(entry)
        await self.session.commit()
        return entry

    async def get_by_simulation(
        self, simulation_id: str
    ) -> list[LLMCallLog]:
        stmt = (
            select(LLMCallLog)
            .where(LLMCallLog.simulation_id == simulation_id)
            .order_by(LLMCallLog.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_summary(self, simulation_id: str) -> dict:
        logs = await self.get_by_simulation(simulation_id)
        return {
            "total_calls": len(logs),
            "total_tokens": sum(l.total_tokens for l in logs),
            "total_latency_ms": sum(l.latency_ms for l in logs),
            "by_task": {
                l.task_name: l.total_tokens for l in logs
            },
        }
