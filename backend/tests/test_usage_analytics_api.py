import uuid
from datetime import timedelta
from unittest.mock import ANY

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.app.api.deps import get_session
from src.app.config import settings
from src.app.database import Base, utcnow_naive
from src.app.main import app
from src.app.models import _import_all_models
from src.app.models.simulation import Simulation
from src.app.models.usage_event import UsageEvent


@pytest_asyncio.fixture
async def session_factory(tmp_path):
    db_path = tmp_path / "usage-analytics-api.db"
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


@pytest.mark.asyncio
async def test_records_anonymous_usage_event(client, session_factory):
    visitor_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())

    response = await client.post(
        "/analytics/events",
        json={
            "event_name": "page_view",
            "visitor_id": visitor_id,
            "session_id": session_id,
            "path": "/sim/example/results",
            "properties": {"route_name": "results"},
        },
    )

    assert response.status_code == 204
    async with session_factory() as session:
        event = (await session.execute(select(UsageEvent))).scalar_one()
        assert event.event_name == "page_view"
        assert event.visitor_id == visitor_id
        assert event.session_id == session_id
        assert event.path == "/sim/example/results"
        assert event.properties_json == {"route_name": "results"}


@pytest.mark.asyncio
async def test_rejects_unknown_events_and_sensitive_properties(client):
    identity = {
        "visitor_id": str(uuid.uuid4()),
        "session_id": str(uuid.uuid4()),
    }

    unknown_event = await client.post(
        "/analytics/events",
        json={**identity, "event_name": "arbitrary_event"},
    )
    sensitive_payload = await client.post(
        "/analytics/events",
        json={
            **identity,
            "event_name": "page_view",
            "properties": {"prompt_text": "個人情報を含み得る入力"},
        },
    )

    assert unknown_event.status_code == 422
    assert sensitive_payload.status_code == 422


@pytest.mark.asyncio
async def test_create_simulation_stores_usage_context_and_start_event(
    client,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(type(settings), "live_simulation_available", lambda self: True)
    monkeypatch.setattr("src.app.api.routes.simulations.spawn_simulation", lambda _simulation_id: None)
    visitor_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())

    response = await client.post(
        "/simulations",
        json={
            "mode": "standard",
            "prompt_text": "大学でAIをどう活用するか",
            "template_name": "business_analysis",
            "usage_context": {
                "visitor_id": visitor_id,
                "session_id": session_id,
                "input_method": "wizard",
            },
        },
    )

    assert response.status_code == 200
    simulation_id = response.json()["id"]
    async with session_factory() as session:
        simulation = await session.get(Simulation, simulation_id)
        assert simulation is not None
        assert simulation.metadata_json["analytics"] == {
            "visitor_id": visitor_id,
            "session_id": session_id,
            "input_method": "wizard",
        }
        event = (
            await session.execute(
                select(UsageEvent).where(UsageEvent.simulation_id == simulation_id)
            )
        ).scalar_one()
        assert event.event_name == "simulation_started"
        assert event.properties_json["mode"] == "standard"
        assert event.properties_json["input_method"] == "wizard"


@pytest.mark.asyncio
async def test_status_transition_records_completion_event(session_factory):
    visitor_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    simulation_id = str(uuid.uuid4())

    async with session_factory() as session:
        simulation = Simulation(
            id=simulation_id,
            mode="standard",
            prompt_text="テスト",
            status="running",
            metadata_json={
                "analytics": {
                    "visitor_id": visitor_id,
                    "session_id": session_id,
                    "input_method": "manual",
                }
            },
        )
        session.add(simulation)
        await session.commit()

        simulation.status = "completed"
        simulation.completed_at = utcnow_naive()
        await session.commit()

    async with session_factory() as session:
        event = (
            await session.execute(
                select(UsageEvent).where(UsageEvent.simulation_id == simulation_id)
            )
        ).scalar_one()
        assert event.event_name == "simulation_completed"
        assert event.visitor_id == visitor_id


@pytest.mark.asyncio
async def test_usage_summary_requires_admin_token(
    client,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("ANALYTICS_ADMIN_TOKEN", "summary-secret")

    response = await client.get("/analytics/summary")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_usage_summary_reports_event_and_simulation_metrics(
    client,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("ANALYTICS_ADMIN_TOKEN", "summary-secret")
    now = utcnow_naive()
    visitor_a = str(uuid.uuid4())
    visitor_b = str(uuid.uuid4())
    session_a = str(uuid.uuid4())
    session_b = str(uuid.uuid4())

    async with session_factory() as session:
        session.add_all(
            [
                UsageEvent(
                    event_name="session_started",
                    visitor_id=visitor_a,
                    session_id=session_a,
                    path="/",
                ),
                UsageEvent(
                    event_name="page_view",
                    visitor_id=visitor_a,
                    session_id=session_a,
                    path="/sim/one/results",
                ),
                UsageEvent(
                    event_name="session_started",
                    visitor_id=visitor_b,
                    session_id=session_b,
                    path="/",
                ),
                Simulation(
                    id=str(uuid.uuid4()),
                    mode="standard",
                    prompt_text="教育へのAI導入",
                    template_name="business_analysis",
                    status="completed",
                    created_at=now - timedelta(minutes=5),
                    started_at=now - timedelta(minutes=4),
                    completed_at=now - timedelta(minutes=1),
                    metadata_json={
                        "analytics": {
                            "visitor_id": visitor_a,
                            "session_id": session_a,
                            "input_method": "wizard",
                        }
                    },
                ),
                Simulation(
                    id=str(uuid.uuid4()),
                    mode="research",
                    prompt_text="地域交通の将来",
                    template_name="policy_impact",
                    status="failed",
                    created_at=now - timedelta(minutes=3),
                    started_at=now - timedelta(minutes=2),
                    metadata_json={
                        "analytics": {
                            "visitor_id": visitor_b,
                            "session_id": session_b,
                            "input_method": "manual",
                        }
                    },
                ),
            ]
        )
        await session.commit()

    response = await client.get(
        "/analytics/summary",
        headers={"X-Analytics-Token": "summary-secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["unique_visitors"] == 2
    assert payload["sessions"] == 2
    assert payload["event_counts"] == {"page_view": 1, "session_started": 2}
    assert payload["simulations"]["total"] == 2
    assert payload["simulations"]["completed"] == 1
    assert payload["simulations"]["failed"] == 1
    assert payload["simulations"]["completion_rate"] == 0.5
    assert payload["simulations"]["median_duration_seconds"] == 180.0
    assert payload["by_mode"] == {"research": 1, "standard": 1}
    assert payload["by_input_method"] == {"manual": 1, "wizard": 1}
    assert payload["top_paths"][0] == {"path": "/", "count": 2}
    assert [item["prompt_preview"] for item in payload["simulation_details"]] == [
        "地域交通の将来",
        "教育へのAI導入",
    ]
    assert payload["simulation_details"][0] == expect_simulation_detail(
        prompt_preview="地域交通の将来",
        status="failed",
        mode="research",
        input_method="manual",
    )


def expect_simulation_detail(
    *,
    prompt_preview: str,
    status: str,
    mode: str,
    input_method: str,
) -> dict:
    return {
        "id": ANY,
        "created_at": ANY,
        "status": status,
        "mode": mode,
        "template_name": "policy_impact" if mode == "research" else "business_analysis",
        "input_method": input_method,
        "duration_seconds": None if status == "failed" else 180.0,
        "prompt_preview": prompt_preview,
    }
