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

from src.app.services.society.age_utils import age_bracket_4 as _age_bracket


# 職業→5区分マッピング
_OCCUPATION_CATEGORY_MAP: dict[str, str] = {
    # white_collar: 事務・専門・管理
    "会社員": "white_collar", "公務員": "white_collar", "教師": "white_collar",
    "医師": "white_collar", "看護師": "white_collar", "エンジニア": "white_collar",
    "研究者": "white_collar", "営業職": "white_collar", "事務職": "white_collar",
    "弁護士": "white_collar", "会計士": "white_collar", "薬剤師": "white_collar",
    "コンサルタント": "white_collar", "記者": "white_collar",
    # blue_collar: 生産・運輸・建設
    "建設作業員": "blue_collar", "運転手": "blue_collar", "農業": "blue_collar",
    "漁業": "blue_collar",
    # self_employed: 自営業・フリーランス
    "自営業": "self_employed", "フリーランス": "self_employed",
    "経営者": "self_employed",
    # not_working: 学生・主婦/主夫・退職者
    "学生": "not_working", "主婦/主夫": "not_working", "退職者": "not_working",
    # other: サービス・その他
    "販売員": "other", "飲食店員": "other", "介護士": "other",
    "デザイナー": "other", "芸術家": "other", "パート/アルバイト": "other",
}


def _occupation_to_category(occupation: str) -> str:
    """職業名を5区分カテゴリに変換する。"""
    return _OCCUPATION_CATEGORY_MAP.get(occupation, "other")


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
    extra_uncertainty: float = 0.0,
) -> dict[str, tuple[float, float]]:
    """ブートストラップ法でスタンス分布の信頼区間を計算する.

    Args:
        responses  : 各エージェントの応答辞書のリスト
        weights    : 各エージェントのサンプリングウェイト
        n_bootstrap: ブートストラップ反復回数 (デフォルト 1000)
        ci         : 信頼水準 (デフォルト 0.95)
        seed       : 乱数シード (再現性のため)
        extra_uncertainty: CI 幅を ± extra_uncertainty で拡張 (トランスファー補正不確実性用)

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
        lo_val = max(0.0, sorted_vals[lo_idx] - extra_uncertainty)
        hi_val = min(1.0, sorted_vals[hi_idx] + extra_uncertainty)
        result[stance] = (lo_val, hi_val)

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
                          region, gender を持つ。age_bracket が無い場合は
                          age から導出する。
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
            if dim == "age_bracket" and value in ("", None):
                age = demographics.get("age")
                if age is not None:
                    value = _age_bracket(age)
            elif dim == "occupation_category" and value in ("", None):
                value = _occupation_to_category(demographics.get("occupation", ""))
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

    # 正規化 + cap を収束するまで反復（cap でクリップ後も mean=1.0 を保証）
    for _ in range(10):
        mean_w = sum(weights) / n
        if mean_w > 0:
            weights = [w / mean_w for w in weights]
        capped = [min(w, cap) for w in weights]
        if capped == weights:
            break
        weights = capped

    return weights


def compute_independence_weights(
    clusters: list[dict],
    edges: list[dict],
    agent_ids: list[str],
) -> dict[str, float]:
    """クラスター構造に基づく独立性補正重みを計算する.

    密に繋がったクラスター内のエージェントは社会的影響で意見が相関しているため、
    独立した意見としてカウントすると過剰評価になる。
    本関数はクラスターサイズと内部エッジ強度に基づき割引重みを算出する。

    Formula (agent i in cluster C_k):
        raw_weight_i = 1 / sqrt(cluster_size_k * avg_internal_edge_strength_k)
        singleton or no internal edges → raw_weight = 1.0
        正規化: mean(weights) = 1.0

    Args:
        clusters: クラスター辞書のリスト。各要素は 'member_ids' (list[str]) と
                  'size' (int) を持つ。
        edges: エッジ辞書のリスト。各要素は 'agent_id', 'target_id', 'strength' を持つ。
        agent_ids: 全エージェント ID のリスト。

    Returns:
        agent_id → independence_weight の辞書 (float > 0, mean ≈ 1.0)。

    Raises:
        ValueError: agent_ids が空のとき。
    """
    if not agent_ids:
        raise ValueError("agent_ids must not be empty")

    n = len(agent_ids)

    # Build agent → cluster mapping
    agent_to_cluster: dict[str, int] = {}
    for ci, cluster in enumerate(clusters):
        for mid in cluster.get("member_ids", []):
            agent_to_cluster[mid] = ci

    # Build set of members per cluster for fast lookup
    cluster_member_sets: list[set[str]] = [
        set(c.get("member_ids", [])) for c in clusters
    ]

    # Compute average internal edge strength per cluster
    cluster_edge_sums: dict[int, float] = defaultdict(float)
    cluster_edge_counts: dict[int, int] = defaultdict(int)

    for edge in edges:
        src = edge.get("agent_id", "")
        tgt = edge.get("target_id", "")
        strength = edge.get("strength", 0.0)

        src_ci = agent_to_cluster.get(src)
        tgt_ci = agent_to_cluster.get(tgt)

        # Both endpoints must be in the same cluster
        if src_ci is not None and src_ci == tgt_ci:
            cluster_edge_sums[src_ci] += strength
            cluster_edge_counts[src_ci] += 1

    # Compute raw weight per cluster
    cluster_raw_weights: dict[int, float] = {}
    for ci, cluster in enumerate(clusters):
        size = cluster.get("size", len(cluster.get("member_ids", [])))
        if size <= 1:
            cluster_raw_weights[ci] = 1.0
            continue

        edge_count = cluster_edge_counts.get(ci, 0)
        if edge_count == 0:
            cluster_raw_weights[ci] = 1.0
            continue

        avg_strength = cluster_edge_sums[ci] / edge_count
        if avg_strength <= 0:
            cluster_raw_weights[ci] = 1.0
            continue

        cluster_raw_weights[ci] = 1.0 / math.sqrt(size * avg_strength)

    # Assign raw weights to each agent
    raw_weights: dict[str, float] = {}
    for aid in agent_ids:
        ci = agent_to_cluster.get(aid)
        if ci is not None and ci in cluster_raw_weights:
            raw_weights[aid] = cluster_raw_weights[ci]
        else:
            raw_weights[aid] = 1.0

    # Normalize so mean = 1.0
    total_raw = sum(raw_weights.values())
    mean_raw = total_raw / n

    if mean_raw > 0:
        return {aid: w / mean_raw for aid, w in raw_weights.items()}
    else:
        return {aid: 1.0 for aid in agent_ids}


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
        "income_bracket": {
            # 国税庁「民間給与実態統計調査」(2021) ベース
            "low": 0.25,
            "lower_middle": 0.30,
            "upper_middle": 0.28,
            "high": 0.12,
            "very_high": 0.05,
        },
        "occupation_category": {
            # 総務省「労働力調査」(2020) ベース、5区分に折り畳み
            "white_collar": 0.40,      # 事務・専門・管理
            "blue_collar": 0.20,       # 生産・運輸・建設
            "self_employed": 0.10,     # 自営業・フリーランス
            "not_working": 0.20,       # 学生・主婦/主夫・退職者
            "other": 0.10,             # サービス・その他
        },
    }
