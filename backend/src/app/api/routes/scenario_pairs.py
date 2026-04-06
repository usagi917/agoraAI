"""Scenario Pairs / Audit Trail / Population Snapshot API エンドポイント (Stream G)"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import get_session
from src.app.models.population import Population
from src.app.models.scenario_pair import ScenarioPair
from src.app.services.audit_trail_service import get_audit_trail as get_audit_trail_events
from src.app.services.population_snapshot_service import create_snapshot
from src.app.services.scenario_comparison import build_scenario_comparison
from src.app.services.scenario_pair_factory import create_scenario_pair
from src.app.services.simulation_dispatcher import spawn_simulation

logger = logging.getLogger(__name__)

router = APIRouter()
audit_trail_router = APIRouter()
populations_router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class CreateScenarioPairRequest(BaseModel):
    population_id: str
    intervention_params: dict
    decision_context: str
    preset: str = "standard"
    seed: int | None = None


class ScenarioPairResponse(BaseModel):
    id: str
    population_snapshot_id: str
    baseline_simulation_id: str | None
    intervention_simulation_id: str | None
    intervention_params: dict
    decision_context: str
    status: str
    created_at: str  # ISO format


class AuditEventResponse(BaseModel):
    id: str
    simulation_id: str
    agent_id: str
    agent_name: str
    round_number: int
    event_type: str
    before_state: dict
    after_state: dict
    reasoning: str
    created_at: str


class PopulationSnapshotResponse(BaseModel):
    id: str
    population_id: str
    agent_count: int
    seed: int
    created_at: str


# ---------------------------------------------------------------------------
# Scenario Pair endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_scenario_pair_endpoint(
    body: CreateScenarioPairRequest,
    session: AsyncSession = Depends(get_session),
):
    """Create a new scenario pair and start both simulations."""
    pair = await create_scenario_pair(
        session=session,
        population_id=body.population_id,
        intervention_params=body.intervention_params,
        decision_context=body.decision_context,
        preset=body.preset,
        seed=body.seed,
    )

    for simulation_id in (pair.baseline_simulation_id, pair.intervention_simulation_id):
        if simulation_id:
            spawn_simulation(simulation_id)

    return ScenarioPairResponse(
        id=pair.id,
        population_snapshot_id=pair.population_snapshot_id,
        baseline_simulation_id=pair.baseline_simulation_id,
        intervention_simulation_id=pair.intervention_simulation_id,
        intervention_params=pair.intervention_params,
        decision_context=pair.decision_context,
        status=pair.status,
        created_at=pair.created_at.isoformat(),
    )


@router.get("/{scenario_pair_id}")
async def get_scenario_pair(
    scenario_pair_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get scenario pair metadata and status."""
    pair = await session.get(ScenarioPair, scenario_pair_id)
    if not pair:
        raise HTTPException(status_code=404, detail="ScenarioPair が見つかりません")
    return ScenarioPairResponse(
        id=pair.id,
        population_snapshot_id=pair.population_snapshot_id,
        baseline_simulation_id=pair.baseline_simulation_id,
        intervention_simulation_id=pair.intervention_simulation_id,
        intervention_params=pair.intervention_params,
        decision_context=pair.decision_context,
        status=pair.status,
        created_at=pair.created_at.isoformat(),
    )


@router.get("/{scenario_pair_id}/comparison")
async def get_scenario_comparison(
    scenario_pair_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get the comparison Decision Brief."""
    pair = await session.get(ScenarioPair, scenario_pair_id)
    if not pair:
        raise HTTPException(status_code=404, detail="ScenarioPair が見つかりません")
    if pair.status != "completed":
        return {
            "scenario_pair_id": pair.id,
            "status": pair.status,
            "comparison": None,
            "message": "Both simulations must complete before comparison is available.",
        }
    return await build_scenario_comparison(session, scenario_pair_id)


# ---------------------------------------------------------------------------
# Audit Trail endpoint (mounted under /simulations)
# ---------------------------------------------------------------------------


@audit_trail_router.get("/{simulation_id}/audit-trail")
async def get_audit_trail(
    simulation_id: str,
    agent_id: str | None = Query(None),
    event_type: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """Get audit trail events for a simulation."""
    events = await get_audit_trail_events(
        session,
        simulation_id=simulation_id,
        agent_id=agent_id,
        event_type=event_type,
    )
    return [
        AuditEventResponse(
            id=e.id,
            simulation_id=e.simulation_id,
            agent_id=e.agent_id,
            agent_name=e.agent_name,
            round_number=e.round_number,
            event_type=e.event_type,
            before_state=e.before_state,
            after_state=e.after_state,
            reasoning=e.reasoning,
            created_at=e.created_at.isoformat(),
        ).model_dump()
        for e in events
    ]


# ---------------------------------------------------------------------------
# Population Snapshot endpoint (mounted under /populations)
# ---------------------------------------------------------------------------


@populations_router.post("/{population_id}/snapshot", status_code=201)
async def create_population_snapshot(
    population_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Create a snapshot of a population."""
    population = await session.get(Population, population_id)
    if not population:
        raise HTTPException(status_code=404, detail="Population が見つかりません")

    snapshot = await create_snapshot(
        session=session,
        population_id=population_id,
        agents=[],
        seed=0,
    )
    agents = snapshot.agent_profiles_json
    agent_count = len(agents) if isinstance(agents, list) else 0
    return PopulationSnapshotResponse(
        id=snapshot.id,
        population_id=snapshot.population_id,
        agent_count=agent_count,
        seed=snapshot.seed,
        created_at=snapshot.created_at.isoformat(),
    )
