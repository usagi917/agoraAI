"""Paired-model diagnostics and calibration for hybrid activation."""

from __future__ import annotations

from collections import Counter

from src.app.services.society.constants import STANCE_ORDER


def _normalized_counts(responses: list[dict]) -> dict[str, float]:
    valid = [response for response in responses if response.get("stance") in STANCE_ORDER]
    if not valid:
        return {stance: 0.0 for stance in STANCE_ORDER}
    counts = Counter(response["stance"] for response in valid)
    return {stance: counts.get(stance, 0) / len(valid) for stance in STANCE_ORDER}


def apply_distribution_residual(
    base_distribution: dict[str, float],
    residual: dict[str, float],
    *,
    shrinkage: float,
) -> dict[str, float]:
    """Apply a bounded model residual to any later-stage distribution."""
    bounded_shrinkage = max(0.0, min(1.0, float(shrinkage)))
    adjusted = {
        stance: max(
            0.0,
            float(base_distribution.get(stance, 0.0))
            + bounded_shrinkage * float(residual.get(stance, 0.0)),
        )
        for stance in STANCE_ORDER
    }
    return _normalize(adjusted)


def correct_distribution_with_shadow(
    local_distribution: dict[str, float],
    local_responses: list[dict],
    shadow_responses: list[dict],
    *,
    shrinkage: float = 1.0,
) -> tuple[dict[str, float], dict]:
    """Apply a paired model residual; GPT is explicitly not treated as observed truth."""
    valid_pairs = [
        (local, shadow)
        for local, shadow in zip(local_responses, shadow_responses, strict=False)
        if (
            not local.get("_failed")
            and not shadow.get("_failed")
            and local.get("stance") in STANCE_ORDER
            and shadow.get("stance") in STANCE_ORDER
        )
    ]
    paired_count = len(valid_pairs)
    if paired_count == 0:
        normalized = _normalize(local_distribution)
        return normalized, {
            "method": "paired_model_residual",
            "paired_count": 0,
            "is_ground_truth": False,
            "applied": False,
        }

    paired_local = [local for local, _ in valid_pairs]
    paired_shadow = [shadow for _, shadow in valid_pairs]
    local_sample = _normalized_counts(paired_local)
    shadow_sample = _normalized_counts(paired_shadow)
    residual = {
        stance: shadow_sample[stance] - local_sample[stance] for stance in STANCE_ORDER
    }
    corrected = apply_distribution_residual(
        local_distribution,
        residual,
        shrinkage=shrinkage,
    )
    disagreement = sum(
        local.get("stance") != shadow.get("stance")
        for local, shadow in valid_pairs
    )
    return corrected, {
        "method": "paired_model_residual",
        "paired_count": paired_count,
        "disagreement_rate": disagreement / paired_count,
        "is_ground_truth": False,
        "applied": True,
        "residual": residual,
    }


def _normalize(distribution: dict[str, float]) -> dict[str, float]:
    values = {stance: max(0.0, float(distribution.get(stance, 0.0))) for stance in STANCE_ORDER}
    total = sum(values.values())
    if total <= 0:
        return {stance: 1.0 / len(STANCE_ORDER) for stance in STANCE_ORDER}
    return {stance: value / total for stance, value in values.items()}


def select_escalation_pairs(
    local_responses: list[dict],
    shadow_responses: list[dict],
    *,
    max_calls: int,
) -> list[tuple[dict, dict]]:
    scored: list[tuple[float, str, dict, dict]] = []
    for index, (local, shadow) in enumerate(zip(local_responses, shadow_responses, strict=False)):
        if local.get("_failed") or shadow.get("_failed"):
            score = 3.0
        else:
            score = 2.0 if local.get("stance") != shadow.get("stance") else 0.0
            score += abs(float(local.get("confidence", 0.5)) - float(shadow.get("confidence", 0.5)))
        agent_id = str(local.get("agent_id") or shadow.get("agent_id") or index)
        scored.append((score, agent_id, local, shadow))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [(local, shadow) for score, _, local, shadow in scored[: max(0, max_calls)] if score > 0]
