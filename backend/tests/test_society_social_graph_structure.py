"""選抜直後に送出するソーシャルグラフ構造のテスト。

`society_social_graph_structure` イベントの中身を組み立てる
`_load_selected_social_edges` が「両端が選抜エージェントのエッジ」だけを
フロント表示用の形（id/source/target/relation_type/strength）で返すことを検証する。
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.app.database import Base
from src.app.models import _import_all_models
from src.app.models.agent_profile import AgentProfile
from src.app.models.population import Population
from src.app.models.social_edge import SocialEdge
from src.app.services.society.society_orchestrator import _load_selected_social_edges


@pytest_asyncio.fixture
async def session_factory(tmp_path):
    db_path = tmp_path / "society-social-graph-structure.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    _import_all_models()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        yield session_maker
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_load_selected_social_edges_filters_to_selected_subgraph(session_factory):
    async with session_factory() as session:
        session.add(Population(id="pop-1", agent_count=4, status="ready"))
        for i in range(4):
            session.add(AgentProfile(
                id=f"agent-{i}",
                population_id="pop-1",
                agent_index=i,
                demographics={"occupation": "会社員", "age": 30 + i, "region": "関東"},
                big_five={"O": 0.5, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5},
            ))
        # 両端が選抜内 → 含まれる
        session.add(SocialEdge(
            id="e-in", population_id="pop-1",
            agent_id="agent-0", target_id="agent-1",
            relation_type="friend", strength=0.8,
        ))
        # 片端が選抜外(agent-3) → 除外される
        session.add(SocialEdge(
            id="e-cross", population_id="pop-1",
            agent_id="agent-0", target_id="agent-3",
            relation_type="family", strength=0.9,
        ))
        await session.commit()

    selected_ids = {"agent-0", "agent-1", "agent-2"}
    async with session_factory() as session:
        edges = await _load_selected_social_edges(session, "pop-1", selected_ids)

    # 選抜内サブグラフのエッジだけがフロント形状で返る
    assert [e["id"] for e in edges] == ["e-in"]
    edge = edges[0]
    assert edge["source"] == "agent-0"
    assert edge["target"] == "agent-1"
    assert edge["relation_type"] == "friend"
    assert edge["strength"] == 0.8


@pytest.mark.asyncio
async def test_load_selected_social_edges_empty_without_selection(session_factory):
    async with session_factory() as session:
        edges = await _load_selected_social_edges(session, "pop-x", set())
    assert edges == []
