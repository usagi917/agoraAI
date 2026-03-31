"""LLM→Human バイアス補正モジュール

LLMエージェントの系統的バイアスを検出・補正する。

- compute_bias_profile       : 比較データからバイアスプロファイルを構築
- apply_transfer_correction  : バイアスプロファイルによる分布補正
- compute_transfer_uncertainty: トランスファー補正による追加の不確実性を推定
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import TypedDict


from src.app.services.society.constants import STANCE_ORDER as STANCES


class StanceBias(TypedDict):
    mean_deviation: float
    sample_count: int
    std_deviation: float


BiasProfile = dict[str, dict[str, StanceBias]]


def compute_bias_profile(comparisons: list[dict]) -> BiasProfile:
    """比較データからカテゴリ別・スタンス別のバイアスプロファイルを構築する。

    各比較データの (sim - actual) の平均/標準偏差/件数を算出。
    """
    # category -> stance -> list of deviations
    deviations: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for comp in comparisons:
        category = comp["theme_category"]
        sim_dist = comp["simulated_distribution"]
        actual_dist = comp["actual_distribution"]

        for stance in STANCES:
            sim_val = sim_dist.get(stance, 0.0)
            actual_val = actual_dist.get(stance, 0.0)
            deviations[category][stance].append(sim_val - actual_val)

    profile: BiasProfile = {}
    for category, stance_devs in deviations.items():
        profile[category] = {}
        for stance in STANCES:
            devs = stance_devs.get(stance, [])
            n = len(devs)
            if n == 0:
                profile[category][stance] = StanceBias(
                    mean_deviation=0.0, sample_count=0, std_deviation=0.0
                )
                continue

            mean_dev = sum(devs) / n
            if n > 1:
                variance = sum((d - mean_dev) ** 2 for d in devs) / (n - 1)
                std_dev = math.sqrt(variance)
            else:
                std_dev = 0.0

            profile[category][stance] = StanceBias(
                mean_deviation=mean_dev,
                sample_count=n,
                std_deviation=std_dev,
            )

    return profile


def apply_transfer_correction(
    distribution: dict[str, float],
    bias_profile: BiasProfile,
    theme_category: str,
    min_samples: int = 3,
) -> dict[str, float]:
    """バイアスプロファイルによる分布補正。

    shrinkage 係数: alpha = min(1.0, sample_count / 20)
    補正: corrected[stance] = max(0, dist[stance] - alpha * mean_deviation[stance])
    再正規化して合計1.0に。
    """
    if theme_category not in bias_profile:
        return dict(distribution)

    category_profile = bias_profile[theme_category]

    # min_samples 未満の場合は補正しない
    sample_counts = [
        category_profile.get(s, {}).get("sample_count", 0)
        for s in STANCES
    ]
    if all(c < min_samples for c in sample_counts):
        return dict(distribution)

    corrected: dict[str, float] = {}
    for stance in STANCES:
        bias = category_profile.get(stance)
        if not bias or bias["sample_count"] < min_samples:
            corrected[stance] = distribution.get(stance, 0.0)
            continue

        alpha = min(1.0, bias["sample_count"] / 20.0)
        raw = distribution.get(stance, 0.0) - alpha * bias["mean_deviation"]
        corrected[stance] = max(0.0, raw)

    # 再正規化
    total = sum(corrected.values())
    if total > 0:
        corrected = {k: v / total for k, v in corrected.items()}

    return corrected


def compute_transfer_uncertainty(
    bias_profile: BiasProfile,
    theme_category: str,
) -> float:
    """トランスファー補正による追加の不確実性を推定する。

    カテゴリ別のスタンスズレの標準偏差の平均。
    """
    if theme_category not in bias_profile:
        return 1.0

    category_profile = bias_profile[theme_category]
    stds: list[float] = []
    counts: list[int] = []

    for stance in STANCES:
        bias = category_profile.get(stance)
        if bias:
            stds.append(bias["std_deviation"])
            counts.append(bias["sample_count"])

    if not stds:
        return 1.0

    avg_std = sum(stds) / len(stds)
    avg_count = sum(counts) / len(counts) if counts else 1

    # サンプルが少ないほど不確実性が高い
    count_factor = 1.0 / math.sqrt(max(avg_count, 1))

    return avg_std + count_factor
