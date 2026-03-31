import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.app.api.deps import get_session
from src.app.config import settings
from src.app.database import Base
from src.app.main import app
from src.app.models import _import_all_models
from src.app.models.population import Population
from src.app.models.simulation import Simulation
from src.app.models.society_result import SocietyResult


@pytest_asyncio.fixture
async def session_factory(tmp_path):
    db_path = tmp_path / "society-api.db"
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
async def test_generate_population_endpoint_uses_config_default_count(
    client,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        type(settings),
        "load_population_mix_config",
        lambda self: {"population": {"default_size": 7, "min_size": 5, "max_size": 20}},
    )

    response = await client.post("/society/populations/generate", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["agent_count"] == 7
    assert payload["status"] == "ready"


@pytest.mark.asyncio
async def test_generate_population_endpoint_uses_configured_range_in_validation(
    client,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        type(settings),
        "load_population_mix_config",
        lambda self: {"population": {"default_size": 7, "min_size": 5, "max_size": 20}},
    )

    response = await client.post("/society/populations/generate", json={"count": 21})

    assert response.status_code == 400
    assert response.json()["detail"] == "count は 5〜20 の範囲で指定してください"


@pytest.mark.asyncio
async def test_activation_endpoint_returns_pre_and_post_independence_aggregations(
    client,
    session_factory,
):
    async with session_factory() as session:
        population = Population(id="pop-1", agent_count=30, status="ready", generation_params={"count": 30})
        simulation = Simulation(id="sim-activation-1", mode="society", prompt_text="test", status="completed")
        activation = SocietyResult(
            id="act-1",
            simulation_id=simulation.id,
            population_id=population.id,
            layer="activation",
            phase_data={
                "aggregation": {"stance_distribution": {"賛成": 0.55, "反対": 0.45}},
                "aggregation_pre_independence": {"stance_distribution": {"賛成": 0.67, "反対": 0.33}},
                "responses_summary": {"total": 30, "stance_distribution": {"賛成": 0.55, "反対": 0.45}},
                "responses_summary_pre_independence": {"total": 30, "stance_distribution": {"賛成": 0.67, "反対": 0.33}},
                "responses": [],
            },
            usage={},
        )
        session.add(population)
        session.add(simulation)
        session.add(activation)
        await session.commit()

    response = await client.get("/society/simulations/sim-activation-1/activation")

    assert response.status_code == 200
    phase_data = response.json()["phase_data"]
    assert phase_data["aggregation"]["stance_distribution"]["賛成"] == 0.55
    assert phase_data["aggregation_pre_independence"]["stance_distribution"]["賛成"] == 0.67
    assert phase_data["responses_summary_pre_independence"]["stance_distribution"]["反対"] == 0.33


@pytest.mark.asyncio
async def test_propagation_endpoint_returns_independence_comparison_summary(
    client,
    session_factory,
):
    async with session_factory() as session:
        population = Population(id="pop-2", agent_count=30, status="ready", generation_params={"count": 30})
        simulation = Simulation(id="sim-prop-1", mode="society", prompt_text="test", status="completed")
        propagation = SocietyResult(
            id="prop-1",
            simulation_id=simulation.id,
            population_id=population.id,
            layer="network_propagation",
            phase_data={
                "cluster_count": 2,
                "clusters": [{"label": 0, "size": 20, "centroid": [0.9]}],
                "aggregation_pre_independence": {"stance_distribution": {"賛成": 0.7, "反対": 0.3}},
                "aggregation_post_independence": {"stance_distribution": {"賛成": 0.58, "反対": 0.42}},
                "independence_re_aggregation": {
                    "applied": True,
                    "effective_sample_size_pre": 28.4,
                    "effective_sample_size_post": 19.1,
                    "stance_distribution_pre": {"賛成": 0.7, "反対": 0.3},
                    "stance_distribution_post": {"賛成": 0.58, "反対": 0.42},
                },
            },
            usage={},
        )
        session.add(population)
        session.add(simulation)
        session.add(propagation)
        await session.commit()

    response = await client.get("/society/simulations/sim-prop-1/propagation")

    assert response.status_code == 200
    phase_data = response.json()["phase_data"]
    assert phase_data["independence_re_aggregation"]["applied"] is True
    assert phase_data["independence_re_aggregation"]["effective_sample_size_post"] == 19.1
    assert phase_data["aggregation_pre_independence"]["stance_distribution"]["賛成"] == 0.7
    assert phase_data["aggregation_post_independence"]["stance_distribution"]["反対"] == 0.42
