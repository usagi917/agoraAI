"""意見更新に対する主要な隣接エージェントの寄与を説明する。"""

import numpy as np

from src.app.services.society.opinion_dynamics import (
    OpinionDynamicsEngine,
    compute_confirmation_bias_weight,
)


def primary_influence(
    engine: OpinionDynamicsEngine,
    target_index: int,
    opinions: np.ndarray,
) -> tuple[str | None, float]:
    """寄与度最大の適格隣人を返し、同値は agent_id で決定する。"""
    target_opinion = float(opinions[target_index][0])
    candidates: list[tuple[float, str, float]] = []
    for neighbor_index, edge_strength in engine._adj[target_index]:
        neighbor_opinion = float(opinions[neighbor_index][0])
        distance = float(np.linalg.norm(opinions[neighbor_index] - opinions[target_index]))
        if distance > engine._thresholds[target_index]:
            continue
        effective_weight = compute_confirmation_bias_weight(
            agent_opinion=target_opinion,
            neighbor_opinion=neighbor_opinion,
            base_weight=edge_strength,
        )
        contribution = effective_weight * abs(neighbor_opinion - target_opinion)
        candidates.append(
            (contribution, engine.agent_ids[neighbor_index], float(edge_strength))
        )

    if not candidates:
        return None, 0.0

    _contribution, source_id, edge_strength = min(
        candidates,
        key=lambda candidate: (-candidate[0], candidate[1]),
    )
    return source_id, edge_strength
