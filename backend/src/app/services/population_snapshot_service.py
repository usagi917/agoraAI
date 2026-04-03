"""PopulationSnapshot サービス: 人口スナップショットの保存・復元"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.population_snapshot import PopulationSnapshot

logger = logging.getLogger(__name__)


async def create_snapshot(
    session: AsyncSession,
    population_id: str,
    agents: list[dict],
    seed: int,
) -> PopulationSnapshot:
    """Save a population snapshot with all agent profiles serialized as JSON."""
    snapshot = PopulationSnapshot(
        population_id=population_id,
        agent_profiles_json=agents,
        relationships_json={},
        initial_beliefs_json={},
        seed=seed,
    )
    session.add(snapshot)
    await session.commit()
    await session.refresh(snapshot)
    logger.info(
        "Created population snapshot %s for population %s (%d agents, seed=%d)",
        snapshot.id,
        population_id,
        len(agents),
        seed,
    )
    return snapshot


async def restore_from_snapshot(
    session: AsyncSession,
    snapshot_id: str,
) -> list[dict]:
    """Restore agent profiles from a snapshot."""
    snapshot = await session.get(PopulationSnapshot, snapshot_id)
    if snapshot is None:
        raise ValueError(f"Snapshot not found: {snapshot_id}")
    agents = snapshot.agent_profiles_json
    logger.info(
        "Restored %d agents from snapshot %s",
        len(agents) if isinstance(agents, list) else 0,
        snapshot_id,
    )
    return agents
