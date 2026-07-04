"""Step 11: MVP カテゴリ拡張 — economy/security の精度検証とリリースゲート

目的:
  economy / security の 2 カテゴリを対象に、
  deterministic gate runner の結果と baseline スナップショットを比較して
  相対改善率（EMD 30% / MAE 20%）を判定し、リリースゲート可否を出力する。

主要関数:
  compute_mae:                    Mean Absolute Error（分布間）
  compute_rps:                    Ranked Probability Score（序数分布 CDF ベース）
  build_category_accuracy_report: カテゴリ別精度レポート（改善フラグ含む）
  check_release_gate:             全カテゴリ改善フラグ → release ゲート判定
  run_mvp_category_validation:    fixture dir + baseline → E2E MVP 検証
  load_baseline_snapshot:         YAML baseline スナップショットの読み込み

定数:
  MIN_RELATIVE_EMD_IMPROVEMENT = 0.30  EMD を baseline 比で 30% 以上改善
  MIN_RELATIVE_MAE_IMPROVEMENT = 0.20  MAE を baseline 比で 20% 以上改善
  MVP_CATEGORIES = ["economy", "security"]
  N_LIVE_RUNS = 5  release 判定で必要な最低 live 実行回数

Unknown カテゴリのガード:
  category="unknown" の場合、改善率の計算対象外とし、
  release_gate_eligible=False を設定する。
  check_release_gate では unknown カテゴリを除外して判定する。
  除外後に対象カテゴリが 0 件の場合は "inconclusive" を返す。
"""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

import yaml

from src.app.evaluation.gate_runner import run_deterministic_gate
from src.app.services.society.baseline_comparator import (
    compute_relative_improvement as _compute_relative_improvement,
)

# =============================================================
# 定数
# =============================================================

#: EMD の baseline 比最小相対改善率（リリースゲート条件）
MIN_RELATIVE_EMD_IMPROVEMENT: float = 0.30

#: 属性別 MAE の baseline 比最小相対改善率（リリースゲート条件）
MIN_RELATIVE_MAE_IMPROVEMENT: float = 0.20

#: MVP 対象カテゴリ（economy と security の 2 カテゴリ）
MVP_CATEGORIES: list[str] = ["economy", "security"]

#: リリース判定で必要な最低 live 実行回数
N_LIVE_RUNS: int = 5


# =============================================================
# 1. compute_mae — Mean Absolute Error
# =============================================================


def compute_mae(
    simulated: dict[str, float],
    actual: dict[str, float],
) -> float:
    """2 つのスタンス分布間の Mean Absolute Error (MAE) を計算する。

    各スタンスキーについて |sim_k - actual_k| を計算し、
    全キーの和をキー数（union）で割った値を返す。
    片方にしか存在しないキーは 0 として扱う。

    Args:
        simulated: シミュレーション分布 {スタンス: 確率}
        actual:    実績分布 {スタンス: 確率}

    Returns:
        MAE (float)。分布が空の場合は 0.0。
    """
    all_keys = set(simulated) | set(actual)
    if not all_keys:
        return 0.0

    total_abs_error = sum(
        abs(simulated.get(k, 0.0) - actual.get(k, 0.0))
        for k in all_keys
    )
    return total_abs_error / len(all_keys)


# =============================================================
# 2. compute_rps — Ranked Probability Score
# =============================================================


def compute_rps(
    simulated: dict[str, float],
    actual: dict[str, float],
    stance_order: list[str],
) -> float:
    """Ranked Probability Score (RPS) を計算する。

    RPS = 1/(K-1) * Σ_{k=1}^{K} (CDF_pred(k) - CDF_obs(k))^2

    序数スタンスの CDF を順に累積して 2 乗誤差の和を取り、
    (K-1) で正規化する（Gneiting & Raftery 2007, JASA）。

    Args:
        simulated:    シミュレーション分布
        actual:       実績分布
        stance_order: スタンスの序数順リスト（例: ["賛成",...,"反対"]）

    Returns:
        RPS (float)。stance_order が 1 要素以下の場合は 0.0。
    """
    K = len(stance_order)
    if K <= 1:
        return 0.0

    cdf_sim = 0.0
    cdf_act = 0.0
    total = 0.0
    for stance in stance_order:
        cdf_sim += simulated.get(stance, 0.0)
        cdf_act += actual.get(stance, 0.0)
        total += (cdf_sim - cdf_act) ** 2

    return total / (K - 1)


# =============================================================
# 3. build_category_accuracy_report
# =============================================================


class CategoryAccuracyReport(TypedDict):
    category: str
    gate: str                        # "pass" | "fail" | "inconclusive"
    avg_emd: float | None
    avg_jsd: float | None
    avg_brier: float | None
    baseline_emd: float | None
    emd_improvement: float | None    # (baseline - current) / baseline
    emd_improvement_flag: bool       # True iff emd_improvement >= MIN_RELATIVE_EMD_IMPROVEMENT
    mae_improvement: float | None    # (baseline_mae - current_mae) / baseline_mae
    mae_improvement_flag: bool       # True iff mae_improvement >= MIN_RELATIVE_MAE_IMPROVEMENT
    release_gate_eligible: bool      # True iff both flags are True AND category != "unknown"


def build_category_accuracy_report(
    category: str,
    gate_result: dict,
    baseline_metrics: dict | None,
) -> CategoryAccuracyReport:
    """カテゴリ別精度レポートを生成する。

    gate_runner の結果と baseline スナップショットから
    EMD/MAE の相対改善率を計算し、改善フラグと release gate 可否を付与する。

    Args:
        category:         テーマカテゴリ名（"economy", "security", "unknown" 等）
        gate_result:      run_deterministic_gate() または run_ci_gate_check() の結果辞書。
                          "avg_emd", "avg_jsd", "avg_brier", "gate" を使用する。
                          "avg_mae" があれば MAE 改善率の計算に使用する。
        baseline_metrics: baseline スナップショットのカテゴリ別メトリクス辞書。
                          {"emd": float|None, "mae_pp": float|None, ...}。
                          None の場合は改善率を計算できない（全 None 扱い）。

    Returns:
        CategoryAccuracyReport
    """
    # baseline から参照値を取得
    baseline_emd: float | None = None
    baseline_mae: float | None = None
    if baseline_metrics is not None:
        baseline_emd = baseline_metrics.get("emd")
        baseline_mae = baseline_metrics.get("mae_pp")

    # gate_result から現在の指標を取得
    current_emd: float | None = gate_result.get("avg_emd")
    current_mae: float | None = gate_result.get("avg_mae")

    # 相対改善率
    emd_improvement = _compute_relative_improvement(baseline_emd, current_emd)
    mae_improvement = _compute_relative_improvement(baseline_mae, current_mae)

    # 改善フラグ
    emd_flag = (
        emd_improvement is not None
        and emd_improvement >= MIN_RELATIVE_EMD_IMPROVEMENT
    )
    mae_flag = (
        mae_improvement is not None
        and mae_improvement >= MIN_RELATIVE_MAE_IMPROVEMENT
    )

    # unknown カテゴリはリリースゲート対象外
    is_unknown = (category == "unknown")
    release_eligible = (not is_unknown) and emd_flag and mae_flag

    return CategoryAccuracyReport(
        category=category,
        gate=gate_result.get("gate", "inconclusive"),
        avg_emd=current_emd,
        avg_jsd=gate_result.get("avg_jsd"),
        avg_brier=gate_result.get("avg_brier"),
        baseline_emd=baseline_emd,
        emd_improvement=emd_improvement,
        emd_improvement_flag=emd_flag,
        mae_improvement=mae_improvement,
        mae_improvement_flag=mae_flag,
        release_gate_eligible=release_eligible,
    )


# =============================================================
# 4. check_release_gate
# =============================================================


class ReleaseGateResult(TypedDict):
    overall: str                                  # "pass" | "fail" | "inconclusive"
    categories: dict[str, CategoryAccuracyReport]  # カテゴリ名 → レポート
    category_count: int


def check_release_gate(
    category_reports: list[CategoryAccuracyReport],
) -> ReleaseGateResult:
    """全カテゴリの精度レポートからリリースゲートの判定を行う。

    判定ルール:
    - unknown カテゴリは判定対象から除外する
    - 対象カテゴリが 0 件 → "inconclusive"
    - 全対象カテゴリが release_gate_eligible=True → "pass"
    - いずれかが release_gate_eligible=False → "fail"

    Args:
        category_reports: CategoryAccuracyReport のリスト

    Returns:
        ReleaseGateResult
    """
    categories: dict[str, CategoryAccuracyReport] = {
        r["category"]: r for r in category_reports
    }

    # unknown を除外した対象カテゴリ
    eligible_reports = [r for r in category_reports if r["category"] != "unknown"]

    if not eligible_reports:
        return ReleaseGateResult(
            overall="inconclusive",
            categories=categories,
            category_count=len(category_reports),
        )

    if all(r["release_gate_eligible"] for r in eligible_reports):
        overall = "pass"
    else:
        overall = "fail"

    return ReleaseGateResult(
        overall=overall,
        categories=categories,
        category_count=len(category_reports),
    )


# =============================================================
# 5. load_baseline_snapshot
# =============================================================


def load_baseline_snapshot(snapshot_path: str) -> dict[str, dict]:
    """YAML baseline スナップショットファイルを読み込み、
    カテゴリ別メトリクス辞書を返す。

    期待するファイル構造:
        baseline_metrics:
          economy:
            emd: 0.10
            jsd: 0.08
            brier: 0.15
            mae_pp: 0.05
            ...
          security:
            ...

    Args:
        snapshot_path: YAML ファイルのパス

    Returns:
        {カテゴリ名: メトリクス辞書}。
        ファイルが存在しないか、baseline_metrics キーがない場合は空辞書を返す。
    """
    path = Path(snapshot_path)
    if not path.exists():
        return {}

    try:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        return {}

    if not isinstance(data, dict):
        return {}

    return data.get("baseline_metrics") or {}


# =============================================================
# 6. run_mvp_category_validation — E2E
# =============================================================


class MVPValidationResult(TypedDict):
    overall: str                                   # "pass" | "fail" | "inconclusive"
    categories: dict[str, CategoryAccuracyReport]  # カテゴリ名 → レポート
    category_count: int
    fixture_count: int


def run_mvp_category_validation(
    fixture_dir: str,
    baseline_snapshot: dict[str, dict],
) -> MVPValidationResult:
    """MVP カテゴリ（economy / security）の E2E 精度検証を実行する。

    指定ディレクトリの *_gate.yaml を読み込み、
    各カテゴリの精度指標を算出して baseline スナップショットと比較し、
    release ゲートの判定を返す。

    判定フロー:
    1. *_gate.yaml を列挙して run_deterministic_gate() を実行
    2. 各カテゴリについて build_category_accuracy_report() でレポート生成
    3. check_release_gate() で全体判定

    Args:
        fixture_dir:        gate fixture YAML が置かれたディレクトリパス
        baseline_snapshot:  load_baseline_snapshot() または直接構築した辞書。
                            {カテゴリ名: {"emd": ..., "mae_pp": ...}}

    Returns:
        MVPValidationResult
    """
    fixture_dir_path = Path(fixture_dir)
    fixture_files = sorted(fixture_dir_path.glob("*_gate.yaml"))

    if not fixture_files:
        return MVPValidationResult(
            overall="inconclusive",
            categories={},
            category_count=0,
            fixture_count=0,
        )

    category_reports: list[CategoryAccuracyReport] = []

    for fixture_path in fixture_files:
        gate_result = run_deterministic_gate(fixture_path)
        category = gate_result["theme_category"] or fixture_path.stem.replace("_gate", "")

        # baseline メトリクスを取得（カテゴリが一致するものを使用）
        baseline_metrics = baseline_snapshot.get(category)

        report = build_category_accuracy_report(
            category=category,
            gate_result=gate_result,
            baseline_metrics=baseline_metrics,
        )
        category_reports.append(report)

    release_gate_result = check_release_gate(category_reports)

    return MVPValidationResult(
        overall=release_gate_result["overall"],
        categories=release_gate_result["categories"],
        category_count=release_gate_result["category_count"],
        fixture_count=len(fixture_files),
    )
