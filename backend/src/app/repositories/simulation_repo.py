"""Simulation リポジトリ"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.simulation import Simulation


class SimulationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **kwargs) -> Simulation:
        sim = Simulation(id=str(uuid.uuid4()), **kwargs)
        self.session.add(sim)
        await self.session.commit()
        return sim

    async def get(self, sim_id: str) -> Simulation | None:
        return await self.session.get(Simulation, sim_id)

    async def list(self, limit: int = 50) -> list[Simulation]:
        stmt = (
            select(Simulation)
            .order_by(Simulation.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(self, sim_id: str, status: str) -> None:
        sim = await self.get(sim_id)
        if sim:
            sim.status = status
            if status == "completed":
                sim.completed_at = datetime.now(timezone.utc)
            await self.session.commit()

    async def save_result(self, sim_id: str, result: dict) -> None:
        sim = await self.get(sim_id)
        if sim:
            sim.metadata_json = result
            await self.session.commit()
