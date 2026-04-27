"""レトロダクション検証パイプライン

歴史的な調査結果（YAML fixture）に対してシミュレーション結果を比較し、
JSD/Brier でバックテストを行う。CI 統合用のリグレッション検知も提供する。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.app.evaluation.accuracy_spec import CI_REGRESSION_THRESHOLD
from src.app.evaluation.metrics import _jsd


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
    """単一ケースを JSD と Brier で評価する.

    Args:
        predicted: シミュレーションで得られたスタンス分布
        observed: 歴史的調査の実際のスタンス分布

    Returns:
        {"jsd": float, "brier": float | None}
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

    return {"jsd": jsd_value, "brier": brier}


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
