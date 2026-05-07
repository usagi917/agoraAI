"""Wondrous Crayon API ルートのテスト."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.app.api.deps import get_session
from src.app.database import Base
from src.app.main import app
from src.app.models import _import_all_models
from src.app.models.simulation import Simulation


@pytest_asyncio.fixture
async def session_factory(tmp_path):
    db_path = tmp_path / "time-axis-api.db"
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


def _sample_report() -> dict:
    return {
        "theme": "ライドシェア解禁",
        "timeline": [
            {
                "key": "t0",
                "label": "即時",
                "delta_days": 0,
                "t_index": 0,
                "distribution": {"賛成": 0.4, "反対": 0.4, "中立": 0.2},
                "driving_factors": [],
            },
            {
                "key": "t5",
                "label": "3年後",
                "delta_days": 1095,
                "t_index": 5,
                "distribution": {"賛成": 0.6, "反対": 0.3, "中立": 0.1},
                "driving_factors": [{"stance": "賛成", "delta": 0.2}],
            },
        ],
        "summary": {"long_term_shift": {"賛成": 0.2}, "horizons": 2},
    }


@pytest.mark.asyncio
async def test_time_axis_returns_404_when_simulation_missing(client):
    resp = await client.get("/society/simulations/no-such/time-axis")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_time_axis_returns_404_when_no_metadata(client, session_factory):
    async with session_factory() as session:
        sim = Simulation(
            id="sim-empty",
            mode="society",
            status="completed",
            prompt_text="t",
            metadata_json={},
        )
        session.add(sim)
        await session.commit()

    resp = await client.get("/society/simulations/sim-empty/time-axis")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_time_axis_returns_full_report(client, session_factory):
    async with session_factory() as session:
        sim = Simulation(
            id="sim-with-report",
            mode="society",
            status="completed",
            prompt_text="t",
            metadata_json={"time_axis_result": _sample_report()},
        )
        session.add(sim)
        await session.commit()

    resp = await client.get("/society/simulations/sim-with-report/time-axis")
    assert resp.status_code == 200
    body = resp.json()
    assert body["theme"] == "ライドシェア解禁"
    assert len(body["timeline"]) == 2


@pytest.mark.asyncio
async def test_ensemble_returns_band_summary(client, session_factory):
    async with session_factory() as session:
        sim = Simulation(
            id="sim-ensemble",
            mode="society",
            status="completed",
            prompt_text="t",
            metadata_json={"time_axis_result": _sample_report()},
        )
        session.add(sim)
        await session.commit()

    resp = await client.get("/society/simulations/sim-ensemble/ensemble")
    assert resp.status_code == 200
    body = resp.json()
    assert body["horizons"] == 2
    assert body["bands"][0]["key"] == "t0"
    assert body["bands"][0]["distribution"]["賛成"] == 0.4


@pytest.mark.asyncio
async def test_report_returns_summary_and_timeline(client, session_factory):
    async with session_factory() as session:
        sim = Simulation(
            id="sim-report",
            mode="society",
            status="completed",
            prompt_text="t",
            metadata_json={"time_axis_result": _sample_report()},
        )
        session.add(sim)
        await session.commit()

    resp = await client.get("/society/simulations/sim-report/report")
    assert resp.status_code == 200
    body = resp.json()
    assert body["theme"] == "ライドシェア解禁"
    assert body["summary"]["horizons"] == 2
    assert "what_if" in body
