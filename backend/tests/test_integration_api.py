"""Stream H2: API Integration Tests for Decision Laboratory

Tests the API endpoints work together as a cohesive system:
- POST to create scenario pairs, GET to fetch them
- Audit trail events created in DB and queried via API
- Filter parameters (agent_id, event_type) work through the API layer
"""

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.app.api.deps import get_session
from src.app.database import Base
from src.app.main import app
from src.app.models import _import_all_models
from src.app.models.audit_event import AuditEvent
from src.app.models.population import Population
from src.app.models.simulation import Simulation


# ---------------------------------------------------------------------------
# Fixtures (follow existing pattern from test_api_scenario_pairs.py)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def session_factory(tmp_path):
    db_path = tmp_path / "integration-api.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    _import_all_models()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False,
    )

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


async def _seed_population(session_factory) -> str:
    """Create a Population record and return its id."""
    async with session_factory() as session:
        pop = Population(agent_count=100)
        session.add(pop)
        await session.commit()
        return pop.id


# ---------------------------------------------------------------------------
# H2.1: Create and fetch scenario pair
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_create_and_fetch_scenario_pair(client, session_factory):
    """POST to create, GET to fetch, verify consistency."""
    population_id = await _seed_population(session_factory)

    # POST /scenario-pairs
    create_response = await client.post(
        "/scenario-pairs",
        json={
            "population_id": population_id,
            "intervention_params": {"policy_type": "subsidy", "amount": 2000},
            "decision_context": "Youth subsidy evaluation",
            "preset": "standard",
            "seed": 42,
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()

    # Verify create response
    assert created["id"]
    assert created["population_snapshot_id"]
    assert created["baseline_simulation_id"] is not None
    assert created["intervention_simulation_id"] is not None
    assert created["intervention_params"]["policy_type"] == "subsidy"
    assert created["intervention_params"]["amount"] == 2000
    assert created["decision_context"] == "Youth subsidy evaluation"
    assert created["status"] == "created"

    # GET /scenario-pairs/{id}
    get_response = await client.get(f"/scenario-pairs/{created['id']}")
    assert get_response.status_code == 200
    fetched = get_response.json()

    # Verify same data returned
    assert fetched["id"] == created["id"]
    assert fetched["population_snapshot_id"] == created["population_snapshot_id"]
    assert fetched["baseline_simulation_id"] == created["baseline_simulation_id"]
    assert fetched["intervention_simulation_id"] == created["intervention_simulation_id"]
    assert fetched["intervention_params"] == created["intervention_params"]
    assert fetched["decision_context"] == created["decision_context"]
    assert fetched["status"] == created["status"]
    assert fetched["created_at"] == created["created_at"]


# ---------------------------------------------------------------------------
# H2.2: Audit trail after events (create events in DB, query via API)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_audit_trail_after_events(client, session_factory):
    """Create events directly, then query via API."""
    # Create a simulation with audit events directly in DB
    async with session_factory() as session:
        sim = Simulation(
            mode="standard",
            prompt_text="audit trail integration test",
            template_name="general",
            execution_profile="standard",
            status="completed",
        )
        session.add(sim)
        await session.flush()

        events_data = [
            ("agent-A", "Alice", 1, "belief_change", 0.3, 0.5),
            ("agent-B", "Bob", 1, "opinion_shift", 0.4, 0.8),
            ("agent-A", "Alice", 2, "opinion_shift", 0.5, 0.7),
            ("agent-C", "Charlie", 2, "action", 0.6, 0.6),
            ("agent-B", "Bob", 3, "belief_change", 0.8, 0.6),
        ]
        for agent_id, agent_name, round_num, event_type, before_val, after_val in events_data:
            event = AuditEvent(
                simulation_id=sim.id,
                agent_id=agent_id,
                agent_name=agent_name,
                round_number=round_num,
                event_type=event_type,
                before_state={"stance": before_val},
                after_state={"stance": after_val},
                reasoning=f"{agent_name} round {round_num}",
            )
            session.add(event)

        await session.commit()
        sim_id = sim.id

    # GET /simulations/{id}/audit-trail (all events)
    response = await client.get(f"/simulations/{sim_id}/audit-trail")
    assert response.status_code == 200
    all_events = response.json()
    assert isinstance(all_events, list)
    assert len(all_events) == 5

    # Verify events have correct structure
    first_event = all_events[0]
    assert "id" in first_event
    assert "simulation_id" in first_event
    assert "agent_id" in first_event
    assert "agent_name" in first_event
    assert "round_number" in first_event
    assert "event_type" in first_event
    assert "before_state" in first_event
    assert "after_state" in first_event
    assert "reasoning" in first_event
    assert "created_at" in first_event

    # Test filter by agent_id
    response_agent_a = await client.get(
        f"/simulations/{sim_id}/audit-trail",
        params={"agent_id": "agent-A"},
    )
    assert response_agent_a.status_code == 200
    agent_a_events = response_agent_a.json()
    assert len(agent_a_events) == 2
    assert all(e["agent_id"] == "agent-A" for e in agent_a_events)
    assert all(e["agent_name"] == "Alice" for e in agent_a_events)

    # Test filter by event_type
    response_opinions = await client.get(
        f"/simulations/{sim_id}/audit-trail",
        params={"event_type": "opinion_shift"},
    )
    assert response_opinions.status_code == 200
    opinion_events = response_opinions.json()
    assert len(opinion_events) == 2
    assert all(e["event_type"] == "opinion_shift" for e in opinion_events)

    # Test filter by event_type = belief_change
    response_beliefs = await client.get(
        f"/simulations/{sim_id}/audit-trail",
        params={"event_type": "belief_change"},
    )
    assert response_beliefs.status_code == 200
    belief_events = response_beliefs.json()
    assert len(belief_events) == 2
    assert all(e["event_type"] == "belief_change" for e in belief_events)


# ---------------------------------------------------------------------------
# H2.3: Scenario pair not found returns 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_scenario_pair_not_found(client):
    """GET /scenario-pairs/{nonexistent} -> 404."""
    response = await client.get(f"/scenario-pairs/{uuid.uuid4()}")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# H2.4: Empty audit trail returns 200 + empty list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_audit_trail_empty(client):
    """GET /simulations/{nonexistent}/audit-trail -> 200 + empty list."""
    response = await client.get(f"/simulations/{uuid.uuid4()}/audit-trail")
    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# H2.5: Comparison placeholder returns correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_comparison_placeholder(client, session_factory):
    """GET /scenario-pairs/{id}/comparison returns placeholder when not completed."""
    population_id = await _seed_population(session_factory)

    create_resp = await client.post(
        "/scenario-pairs",
        json={
            "population_id": population_id,
            "intervention_params": {"test": True},
            "decision_context": "Comparison placeholder test",
        },
    )
    assert create_resp.status_code == 201
    pair_id = create_resp.json()["id"]

    comp_resp = await client.get(f"/scenario-pairs/{pair_id}/comparison")
    assert comp_resp.status_code == 200
    body = comp_resp.json()
    assert body["scenario_pair_id"] == pair_id
    assert body["comparison"] is None


# ---------------------------------------------------------------------------
# H2.6: Create multiple pairs, list via GET
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_create_multiple_pairs(client, session_factory):
    """Create multiple pairs and verify each is independently retrievable."""
    population_id = await _seed_population(session_factory)

    pair_ids = []
    for i in range(3):
        resp = await client.post(
            "/scenario-pairs",
            json={
                "population_id": population_id,
                "intervention_params": {"variant": i},
                "decision_context": f"Variant {i} test",
                "seed": i + 10,
            },
        )
        assert resp.status_code == 201
        pair_ids.append(resp.json()["id"])

    # All ids should be unique
    assert len(set(pair_ids)) == 3

    # Each is independently retrievable with correct data
    for i, pair_id in enumerate(pair_ids):
        resp = await client.get(f"/scenario-pairs/{pair_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == pair_id
        assert body["intervention_params"]["variant"] == i
        assert body["decision_context"] == f"Variant {i} test"


# ---------------------------------------------------------------------------
# H2.7: Population snapshot endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_population_snapshot_roundtrip(client, session_factory):
    """POST /populations/{id}/snapshot -> 201 and verify fields."""
    population_id = await _seed_population(session_factory)

    resp = await client.post(f"/populations/{population_id}/snapshot")
    assert resp.status_code == 201
    body = resp.json()
    assert body["population_id"] == population_id
    assert body["id"]
    assert body["created_at"]
    assert isinstance(body["agent_count"], int)
    assert isinstance(body["seed"], int)
