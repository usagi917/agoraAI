"""検証パイプラインモジュール

シミュレーション実行→記録→事後検証のフローを自動化する。

- register_result       : シミュレーション結果を ValidationRecord に登録
- auto_compare          : 関連する過去調査との自動比較
- resolve_with_actual   : 実績データ投入と精度指標算出
- generate_accuracy_report: テーマカテゴリ別の精度レポート
- update_bias_profile   : バイアスプロファイルの再構築
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.prediction_evaluation import PredictionEvaluation
from src.app.models.validation_record import ValidationRecord
from src.app.repositories.validation_repo import ValidationRepository
from src.app.services.society.survey_anchor import (
    ComparisonReport,
    compare_with_surveys,
)
from src.app.services.society.transfer_calibrator import (
    BiasProfile,
    compute_bias_profile,
)
from src.app.utils.distribution_metrics import (
    earth_movers_distance,
    kl_divergence_symmetric,
)


PredictionType = Literal["distribution", "scenario", "intervention"]


class AccuracyReport(TypedDict):
    total_validated: int
    by_category: dict
    overall_brier: float | None
    overall_kl: float | None
    overall_emd: float | None
    prediction_evaluations: dict


def _distribution_brier(predicted: dict[str, float], actual: dict[str, float]) -> float:
    keys = set(predicted) | set(actual)
    return sum((float(predicted.get(k, 0.0)) - float(actual.get(k, 0.0))) ** 2 for k in keys)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_direction(value: Any) -> str:
    direction = str(value or "").strip().lower()
    if direction in {"up", "increase", "positive", "改善", "増加"}:
        return "up"
    if direction in {"down", "decrease", "negative", "低下", "減少"}:
        return "down"
    return "flat"


def evaluate_distribution_prediction(
    predicted_payload: dict[str, Any],
    actual_payload: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate raw/weighted/calibrated/market distributions against actual."""
    actual = dict(
        actual_payload.get("actual_distribution")
        or actual_payload.get("distribution")
        or actual_payload
        or {}
    )
    candidates = {
        "raw": predicted_payload.get("raw_distribution"),
        "weighted": predicted_payload.get("weighted_distribution") or predicted_payload.get("distribution"),
        "calibrated": predicted_payload.get("calibrated_distribution"),
        "prediction_market": predicted_payload.get("prediction_market_distribution"),
    }
    by_variant: dict[str, dict[str, float]] = {}
    for name, distribution in candidates.items():
        if not isinstance(distribution, dict) or not distribution or not actual:
            continue
        typed_distribution = {str(k): _as_float(v) for k, v in distribution.items()}
        typed_actual = {str(k): _as_float(v) for k, v in actual.items()}
        by_variant[name] = {
            "brier": _distribution_brier(typed_distribution, typed_actual),
            "kl": kl_divergence_symmetric(typed_distribution, typed_actual),
            "emd": earth_movers_distance(typed_distribution, typed_actual),
        }

    best_variant = None
    if by_variant:
        best_variant = min(by_variant, key=lambda item: by_variant[item]["brier"])
    raw_brier = by_variant.get("raw", {}).get("brier")
    calibrated_brier = by_variant.get("calibrated", {}).get("brier")
    improvement = (
        raw_brier - calibrated_brier
        if raw_brier is not None and calibrated_brier is not None
        else None
    )
    return {
        "status": "validated" if by_variant else "pending_validation",
        "by_variant": by_variant,
        "best_variant": best_variant,
        "primary_metric": "brier",
        "primary_score": by_variant.get(best_variant, {}).get("brier") if best_variant else None,
        "calibration_improvement": improvement,
    }


def evaluate_scenario_prediction(
    predicted_payload: dict[str, Any],
    actual_payload: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate structured scenario predictions with hit and probability metrics."""
    predictions = list(predicted_payload.get("predictions") or predicted_payload.get("scenarios") or [])
    actual_labels = {
        str(item).strip()
        for item in (
            actual_payload.get("actual_outcomes")
            or actual_payload.get("outcome_labels")
            or [actual_payload.get("outcome_label") or actual_payload.get("issue_label")]
        )
        if str(item or "").strip()
    }
    if not predictions or not actual_labels:
        return {"status": "pending_validation", "hit_rate": None, "probability_brier": None}

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(predictions, start=1):
        label = str(item.get("outcome_label") or item.get("issue_label") or item.get("label") or "").strip()
        probability = max(0.0, min(1.0, _as_float(item.get("probability"), _as_float(item.get("scenario_score"), 0.0))))
        hit = label in actual_labels
        normalized.append({
            "rank": index,
            "outcome_label": label,
            "probability": probability,
            "hit": hit,
            "brier": (probability - (1.0 if hit else 0.0)) ** 2,
        })

    hit_count = sum(1 for item in normalized if item["hit"])
    first_hit = next((item for item in normalized if item["hit"]), None)
    probability_brier = sum(item["brier"] for item in normalized) / len(normalized)
    return {
        "status": "validated",
        "prediction_count": len(normalized),
        "actual_outcomes": sorted(actual_labels),
        "hit_count": hit_count,
        "hit_rate": hit_count / len(normalized),
        "mean_reciprocal_rank": (1.0 / first_hit["rank"]) if first_hit else 0.0,
        "probability_brier": probability_brier,
        "primary_metric": "probability_brier",
        "primary_score": probability_brier,
        "predictions": normalized,
    }


def evaluate_intervention_prediction(
    predicted_payload: dict[str, Any],
    actual_payload: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate intervention effect direction and magnitude errors."""
    predictions = list(predicted_payload.get("predictions") or predicted_payload.get("interventions") or [])
    actuals = list(actual_payload.get("actuals") or actual_payload.get("interventions") or [])
    if not predictions or not actuals:
        return {"status": "pending_validation", "direction_accuracy": None, "mae": None}

    actual_by_key = {
        (
            str(item.get("intervention_id") or ""),
            str(item.get("metric") or ""),
        ): item
        for item in actuals
    }
    rows: list[dict[str, Any]] = []
    for prediction in predictions:
        key = (
            str(prediction.get("intervention_id") or ""),
            str(prediction.get("metric") or ""),
        )
        actual = actual_by_key.get(key)
        if not actual:
            continue
        expected_delta = _as_float(prediction.get("expected_delta"))
        actual_delta = _as_float(actual.get("actual_delta"), _as_float(actual.get("signed_delta")))
        predicted_direction = _normalize_direction(prediction.get("direction"))
        actual_direction = _normalize_direction(actual.get("direction"))
        if actual_direction == "flat":
            actual_direction = "up" if actual_delta > 0 else "down" if actual_delta < 0 else "flat"
        rows.append({
            "intervention_id": key[0],
            "metric": key[1],
            "expected_delta": expected_delta,
            "actual_delta": actual_delta,
            "direction": predicted_direction,
            "actual_direction": actual_direction,
            "direction_match": predicted_direction == actual_direction,
            "absolute_error": abs(expected_delta - actual_delta),
        })

    if not rows:
        return {"status": "pending_validation", "direction_accuracy": None, "mae": None}

    direction_accuracy = sum(1 for row in rows if row["direction_match"]) / len(rows)
    mae = sum(row["absolute_error"] for row in rows) / len(rows)
    return {
        "status": "validated",
        "comparison_count": len(rows),
        "direction_accuracy": direction_accuracy,
        "mae": mae,
        "primary_metric": "mae",
        "primary_score": mae,
        "comparisons": rows,
    }


def compute_prediction_metrics(
    prediction_type: PredictionType,
    predicted_payload: dict[str, Any],
    actual_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if not actual_payload:
        return {"status": "pending_validation"}
    if prediction_type == "distribution":
        return evaluate_distribution_prediction(predicted_payload, actual_payload)
    if prediction_type == "scenario":
        return evaluate_scenario_prediction(predicted_payload, actual_payload)
    if prediction_type == "intervention":
        return evaluate_intervention_prediction(predicted_payload, actual_payload)
    raise ValueError(f"Unsupported prediction_type: {prediction_type}")


async def register_result(
    session: AsyncSession,
    simulation_id: str,
    theme: str,
    theme_category: str,
    distribution: dict[str, float],
    calibrated_distribution: dict[str, float] | None = None,
) -> ValidationRecord:
    """シミュレーション結果を validation_record に登録する。"""
    repo = ValidationRepository(session)
    return await repo.save(
        simulation_id=simulation_id,
        theme_text=theme,
        theme_category=theme_category,
        simulated_distribution=distribution,
        calibrated_distribution=calibrated_distribution,
    )


async def auto_compare(
    session: AsyncSession,
    record: ValidationRecord,
    survey_data_dir: str,
) -> ComparisonReport | None:
    """関連する調査データと自動比較し、比較結果をレコードへ反映して返す。"""
    report = compare_with_surveys(
        record.simulated_distribution,
        record.theme_text,
        survey_data_dir,
    )
    if report is None:
        return None

    repo = ValidationRepository(session)
    best_survey = next(
        s for s in report["matched_surveys"]
        if s["source"] == report["best_match_source"]
    )
    await repo.resolve(
        record_id=record.id,
        actual_distribution=best_survey["stance_distribution"],
        survey_source=best_survey["source"],
        survey_date=best_survey["survey_date"],
    )
    return report


async def resolve_with_actual(
    session: AsyncSession,
    record_id: str,
    actual_distribution: dict[str, float],
    survey_source: str,
    survey_date: str,
) -> ValidationRecord:
    """実績データを投入し精度指標を算出する。"""
    repo = ValidationRepository(session)
    return await repo.resolve(
        record_id=record_id,
        actual_distribution=actual_distribution,
        survey_source=survey_source,
        survey_date=survey_date,
    )


async def generate_accuracy_report(
    session: AsyncSession,
    theme_category: str | None = None,
) -> AccuracyReport:
    """テーマカテゴリ別の精度レポートを生成する。"""
    repo = ValidationRepository(session)
    agg = await repo.aggregate_by_category(theme_category)

    return AccuracyReport(
        total_validated=agg["count"],
        by_category={theme_category: agg} if theme_category else {},
        overall_brier=agg["avg_brier"],
        overall_kl=agg["avg_kl"],
        overall_emd=agg["avg_emd"],
        prediction_evaluations=await summarize_prediction_evaluations(
            session,
            theme_category=theme_category,
        ),
    )


async def update_bias_profile(
    session: AsyncSession,
    survey_data_dir: str,
) -> BiasProfile:
    """蓄積された validated レコードから comparisons を構築し BiasProfile を再構築する。"""
    repo = ValidationRepository(session)
    records = await repo.list_validated()

    comparisons = []
    for record in records:
        if record.actual_distribution and record.simulated_distribution:
            comparisons.append({
                "theme": record.theme_text,
                "theme_category": record.theme_category,
                "simulated_distribution": record.simulated_distribution,
                "actual_distribution": record.actual_distribution,
            })

    return compute_bias_profile(comparisons)


async def register_prediction_evaluation(
    session: AsyncSession,
    *,
    simulation_id: str,
    prediction_type: PredictionType,
    predicted_payload: dict[str, Any],
    theme_category: str = "",
    horizon: str = "",
    source: str = "",
    actual_payload: dict[str, Any] | None = None,
) -> PredictionEvaluation:
    """Register a cross-type prediction evaluation record.

    Records may be created before actual data is available. In that case the
    metrics status is pending_validation and can be resolved later.
    """
    metrics = compute_prediction_metrics(prediction_type, predicted_payload, actual_payload)
    record = PredictionEvaluation(
        simulation_id=simulation_id,
        prediction_type=prediction_type,
        theme_category=theme_category,
        horizon=horizon,
        predicted_payload=predicted_payload,
        actual_payload=actual_payload,
        metrics=metrics,
        source=source,
        primary_score=metrics.get("primary_score") if isinstance(metrics.get("primary_score"), (int, float)) else None,
    )
    if actual_payload and metrics.get("status") == "validated":
        from src.app.database import utcnow_naive

        record.validated_at = utcnow_naive()
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


async def resolve_prediction_evaluation(
    session: AsyncSession,
    *,
    record_id: str,
    actual_payload: dict[str, Any],
    source: str | None = None,
) -> PredictionEvaluation:
    record = await session.get(PredictionEvaluation, record_id)
    if record is None:
        raise ValueError(f"PredictionEvaluation not found: {record_id}")

    metrics = compute_prediction_metrics(
        record.prediction_type,  # type: ignore[arg-type]
        record.predicted_payload,
        actual_payload,
    )
    record.actual_payload = actual_payload
    record.metrics = metrics
    record.primary_score = metrics.get("primary_score") if isinstance(metrics.get("primary_score"), (int, float)) else None
    if source is not None:
        record.source = source
    if metrics.get("status") == "validated":
        from src.app.database import utcnow_naive

        record.validated_at = utcnow_naive()
    await session.commit()
    await session.refresh(record)
    return record


async def summarize_prediction_evaluations(
    session: AsyncSession,
    *,
    simulation_id: str | None = None,
    theme_category: str | None = None,
) -> dict[str, Any]:
    stmt = select(PredictionEvaluation)
    if simulation_id:
        stmt = stmt.where(PredictionEvaluation.simulation_id == simulation_id)
    if theme_category:
        stmt = stmt.where(PredictionEvaluation.theme_category == theme_category)
    result = await session.execute(stmt)
    records = list(result.scalars().all())

    summary: dict[str, Any] = {
        "distribution": {"count": 0, "validated_count": 0},
        "scenario": {"count": 0, "validated_count": 0},
        "intervention": {"count": 0, "validated_count": 0},
    }
    for record in records:
        bucket = summary.setdefault(record.prediction_type, {"count": 0, "validated_count": 0})
        bucket["count"] += 1
        if record.validated_at is not None:
            bucket["validated_count"] += 1
        metrics = record.metrics or {}
        if record.prediction_type == "distribution":
            best = metrics.get("best_variant")
            if best:
                bucket["best_variant"] = best
            if metrics.get("calibration_improvement") is not None:
                improvements = bucket.setdefault("calibration_improvements", [])
                improvements.append(metrics["calibration_improvement"])
        elif record.prediction_type == "scenario":
            for field in ("hit_rate", "mean_reciprocal_rank", "probability_brier"):
                if isinstance(metrics.get(field), (int, float)):
                    bucket.setdefault(field + "_values", []).append(float(metrics[field]))
        elif record.prediction_type == "intervention":
            for field in ("direction_accuracy", "mae"):
                if isinstance(metrics.get(field), (int, float)):
                    bucket.setdefault(field + "_values", []).append(float(metrics[field]))

    for bucket in summary.values():
        for key in list(bucket.keys()):
            if not key.endswith("_values"):
                continue
            values = bucket.pop(key)
            metric_name = key[: -len("_values")]
            bucket[metric_name] = sum(values) / len(values) if values else None
        improvements = bucket.pop("calibration_improvements", None)
        if improvements:
            bucket["avg_calibration_improvement"] = sum(improvements) / len(improvements)

    return summary


def build_distribution_prediction_payload(
    aggregation: dict[str, Any],
    *,
    prediction_market_distribution: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Build the canonical saved distribution payload from aggregation outputs."""
    return {
        "raw_distribution": aggregation.get("stance_distribution_raw") or aggregation.get("stance_distribution"),
        "weighted_distribution": aggregation.get("stance_distribution"),
        "calibrated_distribution": aggregation.get("calibrated_stance_distribution"),
        "prediction_market_distribution": prediction_market_distribution or aggregation.get("prediction_market_distribution"),
        "effective_sample_size": aggregation.get("effective_sample_size"),
        "margin_of_error": aggregation.get("margin_of_error"),
        "calibration_status": aggregation.get("calibration_status"),
    }
