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
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, TypedDict

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.prediction_evaluation import PredictionEvaluation
from src.app.models.validation_record import ValidationRecord
from src.app.repositories.validation_repo import ValidationRepository
from src.app.services.society.calibration import (
    extremeness_aversion_correction,
)
from src.app.services.society.survey_anchor import (
    ComparisonReport,
    compare_with_surveys,
)
from src.app.services.society.theme_category import ThemeCategoryEstimate
from src.app.services.society.transfer_calibrator import (
    BiasProfile,
    compute_bias_profile,
)
from src.app.utils.distribution_metrics import (
    earth_movers_distance,
    kl_divergence_symmetric,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_DEFAULT_GAMMA = 0.7
PredictionType = Literal["distribution", "scenario", "intervention"]

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
_PRESET_ID_RE = re.compile(r"^[a-z0-9_-]+$")


@dataclass(frozen=True)
class ManifestSplit:
    preset_id: str
    train_ids: set[str]
    eval_ids: set[str]
    train_files: set[str]
    eval_files: set[str]
    train_surveys: list[dict[str, Any]]
    eval_surveys: list[dict[str, Any]]
    manifest_path: Path


def _manifest_path_for_preset(preset_id: str) -> Path:
    if not _PRESET_ID_RE.fullmatch(preset_id):
        raise ValueError(f"Invalid preset_id: {preset_id!r}")

    manifest_dir = Path(MANIFEST_DIR).resolve()
    direct = (manifest_dir / f"{preset_id}_manifest.yaml").resolve()
    if not direct.is_relative_to(manifest_dir):
        raise ValueError(f"Invalid preset_id: {preset_id!r}")

    if direct.exists():
        return direct

    for yaml_file in manifest_dir.glob("*.yaml"):
        try:
            with open(yaml_file, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except (yaml.YAMLError, OSError):
            continue
        if data.get("preset_id") == preset_id:
            return yaml_file
    raise FileNotFoundError(f"Manifest preset not found: {preset_id}")


def load_manifest_split(preset_id: str) -> ManifestSplit:
    """指定 preset の train/eval survey split を読み込む。"""
    manifest_path = _manifest_path_for_preset(preset_id)
    with open(manifest_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    train_surveys = list(data.get("train_surveys") or [])
    eval_surveys = list(data.get("eval_surveys") or [])
    train_ids = {str(s["survey_id"]) for s in train_surveys if s.get("survey_id")}
    eval_ids = {str(s["survey_id"]) for s in eval_surveys if s.get("survey_id")}

    validate_no_leakage(train_ids, eval_ids)

    excluded = {
        str(survey_id)
        for survey_id in (data.get("leakage_prevention") or {}).get(
            "exclude_survey_ids_from_training", []
        )
    }
    leaked_excluded = train_ids & excluded
    if leaked_excluded:
        raise ValueError(
            "Manifest leakage: eval/excluded surveys are present in training: "
            f"{sorted(leaked_excluded)}"
        )

    return ManifestSplit(
        preset_id=str(data.get("preset_id") or preset_id),
        train_ids=train_ids,
        eval_ids=eval_ids,
        train_files={str(s["file"]) for s in train_surveys if s.get("file")},
        eval_files={str(s["file"]) for s in eval_surveys if s.get("file")},
        train_surveys=train_surveys,
        eval_surveys=eval_surveys,
        manifest_path=manifest_path,
    )


def validate_no_leakage(
    anchor_survey_ids: set[str] | list[str] | tuple[str, ...],
    eval_survey_ids: set[str] | list[str] | tuple[str, ...],
) -> None:
    """アンカー/学習に使う survey_id と eval survey_id の交差を禁止する。"""
    anchor_ids = {str(s) for s in anchor_survey_ids}
    eval_ids = {str(s) for s in eval_survey_ids}
    overlap = anchor_ids & eval_ids
    if overlap:
        raise ValueError(f"Survey leakage detected: {sorted(overlap)}")


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
    prediction_evaluations: dict


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

    best_survey = next(
        (s for s in report["matched_surveys"]
         if s["source"] == report["best_match_source"]),
        None,
    )
    if best_survey is None:
        logger.error(
            "auto_compare: best_match_source=%r not found in matched_surveys (sim=%s)",
            report.get("best_match_source"),
            record.simulation_id,
        )
        return None

    repo = ValidationRepository(session)
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


def _direction_from_delta(delta: float) -> str:
    if delta > 0:
        return "up"
    if delta < 0:
        return "down"
    return "flat"


def evaluate_distribution_prediction(
    predicted_payload: dict[str, Any],
    actual_payload: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate raw/weighted/calibrated/market distributions against actual data."""
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

    best_variant = min(by_variant, key=lambda item: by_variant[item]["brier"]) if by_variant else None
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
        probability = max(
            0.0,
            min(1.0, _as_float(item.get("probability"), _as_float(item.get("scenario_score"), 0.0))),
        )
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

    actuals_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in actuals:
        key = (
            str(item.get("intervention_id") or ""),
            str(item.get("metric") or ""),
        )
        actuals_by_key.setdefault(key, []).append(item)

    rows: list[dict[str, Any]] = []
    for prediction in predictions:
        key = (
            str(prediction.get("intervention_id") or ""),
            str(prediction.get("metric") or ""),
        )
        matched_actuals = actuals_by_key.get(key)
        if not matched_actuals:
            continue
        expected_delta = _as_float(prediction.get("expected_delta"))
        actual_deltas = [
            _as_float(actual.get("actual_delta"), _as_float(actual.get("signed_delta")))
            for actual in matched_actuals
        ]
        actual_delta = sum(actual_deltas) / len(actual_deltas)
        predicted_direction = _normalize_direction(prediction.get("direction"))
        actual_direction = _direction_from_delta(actual_delta)
        if actual_direction == "flat":
            actual_direction = next(
                (
                    direction
                    for direction in (
                        _normalize_direction(actual.get("direction"))
                        for actual in matched_actuals
                    )
                    if direction != "flat"
                ),
                "flat",
            )
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
    """Register a cross-type prediction evaluation record."""
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
                bucket.setdefault("calibration_improvements", []).append(metrics["calibration_improvement"])
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
