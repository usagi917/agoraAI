"""検証パイプラインモジュール

シミュレーション実行→記録→事後検証のフローを自動化する。

- register_result       : シミュレーション結果を ValidationRecord に登録
- auto_compare          : 関連する過去調査との自動比較
- resolve_with_actual   : 実績データ投入と精度指標算出
- generate_accuracy_report: テーマカテゴリ別の精度レポート
- update_bias_profile   : バイアスプロファイルの再構築
"""

from __future__ import annotations

from typing import TypedDict

from sqlalchemy.ext.asyncio import AsyncSession

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


class AccuracyReport(TypedDict):
    total_validated: int
    by_category: dict
    overall_brier: float | None
    overall_kl: float | None
    overall_emd: float | None


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
