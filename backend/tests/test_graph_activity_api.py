"""社会グラフのスナップショット・永続イベント API 契約テスト。"""

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.app.api.deps import get_session
from src.app.database import Base
from src.app.main import app
from src.app.models import _import_all_models
from src.app.models.agent_profile import AgentProfile
from src.app.models.graph_activity_event import GraphActivityEvent
from src.app.models.population import Population
from src.app.models.simulation import Simulation
from src.app.models.social_edge import SocialEdge
from src.app.models.society_result import SocietyResult


@pytest_asyncio.fixture
async def session_factory(tmp_path):
    db_path = tmp_path / "graph-activity-api.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    _import_all_models()

    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = ON"))
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def client(session_factory):
    async def override_get_session():
        async with session_factory() as session:
            await session.execute(text("PRAGMA foreign_keys = ON"))
            yield session

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as async_client:
        yield async_client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seeded_graph(session_factory):
    async with session_factory() as session:
        session.add(Population(id="pop-graph", agent_count=3, status="ready"))
        await session.flush()
        for index in range(3):
            session.add(AgentProfile(
                id=f"agent-{index}",
                population_id="pop-graph",
                agent_index=index,
                demographics={
                    "occupation": "会社員",
                    "age": 30 + index,
                    "region": "関東",
                },
                big_five={"O": 0.5, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5},
            ))
        session.add(SocialEdge(
            id="edge-graph",
            population_id="pop-graph",
            agent_id="agent-0",
            target_id="agent-1",
            relation_type="friend",
            strength=0.8,
        ))
        session.add(Simulation(
            id="sim-graph",
            prompt_text="グラフテスト",
            population_id="pop-graph",
            pipeline_stage="meeting",
        ))
        await session.flush()
        session.add(SocietyResult(
            id="activation-graph",
            simulation_id="sim-graph",
            population_id="pop-graph",
            layer="activation",
            phase_data={
                "responses": [
                    {
                        "agent_id": "agent-0",
                        "stance": "賛成",
                        "confidence": 0.9,
                        "reason": "期待している",
                    },
                    {
                        "agent_id": "agent-1",
                        "stance": "反対",
                        "confidence": 0.8,
                        "reason": "懸念がある",
                    },
                ],
            },
            usage={},
        ))
        base_time = datetime(2026, 7, 13, 1, 0, tzinfo=UTC)
        session.add_all([
            GraphActivityEvent(
                simulation_id="sim-graph",
                occurred_at=base_time,
                phase="activation",
                round=0,
                kind="phase_changed",
                payload={"phase": "activation"},
            ),
            GraphActivityEvent(
                simulation_id="sim-graph",
                occurred_at=base_time + timedelta(seconds=1),
                phase="meeting",
                round=2,
                kind="dialogue",
                source_id="agent-0",
                target_id="agent-1",
                edge_id="edge-graph",
                payload={"argument": "意見を伝える"},
            ),
            GraphActivityEvent(
                simulation_id="sim-graph",
                occurred_at=base_time + timedelta(seconds=2),
                phase="meeting",
                round=2,
                kind="relationship_changed",
                source_id="agent-0",
                target_id="agent-1",
                edge_id="edge-graph",
                payload={
                    "before_strength": 0.6,
                    "after_strength": 0.8,
                    "delta": 0.2,
                    "is_new": False,
                },
            ),
        ])
        await session.commit()
    return "sim-graph"


@pytest.mark.asyncio
async def test_graph_events_returns_id_order_after_cursor(client, seeded_graph):
    first_response = await client.get(
        f"/society/simulations/{seeded_graph}/graph-events?limit=2"
    )

    assert first_response.status_code == 200
    first_page = first_response.json()
    assert [event["kind"] for event in first_page] == ["phase_changed", "dialogue"]
    assert first_page[1]["source_id"] == "agent-0"
    assert first_page[1]["occurred_at"].endswith("Z")

    second_response = await client.get(
        f"/society/simulations/{seeded_graph}/graph-events",
        params={"after_id": first_page[-1]["id"], "limit": 10},
    )

    assert second_response.status_code == 200
    second_page = second_response.json()
    assert len(second_page) == 1
    assert second_page[0]["kind"] == "relationship_changed"
    assert second_page[0]["payload"]["before_strength"] == 0.6


@pytest.mark.asyncio
async def test_graph_state_combines_selected_and_compact_population_layers(client, seeded_graph):
    response = await client.get(f"/society/simulations/{seeded_graph}/graph-state")

    assert response.status_code == 200
    payload = response.json()
    assert payload["simulation_id"] == seeded_graph
    assert payload["current_phase"] == "meeting"
    assert payload["current_round"] == 2
    assert payload["latest_event_id"] > 0
    assert [node["id"] for node in payload["nodes"]] == ["agent-0", "agent-1"]
    assert payload["edges"][0]["id"] == "edge-graph"
    assert payload["population_network"]["node_count"] == 3
    assert payload["population_network"]["edges"] == [[0, 1, 0.8]]


@pytest.mark.asyncio
async def test_graph_events_rejects_unknown_simulation(client):
    response = await client.get("/society/simulations/missing/graph-events")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_graph_state_is_available_before_population_assignment(client, session_factory):
    async with session_factory() as session:
        session.add(Simulation(
            id="sim-queued",
            prompt_text="開始直後",
            status="queued",
            pipeline_stage="pending",
        ))
        await session.commit()

    response = await client.get("/society/simulations/sim-queued/graph-state")

    assert response.status_code == 200
    payload = response.json()
    assert payload["population_id"] is None
    assert payload["nodes"] == []
    assert payload["population_network"]["edges"] == []
    assert payload["latest_event_id"] == 0


@pytest.mark.asyncio
async def test_graph_activity_events_cascade_when_simulation_is_deleted(
    session_factory,
    seeded_graph,
):
    async with session_factory() as session:
        await session.execute(text("PRAGMA foreign_keys = ON"))
        await session.execute(
            delete(SocietyResult).where(SocietyResult.simulation_id == seeded_graph)
        )
        await session.execute(delete(Simulation).where(Simulation.id == seeded_graph))
        await session.commit()

        result = await session.execute(
            select(GraphActivityEvent).where(
                GraphActivityEvent.simulation_id == seeded_graph
            )
        )
        assert result.scalars().all() == []
