"""Tests for K-outcome LMSR Market with liquidity profiles.

Phase 6 of "Wondrous Prancing Crayon" plan.
Verifies:
- K=5 outcomes: prices sum to 1.0
- LiquidityProfile changes effective b
- EARLY profile has more price impact than LATE
- buy() returns cost delta
- set_profile() rescales b
"""

from __future__ import annotations

import math

import pytest

from src.app.services.society.prediction_market import (
    LiquidityProfile,
    MultiOutcomeMarket,
)


class TestLiquidityProfile:
    """LiquidityProfile enum maps to b multipliers."""

    def test_profile_values(self):
        assert LiquidityProfile.EARLY.value == "early"
        assert LiquidityProfile.MID.value == "mid"
        assert LiquidityProfile.LATE.value == "late"

    def test_profile_multipliers(self):
        # Each profile maps to a multiplier
        assert LiquidityProfile.EARLY.multiplier == 0.5
        assert LiquidityProfile.MID.multiplier == 1.0
        assert LiquidityProfile.LATE.multiplier == 2.0


class TestMultiOutcomeMarketInit:
    """Constructor and initial state."""

    def test_default_profile_is_mid(self):
        m = MultiOutcomeMarket(outcomes=["a", "b", "c"])
        assert m.profile == LiquidityProfile.MID

    def test_initial_quantities_zero(self):
        m = MultiOutcomeMarket(outcomes=["a", "b", "c"])
        # Initial uniform prices
        prices = m.prices()
        for p in prices:
            assert p == pytest.approx(1 / 3, abs=1e-6)

    def test_b_base_default(self):
        m = MultiOutcomeMarket(outcomes=["a", "b"])
        # MID profile multiplier is 1.0, so effective b = 10.0
        assert m.b == pytest.approx(10.0)


class TestKOutcomePrices:
    """K=5 outcomes: probabilities must sum to 1.0."""

    def test_k5_uniform_initial(self):
        outcomes = [f"o{i}" for i in range(5)]
        m = MultiOutcomeMarket(outcomes=outcomes)
        prices = m.prices()
        assert len(prices) == 5
        assert sum(prices) == pytest.approx(1.0, abs=1e-9)
        for p in prices:
            assert p == pytest.approx(0.2, abs=1e-6)

    def test_k5_after_buys_sum_to_one(self):
        outcomes = [f"o{i}" for i in range(5)]
        m = MultiOutcomeMarket(outcomes=outcomes)
        m.buy(0, 5.0)
        m.buy(2, 3.0)
        m.buy(4, 1.0)
        prices = m.prices()
        assert sum(prices) == pytest.approx(1.0, abs=1e-9)

    def test_k10_sum_to_one(self):
        outcomes = [f"o{i}" for i in range(10)]
        m = MultiOutcomeMarket(outcomes=outcomes)
        m.buy(3, 7.0)
        prices = m.prices()
        assert sum(prices) == pytest.approx(1.0, abs=1e-9)
        # Bought outcome should have highest price
        assert prices[3] == max(prices)


class TestCost:
    """LMSR cost function: b * log(sum(exp(q_i / b)))."""

    def test_cost_initial_zero_quantities(self):
        m = MultiOutcomeMarket(outcomes=["a", "b", "c"])
        # cost([0,0,0]) = b * log(K)
        b = m.b
        expected = b * math.log(3)
        assert m.cost([0.0, 0.0, 0.0]) == pytest.approx(expected, rel=1e-9)

    def test_cost_increases_with_quantity(self):
        m = MultiOutcomeMarket(outcomes=["a", "b"])
        c0 = m.cost([0.0, 0.0])
        c1 = m.cost([5.0, 0.0])
        assert c1 > c0


class TestBuy:
    """buy() should return cost delta and update internal state."""

    def test_buy_returns_positive_delta(self):
        m = MultiOutcomeMarket(outcomes=["a", "b", "c"])
        delta = m.buy(0, 5.0)
        assert delta > 0

    def test_buy_increases_target_price(self):
        m = MultiOutcomeMarket(outcomes=["a", "b", "c"])
        before = m.prices()[0]
        m.buy(0, 5.0)
        after = m.prices()[0]
        assert after > before

    def test_buy_decreases_other_prices(self):
        m = MultiOutcomeMarket(outcomes=["a", "b", "c"])
        before_other = m.prices()[1]
        m.buy(0, 5.0)
        after_other = m.prices()[1]
        assert after_other < before_other


class TestLiquidityProfileImpact:
    """EARLY profile (smaller b) should produce greater price movement."""

    def test_set_profile_rescales_b(self):
        m = MultiOutcomeMarket(outcomes=["a", "b"], b_base=10.0)
        assert m.b == pytest.approx(10.0)
        m.set_profile(LiquidityProfile.EARLY)
        assert m.b == pytest.approx(5.0)
        m.set_profile(LiquidityProfile.LATE)
        assert m.b == pytest.approx(20.0)

    def test_early_more_impact_than_late(self):
        """For the same buy size, EARLY profile produces larger price change."""
        m_early = MultiOutcomeMarket(
            outcomes=["a", "b", "c"], b_base=10.0, profile=LiquidityProfile.EARLY
        )
        m_late = MultiOutcomeMarket(
            outcomes=["a", "b", "c"], b_base=10.0, profile=LiquidityProfile.LATE
        )
        before_early = m_early.prices()[0]
        before_late = m_late.prices()[0]
        m_early.buy(0, 3.0)
        m_late.buy(0, 3.0)
        delta_early = m_early.prices()[0] - before_early
        delta_late = m_late.prices()[0] - before_late
        assert delta_early > delta_late

    def test_mid_between_early_and_late(self):
        """MID profile produces price change between EARLY and LATE."""
        configs = [
            LiquidityProfile.EARLY,
            LiquidityProfile.MID,
            LiquidityProfile.LATE,
        ]
        deltas = []
        for profile in configs:
            m = MultiOutcomeMarket(
                outcomes=["a", "b", "c"], b_base=10.0, profile=profile
            )
            before = m.prices()[0]
            m.buy(0, 3.0)
            deltas.append(m.prices()[0] - before)
        # Strictly decreasing impact: EARLY > MID > LATE
        assert deltas[0] > deltas[1] > deltas[2]


class TestNumericalStability:
    """LMSR should not overflow with extreme quantities."""

    def test_large_quantity_no_overflow(self):
        m = MultiOutcomeMarket(outcomes=["a", "b", "c"], b_base=10.0)
        m.buy(0, 10000.0)
        prices = m.prices()
        assert sum(prices) == pytest.approx(1.0, abs=1e-6)
        # The bought outcome should dominate
        assert prices[0] > 0.99
