"""分布間距離メトリクス

KL divergence と Earth Mover's Distance の共通実装。
service 層 (survey_anchor) と repository 層 (validation_repo) の双方から利用される。
"""

from __future__ import annotations

import math

from src.app.services.society.constants import STANCE_ORDER

__all__ = ["kl_divergence_symmetric", "earth_movers_distance", "STANCE_ORDER"]


def kl_divergence_symmetric(
    p: dict[str, float],
    q: dict[str, float],
    smoothing: float = 1e-6,
) -> float:
    """対称KL-divergence: (KL(p||q) + KL(q||p)) / 2。スムージング付き。"""
    all_keys = set(p.keys()) | set(q.keys())

    p_smooth = {k: p.get(k, 0.0) + smoothing for k in all_keys}
    q_smooth = {k: q.get(k, 0.0) + smoothing for k in all_keys}

    p_total = sum(p_smooth.values())
    q_total = sum(q_smooth.values())
    p_norm = {k: v / p_total for k, v in p_smooth.items()}
    q_norm = {k: v / q_total for k, v in q_smooth.items()}

    kl_pq = sum(p_norm[k] * math.log(p_norm[k] / q_norm[k]) for k in all_keys)
    kl_qp = sum(q_norm[k] * math.log(q_norm[k] / p_norm[k]) for k in all_keys)

    return (kl_pq + kl_qp) / 2.0


def earth_movers_distance(
    p: dict[str, float],
    q: dict[str, float],
) -> float:
    """序数距離を考慮したEarth Mover's Distance。

    スタンスの序数: 賛成=0, 条件付き賛成=1, 中立=2, 条件付き反対=3, 反対=4
    累積差分の絶対値の合計 (= 1次元 Wasserstein-1 距離)。
    """
    p_vals = [p.get(s, 0.0) for s in STANCE_ORDER]
    q_vals = [q.get(s, 0.0) for s in STANCE_ORDER]

    emd = 0.0
    cumulative = 0.0
    for i in range(len(STANCE_ORDER)):
        cumulative += p_vals[i] - q_vals[i]
        emd += abs(cumulative)

    return emd
