from src.app.services.society.backtest import (
    overlay_observed_intervention_comparison,
    run_backtest_analysis,
)
from src.app.services.society.issue_miner import build_intervention_comparison


def _society_first_payload() -> dict:
    return {
        "selected_issues": [
            {
                "issue_id": "issue-1",
                "label": "価格受容性",
                "description": "",
                "selection_score": 0.82,
            },
            {
                "issue_id": "issue-2",
                "label": "規制対応",
                "description": "",
                "selection_score": 0.71,
            },
        ],
        "issue_colonies": [
            {
                "issue_id": "issue-1",
                "label": "価格受容性",
                "top_scenarios": [
                    {"description": "価格障壁で導入が遅れる", "scenario_score": 0.73},
                    {"description": "値下げで試験導入が増える", "scenario_score": 0.58},
                ],
            },
            {
                "issue_id": "issue-2",
                "label": "規制対応",
                "top_scenarios": [
                    {"description": "制度整合で採用が回復する", "scenario_score": 0.63},
                ],
            },
        ],
    }


def test_run_backtest_analysis_matches_predicted_issue_scenarios():
    payload = _society_first_payload()
    backtest = run_backtest_analysis(
        payload,
        [
            {
                "title": "2025 関西ローンチ",
                "observed_at": "2025-10-01",
                "outcome": {
                    "issue_label": "価格受容性",
                    "summary": "価格改定後も本格導入は遅れた",
                    "actual_scenario": "価格障壁で導入が遅れる",
                    "tags": ["価格", "導入"],
                },
                "interventions": [],
            }
        ],
    )

    assert backtest["status"] == "ready"
    assert backtest["summary"]["case_count"] == 1
    assert backtest["summary"]["hit_count"] == 1
    assert backtest["cases"][0]["best_match"]["issue_label"] == "価格受容性"
    assert backtest["cases"][0]["best_match"]["verdict"] == "hit"


def test_overlay_observed_intervention_comparison_uses_backtest_deltas():
    payload = _society_first_payload()
    comparisons = build_intervention_comparison(
        payload["selected_issues"],
        payload["issue_colonies"],
    )
    backtest = run_backtest_analysis(
        payload,
        [
            {
                "title": "2025 関西ローンチ",
                "observed_at": "2025-10-01",
                "baseline_metrics": {
                    "adoption_rate": 0.18,
                    "conversion_rate": 0.09,
                },
                "outcome": {
                    "issue_label": "価格受容性",
                    "summary": "価格改定後に試験導入が増えた",
                    "actual_scenario": "価格障壁で導入が遅れる",
                    "metrics": {
                        "adoption_rate": 0.27,
                        "conversion_rate": 0.13,
                    },
                    "tags": ["価格", "導入"],
                },
                "interventions": [
                    {
                        "intervention_id": "price_reduction",
                        "label": "価格変更",
                        "baseline_metrics": {
                            "adoption_rate": 0.18,
                            "conversion_rate": 0.09,
                        },
                        "outcome_metrics": {
                            "adoption_rate": 0.27,
                            "conversion_rate": 0.13,
                        },
                        "evidence": ["採用率が改善した"],
                    }
                ],
            }
        ],
    )

    observed = overlay_observed_intervention_comparison(comparisons, backtest)
    price_change = next(item for item in observed if item["intervention_id"] == "price_reduction")

    assert price_change["comparison_mode"] == "observed"
    assert price_change["observed_uplift"] > 0
    assert price_change["observed_case_count"] == 1
    assert price_change["supporting_evidence"]
