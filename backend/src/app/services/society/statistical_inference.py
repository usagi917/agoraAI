"""統計的推論モジュール

Society Simulation の出力を学術レベルに引き上げるための統計ユーティリティ。

- effective_sample_size       : 実効標本サイズ (Kish 1965)
- margin_of_error             : 誤差の余地（信頼区間の半幅）
- weighted_stance_distribution: 重み付きスタンス分布
- bootstrap_confidence_intervals: ブートストラップ信頼区間
- compute_poststratification_weights: 事後層化ウェイト（反復比例フィッティング）
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Optional


def effective_sample_size(weights: list[float]) -> float:
    """実効標本サイズを計算する (Kish 1965).

    n_eff = (Σw_i)^2 / Σ(w_i^2)

    Args:
        weights: 各エージェントのサンプリングウェイト (全て正の数)

    Returns:
        実効標本サイズ (float)

    Raises:
        ValueError: weights が空のとき
    """
    if not weights:
        raise ValueError("weights must not be empty")

    sum_w = sum(weights)
    sum_w2 = sum(w * w for w in weights)

    if sum_w2 == 0.0:
        raise ValueError("sum of squared weights is zero")

    return (sum_w ** 2) / sum_w2


def margin_of_error(
    proportion: float,
    n_eff: float,
    z: float = 1.96,
) -> float:
    """二項比率の誤差の余地 (MoE) を計算する.

    MoE = z * sqrt(p * (1 - p) / n_eff)

    Args:
        proportion: 比率 p (0 <= p <= 1)
        n_eff    : 実効標本サイズ
        z        : 正規分布の臨界値 (デフォルト 1.96 = 95% CI)

    Returns:
        MoE (float, >= 0)
    """
    if n_eff <= 0:
        raise ValueError("n_eff must be positive")

    variance = proportion * (1.0 - proportion) / n_eff
    return z * math.sqrt(variance)


def weighted_stance_distribution(
    responses: list[dict],
    weights: list[float],
) -> dict[str, float]:
    """重み付きスタンス分布を計算する.

    Args:
        responses: 各エージェントの応答辞書のリスト。'stance' キーを持つ。
        weights  : 各エージェントのサンプリングウェイト

    Returns:
        スタンス → 正規化された比率 の辞書。
        responses が空のとき空辞書を返す。
    """
    if not responses:
        return {}

    if len(responses) != len(weights):
        raise ValueError("responses and weights must have the same length")

    stance_weights: dict[str, float] = defaultdict(float)
    for resp, w in zip(responses, weights):
        stance = resp.get("stance", "")
        if stance:
            stance_weights[stance] += w

    total = sum(stance_weights.values())
    if total == 0.0:
        return {}

    return {stance: w / total for stance, w in stance_weights.items()}


def bootstrap_confidence_intervals(
    responses: list[dict],
    weights: list[float],
    n_bootstrap: int = 1000,
    ci: float = 0.95,
    seed: Optional[int] = None,
) -> dict[str, tuple[float, float]]:
    """ブートストラップ法でスタンス分布の信頼区間を計算する.

    Args:
        responses  : 各エージェントの応答辞書のリスト
        weights    : 各エージェントのサンプリングウェイト
        n_bootstrap: ブートストラップ反復回数 (デフォルト 1000)
        ci         : 信頼水準 (デフォルト 0.95)
        seed       : 乱数シード (再現性のため)

    Returns:
        スタンス → (下限, 上限) のタプル。
        responses が空のとき空辞書を返す。
    """
    if not responses:
        return {}

    if len(responses) != len(weights):
        raise ValueError("responses and weights must have the same length")

    rng = random.Random(seed)
    n = len(responses)

    # 全スタンスを収集
    all_stances: set[str] = set()
    for resp in responses:
        stance = resp.get("stance", "")
        if stance:
            all_stances.add(stance)

    # ブートストラップサンプルごとの分布を蓄積
    bootstrap_dists: dict[str, list[float]] = {s: [] for s in all_stances}

    for _ in range(n_bootstrap):
        indices = [rng.randint(0, n - 1) for _ in range(n)]
        sample_responses = [responses[i] for i in indices]
        sample_weights = [weights[i] for i in indices]
        dist = weighted_stance_distribution(sample_responses, sample_weights)
        for stance in all_stances:
            bootstrap_dists[stance].append(dist.get(stance, 0.0))

    # パーセンタイルで CI を計算
    alpha = 1.0 - ci
    lo_pct = alpha / 2.0
    hi_pct = 1.0 - alpha / 2.0

    result: dict[str, tuple[float, float]] = {}
    for stance in all_stances:
        sorted_vals = sorted(bootstrap_dists[stance])
        lo_idx = int(math.floor(lo_pct * n_bootstrap))
        hi_idx = int(math.ceil(hi_pct * n_bootstrap)) - 1
        # インデックスをクランプ
        lo_idx = max(0, min(lo_idx, n_bootstrap - 1))
        hi_idx = max(0, min(hi_idx, n_bootstrap - 1))
        result[stance] = (sorted_vals[lo_idx], sorted_vals[hi_idx])

    return result


def compute_poststratification_weights(
    agents: list[dict],
    responses: list[dict],
    target_marginals: dict[str, dict[str, float]],
    cap: float = 5.0,
    max_iter: int = 50,
    tol: float = 1e-6,
) -> list[float]:
    """事後層化ウェイトをレーキング（反復比例フィッティング）で計算する.

    各次元 (age_bracket, region, gender) についてウェイトをターゲット周辺分布に
    フィットさせ、上限 cap で切り詰める。

    Args:
        agents          : エージェントの辞書リスト。'demographics' キー以下に
                          age_bracket, region, gender を持つ。
        responses       : 各エージェントの応答辞書のリスト（現時点では未使用だが
                          インターフェース統一のため受け取る）
        target_marginals: 次元 → カテゴリ → ターゲット比率 の辞書
        cap             : ウェイトの上限値 (デフォルト 5.0)
        max_iter        : 最大反復回数 (デフォルト 50)
        tol             : 収束判定の許容誤差 (デフォルト 1e-6)

    Returns:
        正規化されたウェイトのリスト (長さ = len(agents))。

    Raises:
        ValueError: agents が空のとき
    """
    if not agents:
        raise ValueError("agents must not be empty")

    n = len(agents)
    weights = [1.0] * n

    # 次元名 → エージェントのカテゴリ値 を事前マッピング
    dim_to_values: dict[str, list[str]] = {}
    for dim in target_marginals:
        dim_to_values[dim] = []
        for agent in agents:
            demographics = agent.get("demographics", {})
            value = demographics.get(dim, "")
            dim_to_values[dim].append(str(value))

    for iteration in range(max_iter):
        max_change = 0.0

        for dim, target_dist in target_marginals.items():
            values = dim_to_values[dim]

            # 現在のウェイト付き分布を計算
            cat_weights: dict[str, float] = defaultdict(float)
            for i, val in enumerate(values):
                cat_weights[val] += weights[i]
            total_w = sum(cat_weights.values())

            if total_w == 0.0:
                continue

            # ターゲット分布との比率でウェイトを調整
            for i, val in enumerate(values):
                if val not in target_dist:
                    continue
                current_proportion = cat_weights[val] / total_w
                if current_proportion == 0.0:
                    continue
                ratio = target_dist[val] / current_proportion
                new_w = weights[i] * ratio
                max_change = max(max_change, abs(new_w - weights[i]))
                weights[i] = new_w

        # cap を適用
        weights = [min(w, cap) for w in weights]

        if max_change < tol:
            break

    # 正規化: 平均ウェイト = 1.0 になるよう正規化
    mean_w = sum(weights) / n
    if mean_w > 0:
        weights = [w / mean_w for w in weights]

    # cap を再適用（正規化後に超えた場合）
    weights = [min(w, cap) for w in weights]

    return weights


def load_target_marginals() -> dict[str, dict[str, float]]:
    """日本の人口統計に基づくターゲット周辺分布を返す.

    出典: 総務省統計局「国勢調査」（2020年）

    Returns:
        target_marginals: 次元 → カテゴリ → 比率 の辞書
    """
    return {
        "age_bracket": {
            "18-29": 0.13,
            "30-49": 0.30,
            "50-69": 0.31,
            "70+": 0.26,
        },
        "region": {
            "関東": 0.35,
            "関西": 0.18,
            "中部": 0.15,
            "東北": 0.07,
            "九州": 0.10,
            "北海道": 0.04,
            "四国": 0.03,
            "中国": 0.06,
            "その他": 0.02,
        },
        "gender": {
            "male": 0.485,
            "female": 0.510,
            "other": 0.005,
        },
    }
