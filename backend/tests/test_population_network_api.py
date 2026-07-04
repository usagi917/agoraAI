"""population-network エンドポイント（全人口ノード + 圧縮エッジ）のテスト。"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.app.api.deps import get_session
from src.app.database import Base
from src.app.main import app
from src.app.models import _import_all_models
from src.app.models.agent_profile import AgentProfile
from src.app.models.population import Population
from src.app.models.simulation import Simulation
from src.app.models.social_edge import SocialEdge


@pytest_asyncio.fixture
async def session_factory(tmp_path):
    db_path = tmp_path / "population-network-api.db"
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


@pytest_asyncio.fixture
async def seeded_sim(session_factory):
    """Population(5人) + エッジ2本 + Simulation を投入する。"""
    async with session_factory() as session:
        pop = Population(id="pop-1", agent_count=5, status="ready")
        session.add(pop)
        for i in range(5):
            session.add(AgentProfile(
                id=f"agent-{i}",
                population_id="pop-1",
                agent_index=i,
                demographics={"occupation": "会社員", "age": 30 + i, "region": "関東"},
                big_five={"O": 0.5, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5},
            ))
        session.add(SocialEdge(
            id="edge-0", population_id="pop-1",
            agent_id="agent-0", target_id="agent-1",
            relation_type="friend", strength=0.8,
        ))
        session.add(SocialEdge(
            id="edge-1", population_id="pop-1",
            agent_id="agent-3", target_id="agent-4",
            relation_type="colleague", strength=0.4,
        ))
        sim = Simulation(id="sim-1", prompt_text="テスト", population_id="pop-1")
        session.add(sim)
        await session.commit()
    return "sim-1"


@pytest.mark.asyncio
async def test_population_network_returns_compact_graph(client, seeded_sim):
    response = await client.get(f"/society/simulations/{seeded_sim}/population-network")

    assert response.status_code == 200
    payload = response.json()

    # ノード: agent_index 順、id と agent_index を含む
    assert payload["node_count"] == 5
    assert len(payload["nodes"]) == 5
    assert payload["nodes"][0]["id"] == "agent-0"
    assert payload["nodes"][0]["agent_index"] == 0
    assert payload["nodes"][4]["agent_index"] == 4

    # エッジ: [source_index, target_index, strength] の圧縮形式
    assert payload["edge_count"] == 2
    assert [0, 1, 0.8] in payload["edges"]
    assert [3, 4, 0.4] in payload["edges"]


@pytest.mark.asyncio
async def test_population_network_404_when_simulation_missing(client):
    response = await client.get("/society/simulations/nope/population-network")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_population_network_skips_dangling_edges(client, session_factory):
    """端点が存在しないエッジは圧縮グラフから除外される。"""
    async with session_factory() as session:
        pop = Population(id="pop-d", agent_count=2, status="ready")
        session.add(pop)
        for i in range(2):
            session.add(AgentProfile(
                id=f"d-agent-{i}",
                population_id="pop-d",
                agent_index=i,
                demographics={"occupation": "会社員", "age": 30, "region": "関東"},
                big_five={"O": 0.5, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5},
            ))
        # 有効なエッジ
        session.add(SocialEdge(
            id="d-edge-ok", population_id="pop-d",
            agent_id="d-agent-0", target_id="d-agent-1",
            relation_type="friend", strength=0.7,
        ))
        # target が存在しない孤立エッジ（スキップされるべき）
        session.add(SocialEdge(
            id="d-edge-dangling", population_id="pop-d",
            agent_id="d-agent-0", target_id="ghost-agent",
            relation_type="friend", strength=0.9,
        ))
        session.add(Simulation(id="sim-d", prompt_text="テスト", population_id="pop-d"))
        await session.commit()

    response = await client.get("/society/simulations/sim-d/population-network")

    assert response.status_code == 200
    payload = response.json()
    assert payload["node_count"] == 2
    # 孤立エッジは除外され、有効な 1 本だけが残る
    assert payload["edge_count"] == 1
    assert payload["edges"] == [[0, 1, 0.7]]
