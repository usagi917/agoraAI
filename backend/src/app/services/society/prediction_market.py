"""Prediction Market: LMSR-based confidence aggregation.

Implements Hanson's Logarithmic Market Scoring Rule (LMSR) to aggregate
agent confidence into market-implied probability distributions.

Each agent bets their confidence on a predicted outcome. The market price
reflects the collective belief about each outcome's likelihood.

Reference: Hanson (2003), Combinatorial Information Market Design.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


@dataclass
class MarketPosition:
    agent_id: str
    outcome: str
    confidence: float


class PredictionMarket:
    """LMSR-based prediction market for outcome probability aggregation."""

    def __init__(self, outcomes: list[str], liquidity: float = 10.0, adaptive_b: bool = False) -> None:
        self._outcomes = outcomes
        self._liquidity = liquidity  # LMSR 'b' base parameter
        self._adaptive_b = adaptive_b
        # Quantity per outcome (starts at 0 for uniform prior)
        self._quantities: dict[str, float] = {o: 0.0 for o in outcomes}
        self._positions: list[MarketPosition] = []

    @property
    def effective_liquidity(self) -> float:
        """現在のベット数に応じた実効 liquidity を返す。

        adaptive_b=True の場合: b = base_b * sqrt(n_bets / 10)
        n_bets < 10 では b が縮小し個々のベットの影響が大きくなり、
        n_bets > 10 では b が拡大し市場が安定化する。
        """
        if not self._adaptive_b:
            return self._liquidity
        n_bets = len(self._positions)
        return self._liquidity * math.sqrt(max(1, n_bets) / 10.0)

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
        b = self.effective_liquidity
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


class LiquidityProfile(Enum):
    """Market liquidity profile that scales the LMSR `b` parameter.

    Smaller `b` (EARLY) → higher price impact per trade, useful when the market
    just opened and signal density is low. Larger `b` (LATE) → smoother prices
    once consensus has formed.
    """

    EARLY = "early"
    MID = "mid"
    LATE = "late"

    @property
    def multiplier(self) -> float:
        return _PROFILE_MULTIPLIERS[self]


_PROFILE_MULTIPLIERS: dict[LiquidityProfile, float] = {
    LiquidityProfile.EARLY: 0.5,
    LiquidityProfile.MID: 1.0,
    LiquidityProfile.LATE: 2.0,
}


class MultiOutcomeMarket:
    """K-outcome LMSR market with adjustable liquidity profile.

    Implements Hanson's LMSR cost function over K outcomes:
        cost(q) = b * log(sum_k(exp(q_k / b)))
    Prices are the softmax of `q_k / b`, which always sum to 1.

    Uses the log-sum-exp trick (subtract max(q)) for numerical stability so
    extreme quantities do not overflow `math.exp`.
    """

    def __init__(
        self,
        outcomes: list[str],
        b_base: float = 10.0,
        profile: LiquidityProfile = LiquidityProfile.MID,
    ) -> None:
        if not outcomes:
            raise ValueError("MultiOutcomeMarket requires at least one outcome")
        if b_base <= 0:
            raise ValueError("b_base must be positive")
        self._outcomes = list(outcomes)
        self._b_base = float(b_base)
        self._profile = profile
        self._quantities: list[float] = [0.0] * len(outcomes)

    @property
    def outcomes(self) -> list[str]:
        return list(self._outcomes)

    @property
    def profile(self) -> LiquidityProfile:
        return self._profile

    @property
    def b(self) -> float:
        """Effective liquidity parameter b = b_base * profile.multiplier."""
        return self._b_base * self._profile.multiplier

    def set_profile(self, profile: LiquidityProfile) -> None:
        """Switch liquidity profile, rescaling the effective `b` parameter."""
        self._profile = profile

    def cost(self, quantities: list[float]) -> float:
        """LMSR cost: b * log(sum(exp(q_i / b))) with log-sum-exp stability."""
        if len(quantities) != len(self._outcomes):
            raise ValueError(
                f"quantities length {len(quantities)} != outcomes length {len(self._outcomes)}"
            )
        b = self.b
        max_q = max(quantities)
        exp_sum = sum(math.exp((q - max_q) / b) for q in quantities)
        return max_q + b * math.log(exp_sum)

    def prices(self) -> list[float]:
        """Softmax prices over outcomes; always sums to 1.0."""
        b = self.b
        max_q = max(self._quantities)
        exps = [math.exp((q - max_q) / b) for q in self._quantities]
        total = sum(exps)
        return [e / total for e in exps]

    def buy(self, outcome_idx: int, qty: float) -> float:
        """Buy `qty` shares of `outcome_idx`. Returns the cost delta paid."""
        if not 0 <= outcome_idx < len(self._outcomes):
            raise IndexError(f"outcome_idx {outcome_idx} out of range")
        if qty < 0:
            raise ValueError("qty must be non-negative")
        before = self.cost(self._quantities)
        new_quantities = list(self._quantities)
        new_quantities[outcome_idx] += qty
        after = self.cost(new_quantities)
        self._quantities = new_quantities
        return after - before
