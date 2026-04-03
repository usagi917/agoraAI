"""generate_agents seeds パス ユニットテスト"""
import logging
import uuid

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.factories import make_llm_response
from src.app.services.graphrag.stakeholder_mapper import StakeholderSeed
from src.app.services.agent_generator import generate_agents


def _seed(name="田中太郎", entity_type="person"):
    return StakeholderSeed(
        entity_id=str(uuid.uuid4()),
        name=name,
        entity_type=entity_type,
        goals_hint=["目標1"],
        relationships=[],
        community="community_0",
        description="説明",
    )


def _agent(seed: StakeholderSeed) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "name": seed.name,
        "role": "stakeholder",
        "source_entity_id": seed.entity_id,
        "goals": [],
    }


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seeds_happy_path(mock_session):
    seeds = [_seed(f"person_{i}") for i in range(8)]
    payload = {"agents": [_agent(s) for s in seeds]}

    with patch(
        "src.app.services.agent_generator.llm_client.call_with_retry",
        new=AsyncMock(return_value=make_llm_response(payload)),
    ), patch(
        "src.app.services.agent_generator.record_usage",
        new=AsyncMock(),
    ):
        result = await generate_agents(
            mock_session, "run-1", {}, "template", stakeholder_seeds=seeds,
        )

    assert len(result["agents"]) == 8
    returned_entity_ids = {a["source_entity_id"] for a in result["agents"]}
    assert returned_entity_ids == {s.entity_id for s in seeds}


@pytest.mark.asyncio
async def test_uuid_copy_instruction(mock_session):
    seeds = [_seed()]
    payload = {"agents": [_agent(seeds[0])]}
    captured: dict = {}

    async def capture(*args, **kwargs):
        captured.update(kwargs)
        return make_llm_response(payload)

    with patch(
        "src.app.services.agent_generator.llm_client.call_with_retry",
        new=capture,
    ), patch(
        "src.app.services.agent_generator.record_usage",
        new=AsyncMock(),
    ):
        await generate_agents(
            mock_session, "run-1", {}, "template", stakeholder_seeds=seeds,
        )

    system_prompt = captured.get("system_prompt", "")
    user_prompt = captured.get("user_prompt", "")
    instruction = "source_entity_id は提供されたシードの entity_id UUID を一字一句そのままコピーすること"
    assert instruction in system_prompt or instruction in user_prompt


@pytest.mark.asyncio
async def test_wrong_uuid_excluded(mock_session, caplog):
    seed = _seed()
    bad_agent = {
        "id": str(uuid.uuid4()),
        "name": "bad agent",
        "role": "stakeholder",
        "source_entity_id": str(uuid.uuid4()),  # NOT in seed_ids
        "goals": [],
    }
    payload = {"agents": [bad_agent, _agent(seed)]}

    with patch(
        "src.app.services.agent_generator.llm_client.call_with_retry",
        new=AsyncMock(return_value=make_llm_response(payload)),
    ), patch(
        "src.app.services.agent_generator.record_usage",
        new=AsyncMock(),
    ):
        with caplog.at_level(logging.WARNING):
            result = await generate_agents(
                mock_session, "run-1", {}, "template", stakeholder_seeds=[seed],
            )

    assert len(result["agents"]) == 1
    assert result["agents"][0]["source_entity_id"] == seed.entity_id
    assert any(r.levelno >= logging.WARNING for r in caplog.records)


@pytest.mark.asyncio
async def test_all_excluded_fallback(mock_session):
    seeds = [_seed()]
    bad_payload = {"agents": [
        {"id": str(uuid.uuid4()), "name": "bad", "role": "r",
         "source_entity_id": str(uuid.uuid4()), "goals": []},
    ]}
    generic_payload = {"agents": [
        {"id": str(uuid.uuid4()), "name": "generic", "role": "r", "goals": []},
    ]}

    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return make_llm_response(bad_payload if call_count == 1 else generic_payload)

    with patch(
        "src.app.services.agent_generator.llm_client.call_with_retry",
        new=side_effect,
    ), patch(
        "src.app.services.agent_generator.record_usage",
        new=AsyncMock(),
    ):
        result = await generate_agents(
            mock_session, "run-1",
            {"entities": [], "relations": [], "world_summary": ""},
            "template", stakeholder_seeds=seeds,
        )

    assert call_count == 2
    assert result["agents"][0]["name"] == "generic"


@pytest.mark.asyncio
async def test_more_than_seeds(mock_session):
    seeds = [_seed(f"p{i}") for i in range(8)]
    valid_agents = [_agent(s) for s in seeds]
    excess = [
        {"id": str(uuid.uuid4()), "name": f"excess_{i}", "role": "r",
         "source_entity_id": str(uuid.uuid4()), "goals": []}
        for i in range(2)
    ]
    payload = {"agents": valid_agents + excess}

    with patch(
        "src.app.services.agent_generator.llm_client.call_with_retry",
        new=AsyncMock(return_value=make_llm_response(payload)),
    ), patch(
        "src.app.services.agent_generator.record_usage",
        new=AsyncMock(),
    ):
        result = await generate_agents(
            mock_session, "run-1", {}, "template", stakeholder_seeds=seeds,
        )

    assert len(result["agents"]) == 8


@pytest.mark.asyncio
async def test_backward_compat_none(mock_session):
    """seeds=None → generic path, result unchanged"""
    generic_payload = {"agents": [{"id": "a1", "name": "Generic", "role": "r", "goals": []}]}

    with patch(
        "src.app.services.agent_generator.llm_client.call_with_retry",
        new=AsyncMock(return_value=make_llm_response(generic_payload)),
    ), patch(
        "src.app.services.agent_generator.record_usage",
        new=AsyncMock(),
    ):
        result = await generate_agents(
            mock_session, "run-1",
            {"entities": [], "relations": [], "world_summary": ""},
            "template", stakeholder_seeds=None,
        )

    assert result["agents"][0]["name"] == "Generic"


@pytest.mark.asyncio
async def test_backward_compat_empty(mock_session):
    """seeds=[] (falsy) → generic path"""
    generic_payload = {"agents": [{"id": "a1", "name": "Generic", "role": "r", "goals": []}]}

    with patch(
        "src.app.services.agent_generator.llm_client.call_with_retry",
        new=AsyncMock(return_value=make_llm_response(generic_payload)),
    ), patch(
        "src.app.services.agent_generator.record_usage",
        new=AsyncMock(),
    ):
        result = await generate_agents(
            mock_session, "run-1",
            {"entities": [], "relations": [], "world_summary": ""},
            "template", stakeholder_seeds=[],
        )

    assert result["agents"][0]["name"] == "Generic"
