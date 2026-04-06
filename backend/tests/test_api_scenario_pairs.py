"""Stream G: Scenario Pairs API エンドポイントのテスト"""

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.app.api.deps import get_session
from src.app.api.routes import scenario_pairs as scenario_pairs_route
from src.app.database import Base
from src.app.main import app
from src.app.models import _import_all_models
from src.app.models.audit_event import AuditEvent
from src.app.models.population import Population
from src.app.models.simulation import Simulation


@pytest_asyncio.fixture
async def session_factory(tmp_path):
    db_path = tmp_path / "scenario-pairs-api.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    _import_all_models()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        yield session_maker
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def client(session_factory):
    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as async_client:
        yield async_client

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def mock_spawn_simulation(monkeypatch):
    calls: list[str] = []

    def fake_spawn_simulation(simulation_id: str) -> None:
        calls.append(simulation_id)

    monkeypatch.setattr(scenario_pairs_route, "spawn_simulation", fake_spawn_simulation)
    return calls


async def _seed_population(session_factory) -> str:
    """Create a Population record and return its id."""
    async with session_factory() as session:
        pop = Population(agent_count=100)
        session.add(pop)
        await session.commit()
        return pop.id


async def _seed_simulation_with_audit_events(session_factory) -> str:
    """Create a Simulation with audit events and return its id."""
    async with session_factory() as session:
        sim = Simulation(
            mode="standard",
            prompt_text="test audit trail",
            template_name="general",
            execution_profile="standard",
            status="completed",
        )
        session.add(sim)
        await session.flush()

        for i in range(3):
            event = AuditEvent(
                simulation_id=sim.id,
                agent_id=f"agent-{i}",
                agent_name=f"Agent {i}",
                round_number=i + 1,
                event_type="belief_change" if i % 2 == 0 else "opinion_shift",
                before_state={"stance": 0.3 + i * 0.1},
                after_state={"stance": 0.5 + i * 0.1},
                reasoning=f"Reason {i}",
            )
            session.add(event)

        await session.commit()
        return sim.id


@pytest.mark.asyncio
async def test_create_scenario_pair_endpoint(client, session_factory, mock_spawn_simulation):
    """POST /scenario-pairs -> 201 + correct response."""
    population_id = await _seed_population(session_factory)

    response = await client.post(
        "/scenario-pairs",
        json={
            "population_id": population_id,
            "intervention_params": {"policy_type": "subsidy", "amount": 1000},
            "decision_context": "Youth employment subsidy policy",
            "preset": "standard",
            "seed": 42,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["population_snapshot_id"]
    assert payload["baseline_simulation_id"] is not None
    assert payload["intervention_simulation_id"] is not None
    assert payload["intervention_params"]["policy_type"] == "subsidy"
    assert payload["decision_context"] == "Youth employment subsidy policy"
    assert payload["status"] == "created"
    assert payload["created_at"]
    assert mock_spawn_simulation == [
        payload["baseline_simulation_id"],
        payload["intervention_simulation_id"],
    ]


@pytest.mark.asyncio
async def test_get_scenario_pair_endpoint(client, session_factory):
    """GET /scenario-pairs/{id} -> 200 + correct data."""
    population_id = await _seed_population(session_factory)

    # First create a pair
    create_response = await client.post(
        "/scenario-pairs",
        json={
            "population_id": population_id,
            "intervention_params": {"tax_rate": 0.15},
            "decision_context": "Tax policy change",
        },
    )
    assert create_response.status_code == 201
    pair_id = create_response.json()["id"]

    # Now get it
    response = await client.get(f"/scenario-pairs/{pair_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == pair_id
    assert payload["intervention_params"]["tax_rate"] == 0.15
    assert payload["decision_context"] == "Tax policy change"
    assert payload["status"] == "running"


@pytest.mark.asyncio
async def test_get_scenario_pair_not_found(client):
    """GET /scenario-pairs/{nonexistent} -> 404."""
    response = await client.get(f"/scenario-pairs/{uuid.uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_scenario_comparison_placeholder(client, session_factory):
    """GET /scenario-pairs/{id}/comparison -> 200 + placeholder."""
    population_id = await _seed_population(session_factory)

    create_response = await client.post(
        "/scenario-pairs",
        json={
            "population_id": population_id,
            "intervention_params": {},
            "decision_context": "Comparison test",
        },
    )
    pair_id = create_response.json()["id"]

    response = await client.get(f"/scenario-pairs/{pair_id}/comparison")
    assert response.status_code == 200
    payload = response.json()
    assert payload["scenario_pair_id"] == pair_id
    assert payload["comparison"] is None


@pytest.mark.asyncio
async def test_get_audit_trail_endpoint(client, session_factory):
    """GET /simulations/{id}/audit-trail -> 200 + list of events."""
    sim_id = await _seed_simulation_with_audit_events(session_factory)

    response = await client.get(f"/simulations/{sim_id}/audit-trail")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) == 3
    assert payload[0]["simulation_id"] == sim_id
    assert payload[0]["agent_id"] == "agent-0"
    assert payload[0]["event_type"] == "belief_change"


@pytest.mark.asyncio
async def test_get_audit_trail_filter_by_agent(client, session_factory):
    """GET /simulations/{id}/audit-trail?agent_id=agent-1 -> filtered results."""
    sim_id = await _seed_simulation_with_audit_events(session_factory)

    response = await client.get(
        f"/simulations/{sim_id}/audit-trail",
        params={"agent_id": "agent-1"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["agent_id"] == "agent-1"


@pytest.mark.asyncio
async def test_get_audit_trail_filter_by_event_type(client, session_factory):
    """GET /simulations/{id}/audit-trail?event_type=opinion_shift -> filtered results."""
    sim_id = await _seed_simulation_with_audit_events(session_factory)

    response = await client.get(
        f"/simulations/{sim_id}/audit-trail",
        params={"event_type": "opinion_shift"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert all(e["event_type"] == "opinion_shift" for e in payload)


@pytest.mark.asyncio
async def test_get_audit_trail_empty(client, session_factory):
    """GET /simulations/{nonexistent}/audit-trail -> 200 + empty list."""
    response = await client.get(f"/simulations/{uuid.uuid4()}/audit-trail")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_create_population_snapshot_endpoint(client, session_factory):
    """POST /populations/{id}/snapshot -> 201."""
    population_id = await _seed_population(session_factory)

    response = await client.post(f"/populations/{population_id}/snapshot")
    assert response.status_code == 201
    payload = response.json()
    assert payload["population_id"] == population_id
    assert payload["id"]
    assert payload["created_at"]


@pytest.mark.asyncio
async def test_create_population_snapshot_not_found(client):
    """POST /populations/{nonexistent}/snapshot -> 404."""
    response = await client.post(f"/populations/{uuid.uuid4()}/snapshot")
    assert response.status_code == 404
