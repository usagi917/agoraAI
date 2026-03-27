"""Evaluation リポジトリ"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.evaluation_result import EvaluationResult


class EvaluationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_metrics(
        self, simulation_id: str, metrics: list[dict]
    ) -> None:
        for m in metrics:
            entry = EvaluationResult(
                simulation_id=simulation_id,
                metric_name=m["metric_name"],
                score=m["score"],
                details=m.get("details", {}),
            )
            self.session.add(entry)
        await self.session.commit()

    async def get_by_simulation(
        self, simulation_id: str
    ) -> list[EvaluationResult]:
        stmt = select(EvaluationResult).where(
            EvaluationResult.simulation_id == simulation_id
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_metric_name(
        self, simulation_id: str, metric_name: str
    ) -> list[EvaluationResult]:
        stmt = select(EvaluationResult).where(
            EvaluationResult.simulation_id == simulation_id,
            EvaluationResult.metric_name == metric_name,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
