"""Market trader strategies for the K-outcome LMSR prediction market.

Phase 6 of "Wondrous Prancing Crayon" plan.

Three trader archetypes operate against `MultiOutcomeMarket`:
- `InformedTrader`: trades toward the largest gap between true probability
  and current market price (rational signal-following).
- `NoiseTrader`: picks a random outcome with a small qty; seeded RNG for
  deterministic tests.
- `HerdingTrader`: trades toward the current market leader (follow-the-crowd).

All traders share the interface `decide(market, signal) -> (idx, qty)`.
"""

from __future__ import annotations

import random
from typing import Any

from src.app.services.society.prediction_market import MultiOutcomeMarket


class InformedTrader:
    """Trades toward the outcome with the largest (true_prob - market_price) gap.

    Uses the magnitude of that gap to size the trade so that more confident
    signals translate into larger positions.
    """

    def __init__(self, seed: int = 0, base_qty: float = 5.0) -> None:
        self._seed = seed
        self._base_qty = base_qty

    def decide(
        self, market: MultiOutcomeMarket, signal: dict[str, Any]
    ) -> tuple[int, float]:
        true_prob = signal.get("true_prob")
        if true_prob is None:
            # No signal → fall back to deterministic, neutral pick.
            rng = random.Random(self._seed)
            return rng.randrange(len(market.outcomes)), 0.0
        prices = market.prices()
        gaps = [tp - p for tp, p in zip(true_prob, prices)]
        idx = max(range(len(gaps)), key=lambda i: gaps[i])
        gap = max(gaps[idx], 0.0)
        qty = self._base_qty * gap
        return idx, qty


class NoiseTrader:
    """Picks a random outcome with a small qty; seeded for deterministic tests."""

    def __init__(self, seed: int = 0, max_qty: float = 1.0) -> None:
        self._rng = random.Random(seed)
        self._max_qty = max_qty

    def decide(
        self, market: MultiOutcomeMarket, signal: dict[str, Any]
    ) -> tuple[int, float]:
        idx = self._rng.randrange(len(market.outcomes))
        # Small positive qty in (0, max_qty]
        qty = self._rng.uniform(0.1, self._max_qty)
        return idx, qty


class HerdingTrader:
    """Follows the current market leader (highest-priced outcome)."""

    def __init__(self, seed: int = 0, base_qty: float = 1.0) -> None:
        self._seed = seed
        self._base_qty = base_qty

    def decide(
        self, market: MultiOutcomeMarket, signal: dict[str, Any]
    ) -> tuple[int, float]:
        prices = market.prices()
        # Tie-break with the lowest index, deterministic given identical prices.
        idx = max(range(len(prices)), key=lambda i: (prices[i], -i))
        # Trade size proportional to how far the leader is above uniform.
        uniform = 1.0 / len(prices)
        excess = max(prices[idx] - uniform, 0.0)
        qty = self._base_qty * (1.0 + excess)
        return idx, qty
