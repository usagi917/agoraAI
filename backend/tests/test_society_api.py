import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.app.api.deps import get_session
from src.app.config import settings
from src.app.database import Base
from src.app.main import app
from src.app.models import _import_all_models


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
