"""society_pulse の全人口伝播フェーズ (_run_population_propagation_phase) のテスト。

伝播の有効/無効・未活性化の大衆有無のガード、SSE 配信、population_propagation
レイヤーの永続化、そして失敗時に本流を止めない（警告のみ）挙動を検証する。
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.app.services.phases import society_pulse
from src.app.services.phases.society_pulse import _run_population_propagation_phase
from src.app.services.society.population_propagation import (
    PopulationPropagationResult,
    PropagationRoundDelta,
)


def _agents(n: int) -> list[dict]:
    return [{"id": f"a{i}", "agent_index": i, "big_five": {}} for i in range(n)]


def _fake_result() -> PopulationPropagationResult:
    return PopulationPropagationResult(
        final_stances=[],
        distribution={"賛成": 0.7, "反対": 0.3},
        total_rounds=2,
        converged=True,
        rounds=[
            PropagationRoundDelta(round=0, changes=[], changed_count=3, distribution={}, max_delta=0.1),
            PropagationRoundDelta(round=1, changes=[], changed_count=1, distribution={}, max_delta=0.02),
        ],
    )


def _cfg(enabled: bool = True) -> dict:
    return {"enabled": enabled, "max_timesteps": 8, "confidence_threshold": 0.5}


def _mock_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_persists_layer_and_publishes_events():
    """有効かつ未活性化の大衆が居れば、分布追記・レイヤー永続化・SSE配信を行う。"""
    session = _mock_session()
    aggregation: dict = {}

    with patch.object(society_pulse, "sse_manager") as sse, patch.object(
        society_pulse, "run_population_propagation", new=AsyncMock(return_value=_fake_result())
    ):
        sse.publish = AsyncMock()
        await _run_population_propagation_phase(
            simulation_id="sim-1",
            pop_id="pop-1",
            agents=_agents(10),
            selected_agents=_agents(3),
            individual_responses=[],
            all_edges=[],
            aggregation=aggregation,
            session=session,
            seed=42,
            propagation_cfg=_cfg(),
        )

    # aggregation に全人口分布が追記される
    assert aggregation["population_stance_distribution"] == {"賛成": 0.7, "反対": 0.3}
    # population_propagation レイヤーが永続化される
    added = session.add.call_args[0][0]
    assert added.layer == "population_propagation"
    assert added.simulation_id == "sim-1"
    assert added.phase_data["total_rounds"] == 2
    assert added.phase_data["changed_per_round"] == [3, 1]
    session.commit.assert_awaited()
    # started / completed SSE が配信される
    published = [call.args[1] for call in sse.publish.await_args_list]
    assert "population_propagation_started" in published
    assert "population_propagation_completed" in published


@pytest.mark.asyncio
async def test_skips_when_disabled():
    """伝播が無効なら何もしない（SSE も永続化もしない）。"""
    session = _mock_session()
    with patch.object(society_pulse, "sse_manager") as sse:
        sse.publish = AsyncMock()
        await _run_population_propagation_phase(
            simulation_id="s",
            pop_id="p",
            agents=_agents(10),
            selected_agents=_agents(3),
            individual_responses=[],
            all_edges=[],
            aggregation={},
            session=session,
            seed=None,
            propagation_cfg=_cfg(enabled=False),
        )
    session.add.assert_not_called()
    sse.publish.assert_not_called()


@pytest.mark.asyncio
async def test_runs_numeric_social_update_when_everyone_is_activated():
    """全員がLLM活性化済みでも、全人口の数値的な社会更新は実行する。"""
    session = _mock_session()
    propagation = AsyncMock(return_value=_fake_result())
    with patch.object(society_pulse, "sse_manager") as sse, patch.object(
        society_pulse, "run_population_propagation", new=propagation
    ):
        sse.publish = AsyncMock()
        result = await _run_population_propagation_phase(
            simulation_id="s",
            pop_id="p",
            agents=_agents(5),
            selected_agents=_agents(5),
            individual_responses=[],
            all_edges=[],
            aggregation={},
            session=session,
            seed=None,
            propagation_cfg=_cfg(),
        )
    propagation.assert_awaited_once()
    session.add.assert_called_once()
    assert result is not None
    assert result.distribution == {"賛成": 0.7, "反対": 0.3}


@pytest.mark.asyncio
async def test_caps_visual_graph_events_without_truncating_numeric_propagation():
    """1万人計算は維持しつつ、可視化イベントのDB増幅だけを抑える。"""
    session = _mock_session()
    changes = [
        {
            "agent_id": f"a{index}",
            "agent_index": index,
            "stance": "賛成",
        }
        for index in range(600)
    ]
    delta = PropagationRoundDelta(
        round=0,
        changes=changes,
        changed_count=len(changes),
        distribution={"賛成": 1.0},
        max_delta=0.2,
    )

    async def fake_propagation(*_args, **kwargs):
        await kwargs["on_round"](delta)
        return _fake_result()

    with (
        patch.object(society_pulse, "sse_manager") as sse,
        patch.object(
            society_pulse,
            "run_population_propagation",
            new=AsyncMock(side_effect=fake_propagation),
        ),
        patch.object(
            society_pulse,
            "propagation_changes_to_graph_events",
            return_value=[],
        ) as graph_events,
    ):
        sse.publish = AsyncMock()
        await _run_population_propagation_phase(
            simulation_id="s",
            pop_id="p",
            agents=_agents(600),
            selected_agents=_agents(600),
            individual_responses=[],
            all_edges=[],
            aggregation={},
            session=session,
            seed=None,
            propagation_cfg=_cfg(),
        )

    visual_changes = graph_events.call_args.args[0]
    assert len(visual_changes) == 500
    assert delta.changed_count == 600


@pytest.mark.asyncio
async def test_failure_is_swallowed_and_does_not_block():
    """伝播が失敗しても例外を送出せず、分布もレイヤーも残さない。"""
    session = _mock_session()
    aggregation: dict = {}

    with patch.object(society_pulse, "sse_manager") as sse, patch.object(
        society_pulse,
        "run_population_propagation",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        sse.publish = AsyncMock()
        # 例外を送出しないこと（本流を止めない）
        await _run_population_propagation_phase(
            simulation_id="s",
            pop_id="p",
            agents=_agents(10),
            selected_agents=_agents(3),
            individual_responses=[],
            all_edges=[],
            aggregation=aggregation,
            session=session,
            seed=None,
            propagation_cfg=_cfg(),
        )

    # 失敗時は分布が追記されず、レイヤーも永続化されない
    assert "population_stance_distribution" not in aggregation
    session.add.assert_not_called()
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_persistence_failure_rolls_back_and_does_not_mutate_aggregation():
    """レイヤー永続化に失敗したら rollback し、全人口分布も本流へ混ぜない。"""
    session = _mock_session()
    session.commit.side_effect = RuntimeError("commit failed")
    aggregation: dict = {}

    with patch.object(society_pulse, "sse_manager") as sse, patch.object(
        society_pulse, "run_population_propagation", new=AsyncMock(return_value=_fake_result())
    ):
        sse.publish = AsyncMock()
        await _run_population_propagation_phase(
            simulation_id="s",
            pop_id="p",
            agents=_agents(10),
            selected_agents=_agents(3),
            individual_responses=[],
            all_edges=[],
            aggregation=aggregation,
            session=session,
            seed=None,
            propagation_cfg=_cfg(),
        )

    session.add.assert_called_once()
    session.rollback.assert_awaited_once()
    assert "population_stance_distribution" not in aggregation
