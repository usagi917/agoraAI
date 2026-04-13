"""検証パイプラインモジュール

シミュレーション実行→記録→事後検証のフローを自動化する。

- register_result           : シミュレーション結果を ValidationRecord に登録
- auto_compare              : 関連する過去調査との自動比較
- resolve_with_actual       : 実績データ投入と精度指標算出
- generate_accuracy_report  : テーマカテゴリ別の精度レポート
- update_bias_profile       : バイアスプロファイルの再構築
- run_full_validation       : 全レコードの validation 分類（Step 4）
- build_validation_summary  : ゲート判定サマリー生成（Step 4）
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

import yaml
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
from src.app.services.society.theme_category import ThemeCategoryEstimate

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_DEFAULT_GAMMA = 0.7

# =============================================
# Step 4: validation 基盤定数
# =============================================

# ゲート判定閾値（EMD 主指標、JSD 副指標）
GATE_EMD_THRESHOLD: float = 0.15   # EMD < 0.15 でパス
GATE_JSD_THRESHOLD: float = 0.10   # JSD < 0.10 でパス
GATE_BRIER_THRESHOLD: float = 0.30  # Brier < 0.30 でパス

# カバレッジ基準
MIN_VALIDATED_COUNT: int = 3         # 全体で必要な最低 validated 件数
MIN_VALIDATED_PER_CATEGORY: int = 2  # カテゴリ別の最低 validated 件数
MIN_COVERAGE_RATIO: float = 0.5      # validated / total >= 0.5 が必要

# manifest ファイルが置かれているディレクトリ
# __file__ = backend/src/app/services/society/validation_pipeline.py
# → ../../../../../config/grounding/manifests = /config/grounding/manifests
MANIFEST_DIR: str = os.path.join(
    os.path.dirname(__file__),
    "../../../../..",  # agentAI/
    "config/grounding/manifests",
)


def _load_manifest_surveys() -> list[dict]:
    """manifests/ 以下の YAML を読み、全 survey エントリの辞書リストを返す。

    train_surveys と eval_surveys の両方を収集する。
    各エントリには source, quality_rank 等が含まれる。
    """
    all_surveys: list[dict] = []
    manifest_path = Path(MANIFEST_DIR).resolve()

    if not manifest_path.exists():
        logger.warning("Manifest directory not found: %s", manifest_path)
        return all_surveys

    for yaml_file in manifest_path.glob("*.yaml"):
        try:
            with open(yaml_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except (yaml.YAMLError, OSError) as exc:
            logger.warning("Failed to load manifest %s: %s", yaml_file, exc)
            continue

        if not data:
            continue

        for section in ("train_surveys", "eval_surveys"):
            for survey in data.get(section, []):
                if isinstance(survey, dict) and "source" in survey:
                    all_surveys.append(survey)

    return all_surveys


def _load_manifested_sources() -> set[str]:
    """manifests/ から全 survey source 名の集合を返す。"""
    return {s["source"] for s in _load_manifest_surveys()}


def _determine_manifest_status(
    survey_source: str | None,
    manifested_sources: set[str],
) -> str | None:
    """survey_source が manifest に含まれるか判定する。

    Returns:
        "manifested" | "unmanifested" | None (survey_source が None の場合)
    """
    if survey_source is None:
        return None
    return "manifested" if survey_source in manifested_sources else "unmanifested"


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
    theme_category_estimate: ThemeCategoryEstimate | None = None,
) -> ValidationRecord:
    """シミュレーション結果を validation_record に登録する。

    theme_category_estimate が渡された場合は provenance をログに記録する。
    confidence / source の DB 永続化は Step 2 の DB マイグレーション完了後に行う。
    """
    theme_category_confidence: float | None = None
    theme_category_source: str | None = None
    if theme_category_estimate is not None:
        logger.debug(
            "theme_category provenance: category=%s confidence=%.2f source=%s anchor_eligible=%s",
            theme_category_estimate.category,
            theme_category_estimate.confidence,
            theme_category_estimate.source,
            theme_category_estimate.is_anchor_eligible,
        )
        theme_category_confidence = theme_category_estimate.confidence
        theme_category_source = theme_category_estimate.source
    repo = ValidationRepository(session)
    return await repo.save(
        simulation_id=simulation_id,
        theme_text=theme,
        theme_category=theme_category,
        simulated_distribution=distribution,
        calibrated_distribution=calibrated_distribution,
        theme_category_confidence=theme_category_confidence,
        theme_category_source=theme_category_source,
    )


async def auto_compare(
    session: AsyncSession,
    record: ValidationRecord,
    survey_data_dir: str,
) -> ComparisonReport | None:
    """関連する調査データと自動比較し、比較結果をレコードへ反映して返す。

    ValidationRecord の theme_category を compare_with_surveys へパススルーし、
    異カテゴリ調査との誤マッチを防ぐ。

    theme_category="unknown" の場合は survey 比較をスキップして None を返す。
    """
    if record.theme_category == "unknown":
        logger.debug(
            "auto_compare: skipping survey comparison for unknown category (sim=%s)",
            record.simulation_id,
        )
        return None

    report = compare_with_surveys(
        record.simulated_distribution,
        record.theme_text,
        survey_data_dir,
        theme_category=record.theme_category,
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


# =============================================
# Step 4: run_full_validation / build_validation_summary
# =============================================


class ValidationResultItem(TypedDict):
    simulation_id: str
    record_id: str
    theme_category: str
    status: str                        # "validated" | "report_only"
    gate_eligible: bool
    survey_manifest_status: str | None  # "manifested" | "unmanifested" | None
    survey_source: str | None
    emd: float | None
    jsd: float | None
    brier_score: float | None


async def run_full_validation(
    session: AsyncSession,
    theme_category: str | None = None,
    exclude_quality_ranks: list[str] | None = None,
) -> list[ValidationResultItem]:
    """全 ValidationRecord を取得し、各レコードを validation 状態で分類する。

    各レコードに対して以下を決定する:
    - status: "validated"（actual_distribution あり）/ "report_only"（なし）
    - gate_eligible: exclude_quality_ranks に含まれるソースは False
    - survey_manifest_status: manifest に登録された source かどうか

    Args:
        session: DB セッション
        theme_category: カテゴリフィルタ（None で全件）
        exclude_quality_ranks: 除外するランク指定（現在は survey_source ベースで判定）

    Returns:
        ValidationResultItem のリスト
    """
    from sqlalchemy import select

    stmt = select(ValidationRecord)
    if theme_category:
        stmt = stmt.where(ValidationRecord.theme_category == theme_category)

    result = await session.execute(stmt)
    records = list(result.scalars().all())

    if not records:
        return []

    manifested_sources = _load_manifested_sources()

    items: list[ValidationResultItem] = []
    for record in records:
        # status 判定
        if record.actual_distribution is not None:
            status = "validated"
        else:
            status = "report_only"

        # manifest status 判定
        manifest_status = _determine_manifest_status(
            record.survey_source,
            manifested_sources,
        )

        # gate_eligible: unknown カテゴリは survey 比較対象外のため常に False
        # exclude_quality_ranks による除外も確認する
        gate_eligible = record.theme_category != "unknown"
        if gate_eligible and exclude_quality_ranks and record.survey_source:
            # manifest から quality_rank を取得して判定
            quality_rank = _get_survey_quality_rank(record.survey_source)
            if quality_rank in (exclude_quality_ranks or []):
                gate_eligible = False

        items.append(
            ValidationResultItem(
                simulation_id=record.simulation_id,
                record_id=record.id,
                theme_category=record.theme_category or "",
                status=status,
                gate_eligible=gate_eligible,
                survey_manifest_status=manifest_status,
                survey_source=record.survey_source,
                emd=record.emd,
                jsd=record.jsd,
                brier_score=record.brier_score,
            )
        )

    return items


def _get_survey_quality_rank(survey_source: str) -> str | None:
    """manifest から survey_source の quality_rank を返す。

    manifest に登録されていないソースは None を返す。
    _load_manifest_surveys() の結果を線形探索する。
    """
    for survey in _load_manifest_surveys():
        if survey.get("source") == survey_source:
            return survey.get("quality_rank")
    return None


class ValidationSummary(TypedDict):
    gate: str                  # "pass" | "fail" | "inconclusive"
    avg_emd: float | None
    avg_jsd: float | None
    avg_brier: float | None
    total_count: int
    validated_count: int
    gate_eligible_count: int
    theme_category: str | None


def build_validation_summary(
    records_data: list[dict[str, Any]],
    theme_category: str | None = None,
) -> ValidationSummary:
    """validation 結果リストからゲート判定サマリーを生成する。

    ゲート基準:
    - EMD < 0.15 (主指標)
    - JSD < 0.10 (副指標)
    - Brier < 0.30

    カバレッジ基準:
    - gate_eligible かつ validated なレコードが MIN_VALIDATED_COUNT 以上
    - カテゴリ指定時は MIN_VALIDATED_PER_CATEGORY 以上
    - validated / total >= MIN_COVERAGE_RATIO

    Args:
        records_data: ValidationResultItem 相当の辞書リスト
        theme_category: カテゴリ情報（サマリーに付与するのみ）

    Returns:
        ValidationSummary
    """
    # unknown カテゴリは survey 比較対象外のため gate 判定不可
    if theme_category == "unknown":
        return ValidationSummary(
            gate="inconclusive",
            avg_emd=None,
            avg_jsd=None,
            avg_brier=None,
            total_count=len(records_data),
            validated_count=0,
            gate_eligible_count=0,
            theme_category=theme_category,
        )

    total_count = len(records_data)

    # gate_eligible かつ validated なレコードを gate 判定対象にする
    gate_records = [
        r for r in records_data
        if r.get("status") == "validated" and r.get("gate_eligible", True)
    ]
    validated_count = len([r for r in records_data if r.get("status") == "validated"])
    gate_eligible_count = len(gate_records)

    # カバレッジ基準チェック
    # 1) gate 判定可能なレコードが MIN_VALIDATED_COUNT 未満
    min_required = MIN_VALIDATED_PER_CATEGORY if theme_category else MIN_VALIDATED_COUNT
    if gate_eligible_count < min_required:
        return ValidationSummary(
            gate="inconclusive",
            avg_emd=None,
            avg_jsd=None,
            avg_brier=None,
            total_count=total_count,
            validated_count=validated_count,
            gate_eligible_count=gate_eligible_count,
            theme_category=theme_category,
        )

    # 2) coverage ratio チェック（total が 0 の場合は inconclusive 済）
    if total_count > 0:
        coverage_ratio = validated_count / total_count
        if coverage_ratio < MIN_COVERAGE_RATIO:
            return ValidationSummary(
                gate="inconclusive",
                avg_emd=None,
                avg_jsd=None,
                avg_brier=None,
                total_count=total_count,
                validated_count=validated_count,
                gate_eligible_count=gate_eligible_count,
                theme_category=theme_category,
            )

    # 平均メトリクス計算（gate 対象レコードのみ）
    emds = [r["emd"] for r in gate_records if r.get("emd") is not None]
    jsds = [r["jsd"] for r in gate_records if r.get("jsd") is not None]
    briers = [r["brier_score"] for r in gate_records if r.get("brier_score") is not None]

    avg_emd = sum(emds) / len(emds) if emds else None
    avg_jsd = sum(jsds) / len(jsds) if jsds else None
    avg_brier = sum(briers) / len(briers) if briers else None

    # ゲート判定
    gate = "pass"
    if avg_emd is not None and avg_emd >= GATE_EMD_THRESHOLD:
        gate = "fail"
    elif avg_jsd is not None and avg_jsd >= GATE_JSD_THRESHOLD:
        gate = "fail"
    elif avg_brier is not None and avg_brier >= GATE_BRIER_THRESHOLD:
        gate = "fail"

    return ValidationSummary(
        gate=gate,
        avg_emd=avg_emd,
        avg_jsd=avg_jsd,
        avg_brier=avg_brier,
        total_count=total_count,
        validated_count=validated_count,
        gate_eligible_count=gate_eligible_count,
        theme_category=theme_category,
    )
