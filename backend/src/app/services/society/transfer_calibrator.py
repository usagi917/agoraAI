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


_TIME_DECAY_HALF_LIFE = 90.0  # 日数


def compute_bias_profile(comparisons: list[dict]) -> BiasProfile:
    """比較データからカテゴリ別・スタンス別のバイアスプロファイルを構築する。

    各比較データの (sim - actual) の時間減衰付き加重平均/標準偏差/件数を算出。
    days_since フィールドがあれば指数減衰 (半減期90日) で重み付け。
    """
    # category -> stance -> list of (deviation, weight)
    weighted_devs: dict[str, dict[str, list[tuple[float, float]]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for comp in comparisons:
        category = comp["theme_category"]
        sim_dist = comp["simulated_distribution"]
        actual_dist = comp["actual_distribution"]

        # 時間減衰ウェイト
        days_since = comp.get("days_since")
        if days_since is not None and days_since > 0:
            w = math.exp(-days_since * math.log(2) / _TIME_DECAY_HALF_LIFE)
        else:
            w = 1.0

        for stance in STANCES:
            sim_val = sim_dist.get(stance, 0.0)
            actual_val = actual_dist.get(stance, 0.0)
            weighted_devs[category][stance].append((sim_val - actual_val, w))

    profile: BiasProfile = {}
    for category, stance_devs in weighted_devs.items():
        profile[category] = {}
        for stance in STANCES:
            pairs = stance_devs.get(stance, [])
            n = len(pairs)
            if n == 0:
                profile[category][stance] = StanceBias(
                    mean_deviation=0.0, sample_count=0, std_deviation=0.0
                )
                continue

            total_w = sum(w for _, w in pairs)
            mean_dev = sum(d * w for d, w in pairs) / total_w if total_w > 0 else 0.0

            if n > 1 and total_w > 0:
                variance = sum(w * (d - mean_dev) ** 2 for d, w in pairs) / total_w
                std_dev = math.sqrt(variance)
            else:
                std_dev = 0.0

            profile[category][stance] = StanceBias(
                mean_deviation=mean_dev,
                sample_count=n,
                std_deviation=std_dev,
            )

    return profile


def _compute_grand_mean(bias_profile: BiasProfile, stance: str) -> float:
    """全カテゴリを通じたグランド平均バイアスを計算。"""
    vals = []
    for cat_profile in bias_profile.values():
        bias = cat_profile.get(stance)
        if bias and bias["sample_count"] > 0:
            vals.append(bias["mean_deviation"])
    return sum(vals) / len(vals) if vals else 0.0


def apply_transfer_correction(
    distribution: dict[str, float],
    bias_profile: BiasProfile,
    theme_category: str,
    min_samples: int = 3,
) -> dict[str, float]:
    """James-Stein shrinkage によるバイアス補正。

    shrink 先: 全カテゴリのグランド平均
    shrinkage 係数: α = 1 - ((k-2) * σ² / Σ(bias_j - grand_mean)²)
    clamp [0, 1]。データ不足時はグランド平均にフォールバック。
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

        grand_mean = _compute_grand_mean(bias_profile, stance)

        # James-Stein shrinkage
        k = max(len(bias_profile), 1)
        sigma_sq = bias["std_deviation"] ** 2
        diff_sq = (bias["mean_deviation"] - grand_mean) ** 2

        if k >= 3 and diff_sq > 0:
            alpha = max(0.0, min(1.0, 1.0 - (k - 2) * sigma_sq / (diff_sq * k)))
            # shrink された補正量: グランド平均 + α * (カテゴリ平均 - グランド平均)
            effective_bias = grand_mean + alpha * (bias["mean_deviation"] - grand_mean)
        else:
            # k < 3 or diff_sq == 0: 旧フォールバック (linear shrinkage)
            alpha = min(1.0, bias["sample_count"] / 20.0)
            effective_bias = alpha * bias["mean_deviation"]
        raw = distribution.get(stance, 0.0) - effective_bias
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
