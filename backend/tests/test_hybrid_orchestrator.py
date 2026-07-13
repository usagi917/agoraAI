"""Vertical integration tests for the hybrid activation workflow."""

from unittest.mock import AsyncMock, patch

import pytest

from src.app.services.society.hybrid_config import load_hybrid_inference_config
from src.app.services.society.hybrid_ensemble import HybridShrinkage
from src.app.services.society.hybrid_orchestrator import (
    run_hybrid_activation,
    run_hybrid_social_requery,
)


def _agents(count: int) -> list[dict]:
    return [
        {
            "id": f"agent-{index}",
            "agent_index": index,
            "demographics": {
                "age": 20 + index,
                "gender": "female" if index % 2 else "male",
                "region": f"region-{index % 3}",
                "occupation": "会社員",
            },
            "big_five": {},
            "values": {},
        }
        for index in range(count)
    ]


def _activation_result(agents: list[dict], provider: str, *, invert: bool = False) -> dict:
    responses = []
    for index, agent in enumerate(agents):
        stance = "賛成" if index % 2 == 0 else "反対"
        if invert and index < 4:
            stance = "反対" if stance == "賛成" else "賛成"
        responses.append(
            {
                "agent_id": agent["id"],
                "stance": stance,
                "confidence": 0.8,
                "reason": "理由",
                "concern": "懸念",
                "priority": "優先",
            }
        )
    counts = {"賛成": 0, "反対": 0}
    for response in responses:
        counts[response["stance"]] += 1
    total = len(responses) or 1
    return {
        "responses": responses,
        "aggregation": {
            "stance_distribution": {key: value / total for key, value in counts.items()},
            "total_respondents": len(responses),
        },
        "representatives": [],
        "usage": {
            "prompt_tokens": len(agents) * 100,
            "completion_tokens": len(agents) * 20,
            "total_tokens": len(agents) * 120,
            "by_provider": {provider: {"calls": len(agents), "total_tokens": len(agents) * 120}},
        },
    }


@pytest.mark.asyncio
async def test_hybrid_orchestrator_activates_all_and_bounds_gpt_calls() -> None:
    agents = _agents(20)
    config = load_hybrid_inference_config(
        {
            "enabled": True,
            "budget": {"hard_limit_usd": 0.85, "reserve_usd": 0.15, "shadow_stop_usd": 0.70},
            "population_activation": {
                "provider": "liquid",
                "target_count": 20,
                "max_tokens": 160,
                "chunk_size": 8,
                "max_concurrency": 2,
            },
            "gpt_shadow": {
                "provider": "openai_shadow",
                "sample_size": 6,
                "max_calls": 6,
                "max_tokens": 120,
                "estimated_input_tokens": 100,
                "estimated_output_tokens": 20,
            },
            "gpt_escalation": {
                "provider": "openai_escalation",
                "max_calls": 2,
                "max_tokens": 250,
                "estimated_input_tokens": 100,
                "estimated_output_tokens": 20,
            },
        }
    )
    providers_called: list[tuple[str, int]] = []
    persisted_stages: list[str] = []

    async def fake_run_activation(selected_agents: list[dict], _theme: str, **kwargs):
        provider = kwargs["provider_override"]
        providers_called.append((provider, len(selected_agents)))
        result = _activation_result(
            selected_agents,
            provider,
            invert=provider == "openai_shadow",
        )
        callback = kwargs.get("on_chunk")
        if callback:
            records = [
                {
                    "agent_id": response["agent_id"],
                    "agent_index": agent["agent_index"],
                    "provider": provider,
                    "model": provider,
                    "response": response,
                    "usage": {"provider": provider, "model": provider, "total_tokens": 120},
                }
                for agent, response in zip(selected_agents, result["responses"], strict=True)
            ]
            await callback(records, len(selected_agents), len(selected_agents))
        return result

    async def fake_persist(*_args, **kwargs):
        persisted_stages.append(kwargs["stage"])

    activation_mock = AsyncMock(side_effect=fake_run_activation)

    with (
        patch(
            "src.app.services.society.hybrid_orchestrator.run_activation",
            new=activation_mock,
        ),
        patch(
            "src.app.services.society.hybrid_orchestrator.load_completed_responses",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "src.app.services.society.hybrid_orchestrator.persist_activation_chunk",
            new=AsyncMock(side_effect=fake_persist),
        ),
        patch(
            "src.app.services.society.hybrid_orchestrator.load_learned_hybrid_shrinkage",
            new=AsyncMock(return_value=HybridShrinkage(0.25, 4, "validated_theme_history")),
        ),
    ):
        result = await run_hybrid_activation(
            AsyncMock(),
            simulation_id="sim-1",
            population_id="pop-1",
            agents=agents,
            theme="テーマ",
            seed=12,
            config=config,
            theme_category="politics",
        )

    assert providers_called[0] == ("liquid", 20)
    assert providers_called[1] == ("openai_shadow", 6)
    assert providers_called[2] == ("openai_escalation", 2)
    assert persisted_stages == ["local_initial", "gpt_shadow", "gpt_escalation"]
    assert result["aggregation"]["activated_count"] == 20
    assert result["aggregation"]["gpt_validated_count"] == 6
    assert result["aggregation"]["gpt_escalated_count"] == 2
    assert result["aggregation"]["hybrid_calibration"]["is_ground_truth"] is False
    assert result["aggregation"]["hybrid_calibration"]["shrinkage"] == 0.25
    assert result["aggregation"]["hybrid_calibration"]["shrinkage_sample_count"] == 4
    assert result["aggregation"]["api_cost_usd"] <= 0.85
    assert sum(result["aggregation"]["stance_distribution"].values()) == pytest.approx(1.0)
    assert activation_mock.await_args_list[0].kwargs["require_provider_ready"] is True
    assert activation_mock.await_args_list[1].kwargs["require_provider_ready"] is False
    assert activation_mock.await_args_list[0].kwargs["max_retries"] == 2
    assert activation_mock.await_args_list[1].kwargs["max_retries"] == 0
    assert activation_mock.await_args_list[2].kwargs["max_retries"] == 0


@pytest.mark.asyncio
async def test_hybrid_orchestrator_never_falls_back_local_failures_to_gpt() -> None:
    agents = _agents(5)
    config = load_hybrid_inference_config(
        {
            "population_activation": {"provider": "liquid", "target_count": 5},
            "gpt_shadow": {"provider": "openai_shadow", "sample_size": 5, "max_calls": 5},
            "gpt_escalation": {"provider": "openai_escalation", "max_calls": 2},
        }
    )
    local_failure = {
        "responses": [
            {"agent_id": agent["id"], "stance": "", "confidence": 0, "_failed": True}
            for agent in agents
        ],
        "aggregation": {"stance_distribution": {}, "total_respondents": 0},
        "representatives": [],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "by_provider": {}},
    }
    activation_mock = AsyncMock(return_value=local_failure)

    with (
        patch("src.app.services.society.hybrid_orchestrator.run_activation", new=activation_mock),
        patch(
            "src.app.services.society.hybrid_orchestrator.load_completed_responses",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "src.app.services.society.hybrid_orchestrator.persist_activation_chunk",
            new=AsyncMock(),
        ),
    ):
        result = await run_hybrid_activation(
            AsyncMock(),
            simulation_id="sim-2",
            population_id="pop-2",
            agents=agents,
            theme="テーマ",
            seed=1,
            config=config,
        )

    assert activation_mock.await_count == 1
    assert result["aggregation"]["gpt_validated_count"] == 0
    assert result["aggregation"]["hybrid_status"] == "local_activation_failed"


@pytest.mark.asyncio
async def test_gpt_shadow_outage_returns_uncorrected_liquid_distribution() -> None:
    agents = _agents(6)
    config = load_hybrid_inference_config(
        {
            "population_activation": {"provider": "liquid", "target_count": 6},
            "gpt_shadow": {"provider": "openai_shadow", "sample_size": 3, "max_calls": 3},
            "gpt_escalation": {"provider": "openai_escalation", "max_calls": 2},
        }
    )
    local_result = _activation_result(agents, "liquid")

    async def activation_side_effect(selected_agents: list[dict], _theme: str, **kwargs):
        if kwargs["provider_override"] == "liquid":
            return local_result
        return {
            "responses": [
                {"agent_id": agent["id"], "stance": "", "confidence": 0, "_failed": True}
                for agent in selected_agents
            ],
            "aggregation": {"stance_distribution": {}},
            "representatives": [],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

    activation = AsyncMock(side_effect=activation_side_effect)
    with (
        patch("src.app.services.society.hybrid_orchestrator.run_activation", new=activation),
        patch(
            "src.app.services.society.hybrid_orchestrator.load_completed_responses",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "src.app.services.society.hybrid_orchestrator.persist_activation_chunk",
            new=AsyncMock(),
        ),
    ):
        result = await run_hybrid_activation(
            AsyncMock(),
            simulation_id="sim-shadow-down",
            population_id="pop-shadow-down",
            agents=agents,
            theme="テーマ",
            seed=4,
            config=config,
        )

    assert activation.await_count == 2
    assert result["aggregation"]["hybrid_status"] == "local_only_gpt_unavailable"
    assert result["aggregation"]["gpt_validated_count"] == 0
    assert (
        result["aggregation"]["stance_distribution"]
        == local_result["aggregation"]["stance_distribution"]
    )


@pytest.mark.asyncio
async def test_social_requery_only_runs_changed_agents_with_hard_cap() -> None:
    agents = _agents(5)
    initial = _activation_result(agents, "liquid")["responses"]
    final_stances = [
        {
            "agent_id": agent["id"],
            "stance": "反対" if index in {0, 2, 4} else initial[index]["stance"],
        }
        for index, agent in enumerate(agents)
    ]
    config = load_hybrid_inference_config(
        {
            "population_activation": {"provider": "liquid", "max_tokens": 160},
            "social_requery_max": 2,
        }
    )
    stage_result = _activation_result(agents[:2], "liquid")

    with patch(
        "src.app.services.society.hybrid_orchestrator._run_checkpointed_stage",
        new=AsyncMock(return_value=stage_result),
    ) as stage:
        result = await run_hybrid_social_requery(
            AsyncMock(),
            simulation_id="sim-social",
            population_id="pop-social",
            agents=agents,
            initial_responses=initial,
            final_stances=final_stances,
            theme="テーマ",
            seed=9,
            config=config,
        )

    selected_agents = stage.await_args.kwargs["agents"]
    assert stage.await_args.kwargs["stage"] == "local_social"
    assert len(selected_agents) == 2
    assert {agent["id"] for agent in selected_agents}.issubset({"agent-0", "agent-2", "agent-4"})
    assert all(
        agent["social_context"]["initial_stance"]
        != agent["social_context"]["network_stance"]
        for agent in selected_agents
    )
    assert result["requeried_count"] == 2
    assert result["changed_count"] == 3


@pytest.mark.asyncio
async def test_social_requery_cap_preserves_unequal_changed_population_strata() -> None:
    agents = _agents(100)
    for index, agent in enumerate(agents):
        agent["demographics"].update(
            {
                "region": "large" if index < 90 else "small",
                "gender": "all",
                "age": 40,
            }
        )
    initial = [
        {"agent_id": agent["id"], "stance": "賛成", "confidence": 0.7}
        for agent in agents
    ]
    final_stances = [
        {"agent_id": agent["id"], "stance": "反対"}
        for agent in agents
    ]
    config = load_hybrid_inference_config(
        {
            "population_activation": {"provider": "liquid"},
            "social_requery_max": 10,
        }
    )
    stage_result = _activation_result(agents[:10], "liquid")

    with patch(
        "src.app.services.society.hybrid_orchestrator._run_checkpointed_stage",
        new=AsyncMock(return_value=stage_result),
    ) as stage:
        await run_hybrid_social_requery(
            AsyncMock(),
            simulation_id="sim-social-strata",
            population_id="pop-social-strata",
            agents=agents,
            initial_responses=initial,
            final_stances=final_stances,
            theme="テーマ",
            seed=4,
            config=config,
        )

    selected = stage.await_args.kwargs["agents"]
    regions = [agent["demographics"]["region"] for agent in selected]
    assert regions.count("large") == 9
    assert regions.count("small") == 1
