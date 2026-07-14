from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.app.services.phases import society_pulse
from src.app.services.phases.society_pulse import _run_population_propagation_phase
from src.app.services.society.population_propagation import (
    PopulationPropagationResult,
    PropagationRoundDelta,
)


def _agent(agent_id: str, index: int) -> dict:
    return {
        "id": agent_id,
        "agent_index": index,
        "speech_style": "率直で簡潔",
        "life_event": "",
        "big_five": {},
        "demographics": {"age": 35, "occupation": "会社員"},
    }


def _delta(changes: list[dict]) -> PropagationRoundDelta:
    return PropagationRoundDelta(
        round=1, changes=changes, changed_count=len(changes), distribution={"賛成": 1.0}, max_delta=0.1
    )


def _change(agent_id: str, index: int) -> dict:
    return {"agent_index": index, "agent_id": agent_id, "stance": "賛成", "opinion": 0.9}


def _result(delta: PropagationRoundDelta) -> PopulationPropagationResult:
    return PopulationPropagationResult([], {"賛成": 1.0}, 1, True, [delta])


def _session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


async def _run_with_delta(delta: PropagationRoundDelta, **kwargs):
    callback = kwargs["on_round"]
    await callback(delta)
    return _result(delta)


async def _invoke(delta: PropagationRoundDelta, selected_agents: list[dict] | None = None):
    agents = [_agent("selected", 0), _agent("mass", 1)]
    session = _session()

    async def fake_propagation(*args, **kwargs):
        return await _run_with_delta(delta, **kwargs)

    with patch.object(society_pulse, "sse_manager") as sse, patch.object(
        society_pulse,
        "run_population_propagation",
        new=AsyncMock(side_effect=fake_propagation),
    ):
        sse.publish = AsyncMock()
        await _run_population_propagation_phase(
            simulation_id="sim", pop_id="pop", agents=agents,
            selected_agents=selected_agents or [_agent("selected", 0)],
            individual_responses=[], all_edges=[], aggregation={}, session=session,
            seed=9, propagation_cfg={"enabled": True, "max_timesteps": 2, "confidence_threshold": 0.5},
        )
    return sse.publish.await_args_list, session


@pytest.mark.asyncio
async def test_publishes_population_voice_after_round_event():
    calls, _ = await _invoke(_delta([_change("mass", 1)]))
    events = [call.args[1] for call in calls]

    assert events.index("population_propagation_round") < events.index("population_voice")
    payload = next(call.args[2] for call in calls if call.args[1] == "population_voice")
    assert payload["round"] == 1
    assert set(payload["voices"][0]) == {
        "agent_id", "agent_index", "comment", "stance", "prev_stance", "occupation", "age_bracket"
    }


@pytest.mark.asyncio
async def test_selected_agents_are_excluded_from_voices():
    calls, _ = await _invoke(_delta([_change("selected", 0), _change("mass", 1)]))
    payload = next(call.args[2] for call in calls if call.args[1] == "population_voice")

    assert [voice["agent_id"] for voice in payload["voices"]] == ["mass"]


@pytest.mark.asyncio
async def test_voice_failure_does_not_interrupt_propagation_or_persistence():
    delta = _delta([_change("mass", 1)])
    with patch.object(society_pulse, "generate_population_voices", side_effect=RuntimeError("voice boom")):
        calls, session = await _invoke(delta)
    events = [call.args[1] for call in calls]

    assert "population_propagation_round" in events
    assert "population_propagation_completed" in events
    assert "population_voice" not in events
    session.add.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_changes_does_not_publish_population_voice():
    calls, _ = await _invoke(_delta([]))

    assert "population_voice" not in [call.args[1] for call in calls]
