"""Phase 4: Monte Carlo Ensemble Runner.

N 走の予測器を並列実行 (concurrency limit) し、確率帯 (CI) を集計する。
LLM コストを意識して fixture replay モードに差し替え可能な predictor を受け取る。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

Distribution = dict[str, float]
Predictor = Callable[[int], Awaitable[Distribution]]


@dataclass
class EnsembleResult:
    distributions: list[Distribution] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.distributions)

    def mean_distribution(self) -> Distribution:
        if not self.distributions:
            return {}
        keys: set[str] = set()
        for d in self.distributions:
            keys.update(d.keys())
        result: Distribution = {}
        for k in keys:
            vals = [d.get(k, 0.0) for d in self.distributions]
            result[k] = sum(vals) / len(vals)
        # normalize
        total = sum(result.values())
        if total > 0:
            return {k: v / total for k, v in result.items()}
        return result

    def credible_intervals(
        self,
        levels: tuple[float, ...] = (0.5, 0.8, 0.95),
    ) -> dict[str, dict[str, dict[str, float]]]:
        """各 level の lower/median/upper をスタンス別に返す.

        Returns:
            { "50": {stance: {lower, median, upper}}, "80": ..., "95": ... }
        """
        if not self.distributions:
            return {}
        keys: set[str] = set()
        for d in self.distributions:
            keys.update(d.keys())

        result: dict[str, dict[str, dict[str, float]]] = {}
        for level in levels:
            label = str(int(level * 100))
            tail = (1 - level) / 2
            level_dict: dict[str, dict[str, float]] = {}
            for stance in keys:
                vals = sorted(d.get(stance, 0.0) for d in self.distributions)
                lower = _percentile(vals, tail * 100)
                median = _percentile(vals, 50)
                upper = _percentile(vals, (1 - tail) * 100)
                level_dict[stance] = {
                    "lower": lower,
                    "median": median,
                    "upper": upper,
                }
            result[label] = level_dict
        return result


class EnsembleRunner:
    def __init__(self, n_runs: int = 30, concurrency: int = 4) -> None:
        if n_runs <= 0:
            raise ValueError("n_runs must be > 0")
        if concurrency <= 0:
            raise ValueError("concurrency must be > 0")
        self.n_runs = n_runs
        self.concurrency = concurrency

    async def run(self, predictor: Predictor) -> EnsembleResult:
        sem = asyncio.Semaphore(self.concurrency)

        async def _one(seed: int) -> Distribution | None:
            async with sem:
                try:
                    return await predictor(seed)
                except Exception as exc:
                    logger.warning("ensemble run %d failed: %s", seed, exc)
                    return None

        tasks = [asyncio.create_task(_one(seed)) for seed in range(self.n_runs)]
        results = await asyncio.gather(*tasks)
        distributions = [r for r in results if r is not None]
        return EnsembleResult(distributions=distributions)


def _percentile(sorted_values: list[float], q: float) -> float:
    """Linear interpolation percentile (q in 0..100)."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (q / 100) * (len(sorted_values) - 1)
    lower_idx = int(pos)
    upper_idx = min(lower_idx + 1, len(sorted_values) - 1)
    fraction = pos - lower_idx
    return sorted_values[lower_idx] * (1 - fraction) + sorted_values[upper_idx] * fraction
