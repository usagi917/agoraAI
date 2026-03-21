from src.app.services.verification import (
    merge_verification_results,
    verify_pm_board_result,
    verify_report_content,
    verify_scenarios,
    verify_world_build_result,
)


def test_verify_world_build_result_passes_for_connected_world():
    verification = verify_world_build_result(
        {
            "entities": [
                {"id": "e1", "label": "A"},
                {"id": "e2", "label": "B"},
            ],
            "relations": [
                {"source": "e1", "target": "e2", "relation_type": "cooperation"},
            ],
            "timeline": [{"event": "launch"}],
            "world_summary": "connected world",
        }
    )

    assert verification["status"] == "passed"
    assert verification["metrics"]["entity_count"] == 2


def test_verify_world_build_result_fails_when_entities_missing():
    verification = verify_world_build_result(
        {
            "entities": [],
            "relations": [],
            "timeline": [],
            "world_summary": "",
        }
    )

    assert verification["status"] == "failed"
    assert "no_entities" in verification["issues"]


def test_verify_scenarios_detects_invalid_probability():
    verification = verify_scenarios(
        [{"description": "bad", "probability": 1.2}]
    )

    assert verification["status"] == "failed"
    assert "scenario_probability_out_of_range" in verification["issues"]


def test_verify_pm_board_result_requires_core_sections():
    verification = verify_pm_board_result(
        {
            "sections": {
                "core_question": "Should we launch?",
                "assumptions": [],
                "uncertainties": [],
                "risks": [],
                "winning_hypothesis": {"if_true": "x"},
                "customer_validation_plan": {},
                "market_view": {},
                "gtm_hypothesis": {},
                "mvp_scope": {},
                "plan_30_60_90": {},
                "top_5_actions": [{"action": "talk to customers"}],
            },
            "contradictions": [],
            "overall_confidence": 0.5,
        }
    )

    assert verification["status"] == "passed"
    assert "no_contradictions_recorded" in verification["warnings"]


def test_verify_report_content_requires_sections():
    verification = verify_report_content(
        "# summary only",
        required_sections=["エグゼクティブサマリー", "結論"],
        quality={"status": "verified"},
    )

    assert verification["status"] == "failed"
    assert "missing_report_sections" in verification["issues"]


def test_merge_verification_results_fails_if_any_check_fails():
    verification = merge_verification_results(
        {
            "report": {"status": "passed", "issues": [], "warnings": [], "metrics": {}},
            "pm_board": {"status": "failed", "issues": ["missing_core_question"], "warnings": [], "metrics": {}},
        }
    )

    assert verification["status"] == "failed"
    assert "pm_board:missing_core_question" in verification["issues"]
