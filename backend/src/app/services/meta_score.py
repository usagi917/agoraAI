"""Score helpers for meta simulations."""

from __future__ import annotations

from typing import Any


TARGET_OBJECTIVE_SCORE = 0.78
PLATEAU_DELTA = 0.02
PLATEAU_PATIENCE = 2
MAX_META_CYCLES = 5


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def compute_society_score(society_summary: dict[str, Any]) -> float:
    aggregation = dict(society_summary.get("aggregation") or {})
    evaluation = dict(society_summary.get("evaluation") or {})

    average_confidence = _safe_float(aggregation.get("average_confidence"), 0.0)
    consistency = _safe_float(evaluation.get("consistency"), 0.0)
    calibration = _safe_float(evaluation.get("calibration"), 0.0)

    return round((average_confidence + consistency + calibration) / 3, 4)


def compute_swarm_score(
    issue_colonies: list[dict[str, Any]],
    selected_issues: list[dict[str, Any]],
) -> float:
    if not issue_colonies:
        return 0.0

    issue_weights = {
        str(issue.get("label") or ""): max(_safe_float(issue.get("selection_score"), 0.0), 0.05)
        for issue in selected_issues
    }

    weighted_total = 0.0
    weight_sum = 0.0
    for colony in issue_colonies:
        label = str(colony.get("label") or "")
        top_scenarios = list(colony.get("top_scenarios") or [])
        if not top_scenarios:
            continue
        top_score = max(
            _safe_float(
                scenario.get("scenario_score", scenario.get("probability", 0.0)),
                0.0,
            )
            for scenario in top_scenarios[:3]
        )
        weight = issue_weights.get(label, 0.2)
        weighted_total += top_score * weight
        weight_sum += weight

    if weight_sum <= 0:
        return 0.0
    return round(weighted_total / weight_sum, 4)


def compute_pm_score(pm_result: dict[str, Any]) -> float:
    return round(_safe_float(pm_result.get("overall_confidence"), 0.0), 4)


def compute_objective_score(
    society_summary: dict[str, Any],
    issue_colonies: list[dict[str, Any]],
    selected_issues: list[dict[str, Any]],
    pm_result: dict[str, Any],
) -> dict[str, float]:
    society_score = compute_society_score(society_summary)
    swarm_score = compute_swarm_score(issue_colonies, selected_issues)
    pm_score = compute_pm_score(pm_result)

    objective_score = round(
        society_score * 0.35 + swarm_score * 0.35 + pm_score * 0.30,
        4,
    )

    return {
        "society_score": society_score,
        "swarm_score": swarm_score,
        "pm_score": pm_score,
        "objective_score": objective_score,
    }


def evaluate_stop_condition(
    scores: list[float],
    *,
    target_score: float = TARGET_OBJECTIVE_SCORE,
    plateau_delta: float = PLATEAU_DELTA,
    plateau_patience: int = PLATEAU_PATIENCE,
    max_cycles: int = MAX_META_CYCLES,
) -> dict[str, Any]:
    current_score = scores[-1] if scores else 0.0
    deltas = []
    for prev, curr in zip(scores, scores[1:]):
        deltas.append(round(curr - prev, 4))

    plateau_count = 0
    for delta in reversed(deltas):
        if delta < plateau_delta:
            plateau_count += 1
        else:
            break

    if current_score >= target_score:
        return {
            "should_stop": True,
            "reason": "target_reached",
            "target_score": target_score,
            "current_score": current_score,
            "delta_from_prev": deltas[-1] if deltas else current_score,
            "plateau_count": plateau_count,
        }

    if plateau_count >= plateau_patience:
        return {
            "should_stop": True,
            "reason": "plateau",
            "target_score": target_score,
            "current_score": current_score,
            "delta_from_prev": deltas[-1] if deltas else current_score,
            "plateau_count": plateau_count,
        }

    if len(scores) >= max_cycles:
        return {
            "should_stop": True,
            "reason": "max_cycles",
            "target_score": target_score,
            "current_score": current_score,
            "delta_from_prev": deltas[-1] if deltas else current_score,
            "plateau_count": plateau_count,
        }

    return {
        "should_stop": False,
        "reason": "continue",
        "target_score": target_score,
        "current_score": current_score,
        "delta_from_prev": deltas[-1] if deltas else current_score,
        "plateau_count": plateau_count,
    }
