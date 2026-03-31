"""感度分析モジュール: 異なるランダムシードでシミュレーションを複数回実行し、結果の安定性を検証する。

LLM呼び出しを伴うためコストが大きく、オプトイン機能として実装する。
"""

import math
import logging
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


async def run_sensitivity_check(
    agents: list[dict],
    theme: str,
    n_seeds: int = 3,
    activation_fn: Callable[..., Awaitable[dict]] | None = None,
) -> dict:
    """異なるランダムシードでアクティベーションを複数回実行し、結果の安定性を検証する。

    Args:
        agents: エージェントのリスト。
        theme: シミュレーションのテーマ。
        n_seeds: 実行するシード数（デフォルト3）。
        activation_fn: アクティベーション関数。None の場合は run_activation を使用。
                       テスト時はモック関数を注入する。

    Returns:
        {
            "robustness_score": float,   # 1 - 正規化最大偏差 (0-1, 高い方が安定)
            "stability": str,            # "stable" | "unstable"
            "max_deviation": float,      # 全スタンスの最大標準偏差
            "distributions": list[dict], # 各シードのスタンス分布
            "n_seeds": int,
        }
    """
    if activation_fn is None:
        from src.app.services.society.activation_layer import run_activation
        activation_fn = run_activation

    # 各シードでアクティベーションを実行してスタンス分布を収集
    distributions: list[dict] = []
    for seed_idx in range(n_seeds):
        logger.info("sensitivity_analysis: seed %d / %d", seed_idx + 1, n_seeds)
        result = await activation_fn(agents, theme, seed=seed_idx)
        dist = result.get("stance_distribution", {})
        distributions.append(dist)

    # 全スタンスキーのユニオンを取得
    all_stances: set[str] = set()
    for dist in distributions:
        all_stances.update(dist.keys())

    # 各スタンスについて標準偏差を計算
    std_devs: dict[str, float] = {}
    for stance in all_stances:
        values = [dist.get(stance, 0.0) for dist in distributions]
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std_devs[stance] = math.sqrt(variance)

    # max_deviation = 全スタンスの標準偏差の最大値
    max_deviation = max(std_devs.values()) if std_devs else 0.0

    # robustness_score = max(0, 1 - max_deviation / 0.10)
    # 0.10以上の標準偏差はスコア0 (10%以上の変動で不安定と判定)
    _STABILITY_THRESHOLD = 0.10
    robustness_score = max(0.0, 1.0 - max_deviation / _STABILITY_THRESHOLD)

    # stability: max_deviation > 0.10 なら "unstable"
    stability = "unstable" if max_deviation > _STABILITY_THRESHOLD else "stable"

    return {
        "robustness_score": robustness_score,
        "stability": stability,
        "max_deviation": max_deviation,
        "distributions": distributions,
        "n_seeds": n_seeds,
    }
