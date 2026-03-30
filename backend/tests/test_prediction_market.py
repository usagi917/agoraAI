"""Tests for Prediction Market: LMSR-based confidence aggregation.

Verifies:
- Agents can submit bets (confidence-weighted positions)
- LMSR market price computation
- Market resolution and payoff calculation
- Aggregate prediction from market prices
"""

import pytest

from src.app.services.society.prediction_market import PredictionMarket


class TestSubmitBet:
    """Agents should be able to place bets on outcomes."""

    def test_single_bet(self):
        market = PredictionMarket(outcomes=["賛成多数", "反対多数", "拮抗"])
        market.submit_bet("agent_0", "賛成多数", confidence=0.8)

        prices = market.get_prices()
        assert "賛成多数" in prices
        # After one bet on 賛成多数, its price should be highest
        assert prices["賛成多数"] > prices["反対多数"]

    def test_multiple_bets_same_outcome(self):
        market = PredictionMarket(outcomes=["賛成多数", "反対多数"])
        market.submit_bet("agent_0", "賛成多数", confidence=0.9)
        market.submit_bet("agent_1", "賛成多数", confidence=0.8)

        prices = market.get_prices()
        assert prices["賛成多数"] > prices["反対多数"]

    def test_balanced_bets(self):
        market = PredictionMarket(outcomes=["A", "B"])
        market.submit_bet("agent_0", "A", confidence=0.8)
        market.submit_bet("agent_1", "B", confidence=0.8)

        prices = market.get_prices()
        # Equal bets → prices should be roughly equal
        assert abs(prices["A"] - prices["B"]) < 0.1


class TestMarketPrices:
    """LMSR prices should sum to approximately 1.0."""

    def test_prices_sum_to_one(self):
        market = PredictionMarket(outcomes=["A", "B", "C"])
        market.submit_bet("agent_0", "A", confidence=0.9)
        market.submit_bet("agent_1", "B", confidence=0.5)

        prices = market.get_prices()
        assert sum(prices.values()) == pytest.approx(1.0, abs=0.01)

    def test_initial_prices_uniform(self):
        market = PredictionMarket(outcomes=["A", "B", "C"])
        prices = market.get_prices()
        for p in prices.values():
            assert p == pytest.approx(1 / 3, abs=0.01)


class TestResolve:
    """Market resolution should compute payoffs based on actual outcome."""

    def test_correct_prediction_positive_payoff(self):
        market = PredictionMarket(outcomes=["A", "B"])
        market.submit_bet("agent_0", "A", confidence=0.9)
        market.submit_bet("agent_1", "B", confidence=0.9)

        payoffs = market.resolve("A")
        assert payoffs["agent_0"] > 0
        assert payoffs["agent_1"] == 0

    def test_all_correct_payoffs(self):
        market = PredictionMarket(outcomes=["A", "B"])
        market.submit_bet("agent_0", "A", confidence=0.9)
        market.submit_bet("agent_1", "A", confidence=0.5)

        payoffs = market.resolve("A")
        # Higher confidence bet should get higher payoff
        assert payoffs["agent_0"] > payoffs["agent_1"]


class TestAggregatePrediction:
    """Market should produce aggregate probability distribution."""

    def test_aggregate_matches_prices(self):
        market = PredictionMarket(outcomes=["A", "B", "C"])
        market.submit_bet("agent_0", "A", confidence=0.9)
        market.submit_bet("agent_1", "B", confidence=0.3)

        prediction = market.aggregate_prediction()
        assert set(prediction.keys()) == {"A", "B", "C"}
        assert sum(prediction.values()) == pytest.approx(1.0, abs=0.01)
        assert prediction["A"] > prediction["B"]


class TestBrierScore:
    """Market calibration via Brier score."""

    def test_perfect_prediction_low_brier(self):
        market = PredictionMarket(outcomes=["A", "B"])
        # Everyone bets A with high confidence
        for i in range(10):
            market.submit_bet(f"agent_{i}", "A", confidence=0.95)

        brier = market.compute_brier_score("A")
        assert brier < 0.3  # reasonably good prediction

    def test_wrong_prediction_high_brier(self):
        market = PredictionMarket(outcomes=["A", "B"])
        # Everyone bets A but outcome is B
        for i in range(10):
            market.submit_bet(f"agent_{i}", "A", confidence=0.95)

        brier = market.compute_brier_score("B")
        assert brier > 0.5  # poor prediction
