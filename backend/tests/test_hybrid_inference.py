"""Hybrid Liquid + GPT inference policy tests."""

import pytest

from src.app.config import settings
from src.app.services.society.hybrid_budget import (
    BudgetExceededError,
    HybridBudgetGuard,
    estimate_token_cost,
)
from src.app.services.society.hybrid_calibration import (
    apply_distribution_residual,
    correct_distribution_with_shadow,
    select_escalation_pairs,
)
from src.app.services.society.hybrid_config import load_hybrid_inference_config
from src.app.services.society.hybrid_sampling import select_shadow_pairs


def _agent(index: int) -> dict:
    return {
        "id": f"agent-{index}",
        "agent_index": index,
        "demographics": {
            "age": 20 + index % 70,
            "gender": "female" if index % 2 else "male",
            "region": f"region-{index % 5}",
        },
    }


def _response(index: int) -> dict:
    stances = ["賛成", "反対", "条件付き賛成", "条件付き反対", "中立"]
    return {"stance": stances[index % len(stances)], "confidence": 0.5 + (index % 4) * 0.1}


def test_load_hybrid_config_enforces_one_dollar_run_policy() -> None:
    config = load_hybrid_inference_config(
        {
            "enabled": True,
            "budget": {"hard_limit_usd": 0.85, "reserve_usd": 0.15, "shadow_stop_usd": 0.70},
            "population_activation": {
                "provider": "liquid",
                "target_count": 10_000,
                "chunk_size": 128,
                "max_concurrency": 2,
                "max_tokens": 160,
            },
            "gpt_shadow": {"provider": "openai_shadow", "sample_size": 800, "max_calls": 1_000},
            "gpt_escalation": {"provider": "openai_escalation", "max_calls": 40},
        }
    )

    assert config.population_activation.target_count == 10_000
    assert config.population_activation.provider == "liquid"
    assert config.gpt_shadow.sample_size == 800
    assert config.gpt_escalation.max_calls == 40
    assert config.budget.total_envelope_usd == pytest.approx(1.0)


def test_repository_runtime_is_openai_only_and_keeps_paid_activation_bounded() -> None:
    config = load_hybrid_inference_config()
    providers_config = settings.load_llm_providers_config()
    providers = providers_config["providers"]

    assert config.enabled is False
    assert config.population_activation.provider == "openai"
    assert config.population_activation.target_count == 200
    assert config.population_activation.max_concurrency == 20
    assert config.population_activation.chunk_size == 25
    assert config.population_activation.minimal_output is False
    assert config.gpt_shadow.provider == "openai_shadow"
    assert config.gpt_shadow.sample_size == 800
    assert config.gpt_shadow.estimated_output_tokens >= 384
    assert config.gpt_escalation.provider == "openai_escalation"
    assert config.gpt_escalation.max_calls == 40
    assert config.gpt_escalation.estimated_output_tokens >= 512
    assert set(providers) == {"openai", "openai_shadow", "openai_escalation"}
    assert {provider["type"] for provider in providers.values()} == {"openai"}
    assert {
        provider["api_base"] for provider in providers.values()
    } == {"https://api.openai.com/v1"}
    assert providers_config["fallback_order"] == ["openai"]


def test_hybrid_budget_guard_stops_shadow_before_reserve() -> None:
    guard = HybridBudgetGuard(hard_limit_usd=0.85, reserve_usd=0.15, shadow_stop_usd=0.70)
    guard.record_cost("shadow", 0.69)

    assert guard.can_schedule("shadow", 0.009)
    assert not guard.can_schedule("shadow", 0.02)
    assert guard.can_schedule("synthesis", 0.10)
    with pytest.raises(BudgetExceededError):
        guard.reserve("shadow", 0.02)


def test_repository_worst_case_token_caps_fit_one_dollar_envelope() -> None:
    config = load_hybrid_inference_config()
    providers = settings.load_llm_providers_config()["providers"]

    def role_cost(role, count: int, output_tokens: int) -> float:
        provider = providers[role.provider]
        return count * estimate_token_cost(
            input_tokens=role.estimated_input_tokens,
            output_tokens=output_tokens,
            input_per_million_usd=provider["cost_per_1k_input"] * 1_000,
            output_per_million_usd=provider["cost_per_1k_output"] * 1_000,
        )

    shadow_cost = role_cost(config.gpt_shadow, config.gpt_shadow.sample_size, 384)
    escalation_cost = role_cost(config.gpt_escalation, config.gpt_escalation.max_calls, 512)

    assert shadow_cost <= config.budget.shadow_stop_usd
    assert shadow_cost + escalation_cost <= config.budget.hard_limit_usd
    assert shadow_cost + escalation_cost + config.budget.reserve_usd <= 1.0


def test_shadow_sampling_is_deterministic_stratified_and_bounded() -> None:
    agents = [_agent(i) for i in range(10_000)]
    responses = [_response(i) for i in range(10_000)]

    first = select_shadow_pairs(agents, responses, sample_size=800, seed=17)
    second = select_shadow_pairs(agents, responses, sample_size=800, seed=17)

    assert len(first) == 800
    assert [pair[0]["id"] for pair in first] == [pair[0]["id"] for pair in second]
    assert len({pair[1]["stance"] for pair in first}) == 5
    assert len({pair[0]["demographics"]["region"] for pair in first}) == 5


def test_shadow_sampling_preserves_population_weight_of_unequal_strata() -> None:
    agents = [_agent(index) for index in range(1_000)]
    for index, agent in enumerate(agents):
        agent["demographics"].update(
            {
                "region": "large" if index < 900 else "small",
                "gender": "all",
                "age": 40,
            }
        )
    responses = [{"stance": "賛成", "confidence": 0.7} for _ in agents]

    sample = select_shadow_pairs(agents, responses, sample_size=100, seed=3)
    regions = [pair[0]["demographics"]["region"] for pair in sample]

    assert regions.count("large") == 90
    assert regions.count("small") == 10


def test_shadow_correction_applies_paired_residual_without_calling_it_ground_truth() -> None:
    local_distribution = {"賛成": 0.7, "反対": 0.3}
    local = [
        {"stance": "賛成", "confidence": 0.8},
        {"stance": "賛成", "confidence": 0.7},
        {"stance": "反対", "confidence": 0.8},
        {"stance": "反対", "confidence": 0.7},
    ]
    shadow = [
        {"stance": "賛成", "confidence": 0.8},
        {"stance": "反対", "confidence": 0.7},
        {"stance": "反対", "confidence": 0.8},
        {"stance": "反対", "confidence": 0.7},
    ]

    corrected, diagnostics = correct_distribution_with_shadow(local_distribution, local, shadow)

    assert sum(corrected.values()) == pytest.approx(1.0)
    assert corrected["賛成"] < local_distribution["賛成"]
    assert diagnostics["method"] == "paired_model_residual"
    assert diagnostics["is_ground_truth"] is False


def test_residual_can_be_reapplied_after_social_dynamics_without_losing_normalization() -> None:
    corrected = apply_distribution_residual(
        {"賛成": 0.5, "反対": 0.5},
        {"賛成": -0.2, "反対": 0.2},
        shrinkage=0.5,
    )

    assert sum(corrected.values()) == pytest.approx(1.0)
    assert corrected["賛成"] == pytest.approx(0.4)
    assert corrected["反対"] == pytest.approx(0.6)


def test_shadow_failures_are_removed_as_pairs_instead_of_becoming_model_bias() -> None:
    base = {"賛成": 0.5, "反対": 0.5}
    local = [
        {"stance": "賛成", "confidence": 0.8},
        {"stance": "反対", "confidence": 0.8},
    ]
    shadow = [
        {"stance": "", "confidence": 0.0, "_failed": True},
        {"stance": "反対", "confidence": 0.8},
    ]

    corrected, diagnostics = correct_distribution_with_shadow(base, local, shadow)

    assert corrected["賛成"] == pytest.approx(0.5)
    assert corrected["反対"] == pytest.approx(0.5)
    assert diagnostics["paired_count"] == 1


def test_escalation_prioritizes_stance_disagreement_and_caps_calls() -> None:
    local = [{"agent_id": f"a-{i}", "stance": "賛成", "confidence": 0.9} for i in range(100)]
    shadow = [
        {"agent_id": f"a-{i}", "stance": "反対" if i < 60 else "賛成", "confidence": 0.9}
        for i in range(100)
    ]

    selected = select_escalation_pairs(local, shadow, max_calls=40)

    assert len(selected) == 40
    assert all(pair[0]["stance"] != pair[1]["stance"] for pair in selected)
