"""
TDD tests for three benchmark-identified fixes:
  1. GZipMiddleware on /runs (compressed response for large payloads)
  2. Pagination (skip/limit) on GET /runs and GET /simulations
  3. Cache-Control header on GET /templates
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
from src.app.models.project import Project
from src.app.models.run import Run
from src.app.models.simulation import Simulation
from src.app.models.template import Template


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def session_factory(tmp_path):
    db_path = tmp_path / "benchmark-fixes.db"
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_runs(session_factory, *, count: int, project_id: str | None = None) -> str:
    """Seed `count` Run rows and return the project_id used."""
    pid = project_id or str(uuid.uuid4())
    async with session_factory() as session:
        project = Project(id=pid, name="Benchmark Project", prompt_text="benchmark test")
        session.add(project)
        for _ in range(count):
            session.add(
                Run(
                    id=str(uuid.uuid4()),
                    project_id=pid,
                    template_name="business_analysis",
                    execution_profile="standard",
                    status="completed",
                )
            )
        await session.commit()
    return pid


async def _seed_simulations(session_factory, *, count: int) -> str:
    """Seed `count` Simulation rows and return the project_id used."""
    pid = str(uuid.uuid4())
    async with session_factory() as session:
        project = Project(id=pid, name="Benchmark Sim Project", prompt_text="sim benchmark")
        session.add(project)
        for _ in range(count):
            session.add(
                Simulation(
                    id=str(uuid.uuid4()),
                    project_id=pid,
                    mode="single",
                    prompt_text="benchmark",
                    template_name="business_analysis",
                    execution_profile="standard",
                    status="completed",
                )
            )
        await session.commit()
    return pid


async def _seed_templates(session_factory, *, count: int) -> None:
    """Seed `count` Template rows."""
    async with session_factory() as session:
        for i in range(count):
            session.add(
                Template(
                    id=str(uuid.uuid4()),
                    name=f"template_{i}",
                    display_name=f"Template {i}",
                    description=f"Description {i}",
                    category="test",
                    prompts={},
                )
            )
        await session.commit()


# ===========================================================================
# 1. GZipMiddleware
# ===========================================================================


@pytest.mark.asyncio
async def test_gzip_middleware_compresses_large_runs_response(client, session_factory):
    """GET /runs should return gzip-encoded body when Accept-Encoding: gzip is sent
    and the response is large enough to trigger compression (minimum_size=1000)."""
    # Seed enough runs to produce a payload > 1000 bytes
    await _seed_runs(session_factory, count=30)

    response = await client.get(
        "/runs",
        headers={"Accept-Encoding": "gzip"},
    )

    assert response.status_code == 200
    # httpx transparently decompresses gzip; the server signals compression via
    # the Content-Encoding header BEFORE decompression.
    assert response.headers.get("content-encoding") == "gzip", (
        "Expected Content-Encoding: gzip but got: "
        + str(response.headers.get("content-encoding"))
    )


@pytest.mark.asyncio
async def test_gzip_middleware_is_present_in_app_middleware_stack():
    """The app middleware stack must include GZipMiddleware."""
    from fastapi.middleware.gzip import GZipMiddleware

    middleware_types = [m.cls for m in app.user_middleware]
    assert GZipMiddleware in middleware_types, (
        f"GZipMiddleware not found in app.user_middleware. Found: {middleware_types}"
    )


# ===========================================================================
# 2. Pagination – GET /runs
# ===========================================================================


@pytest.mark.asyncio
async def test_list_runs_default_limit_is_20(client, session_factory):
    """Without explicit pagination params, /runs returns at most 20 items."""
    await _seed_runs(session_factory, count=25)

    response = await client.get("/runs")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 20, f"Expected 20 items by default, got {len(data)}"


@pytest.mark.asyncio
async def test_list_runs_skip_parameter_offsets_results(client, session_factory):
    """GET /runs?skip=10 should skip the first 10 results."""
    await _seed_runs(session_factory, count=25)

    all_response = await client.get("/runs?limit=25")
    all_data = all_response.json()

    skipped_response = await client.get("/runs?skip=10&limit=25")
    skipped_data = skipped_response.json()

    assert len(skipped_data) == 15
    # The first item of skipped result should be the 11th item overall
    assert skipped_data[0]["id"] == all_data[10]["id"]


@pytest.mark.asyncio
async def test_list_runs_limit_parameter_respected(client, session_factory):
    """GET /runs?limit=5 should return exactly 5 items."""
    await _seed_runs(session_factory, count=10)

    response = await client.get("/runs?limit=5")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 5


@pytest.mark.asyncio
async def test_list_runs_limit_capped_at_100(client, session_factory):
    """GET /runs?limit=200 should be silently capped at 100."""
    await _seed_runs(session_factory, count=110)

    response = await client.get("/runs?limit=200")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 100, f"Expected limit capped at 100, got {len(data)}"


@pytest.mark.asyncio
async def test_list_runs_skip_0_returns_first_page(client, session_factory):
    """GET /runs?skip=0 is equivalent to the default first page."""
    await _seed_runs(session_factory, count=5)

    default_response = await client.get("/runs?limit=5")
    skip0_response = await client.get("/runs?skip=0&limit=5")

    assert default_response.json() == skip0_response.json()


# ===========================================================================
# 2. Pagination – GET /simulations
# ===========================================================================


@pytest.mark.asyncio
async def test_list_simulations_default_limit_is_20(client, session_factory):
    """Without explicit pagination params, /simulations returns at most 20 items."""
    await _seed_simulations(session_factory, count=25)

    response = await client.get("/simulations")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 20, f"Expected 20 items by default, got {len(data)}"


@pytest.mark.asyncio
async def test_list_simulations_skip_parameter_offsets_results(client, session_factory):
    """GET /simulations?skip=10 should skip the first 10 results."""
    await _seed_simulations(session_factory, count=25)

    all_response = await client.get("/simulations?limit=25")
    all_data = all_response.json()

    skipped_response = await client.get("/simulations?skip=10&limit=25")
    skipped_data = skipped_response.json()

    assert len(skipped_data) == 15
    assert skipped_data[0]["id"] == all_data[10]["id"]


@pytest.mark.asyncio
async def test_list_simulations_limit_parameter_respected(client, session_factory):
    """GET /simulations?limit=5 should return exactly 5 items."""
    await _seed_simulations(session_factory, count=10)

    response = await client.get("/simulations?limit=5")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 5


@pytest.mark.asyncio
async def test_list_simulations_limit_capped_at_100(client, session_factory):
    """GET /simulations?limit=200 should be silently capped at 100."""
    await _seed_simulations(session_factory, count=110)

    response = await client.get("/simulations?limit=200")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 100, f"Expected limit capped at 100, got {len(data)}"


# ===========================================================================
# 3. Cache-Control header – GET /templates
# ===========================================================================


@pytest.mark.asyncio
async def test_list_templates_returns_cache_control_header(client, session_factory):
    """GET /templates must include Cache-Control: public, max-age=300."""
    await _seed_templates(session_factory, count=3)

    response = await client.get("/templates")

    assert response.status_code == 200
    cache_header = response.headers.get("cache-control", "")
    assert "public" in cache_header, f"Expected 'public' in Cache-Control but got: {cache_header!r}"
    assert "max-age=300" in cache_header, f"Expected 'max-age=300' in Cache-Control but got: {cache_header!r}"


@pytest.mark.asyncio
async def test_list_templates_cache_control_absent_on_empty_db(client, session_factory):
    """Cache-Control must be present even when no templates exist."""
    response = await client.get("/templates")

    assert response.status_code == 200
    cache_header = response.headers.get("cache-control", "")
    assert "public" in cache_header
    assert "max-age=300" in cache_header
