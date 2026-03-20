"""pipeline_orchestrator の純粋関数テスト"""

import pytest
from src.app.services.pipeline_orchestrator import _build_swarm_context, _build_pm_context


# -----------------------------------------------------------------------
# _build_swarm_context
# -----------------------------------------------------------------------

def test_build_swarm_context_basic():
    single_result = {
        "world_state": {"entities": [{"id": "e1"}]},
        "report_content": "レポート内容",
    }
    ctx = _build_swarm_context(single_result)
    assert ctx["world_state"] == {"entities": [{"id": "e1"}]}
    assert ctx["additional_context"] == "レポート内容"


def test_build_swarm_context_empty_single():
    ctx = _build_swarm_context({})
    assert ctx["world_state"] is None
    assert ctx["additional_context"] == ""


def test_build_swarm_context_truncates_long_report():
    long_report = "x" * 20000
    ctx = _build_swarm_context({"report_content": long_report})
    # 8000文字 + 省略テキスト
    assert len(ctx["additional_context"]) <= 8100
    assert "[...レポート後半省略...]" in ctx["additional_context"]


def test_build_swarm_context_short_report_not_truncated():
    short_report = "A" * 100
    ctx = _build_swarm_context({"report_content": short_report})
    assert ctx["additional_context"] == short_report
    assert "[...レポート後半省略...]" not in ctx["additional_context"]


def test_build_swarm_context_exactly_at_limit():
    """8000文字ちょうどは切り捨てされない。"""
    report = "x" * 8000
    ctx = _build_swarm_context({"report_content": report})
    assert ctx["additional_context"] == report


def test_build_swarm_context_world_state_none():
    ctx = _build_swarm_context({"report_content": "test"})
    assert ctx["world_state"] is None


# -----------------------------------------------------------------------
# _build_pm_context
# -----------------------------------------------------------------------

def test_build_pm_context_basic():
    single = {"report_content": "stage1"}
    swarm = {
        "integrated_report": "stage2",
        "aggregation": {
            "scenarios": [{"description": "Scenario A", "probability": 0.6}],
            "diversity_score": 0.5,
            "entropy": 1.0,
        },
    }
    ctx = _build_pm_context(single, swarm)
    assert "stage1" in ctx["document_text"]
    assert "stage2" in ctx["document_text"]
    assert "Scenario A" in ctx["document_text"]
    assert len(ctx["scenarios"]) == 1


def test_build_pm_context_empty_inputs():
    ctx = _build_pm_context({}, {})
    assert ctx["document_text"] == ""
    assert ctx["scenarios"] == []


def test_build_pm_context_no_scenarios():
    single = {"report_content": "report"}
    swarm = {"integrated_report": "", "aggregation": {"scenarios": [], "diversity_score": 0, "entropy": 0}}
    ctx = _build_pm_context(single, swarm)
    assert "report" in ctx["document_text"]
    assert ctx["scenarios"] == []


def test_build_pm_context_truncates_long_document():
    long_report = "A" * 20000
    single = {"report_content": long_report}
    swarm = {"integrated_report": long_report, "aggregation": {"scenarios": [], "diversity_score": 0, "entropy": 0}}
    ctx = _build_pm_context(single, swarm)
    assert len(ctx["document_text"]) <= 15200  # 15000 + 省略テキスト
    assert "[...コンテキスト後半省略...]" in ctx["document_text"]


def test_build_pm_context_scenarios_limited_to_10():
    """シナリオが10件を超える場合、先頭10件のみ表示される。"""
    scenarios = [{"description": f"S{i}", "probability": 0.1} for i in range(20)]
    swarm = {
        "integrated_report": "",
        "aggregation": {
            "scenarios": scenarios,
            "diversity_score": 0.5,
            "entropy": 1.0,
        },
    }
    ctx = _build_pm_context({}, swarm)
    # document_text 内にシナリオが存在するが 20件分はない
    assert "S10" not in ctx["document_text"] or "S0" in ctx["document_text"]
    # scenarios はそのまま全件渡す
    assert len(ctx["scenarios"]) == 20


def test_build_pm_context_probability_formatting():
    """確率は % 表示でフォーマットされる。"""
    swarm = {
        "integrated_report": "",
        "aggregation": {
            "scenarios": [{"description": "Test", "probability": 0.75}],
            "diversity_score": 0.5,
            "entropy": 1.0,
        },
    }
    ctx = _build_pm_context({}, swarm)
    assert "75%" in ctx["document_text"]


def test_build_pm_context_diversity_metrics_in_text():
    swarm = {
        "integrated_report": "",
        "aggregation": {
            "scenarios": [{"description": "X", "probability": 0.5}],
            "diversity_score": 0.42,
            "entropy": 2.3,
        },
    }
    ctx = _build_pm_context({}, swarm)
    assert "0.42" in ctx["document_text"]
    assert "2.30" in ctx["document_text"]
