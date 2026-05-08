"""Wave A: 内部観測ループ.

Phase 5 cascade_propagator が出力する各ラウンドのレスポンス群を、
Phase 3 のベイジアン更新 (ParticleFilter.step) の observation として
流し込むためのアダプタ。外部ニュースを使わずに、agent 同士の発言を
集合知の観測として扱う設計。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from src.app.services.society.particle_filter import ParticleFilter


def round_to_observation(
    round_snapshot: Iterable[dict],
    weight_by_confidence: bool = False,
) -> dict[str, float]:
    """1 ラウンドのレスポンス群から observation 辞書 {stance: count} を作る.

    Args:
        round_snapshot: 各要素が {"agent_id", "stance", "confidence"} を持つ dict
        weight_by_confidence: True なら count に confidence を掛ける
    """
    obs: dict[str, float] = defaultdict(float)
    for resp in round_snapshot:
        stance = resp.get("stance")
        if stance is None:
            continue
        weight = float(resp.get("confidence", 1.0)) if weight_by_confidence else 1.0
        obs[stance] += weight
    return dict(obs)


def neighbor_observation(
    round_snapshot: Iterable[dict],
    edges: list[tuple[int, int]],
    target_agent_id: int,
    weight_by_confidence: bool = False,
) -> dict[str, float]:
    """target_agent_id の隣接 agent の発言だけを観測としてまとめる.

    エッジは無向として扱う。target が孤立していれば空 dict を返す。
    """
    neighbors: set[int] = set()
    for a, b in edges:
        if a == target_agent_id:
            neighbors.add(b)
        elif b == target_agent_id:
            neighbors.add(a)
    if not neighbors:
        return {}
    filtered = [r for r in round_snapshot if r.get("agent_id") in neighbors]
    return round_to_observation(filtered, weight_by_confidence=weight_by_confidence)


def integrate_cascade_with_belief(
    cascade_snapshots: list[list[dict]],
    particle_filter: ParticleFilter,
    weight_by_confidence: bool = False,
    skip_initial: bool = True,
) -> dict[str, float]:
    """cascade のラウンドごとに particle_filter.step() を呼び、aggregate 分布を返す.

    Args:
        cascade_snapshots: cascade_propagator.propagate の戻り値 (先頭は初期 snapshot)
        particle_filter: 既に prior が設定された粒子フィルタ
        weight_by_confidence: True で confidence 重み付け
        skip_initial: True なら先頭 (round 0 = 初期) は prior として扱い observation に流さない
    """
    if not cascade_snapshots:
        return particle_filter.aggregate_distribution()

    rounds = cascade_snapshots[1:] if skip_initial else cascade_snapshots
    for round_snap in rounds:
        obs = round_to_observation(round_snap, weight_by_confidence=weight_by_confidence)
        if obs:
            particle_filter.step(observation=obs)

    return particle_filter.aggregate_distribution()
