from src.app.services.meta_score import (
    compute_objective_score,
    evaluate_stop_condition,
)


def test_compute_objective_score_combines_society_swarm_and_pm():
    result = compute_objective_score(
        {
            "aggregation": {"average_confidence": 0.75},
            "evaluation": {"consistency": 0.7, "calibration": 0.65},
        },
        [
            {
                "label": "価格受容性",
                "top_scenarios": [{"scenario_score": 0.8}],
            }
        ],
        [{"label": "価格受容性", "selection_score": 0.82}],
        {"overall_confidence": 0.78},
    )

    assert result["society_score"] > 0.0
    assert result["swarm_score"] == 0.8
    assert result["pm_score"] == 0.78
    assert result["objective_score"] > 0.0


def test_evaluate_stop_condition_stops_on_target():
    result = evaluate_stop_condition([0.61, 0.79])
    assert result["should_stop"] is True
    assert result["reason"] == "target_reached"


def test_evaluate_stop_condition_stops_on_plateau():
    result = evaluate_stop_condition([0.61, 0.62, 0.625])
    assert result["should_stop"] is True
    assert result["reason"] == "plateau"
