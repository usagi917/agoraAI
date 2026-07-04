import pytest

from src.app.evaluation.diagnostic import (
    DiagnosticConfig,
    aggregate_results,
    bootstrap_ci,
    build_trial_plan,
    condition_definitions,
    estimate_dry_run,
    evaluate_prediction,
    load_eval_cases,
    run_trial_with_retry,
)
from src.app.services.society.diagnostic_baseline import (
    UNIFORM_DISTRIBUTION,
    normalize_llm_distribution_payload,
)


def test_evaluate_prediction_adds_emd_and_known_zero_metrics():
    distribution = {
        "賛成": 0.2,
        "条件付き賛成": 0.2,
        "中立": 0.2,
        "条件付き反対": 0.2,
        "反対": 0.2,
    }

    metrics = evaluate_prediction(distribution, distribution)

    assert metrics["jsd"] == pytest.approx(0.0)
    assert metrics["emd"] == pytest.approx(0.0)
    assert metrics["brier"] == pytest.approx(0.0)


def test_bootstrap_ci_shape():
    low, high = bootstrap_ci([0.1, 0.2, 0.3], iterations=100, seed=42)

    assert 0.1 <= low <= high <= 0.3


def test_aggregate_results_marks_partial_and_summarizes():
    rows = [
        {
            "condition_id": "0",
            "survey_id": "s1",
            "theme": "t",
            "jsd": 0.1,
            "emd": 0.2,
            "brier": 0.03,
            "ece": 0.04,
        },
        {
            "condition_id": "0",
            "survey_id": "s1",
            "theme": "t",
            "jsd": 0.3,
            "emd": 0.4,
            "brier": 0.05,
            "ece": 0.06,
        },
        {
            "partial": True,
            "condition_id": "2",
            "survey_id": "s1",
            "theme": "t",
            "error": "boom",
        },
    ]

    result = aggregate_results(rows)

    assert result["status"] == "partial"
    assert result["by_condition"]["0"]["mean_jsd"] == pytest.approx(0.2)
    assert len(result["partial_failures"]) == 1


def test_load_eval_cases_uses_manifest_holdout_only():
    cases = load_eval_cases("economy")

    survey_ids = {case["survey_id"] for case in cases}
    assert "boj_living_2024_economy_景況感" not in survey_ids
    assert "boj_living_2024_economy_金利政策" in survey_ids
    assert len(cases) >= 4
    assert any(case["source_origin"] == "cross_source" for case in cases)


def test_dry_run_counts_simulation_calls():
    estimate = estimate_dry_run(
        DiagnosticConfig(
            preset="economy",
            runs=2,
            seeds=(42, 43),
            conditions=("0", "1", "2"),
            dry_run=True,
        )
    )

    assert estimate["eval_cases"] >= 4
    assert estimate["single_llm_calls"] == 13
    assert estimate["simulation_runs"] == 13


def test_trial_plan_uses_screening_runs_for_cross_source_cases():
    config = DiagnosticConfig(
        preset="economy",
        runs=2,
        seeds=(42, 43),
        conditions=("2",),
    )
    cases = load_eval_cases("economy")
    conditions = [condition_definitions("economy")["2"]]

    plan = build_trial_plan(config, conditions, cases)

    same_source = [item for item in plan if item[1]["source_origin"] == "same_source_as_train"]
    cross_source = [item for item in plan if item[1]["source_origin"] == "cross_source"]
    assert len(same_source) == 4
    assert len(cross_source) == 9


def test_single_llm_payload_normalizes_missing_keys():
    result = normalize_llm_distribution_payload({"賛成": 2, "反対": 1})

    assert result["賛成"] == pytest.approx(2 / 3)
    assert result["反対"] == pytest.approx(1 / 3)
    assert result["中立"] == pytest.approx(0.0)


def test_single_llm_invalid_json_falls_back_to_uniform():
    result = normalize_llm_distribution_payload("{not json")

    assert result == UNIFORM_DISTRIBUTION


@pytest.mark.asyncio
async def test_retry_marks_partial_after_two_failures():
    condition = condition_definitions("economy")["1"]
    case = {
        "survey_id": "eval-1",
        "theme": "金利政策",
        "source": "source",
        "actual_distribution": UNIFORM_DISTRIBUTION,
    }

    async def failing_llm(_theme: str, _seed: int):
        raise RuntimeError("provider down")

    row = await run_trial_with_retry(
        condition,
        case,
        42,
        0,
        preset="economy",
        single_llm_fn=failing_llm,
    )

    assert row["partial"] is True
    assert "provider down" in row["error"]


@pytest.mark.asyncio
async def test_leakage_exception_is_retried_then_partial():
    condition = condition_definitions("economy")["0"]
    case = {
        "survey_id": "boj_living_2024_economy_景況感",
        "theme": "景況感",
        "source": "source",
        "actual_distribution": UNIFORM_DISTRIBUTION,
    }

    row = await run_trial_with_retry(condition, case, 42, 0, preset="economy")

    assert row["partial"] is True
    assert "Survey leakage" in row["error"]
