"""Prediction Market: LMSR-based confidence aggregation.

Implements Hanson's Logarithmic Market Scoring Rule (LMSR) to aggregate
agent confidence into market-implied probability distributions.

Each agent bets their confidence on a predicted outcome. The market price
reflects the collective belief about each outcome's likelihood.

Reference: Hanson (2003), Combinatorial Information Market Design.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MarketPosition:
    agent_id: str
    outcome: str
    confidence: float


class PredictionMarket:
    """LMSR-based prediction market for outcome probability aggregation."""

    def __init__(self, outcomes: list[str], liquidity: float = 10.0) -> None:
        self._outcomes = outcomes
        self._liquidity = liquidity  # LMSR 'b' parameter
        # Quantity per outcome (starts at 0 for uniform prior)
        self._quantities: dict[str, float] = {o: 0.0 for o in outcomes}
        self._positions: list[MarketPosition] = []

    def submit_bet(self, agent_id: str, outcome: str, confidence: float, weight: float = 1.0) -> None:
        """Agent bets confidence on an outcome, scaled by independence weight."""
        if outcome not in self._quantities:
            return
        self._positions.append(MarketPosition(agent_id, outcome, confidence))
        # Scale bet by confidence * weight (lower weight for clustered agents)
        self._quantities[outcome] += confidence * weight

    def get_prices(self) -> dict[str, float]:
        """Compute LMSR prices (softmax over quantities/b).

        Uses log-sum-exp trick for numerical stability: subtract max(q)
        before exponentiation to prevent overflow with large quantities.
        """
        b = self._liquidity
        max_q = max(self._quantities.values())
        exp_vals = {o: math.exp((q - max_q) / b) for o, q in self._quantities.items()}
        total = sum(exp_vals.values())
        return {o: v / total for o, v in exp_vals.items()}

    def resolve(self, actual_outcome: str) -> dict[str, float]:
        """Resolve market: agents who bet on actual_outcome receive payoffs."""
        payoffs: dict[str, float] = {}
        for pos in self._positions:
            if pos.outcome == actual_outcome:
                payoffs[pos.agent_id] = payoffs.get(pos.agent_id, 0.0) + pos.confidence
            else:
                payoffs.setdefault(pos.agent_id, 0.0)
        return payoffs

    def aggregate_prediction(self) -> dict[str, float]:
        """Return market-implied probability distribution."""
        return self.get_prices()

    def compute_brier_score(self, actual_outcome: str) -> float:
        """Compute Brier score for market prediction vs actual outcome.

        Brier = sum_k (p_k - o_k)^2, where o_k=1 if k is actual, 0 otherwise.
        Lower is better. Range [0, 2].
        """
        prices = self.get_prices()
        score = 0.0
        for outcome, prob in prices.items():
            actual = 1.0 if outcome == actual_outcome else 0.0
            score += (prob - actual) ** 2
        return score
