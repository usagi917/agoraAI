"""Tests for market trader strategies.

Phase 6 of "Wondrous Prancing Crayon" plan.
Verifies:
- InformedTrader trades toward (true_prob - market_price) max gap
- NoiseTrader picks random outcome with seedable determinism
- HerdingTrader follows the current highest-priced outcome
"""

from __future__ import annotations

import pytest

from src.app.services.society.market_strategies import (
    HerdingTrader,
    InformedTrader,
    NoiseTrader,
)
from src.app.services.society.prediction_market import (
    LiquidityProfile,
    MultiOutcomeMarket,
)


class TestInformedTrader:
    """InformedTrader trades toward outcome with highest (true_prob - price) gap."""

    def test_informed_picks_max_gap(self):
        market = MultiOutcomeMarket(outcomes=["a", "b", "c"])
        # All prices are uniform (~0.333). True probs strongly favor index 1.
        signal = {"true_prob": [0.1, 0.7, 0.2]}
        trader = InformedTrader(seed=0)
        idx, qty = trader.decide(market, signal)
        assert idx == 1
        assert qty > 0

    def test_informed_deterministic(self):
        """Same inputs produce same output (seeded determinism)."""
        market_a = MultiOutcomeMarket(outcomes=["a", "b", "c"])
        market_b = MultiOutcomeMarket(outcomes=["a", "b", "c"])
        signal = {"true_prob": [0.5, 0.3, 0.2]}
        t1 = InformedTrader(seed=42)
        t2 = InformedTrader(seed=42)
        assert t1.decide(market_a, signal) == t2.decide(market_b, signal)

    def test_informed_responds_to_market_state(self):
        """If a price already matches its true_prob, informed picks elsewhere."""
        market = MultiOutcomeMarket(outcomes=["a", "b", "c"])
        # Push outcome 1 to high price
        market.buy(1, 20.0)
        # Now true_prob favors index 1, but market already overprices it
        signal = {"true_prob": [0.4, 0.4, 0.2]}
        trader = InformedTrader(seed=0)
        idx, _qty = trader.decide(market, signal)
        # Should not pick the already-overpriced outcome
        assert idx != 1


class TestNoiseTrader:
    """NoiseTrader picks random outcome deterministically with seed."""

    def test_noise_qty_is_small(self):
        market = MultiOutcomeMarket(outcomes=["a", "b", "c"])
        trader = NoiseTrader(seed=0)
        _idx, qty = trader.decide(market, {})
        assert 0 < qty <= 1.0

    def test_noise_seed_determinism(self):
        m1 = MultiOutcomeMarket(outcomes=["a", "b", "c", "d", "e"])
        m2 = MultiOutcomeMarket(outcomes=["a", "b", "c", "d", "e"])
        t1 = NoiseTrader(seed=123)
        t2 = NoiseTrader(seed=123)
        assert t1.decide(m1, {}) == t2.decide(m2, {})

    def test_noise_different_seeds_can_differ(self):
        """Two different seeds usually produce different outcomes (probabilistic)."""
        outcomes = [f"o{i}" for i in range(10)]
        # Ensure at least one of many seed pairs differs
        m_a = MultiOutcomeMarket(outcomes=outcomes)
        m_b = MultiOutcomeMarket(outcomes=outcomes)
        decisions = {
            NoiseTrader(seed=s).decide(MultiOutcomeMarket(outcomes=outcomes), {})[0]
            for s in range(20)
        }
        # In 10 outcomes with 20 seeds, we expect more than one unique pick
        assert len(decisions) >= 2
        # Avoid unused-variable warnings
        del m_a, m_b

    def test_noise_idx_in_range(self):
        outcomes = [f"o{i}" for i in range(5)]
        market = MultiOutcomeMarket(outcomes=outcomes)
        for seed in range(20):
            trader = NoiseTrader(seed=seed)
            idx, _ = trader.decide(market, {})
            assert 0 <= idx < 5


class TestHerdingTrader:
    """HerdingTrader follows the current highest-priced outcome."""

    def test_herding_follows_leader(self):
        market = MultiOutcomeMarket(outcomes=["a", "b", "c"])
        # Push outcome 2 to be the leader
        market.buy(2, 10.0)
        trader = HerdingTrader(seed=0)
        idx, qty = trader.decide(market, {})
        assert idx == 2
        assert qty > 0

    def test_herding_switches_with_leader(self):
        market = MultiOutcomeMarket(outcomes=["a", "b", "c"])
        market.buy(0, 10.0)
        trader = HerdingTrader(seed=0)
        assert trader.decide(market, {})[0] == 0
        # Now make outcome 2 the leader
        market.buy(2, 30.0)
        assert trader.decide(market, {})[0] == 2

    def test_herding_deterministic(self):
        market_a = MultiOutcomeMarket(outcomes=["a", "b", "c"])
        market_b = MultiOutcomeMarket(outcomes=["a", "b", "c"])
        market_a.buy(1, 5.0)
        market_b.buy(1, 5.0)
        t1 = HerdingTrader(seed=7)
        t2 = HerdingTrader(seed=7)
        assert t1.decide(market_a, {}) == t2.decide(market_b, {})


class TestStrategyInteraction:
    """Strategies should work together on the same market."""

    def test_three_strategies_on_same_market(self):
        market = MultiOutcomeMarket(
            outcomes=["a", "b", "c", "d", "e"], profile=LiquidityProfile.MID
        )
        signal = {"true_prob": [0.05, 0.05, 0.7, 0.1, 0.1]}

        informed = InformedTrader(seed=1)
        noise = NoiseTrader(seed=2)
        herding = HerdingTrader(seed=3)

        for trader in [informed, noise, herding]:
            idx, qty = trader.decide(market, signal)
            market.buy(idx, qty)

        # Prices still valid
        prices = market.prices()
        assert sum(prices) == pytest.approx(1.0, abs=1e-9)
