"""Tests for diversity_enforcer (Phase 9).

Verifies Gini-based skew detection, temperature recommendation, and persona
diversification flagging across the 5 standard stances.
"""

from __future__ import annotations

import math

import pytest

from src.app.services.society.diversity_enforcer import (
    DiversityEnforcer,
    gini_coefficient,
    is_skewed,
    recommend_temperature,
)


STANCES = ["賛成", "条件付き賛成", "中立", "条件付き反対", "反対"]


def _even_distribution() -> dict[str, float]:
    return {s: 1.0 / len(STANCES) for s in STANCES}


def _highly_skewed_distribution() -> dict[str, float]:
    # ~all mass on a single stance
    dist = {s: 0.0 for s in STANCES}
    dist["賛成"] = 1.0
    return dist


def test_gini_zero_for_even_distribution() -> None:
    gini = gini_coefficient(_even_distribution())
    assert gini == pytest.approx(0.0, abs=1e-9)


def test_gini_high_for_highly_skewed_distribution() -> None:
    gini = gini_coefficient(_highly_skewed_distribution())
    # For n=5 categories with all mass on one, the Gini is (n-1)/n = 0.8
    assert gini == pytest.approx(0.8, abs=1e-6)
    assert gini > 0.6


def test_is_skewed_detects_concentration() -> None:
    assert is_skewed(_highly_skewed_distribution()) is True
    assert is_skewed(_even_distribution()) is False


def test_recommended_temperature_increases_with_skew() -> None:
    base_temp = 0.7
    even_temp = recommend_temperature(base_temp, _even_distribution())
    skewed_temp = recommend_temperature(base_temp, _highly_skewed_distribution())
    # Even distribution should keep temperature unchanged (clipped to current)
    assert even_temp == pytest.approx(base_temp)
    # Skewed should bump temperature up
    assert skewed_temp > base_temp


def test_recommended_temperature_clipped_at_max() -> None:
    # Force a degenerate, very-high-skew scenario
    dist = _highly_skewed_distribution()
    result = recommend_temperature(1.4, dist, target_gini=0.0, max_temp=1.5)
    assert result <= 1.5
    assert result == pytest.approx(1.5)


def test_recommended_temperature_never_below_current() -> None:
    # Even with no skew, temperature should not decrease below current_temp
    result = recommend_temperature(0.9, _even_distribution())
    assert result >= 0.9


def test_evaluate_returns_expected_keys() -> None:
    enforcer = DiversityEnforcer()
    result = enforcer.evaluate(_highly_skewed_distribution())
    assert set(result.keys()) == {
        "gini",
        "is_skewed",
        "recommended_temperature",
        "missing_stances",
    }
    assert result["is_skewed"] is True
    assert isinstance(result["missing_stances"], list)


def test_missing_stances_detection() -> None:
    enforcer = DiversityEnforcer()
    dist = {
        "賛成": 0.50,
        "条件付き賛成": 0.45,
        "中立": 0.04,  # below 0.05 threshold
        "条件付き反対": 0.01,  # below 0.05 threshold
        "反対": 0.00,  # below 0.05 threshold
    }
    result = enforcer.evaluate(dist)
    missing = result["missing_stances"]
    assert "中立" in missing
    assert "条件付き反対" in missing
    assert "反対" in missing
    assert "賛成" not in missing
    assert "条件付き賛成" not in missing


def test_apply_persona_diversification_flags_minority_targets() -> None:
    enforcer = DiversityEnforcer()
    personas = [
        {"id": "p1", "target_stance": "賛成"},
        {"id": "p2", "target_stance": "中立"},  # minority -> should be flagged
        {"id": "p3", "target_stance": "反対"},  # minority -> should be flagged
        {"id": "p4"},  # no target_stance -> assumed 中立 -> flagged
    ]
    dist = {
        "賛成": 0.80,
        "条件付き賛成": 0.10,
        "中立": 0.04,
        "条件付き反対": 0.03,
        "反対": 0.03,
    }
    out = enforcer.apply_persona_diversification(personas, dist)

    # New list, no mutation of input personas
    assert out is not personas
    for original in personas:
        assert "diversity_boost" not in original

    by_id = {p["id"]: p for p in out}
    assert by_id["p1"].get("diversity_boost", False) is False
    assert by_id["p2"]["diversity_boost"] is True
    assert by_id["p3"]["diversity_boost"] is True
    assert by_id["p4"]["diversity_boost"] is True


def test_apply_persona_diversification_no_flag_when_balanced() -> None:
    enforcer = DiversityEnforcer()
    personas = [
        {"id": "p1", "target_stance": "賛成"},
        {"id": "p2", "target_stance": "中立"},
    ]
    out = enforcer.apply_persona_diversification(personas, _even_distribution())
    for p in out:
        # When no stance is below 0.05 threshold, no persona should be boosted
        assert p.get("diversity_boost", False) is False


def test_gini_handles_unnormalized_input() -> None:
    # Counts (sum != 1) — Gini should still be 0 for a perfectly even split
    dist = {s: 10.0 for s in STANCES}
    assert gini_coefficient(dist) == pytest.approx(0.0, abs=1e-9)


def test_gini_is_finite_for_empty_or_zero_distribution() -> None:
    # All zeros — should not raise; treat as 0 (no concentration measurable)
    dist = {s: 0.0 for s in STANCES}
    g = gini_coefficient(dist)
    assert math.isfinite(g)
    assert g == pytest.approx(0.0)
