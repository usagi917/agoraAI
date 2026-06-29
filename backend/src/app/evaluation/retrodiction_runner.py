"""レトロダクション検証パイプライン

歴史的な調査結果（YAML fixture）に対してシミュレーション結果を比較し、
JSD/Brier/ECE でバックテストを行う。CI 統合用のリグレッション検知も提供する。
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from src.app.evaluation.accuracy_spec import CI_REGRESSION_THRESHOLD
from src.app.evaluation.metrics import _jsd


def _distribution_ece(
    predicted: dict[str, float],
    observed: dict[str, float],
    n_bins: int = 10,
) -> float | None:
    """分布間の Expected Calibration Error.

    予測分布の各カテゴリ確率を予測値、観測分布の対応確率を ground truth として
    bin 分割し、各 bin の平均 |predicted - observed| を頻度加重平均する。
    同一分布では 0、完全に外せば最大 1.0。
    """
    keys = set(predicted) | set(observed)
    if not keys:
        return None
    bins: list[list[tuple[float, float]]] = [[] for _ in range(n_bins)]
    bin_size = 1.0 / n_bins
    for k in keys:
        p = predicted.get(k, 0.0)
        o = observed.get(k, 0.0)
        idx = min(int(p / bin_size), n_bins - 1)
        bins[idx].append((p, o))
    n = len(keys)
    ece = 0.0
    for bin_items in bins:
        if not bin_items:
            continue
        bn = len(bin_items)
        avg_p = sum(p for p, _ in bin_items) / bn
        avg_o = sum(o for _, o in bin_items) / bn
        ece += (bn / n) * abs(avg_p - avg_o)
    return ece


def load_retrodiction_fixtures(path: str | Path) -> list[dict[str, Any]]:
    """YAML fixture から歴史的調査ケースを読み込む.

    Args:
        path: YAML ファイルのパス

    Returns:
        調査ケースの辞書リスト
    """
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("surveys", [])


def evaluate_case(
    predicted: dict[str, float],
    observed: dict[str, float],
) -> dict[str, float | None]:
    """単一ケースを JSD, Brier, ECE で評価する.

    Args:
        predicted: シミュレーションで得られたスタンス分布
        observed: 歴史的調査の実際のスタンス分布

    Returns:
        {"jsd": float, "brier": float | None, "ece": float | None}
    """
    jsd_value = _jsd(predicted, observed)

    # Brier Score: Σ(predicted_i - observed_i)^2 / n_categories
    all_keys = set(predicted) | set(observed)
    if all_keys:
        brier = sum(
            (predicted.get(k, 0.0) - observed.get(k, 0.0)) ** 2
            for k in all_keys
        ) / len(all_keys)
    else:
        brier = None

    ece = _distribution_ece(predicted, observed)

    return {"jsd": jsd_value, "brier": brier, "ece": ece}


def check_regression(
    current_jsd: float,
    baseline_jsd: float,
    threshold: float = CI_REGRESSION_THRESHOLD,
) -> bool:
    """JSD がベースラインから閾値以上悪化していないかチェックする.

    Args:
        current_jsd: 今回の JSD 値
        baseline_jsd: ベースラインの JSD 値
        threshold: 許容悪化量（デフォルト: CI_REGRESSION_THRESHOLD = 0.02）

    Returns:
        True = リグレッションなし（合格）, False = リグレッション検出（失敗）
    """
    return (current_jsd - baseline_jsd) < threshold


def run_batch(
    fixtures: list[dict[str, Any]],
    predictor: Callable[[dict[str, Any]], dict[str, float]],
) -> dict[str, Any]:
    """複数 fixture を一括評価する.

    Args:
        fixtures: 各ケースに `theme`, `stance_distribution`, `theme_category` を含む dict のリスト
        predictor: 1 ケースを受け取って予測分布を返す関数 (LLM/モック切替可能)

    Returns:
        {"cases": [{"theme", "jsd", "brier", "ece", ...}, ...], "summary": {"mean_jsd", "mean_brier", "mean_ece", "n"}}
    """
    cases: list[dict[str, Any]] = []
    for fixture in fixtures:
        observed = fixture.get("stance_distribution", {})
        predicted = predictor(fixture)
        metrics = evaluate_case(predicted, observed)
        cases.append({
            "theme": fixture.get("theme", ""),
            "theme_category": fixture.get("theme_category", ""),
            "predicted": predicted,
            "observed": observed,
            "jsd": metrics["jsd"],
            "brier": metrics["brier"],
            "ece": metrics["ece"],
        })

    n = len(cases)
    if n == 0:
        summary = {"mean_jsd": 0.0, "mean_brier": 0.0, "mean_ece": 0.0, "n": 0}
    else:
        jsd_values = [c["jsd"] for c in cases if c["jsd"] is not None]
        brier_values = [c["brier"] for c in cases if c["brier"] is not None]
        ece_values = [c["ece"] for c in cases if c["ece"] is not None]
        summary = {
            "mean_jsd": sum(jsd_values) / len(jsd_values) if jsd_values else 0.0,
            "mean_brier": sum(brier_values) / len(brier_values) if brier_values else 0.0,
            "mean_ece": sum(ece_values) / len(ece_values) if ece_values else 0.0,
            "n": n,
        }

    return {"cases": cases, "summary": summary}


def save_baseline(result: dict[str, Any], path: str | Path) -> None:
    """ベンチマーク結果を JSON で保存する.

    Args:
        result: run_batch の戻り値
        path: 出力ファイルパス
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


def _mock_predictor(case: dict[str, Any]) -> dict[str, float]:
    """軽量モック予測器: stance_distribution を平坦に近づけた値を返す.

    LLM コストなしで CI を通すためのデフォルト実装。
    """
    observed = case.get("stance_distribution", {})
    if not observed:
        return {}
    n = len(observed)
    uniform = 1.0 / n
    blend = 0.5
    # 平坦寄せ (uniform と observed の中点) で baseline JSD > 0 になるよう構成
    return {k: blend * v + (1.0 - blend) * uniform for k, v in observed.items()}


def main() -> None:
    """CLI エントリポイント.

    Examples:
        python -m src.app.evaluation.retrodiction_runner \
            --fixtures backend/tests/fixtures/survey_data_sample.yaml \
            --output evaluation_results/baseline_v0.json
    """
    parser = argparse.ArgumentParser(description="Retrodiction benchmark runner")
    parser.add_argument(
        "--fixtures",
        required=True,
        help="YAML fixture へのパス",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="出力 JSON ファイルパス",
    )
    args = parser.parse_args()

    fixtures = load_retrodiction_fixtures(args.fixtures)
    result = run_batch(fixtures, _mock_predictor)
    save_baseline(result, args.output)
    summary = result["summary"]
    print(
        f"baseline saved: n={summary['n']}, "
        f"mean_jsd={summary['mean_jsd']:.4f}, "
        f"mean_brier={summary['mean_brier']:.4f}, "
        f"mean_ece={summary['mean_ece']:.4f} -> {args.output}"
    )


if __name__ == "__main__":
    main()
