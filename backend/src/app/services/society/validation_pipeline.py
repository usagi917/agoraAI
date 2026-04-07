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
from src.app.services.society.calibration import (
    extremeness_aversion_correction,
)
from src.app.services.society.transfer_calibrator import (
    BiasProfile,
    compute_bias_profile,
)

_DEFAULT_GAMMA = 0.7


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


class GammaSearchResult(TypedDict):
    best_gamma: float
    gamma_scores: list[dict]
    theme_category: str | None


async def find_optimal_gamma(
    session: AsyncSession,
    theme_category: str | None = None,
    gamma_range: tuple[float, float] = (0.3, 1.5),
    gamma_step: float = 0.1,
    _records: list | None = None,
) -> GammaSearchResult:
    """検証済みレコードから最適な extremeness aversion γ をグリッドサーチで発見する。

    各 γ 候補に対して extremeness_aversion_correction を適用し、
    actual_distribution との Brier スコアが最小になる γ を返す。

    Args:
        session: DB セッション
        theme_category: フィルタ用のテーマカテゴリ（None で全カテゴリ）
        gamma_range: γ の探索範囲 (min, max)
        gamma_step: γ のステップ幅
        _records: 事前フェッチ済みレコード（find_optimal_gamma_by_category からの再利用用）

    Returns:
        best_gamma, gamma_scores, theme_category を含む辞書
    """
    if _records is None:
        repo = ValidationRepository(session)
        records = await repo.list_validated()
    else:
        records = _records

    # カテゴリフィルタ
    if theme_category:
        records = [r for r in records if r.theme_category == theme_category]

    if not records:
        return GammaSearchResult(
            best_gamma=_DEFAULT_GAMMA,
            gamma_scores=[],
            theme_category=theme_category,
        )

    # γ 候補を生成
    gammas: list[float] = []
    g = gamma_range[0]
    while g <= gamma_range[1] + 1e-9:
        gammas.append(round(g, 2))
        g += gamma_step

    # 各 γ について平均 Brier スコアを計算
    # validation_repo の _brier_score_distributions と同じ全分布 Brier を使用:
    # Σ(p_i - a_i)² where p_i = corrected, a_i = actual
    gamma_scores: list[dict] = []
    for gamma in gammas:
        brier_sum = 0.0
        count = 0
        for record in records:
            if not record.simulated_distribution or not record.actual_distribution:
                continue
            corrected = extremeness_aversion_correction(record.simulated_distribution, gamma)
            actual = record.actual_distribution
            all_keys = set(corrected.keys()) | set(actual.keys())
            full_dist_brier = sum(
                (corrected.get(k, 0.0) - actual.get(k, 0.0)) ** 2
                for k in all_keys
            )
            brier_sum += full_dist_brier
            count += 1
        avg_brier = brier_sum / count if count > 0 else float("inf")
        gamma_scores.append({"gamma": gamma, "avg_brier": avg_brier})

    # 最小 Brier の γ を選択
    best = min(gamma_scores, key=lambda x: x["avg_brier"])

    return GammaSearchResult(
        best_gamma=best["gamma"],
        gamma_scores=gamma_scores,
        theme_category=theme_category,
    )


class CategoryGammaResult(TypedDict):
    by_category: dict[str, GammaSearchResult]


async def find_optimal_gamma_by_category(
    session: AsyncSession,
) -> CategoryGammaResult:
    """全カテゴリについて個別に最適 γ をグリッドサーチする。

    Returns:
        by_category: カテゴリ名 → GammaSearchResult のマッピング
    """
    repo = ValidationRepository(session)
    records = await repo.list_validated()

    # カテゴリの収集
    categories: set[str] = set()
    for r in records:
        if r.theme_category:
            categories.add(r.theme_category)

    by_category: dict[str, GammaSearchResult] = {}
    for cat in categories:
        result = await find_optimal_gamma(session, theme_category=cat, _records=records)
        by_category[cat] = result

    return CategoryGammaResult(by_category=by_category)
