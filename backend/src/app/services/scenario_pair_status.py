"""Helpers for keeping ScenarioPair status in sync with child simulations."""

from __future__ import annotations

from src.app.models.scenario_pair import ScenarioPair
from src.app.models.simulation import Simulation


def derive_scenario_pair_status(simulation_statuses: list[str]) -> str:
    """Collapse child simulation statuses into a single pair status."""
    if not simulation_statuses:
        return "created"
    if any(status == "failed" for status in simulation_statuses):
        return "failed"
    if all(status == "completed" for status in simulation_statuses):
        return "completed"
    if any(status in {"queued", "running"} for status in simulation_statuses):
        return "running"
    return "created"


async def refresh_scenario_pair_status(
    session,
    scenario_pair_id: str | None,
) -> ScenarioPair | None:
    """Update the stored ScenarioPair status from current simulation rows."""
    if not scenario_pair_id:
        return None

    pair = await session.get(ScenarioPair, scenario_pair_id)
    if not pair:
        return None

    simulation_statuses: list[str] = []
    for simulation_id in (pair.baseline_simulation_id, pair.intervention_simulation_id):
        if not simulation_id:
            continue
        simulation = await session.get(Simulation, simulation_id)
        if simulation:
            simulation_statuses.append(simulation.status)

    pair.status = derive_scenario_pair_status(simulation_statuses)
    return pair
