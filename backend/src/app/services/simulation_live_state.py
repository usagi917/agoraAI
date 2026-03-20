from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from src.app.models.simulation import Simulation


def _merge_dict(base: dict | None, patch: dict) -> dict:
    merged = dict(base or {})
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            nested = dict(merged[key])
            nested.update(value)
            merged[key] = nested
        else:
            merged[key] = value
    return merged


async def _find_simulation(
    session: AsyncSession,
    *,
    simulation_id: str | None = None,
    run_id: str | None = None,
    swarm_id: str | None = None,
) -> Simulation | None:
    if simulation_id:
        return await session.get(Simulation, simulation_id)

    query = select(Simulation)
    if run_id:
        query = query.where(Simulation.run_id == run_id)
    elif swarm_id:
        query = query.where(Simulation.swarm_id == swarm_id)
    else:
        return None

    result = await session.execute(query.limit(1))
    return result.scalar_one_or_none()


async def update_simulation_metadata(
    session: AsyncSession,
    patch: dict,
    *,
    simulation_id: str | None = None,
    run_id: str | None = None,
    swarm_id: str | None = None,
) -> None:
    sim = await _find_simulation(
        session,
        simulation_id=simulation_id,
        run_id=run_id,
        swarm_id=swarm_id,
    )
    if not sim:
        return

    sim.metadata_json = _merge_dict(sim.metadata_json, patch)
    flag_modified(sim, "metadata_json")
    await session.commit()


async def update_report_progress(
    session: AsyncSession,
    *,
    status: str,
    sections: list[str] | None = None,
    completed_sections: list[str] | None = None,
    last_error: str | None = None,
    scope: str | None = None,
    simulation_id: str | None = None,
    run_id: str | None = None,
    swarm_id: str | None = None,
) -> None:
    sim = await _find_simulation(
        session,
        simulation_id=simulation_id,
        run_id=run_id,
        swarm_id=swarm_id,
    )
    if not sim:
        return

    current = dict((sim.metadata_json or {}).get("report_progress") or {})
    if sections is not None:
        current["sections"] = sections
    if completed_sections is not None:
        current["completed_sections"] = completed_sections
    if last_error is not None:
        current["last_error"] = last_error
    if scope is not None:
        current["scope"] = scope

    current["status"] = status
    current["updated_at"] = datetime.now(timezone.utc).isoformat()

    sim.metadata_json = _merge_dict(sim.metadata_json, {"report_progress": current})
    flag_modified(sim, "metadata_json")
    await session.commit()
