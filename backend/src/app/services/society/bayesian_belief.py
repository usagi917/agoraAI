"""Phase 3: Dirichlet 分布によるスタンス信念の逐次更新.

5 カテゴリ (賛成/条件付き賛成/中立/条件付き反対/反対) の Dirichlet を保持し、
観測 (擬似カウント) を加えることで posterior に更新する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class BeliefDistribution:
    """Dirichlet over a finite set of stances."""

    alpha: dict[str, float] = field(default_factory=dict)

    @classmethod
    def uniform(cls, stances: Iterable[str], pseudo_count: float = 1.0) -> "BeliefDistribution":
        return cls(alpha={s: pseudo_count for s in stances})

    def total(self) -> float:
        return sum(self.alpha.values())

    def probabilities(self) -> dict[str, float]:
        total = self.total()
        if total == 0:
            n = len(self.alpha) or 1
            return {k: 1.0 / n for k in self.alpha}
        return {k: v / total for k, v in self.alpha.items()}

    def variance(self) -> dict[str, float]:
        """各カテゴリの分散 alpha_k * (alpha0 - alpha_k) / (alpha0^2 * (alpha0 + 1))."""
        a0 = self.total()
        if a0 <= 0:
            return {k: 0.0 for k in self.alpha}
        return {
            k: (v * (a0 - v)) / (a0 * a0 * (a0 + 1))
            for k, v in self.alpha.items()
        }


def update_belief(
    prior: BeliefDistribution,
    observation: dict[str, float] | None,
) -> BeliefDistribution:
    """観測 (擬似カウント) を prior に加えて posterior を返す.

    Args:
        prior: 元の Dirichlet
        observation: {stance: count} の擬似カウント. None または空なら prior を保つ.
    """
    new_alpha = dict(prior.alpha)
    if observation:
        for stance, count in observation.items():
            if count <= 0:
                continue
            new_alpha[stance] = new_alpha.get(stance, 0.0) + float(count)
    return BeliefDistribution(alpha=new_alpha)
