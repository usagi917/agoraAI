"""CognitiveAgent SSE イベント発行テスト"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_sse():
    """SSE manager の publish をモックする。"""
    with patch("src.app.services.cognition.cognitive_agent.sse_manager") as mock:
        mock.publish = AsyncMock()
        yield mock


@pytest.fixture
def _mock_deps():
    """CognitiveAgent 依存をモック（LLM 不要）。"""
    with patch("src.app.services.cognition.deliberation.llm_client") as llm_d, \
         patch("src.app.services.cognition.action_executor.llm_client") as llm_a, \
         patch("src.app.services.cognition.perception.llm_client") as llm_p, \
         patch("src.app.services.memory.agent_memory.llm_client") as llm_m, \
         patch("src.app.services.memory.reflection.llm_client") as llm_r, \
         patch("src.app.services.cost_tracker.record_usage", new_callable=AsyncMock):
        llm_m.call = AsyncMock(return_value=(
            {"importance": 0.5},
            {"total_tokens": 5},
        ))
        llm_m.call_with_retry = AsyncMock(return_value=(
            {"importance": 0.5},
            {"total_tokens": 5},
        ))
        llm_r.call_with_retry = AsyncMock(return_value=(
            {"reflections": []},
            {"total_tokens": 5},
        ))
        llm_d.call_with_retry = AsyncMock(return_value=(
            {
                "reasoning_chain": "テスト推論",
                "chosen_action": "情報収集",
                "expected_outcomes": ["知識増加"],
                "commitment_strength": 0.8,
                "belief_updates": [],
                "communication_intents": [
                    {"type": "say", "target_ids": ["agent_2"], "content": "hello"}
                ],
            },
            {"total_tokens": 50},
        ))
        llm_a.call_with_retry = AsyncMock(return_value=(
            {
                "action_description": "情報を収集した",
                "impact": "知識が増加",
                "entity_updates": [],
                "relation_updates": [],
            },
            {"total_tokens": 30},
        ))
        llm_p.call_with_retry = AsyncMock(return_value=(
            {"salient_entities": [], "potential_threats": [], "opportunities": []},
            {"total_tokens": 20},
        ))
        yield


def _make_agent(run_id: str = "run_1"):
    """テスト用 CognitiveAgent を生成する。"""
    profile = {
        "id": "agent_1",
        "name": "テストエージェント",
        "role": "researcher",
        "entity_id": "entity_1",
        "goals": ["情報収集"],
        "relationships": [],
    }
    with patch("src.app.services.cognition.cognitive_agent.settings") as mock_settings:
        mock_settings.load_cognitive_config.return_value = {
            "cognitive": {
                "bdi": {},
                "perception": {},
                "memory": {"capacity": 100, "reflection_threshold": 5},
                "tom": {"enabled": False},
            },
        }
        from src.app.services.cognition.cognitive_agent import CognitiveAgent
        return CognitiveAgent(run_id=run_id, agent_profile=profile)


@pytest.mark.asyncio
async def test_save_state_publishes_agent_state_updated(db_session, mock_sse, _mock_deps):
    """_save_state() 完了後に agent_state_updated SSE が発行される。"""
    agent = _make_agent("run_test")

    # 最小限の run_cognitive_cycle
    result = await agent.run_cognitive_cycle(
        session=db_session,
        world_state={"entities": [], "relations": []},
        recent_events=[],
        round_number=1,
    )

    # SSE publish が呼ばれたことを検証
    calls = mock_sse.publish.call_args_list
    state_updated_calls = [
        c for c in calls if c.args[1] == "agent_state_updated"
    ]
    assert len(state_updated_calls) >= 1, "agent_state_updated が発行されるべき"

    payload = state_updated_calls[0].args[2]
    assert payload["agent_id"] == "agent_1"
    assert payload["agent_name"] == "テストエージェント"
    assert payload["round"] == 1
    assert "beliefs" in payload
    assert "desires" in payload
    assert "intentions" in payload
    assert "reasoning_chain" in payload
    assert "trust_map" in payload


@pytest.mark.asyncio
async def test_agent_state_updated_contains_communication_intents(db_session, mock_sse, _mock_deps):
    """agent_state_updated ペイロードに communication_intents が含まれる。"""
    agent = _make_agent("run_test")

    await agent.run_cognitive_cycle(
        session=db_session,
        world_state={"entities": [], "relations": []},
        recent_events=[],
        round_number=1,
    )

    calls = mock_sse.publish.call_args_list
    state_updated_calls = [
        c for c in calls if c.args[1] == "agent_state_updated"
    ]
    assert len(state_updated_calls) >= 1
    payload = state_updated_calls[0].args[2]
    assert "communication_intents" in payload
