"""Diversity enforcer (Phase 9).

Detects skewed stance distributions across the 5 standard stances and
recommends corrective actions (e.g. raising LLM temperature, flagging
under-represented personas for diversification).

The enforcer is a lightweight, deterministic, stdlib-only utility. It does
NOT touch the LLM directly — it only emits a recommendation that callers
(persona_generator etc.) wire up in a later phase.
"""

from __future__ import annotations

from typing import Iterable


__all__ = [
    "gini_coefficient",
    "is_skewed",
    "recommend_temperature",
    "DiversityEnforcer",
]


# Mass below this is treated as a "missing" stance (under-represented).
_MISSING_STANCE_THRESHOLD = 0.05


def _normalize(distribution: dict[str, float]) -> list[float]:
    """Return a list of non-negative probabilities summing to 1 (or all zero).

    - Coerces None/negatives to 0.
    - If the sum is positive, normalizes; otherwise returns zeros.
    """
    values = [max(0.0, float(v)) for v in distribution.values()]
    total = sum(values)
    if total <= 0.0:
        return [0.0] * len(values)
    return [v / total for v in values]


def gini_coefficient(distribution: dict[str, float]) -> float:
    """Standard Gini coefficient on the probability mass.

    For n categories with probabilities p_i (sum = 1), Gini =
    (1 / (2 * n^2 * mean)) * sum_i sum_j |p_i - p_j|.

    With mean = 1/n, this simplifies to:
        Gini = (1 / (2 * n)) * sum_i sum_j |p_i - p_j|.

    - Even split (p_i = 1/n)  -> Gini = 0.0
    - Fully concentrated      -> Gini = (n - 1) / n  (upper bound for n cats)
    """
    probs = _normalize(distribution)
    n = len(probs)
    if n == 0:
        return 0.0
    total_mass = sum(probs)
    if total_mass <= 0.0:
        return 0.0

    abs_diff_sum = 0.0
    for i in range(n):
        for j in range(n):
            abs_diff_sum += abs(probs[i] - probs[j])
    # mean of probs is total_mass / n; with total_mass == 1 this is 1/n
    mean = total_mass / n
    denom = 2.0 * (n * n) * mean
    if denom <= 0.0:
        return 0.0
    return abs_diff_sum / denom


def is_skewed(distribution: dict[str, float], threshold: float = 0.6) -> bool:
    """True when the Gini coefficient exceeds the threshold."""
    return gini_coefficient(distribution) > threshold


def recommend_temperature(
    current_temp: float,
    distribution: dict[str, float],
    target_gini: float = 0.4,
    max_temp: float = 1.5,
) -> float:
    """Recommend an LLM temperature given the observed stance distribution.

    Behavior:
    - If the distribution is not skewed (Gini <= threshold default 0.6),
      return current_temp unchanged (clipped at max_temp).
    - If skewed, scale up by ``1 + (gini - target_gini)`` and clip the
      result to ``[current_temp, max_temp]``.
    """
    gini = gini_coefficient(distribution)
    if not is_skewed(distribution):
        # Don't lower temperature; simply respect the cap.
        return min(current_temp, max_temp)

    scale = 1.0 + (gini - target_gini)
    # Defensive: never scale down below 1.0
    if scale < 1.0:
        scale = 1.0
    proposed = current_temp * scale
    # Clip to [current_temp, max_temp]
    if proposed < current_temp:
        proposed = current_temp
    if proposed > max_temp:
        proposed = max_temp
    return proposed


def _missing_stances(distribution: dict[str, float]) -> list[str]:
    """Stances whose normalized mass is < 0.05."""
    probs = _normalize(distribution)
    keys = list(distribution.keys())
    return [k for k, p in zip(keys, probs) if p < _MISSING_STANCE_THRESHOLD]


class DiversityEnforcer:
    """Bundle Gini-based skew detection with recommendation helpers."""

    def __init__(self, target_gini: float = 0.4, max_temp: float = 1.5) -> None:
        self.target_gini = target_gini
        self.max_temp = max_temp

    def evaluate(self, distribution: dict[str, float]) -> dict:
        """Return diagnostic information for a stance distribution."""
        gini = gini_coefficient(distribution)
        skewed = is_skewed(distribution)
        # When evaluating without a known current_temp, treat the target_gini
        # as the "ideal" baseline temperature anchor — but we still want a
        # meaningful recommendation, so we anchor to a neutral 1.0 default.
        recommended = recommend_temperature(
            current_temp=1.0,
            distribution=distribution,
            target_gini=self.target_gini,
            max_temp=self.max_temp,
        )
        return {
            "gini": gini,
            "is_skewed": skewed,
            "recommended_temperature": recommended,
            "missing_stances": _missing_stances(distribution),
        }

    def apply_persona_diversification(
        self,
        personas: list[dict],
        distribution: dict[str, float],
    ) -> list[dict]:
        """Mark personas whose target stance is under-represented.

        Returns a NEW list of NEW persona dicts; input is never mutated.
        Personas without a ``target_stance`` key are assumed to target
        中立 (neutral).
        """
        missing = set(_missing_stances(distribution))
        result: list[dict] = []
        for persona in personas:
            new_persona = dict(persona)  # shallow copy
            target = new_persona.get("target_stance", "中立")
            if target in missing:
                new_persona["diversity_boost"] = True
            result.append(new_persona)
        return result


def _iter_values(distribution: dict[str, float]) -> Iterable[float]:
    """Internal helper kept for forwards-compatibility / clarity."""
    return distribution.values()
