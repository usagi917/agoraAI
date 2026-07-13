"""Default census populations are persistent assets shared across simulations.

User journey: as a simulation user, I want the census-based population to be
created once and reused, so repeated runs do not recreate residents or their
social graph.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.app.models.agent_profile import AgentProfile
from src.app.models.population import Population
from src.app.models.social_edge import SocialEdge
from src.app.services.society import society_orchestrator as orchestrator


def _agent_payload(population_id: str, index: int) -> dict:
    return {
        "id": f"{population_id}-agent-{index}",
        "population_id": population_id,
        "agent_index": index,
        "demographics": {"age": 30 + index % 40, "region": "関東"},
        "big_five": {},
    }


async def _fake_population(population_id: str, count: int, seed: int | None = None) -> list[dict]:
    del seed
    return [_agent_payload(population_id, index) for index in range(count)]


async def _population_count(db_session) -> int:
    result = await db_session.execute(select(func.count()).select_from(Population))
    return int(result.scalar() or 0)


@pytest.mark.asyncio
async def test_default_population_is_created_once_and_reused_across_seeds(
    db_session,
    monkeypatch,
):
    generate_population = AsyncMock(side_effect=_fake_population)
    monkeypatch.setattr(orchestrator, "generate_population", generate_population)

    first_id, first_agents = await orchestrator._get_or_create_population(
        db_session,
        population_id=None,
        count=100,
        seed=11,
    )
    second_id, second_agents = await orchestrator._get_or_create_population(
        db_session,
        population_id=None,
        count=100,
        seed=99,
    )

    assert second_id == first_id
    assert [agent["id"] for agent in second_agents] == [agent["id"] for agent in first_agents]
    assert await _population_count(db_session) == 1
    generate_population.assert_awaited_once()


@pytest.mark.asyncio
async def test_existing_legacy_census_population_is_adopted_as_default(
    db_session,
    monkeypatch,
):
    population_id = "legacy-census-population"
    db_session.add(Population(
        id=population_id,
        agent_count=100,
        generation_params={"count": 100},
        status="ready",
    ))
    db_session.add_all([
        AgentProfile(**_agent_payload(population_id, index))
        for index in range(100)
    ])
    await db_session.commit()
    generate_population = AsyncMock(side_effect=_fake_population)
    monkeypatch.setattr(orchestrator, "generate_population", generate_population)

    resolved_id, agents = await orchestrator._get_or_create_population(
        db_session,
        population_id=None,
        count=100,
        seed=42,
    )

    assert resolved_id == population_id
    assert len(agents) == 100
    assert await _population_count(db_session) == 1
    generate_population.assert_not_awaited()


@pytest.mark.asyncio
async def test_incomplete_legacy_population_is_not_reused(
    db_session,
    monkeypatch,
):
    legacy_id = "incomplete-legacy-population"
    db_session.add(Population(
        id=legacy_id,
        agent_count=100,
        generation_params={"count": 100},
        status="ready",
    ))
    db_session.add(AgentProfile(**_agent_payload(legacy_id, 0)))
    await db_session.commit()
    generate_population = AsyncMock(side_effect=_fake_population)
    monkeypatch.setattr(orchestrator, "generate_population", generate_population)

    resolved_id, agents = await orchestrator._get_or_create_population(
        db_session,
        population_id=None,
        count=100,
    )

    assert resolved_id != legacy_id
    assert len(agents) == 100
    generate_population.assert_awaited_once()


@pytest.mark.asyncio
async def test_changed_population_config_uses_a_new_default(
    db_session,
    monkeypatch,
):
    active_config = {
        "population": {"demographics": {"gender": {"weights": {"female": 1.0}}}},
        "activation_layer": {"weights": {"liquid": 1.0}},
    }
    monkeypatch.setattr(
        type(orchestrator.settings),
        "load_population_mix_config",
        lambda _self: active_config,
    )
    generate_population = AsyncMock(side_effect=_fake_population)
    monkeypatch.setattr(orchestrator, "generate_population", generate_population)

    first_id, _ = await orchestrator._get_or_create_population(
        db_session,
        population_id=None,
        count=100,
    )
    active_config = {
        "population": {"demographics": {"gender": {"weights": {"male": 1.0}}}},
        "activation_layer": {"weights": {"liquid": 1.0}},
    }
    second_id, _ = await orchestrator._get_or_create_population(
        db_session,
        population_id=None,
        count=100,
    )

    assert second_id != first_id
    assert await _population_count(db_session) == 2
    assert generate_population.await_count == 2


@pytest.mark.asyncio
async def test_incomplete_generated_population_is_not_persisted(
    db_session,
    monkeypatch,
):
    async def generate_too_few(
        population_id: str,
        count: int,
        seed: int | None = None,
    ) -> list[dict]:
        del seed
        return [_agent_payload(population_id, index) for index in range(count - 1)]

    monkeypatch.setattr(
        orchestrator,
        "generate_population",
        AsyncMock(side_effect=generate_too_few),
    )

    with pytest.raises(RuntimeError, match="Generated population size mismatch"):
        await orchestrator._get_or_create_population(
            db_session,
            population_id=None,
            count=100,
        )

    assert await _population_count(db_session) == 0


@pytest.mark.asyncio
async def test_concurrent_default_creation_joins_the_committed_winner(monkeypatch):
    losing_population_id = "losing-population"
    winner = ("winning-population", [_agent_payload("winning-population", 0)])
    session = MagicMock()
    session.commit = AsyncMock(
        side_effect=IntegrityError("INSERT populations", {}, RuntimeError("duplicate"))
    )
    session.rollback = AsyncMock()
    generate_population = AsyncMock(side_effect=_fake_population)
    find_reusable = AsyncMock(return_value=winner)
    monkeypatch.setattr(orchestrator, "generate_population", generate_population)
    monkeypatch.setattr(
        orchestrator,
        "_find_reusable_default_population",
        find_reusable,
    )

    result = await orchestrator._create_default_population(
        session,
        count=100,
        reuse_key="reuse-key",
        population_id=losing_population_id,
        generation_seed=123,
    )

    assert result == winner
    session.rollback.assert_awaited_once()
    find_reusable.assert_awaited_once_with(
        session,
        count=100,
        reuse_key="reuse-key",
    )


@pytest.mark.asyncio
async def test_concurrent_creation_error_is_not_hidden_without_a_winner(monkeypatch):
    session = MagicMock()
    session.commit = AsyncMock(
        side_effect=IntegrityError("INSERT populations", {}, RuntimeError("duplicate"))
    )
    session.rollback = AsyncMock()
    monkeypatch.setattr(
        orchestrator,
        "generate_population",
        AsyncMock(side_effect=_fake_population),
    )
    monkeypatch.setattr(
        orchestrator,
        "_find_reusable_default_population",
        AsyncMock(return_value=None),
    )

    with pytest.raises(IntegrityError):
        await orchestrator._create_default_population(
            session,
            count=100,
            reuse_key="reuse-key",
            population_id="losing-population",
            generation_seed=123,
        )

    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_explicit_population_id_takes_precedence_over_default(
    db_session,
    monkeypatch,
):
    explicit_id = "explicit-population"
    db_session.add(Population(
        id=explicit_id,
        agent_count=1,
        generation_params={"count": 1, "seed": 7},
        status="ready",
    ))
    db_session.add(AgentProfile(**_agent_payload(explicit_id, 0)))
    await db_session.commit()
    generate_population = AsyncMock(side_effect=_fake_population)
    monkeypatch.setattr(orchestrator, "generate_population", generate_population)

    resolved_id, agents = await orchestrator._get_or_create_population(
        db_session,
        population_id=explicit_id,
        count=100,
        seed=42,
    )

    assert resolved_id == explicit_id
    assert [agent["id"] for agent in agents] == [f"{explicit_id}-agent-0"]
    generate_population.assert_not_awaited()


@pytest.mark.asyncio
async def test_existing_social_network_is_reused_without_regeneration(
    db_session,
    monkeypatch,
):
    population_id = "population-with-network"
    agents = [_agent_payload(population_id, index) for index in range(2)]
    db_session.add(Population(id=population_id, agent_count=2, status="ready"))
    db_session.add_all([AgentProfile(**agent) for agent in agents])
    db_session.add(SocialEdge(
        id="existing-edge",
        population_id=population_id,
        agent_id=agents[0]["id"],
        target_id=agents[1]["id"],
        relation_type="friend",
        strength=0.8,
    ))
    await db_session.commit()
    generate_network = AsyncMock(return_value=[])
    monkeypatch.setattr(orchestrator, "generate_network", generate_network)

    await orchestrator._save_network(db_session, agents, population_id, seed=99)

    result = await db_session.execute(
        select(SocialEdge).where(SocialEdge.population_id == population_id)
    )
    edges = result.scalars().all()
    assert [edge.id for edge in edges] == ["existing-edge"]
    generate_network.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_social_network_is_generated_only_once(
    db_session,
    monkeypatch,
):
    population_id = "population-without-network"
    agents = [_agent_payload(population_id, index) for index in range(2)]
    db_session.add(Population(id=population_id, agent_count=2, status="ready"))
    db_session.add_all([AgentProfile(**agent) for agent in agents])
    await db_session.commit()
    generate_network = AsyncMock(return_value=[{
        "id": "generated-edge",
        "population_id": population_id,
        "agent_id": agents[0]["id"],
        "target_id": agents[1]["id"],
        "relation_type": "neighbor",
        "strength": 0.6,
    }])
    monkeypatch.setattr(orchestrator, "generate_network", generate_network)

    await orchestrator._save_network(db_session, agents, population_id, seed=11)
    await orchestrator._save_network(db_session, agents, population_id, seed=99)

    result = await db_session.execute(
        select(func.count()).select_from(SocialEdge).where(
            SocialEdge.population_id == population_id
        )
    )
    assert result.scalar() == 1
    generate_network.assert_awaited_once()
