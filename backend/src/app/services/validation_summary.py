"""Compact validation summary for report responses."""

from __future__ import annotations

import logging
from typing import Any

from src.app.config import settings
from src.app.services.society.survey_anchor import compare_with_surveys
from src.app.services.society.transfer_calibrator import (
    apply_transfer_correction,
    compute_bias_profile,
    compute_transfer_uncertainty,
)

logger = logging.getLogger(__name__)


def build_unvalidated_summary(
    *,
    calibration_status: str = "uncalibrated",
    scenario_backtest_status: str = "no_data",
    hit_rate: float | None = None,
) -> dict[str, Any]:
    return {
        "survey_anchor_status": "未検証",
        "distribution_error": None,
        "scenario_backtest_status": scenario_backtest_status,
        "hit_rate": hit_rate,
        "calibration_status": calibration_status,
    }


def build_validation_summary(
    *,
    theme: str,
    theme_category: str,
    distribution: dict[str, float],
    scenario_backtest_status: str = "no_data",
    hit_rate: float | None = None,
) -> dict[str, Any]:
    """Compare a stance distribution against survey anchors when available.

    The return shape is intentionally small and stable for the frontend. Detailed
    survey rows stay nested under optional fields so existing consumers can ignore
    them.
    """
    summary = build_unvalidated_summary(
        scenario_backtest_status=scenario_backtest_status,
        hit_rate=hit_rate,
    )
    if not distribution:
        return summary

    try:
        survey_dir = settings.config_dir / "grounding" / "survey_data"
        comparison = compare_with_surveys(distribution, theme, str(survey_dir))
    except Exception as exc:
        logger.warning("Survey validation summary failed: %s", exc)
        return summary

    if not comparison:
        return summary

    best = next(
        (
            survey for survey in comparison.get("matched_surveys", [])
            if survey.get("source") == comparison.get("best_match_source")
        ),
        None,
    )
    corrected_distribution = None
    transfer_uncertainty = None
    if best:
        bias_profile = compute_bias_profile([
            {
                "theme": theme,
                "theme_category": theme_category,
                "simulated_distribution": distribution,
                "actual_distribution": best["stance_distribution"],
            }
        ])
        corrected_distribution = apply_transfer_correction(
            distribution,
            bias_profile,
            theme_category,
            min_samples=1,
        )
        transfer_uncertainty = compute_transfer_uncertainty(bias_profile, theme_category)

    return {
        **summary,
        "survey_anchor_status": "実調査アンカーあり",
        "distribution_error": {
            "kl_divergence": comparison.get("kl_divergence"),
            "emd": comparison.get("emd"),
        },
        "calibration_status": "survey_anchored",
        "matched_survey_count": len(comparison.get("matched_surveys", [])),
        "best_match_source": comparison.get("best_match_source"),
        "corrected_distribution": corrected_distribution,
        "transfer_uncertainty": transfer_uncertainty,
    }


def merge_scenario_backtest_status(
    summary: dict[str, Any] | None,
    backtest: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(summary or build_unvalidated_summary())
    backtest_summary = (backtest or {}).get("summary") or {}
    case_count = int(backtest_summary.get("case_count") or 0)
    if case_count > 0:
        merged["scenario_backtest_status"] = "過去ケース検証あり"
        merged["hit_rate"] = backtest_summary.get("hit_rate")
    else:
        merged["scenario_backtest_status"] = "no_data"
        merged["hit_rate"] = merged.get("hit_rate")
    return merged
