"""感度分析モジュール: 異なるランダムシードでシミュレーションを複数回実行し、結果の安定性を検証する。

LLM呼び出しを伴うためコストが大きく、オプトイン機能として実装する。
"""

import asyncio
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


async def run_provider_ensemble(
    agents: list[dict],
    theme: str,
    providers: list[str] | None = None,
    activation_fn: Callable[..., Awaitable[dict]] | None = None,
) -> dict:
    """異なる LLM プロバイダでアクティベーションを実行し、アンサンブル集約する。

    Args:
        agents: エージェントのリスト。
        theme: シミュレーションのテーマ。
        providers: プロバイダ名のリスト。None の場合は ["default"]。
        activation_fn: アクティベーション関数。provider kwarg でプロバイダを指定される。

    Returns:
        {
            "ensemble_distribution": dict,   # 加重平均された分布
            "provider_distributions": list,  # 各プロバイダの分布
            "weights": dict,                 # プロバイダごとの重み
            "agreement_score": float,        # プロバイダ間一致度 (0-1)
        }
    """
    if providers is None:
        providers = ["default"]

    if activation_fn is None:
        from src.app.services.society.activation_layer import run_activation
        activation_fn = run_activation

    # 各プロバイダでアクティベーションを並列実行
    async def _run_one(provider: str) -> tuple[str, dict]:
        logger.info("provider_ensemble: running provider=%s", provider)
        result = await activation_fn(agents, theme)
        dist = result.get("aggregation", {}).get("stance_distribution", {})
        return (provider, dist)

    provider_results: list[tuple[str, dict]] = list(
        await asyncio.gather(*[_run_one(p) for p in providers])
    )

    if not provider_results:
        return {
            "ensemble_distribution": {},
            "provider_distributions": [],
            "weights": {},
            "agreement_score": 1.0,
        }

    # 全スタンスキーの収集
    all_stances: set[str] = set()
    for _, dist in provider_results:
        all_stances.update(dist.keys())

    n = len(provider_results)
    dists_list = [dist for _, dist in provider_results]

    # プロバイダ間一致度: 1 - 平均ペアワイズ TVD (Total Variation Distance)
    agreement_score = 1.0
    if n >= 2:
        # 各プロバイダの平均 TVD を計算（コンセンサスから遠いプロバイダは低重み）
        avg_tvd_per_provider: dict[str, float] = {}
        for i, (provider, _) in enumerate(provider_results):
            tvds = []
            for j in range(n):
                if i == j:
                    continue
                d = sum(abs(dists_list[i].get(s, 0.0) - dists_list[j].get(s, 0.0)) for s in all_stances) / 2.0
                tvds.append(d)
            avg_tvd_per_provider[provider] = sum(tvds) / len(tvds)

        # 逆 TVD で重み付け: コンセンサスに近いプロバイダほど高い重み
        inv_tvds = {p: 1.0 / (tvd + 1e-8) for p, tvd in avg_tvd_per_provider.items()}
        inv_total = sum(inv_tvds.values())
        weights = {p: v / inv_total for p, v in inv_tvds.items()}

        avg_distance = sum(avg_tvd_per_provider.values()) / len(avg_tvd_per_provider)
        agreement_score = max(0.0, 1.0 - avg_distance)
    else:
        weights = {provider_results[0][0]: 1.0}

    # 加重平均で ensemble_distribution を算出
    ensemble: dict[str, float] = {s: 0.0 for s in all_stances}
    for provider, dist in provider_results:
        w = weights[provider]
        for stance in all_stances:
            ensemble[stance] += dist.get(stance, 0.0) * w

    # 正規化
    total = sum(ensemble.values())
    if total > 0:
        ensemble = {k: v / total for k, v in ensemble.items()}

    return {
        "ensemble_distribution": ensemble,
        "provider_distributions": [
            {"provider": p, "distribution": d} for p, d in provider_results
        ],
        "weights": weights,
        "agreement_score": agreement_score,
    }
