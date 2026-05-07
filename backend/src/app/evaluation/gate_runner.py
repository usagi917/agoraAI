"""決定論的ゲートランナー

YAML fixture を読み込み、EMD/JSD/Brier を計算して gate 判定を行う。
DB セッションを使わず fixture ファイルのみで完全決定論的に動作する。

主要な用途:
- CI での再現性保証（同一 fixture + 同一 seed → 同一結果）
- baseline snapshot との比較
- live 実行結果との乖離 warning 発行

live 実行結果との乖離チェック:
- |fixture_avg_emd - live_avg_emd| > MAX_LIVE_REPLAY_GAP (0.03) で RuntimeWarning
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, TypedDict

import yaml

from src.app.evaluation.metrics import _jsd
from src.app.services.society.validation_pipeline import (
    build_validation_summary,
)
from src.app.utils.distribution_metrics import earth_movers_distance

# EMD 基準の live replay 最大許容乖離
MAX_LIVE_REPLAY_GAP: float = 0.03


class GateCaseResult(TypedDict):
    case_id: str
    theme: str
    survey_source: str
    emd: float | None
    jsd: float | None
    brier_score: float | None
    gate_eligible: bool


class GateRunnerResult(TypedDict):
    gate: str                       # "pass" | "fail" | "inconclusive"
    theme_category: str
    avg_emd: float | None
    avg_jsd: float | None
    avg_brier: float | None
    case_results: list[GateCaseResult]
    total_count: int
    validated_count: int
    gate_eligible_count: int
    seed: int | None
    live_replay_warning: bool


def load_gate_fixture(path: str | Path) -> dict[str, Any]:
    """gate fixture YAML を読み込む。

    Args:
        path: gate fixture YAML のパス

    Returns:
        fixture 辞書（preset_id / theme_category / seed / cases を含む）

    Raises:
        FileNotFoundError: ファイルが存在しない場合
    """
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _compute_brier(
    simulated: dict[str, float],
    actual: dict[str, float],
) -> float:
    """全分布 Brier スコアを計算する: Σ(p_i - a_i)²"""
    all_keys = set(simulated) | set(actual)
    return sum(
        (simulated.get(k, 0.0) - actual.get(k, 0.0)) ** 2
        for k in all_keys
    )


def _compute_case_metrics(case: dict[str, Any]) -> GateCaseResult:
    """1 ケースの EMD/JSD/Brier を計算する。

    actual_distribution がない場合は各メトリクスを None で返す。
    """
    simulated: dict[str, float] = case.get("simulated_distribution") or {}
    actual: dict[str, float] | None = case.get("actual_distribution")

    if not actual:
        return GateCaseResult(
            case_id=case.get("case_id", ""),
            theme=case.get("theme", ""),
            survey_source=case.get("survey_source", ""),
            emd=None,
            jsd=None,
            brier_score=None,
            gate_eligible=case.get("gate_eligible", True),
        )

    return GateCaseResult(
        case_id=case.get("case_id", ""),
        theme=case.get("theme", ""),
        survey_source=case.get("survey_source", ""),
        emd=earth_movers_distance(simulated, actual),
        jsd=_jsd(simulated, actual),
        brier_score=_compute_brier(simulated, actual),
        gate_eligible=case.get("gate_eligible", True),
    )


def run_deterministic_gate(
    fixture_path: str | Path,
    seed: int | None = None,
) -> GateRunnerResult:
    """fixture YAML から決定論的ゲート判定を実行する。

    fixture ベースの計算はすべて確定的であり、seed は結果に影響しない。
    seed は将来の確率的要素導入時に備えて受け取り、結果に記録する。

    内部で build_validation_summary() を呼び出してゲート判定を行う。

    Args:
        fixture_path: gate fixture YAML のパス
        seed: 再現性確保用シード値（現在は計算結果に影響しない）

    Returns:
        GateRunnerResult

    Raises:
        FileNotFoundError: fixture ファイルが存在しない場合
    """
    data = load_gate_fixture(fixture_path)

    theme_category: str = data.get("theme_category") or ""
    cases: list[dict[str, Any]] = data.get("cases") or []

    # unknown カテゴリは survey 比較対象外のため gate 判定不可
    if theme_category == "unknown":
        return GateRunnerResult(
            gate="inconclusive",
            theme_category=theme_category,
            avg_emd=None,
            avg_jsd=None,
            avg_brier=None,
            case_results=[],
            total_count=len(cases),
            validated_count=0,
            gate_eligible_count=0,
            seed=seed,
            live_replay_warning=False,
        )

    if not cases:
        return GateRunnerResult(
            gate="inconclusive",
            theme_category=theme_category,
            avg_emd=None,
            avg_jsd=None,
            avg_brier=None,
            case_results=[],
            total_count=0,
            validated_count=0,
            gate_eligible_count=0,
            seed=seed,
            live_replay_warning=False,
        )

    case_results = [_compute_case_metrics(c) for c in cases]

    # build_validation_summary が期待する形式に変換
    records_data = [
        {
            "status": "validated" if cr["emd"] is not None else "report_only",
            "gate_eligible": cr["gate_eligible"],
            "emd": cr["emd"],
            "jsd": cr["jsd"],
            "brier_score": cr["brier_score"],
        }
        for cr in case_results
    ]

    summary = build_validation_summary(
        records_data,
        theme_category=theme_category or None,
    )

    return GateRunnerResult(
        gate=summary["gate"],
        theme_category=theme_category,
        avg_emd=summary["avg_emd"],
        avg_jsd=summary["avg_jsd"],
        avg_brier=summary["avg_brier"],
        case_results=case_results,
        total_count=summary["total_count"],
        validated_count=summary["validated_count"],
        gate_eligible_count=summary["gate_eligible_count"],
        seed=seed,
        live_replay_warning=False,
    )


class CIGateResult(TypedDict):
    overall: str                            # "pass" | "fail" | "inconclusive"
    categories: dict[str, GateRunnerResult]
    fixture_count: int


def run_ci_gate_check(
    fixture_dir: str | Path,
    seed: int | None = None,
) -> CIGateResult:
    """指定ディレクトリ内の全 *_gate.yaml fixture を実行し、CI ゲート判定を行う。

    判定ルール:
    - 全カテゴリが pass → overall = "pass"
    - いずれかが fail → overall = "fail"
    - fixture なし / 全カテゴリ inconclusive → overall = "inconclusive"

    Args:
        fixture_dir: gate fixture YAML ファイルが置かれているディレクトリ
        seed:        各 fixture 実行に渡すシード値

    Returns:
        CIGateResult
    """
    fixture_dir = Path(fixture_dir)
    fixture_files = sorted(fixture_dir.glob("*_gate.yaml"))

    if not fixture_files:
        return CIGateResult(overall="inconclusive", categories={}, fixture_count=0)

    categories: dict[str, GateRunnerResult] = {}
    for fixture_path in fixture_files:
        result = run_deterministic_gate(fixture_path, seed=seed)
        category = result["theme_category"] or fixture_path.stem.replace("_gate", "")
        categories[category] = result

    gates = [r["gate"] for r in categories.values()]
    if "fail" in gates:
        overall = "fail"
    elif all(g == "pass" for g in gates):
        overall = "pass"
    else:
        overall = "inconclusive"

    return CIGateResult(overall=overall, categories=categories, fixture_count=len(fixture_files))


def check_live_replay_gap(
    gate_result: GateRunnerResult,
    live_avg_emd: float | None,
    threshold: float = MAX_LIVE_REPLAY_GAP,
) -> bool:
    """live 実行の EMD と fixture replay の EMD を比較し、乖離が閾値を超えたら True を返す。

    乖離が閾値を超えた場合は RuntimeWarning も発行する。

    Args:
        gate_result: run_deterministic_gate() の結果
        live_avg_emd: live 実行の平均 EMD
        threshold: 許容乖離量（デフォルト: MAX_LIVE_REPLAY_GAP = 0.03）

    Returns:
        True = 乖離あり（gap > threshold）、False = 乖離なし
    """
    fixture_emd = gate_result["avg_emd"]
    if fixture_emd is None or live_avg_emd is None:
        return False

    gap = abs(fixture_emd - live_avg_emd)
    if gap > threshold:
        warnings.warn(
            f"Live replay gap detected: "
            f"fixture_emd={fixture_emd:.4f}, live_emd={live_avg_emd:.4f}, "
            f"gap={gap:.4f} > threshold={threshold} "
            f"(category={gate_result['theme_category']})",
            RuntimeWarning,
            stacklevel=2,
        )
        return True

    return False
