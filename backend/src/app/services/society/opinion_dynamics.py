"""Opinion Dynamics Engine: Bounded Confidence (Hegselmann-Krause) + Friedkin-Johnsen.

Implements network-based opinion propagation where agents update their opinions
based on neighbors within a confidence threshold, anchored by individual stubbornness.

Mathematical model per agent i at timestep t:
    x_i(t+1) = s_i * x_i(0) + (1 - s_i) * weighted_mean(neighbors)

Where:
    s_i = stubbornness (derived from Big Five C: 0.3 + 0.4 * C)
    neighbors = {j in N_i : ||x_j(t) - x_i(t)|| < confidence_threshold}
    weighted_mean uses edge strength as weights

References:
    - Hegselmann & Krause (2002): Opinion Dynamics and Bounded Confidence
    - Friedkin & Johnsen (1990): Social Influence and Opinions
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.cluster import DBSCAN


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PropagationStepResult:
    updated_opinions: list[list[float]]
    max_delta: float
    timestep: int


@dataclass
class ClusterInfo:
    label: int
    member_ids: list[str]
    centroid: list[float]
    size: int


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def stubbornness_from_big_five(conscientiousness: float) -> float:
    """Derive stubbornness from Big Five Conscientiousness score.

    s = 0.4 + 0.45 * C, yielding range [0.4, 0.85].
    Higher range preserves stronger initial convictions.
    """
    return 0.4 + 0.45 * conscientiousness


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class OpinionDynamicsEngine:
    """Bounded Confidence + Friedkin-Johnsen opinion dynamics on a weighted graph."""

    def __init__(
        self,
        agents: list[dict],
        edges: list[dict],
        confidence_threshold: float = 0.3,
    ) -> None:
        self.n = len(agents)
        self.agent_ids = [a["id"] for a in agents]
        self._id_to_idx = {a["id"]: i for i, a in enumerate(agents)}

        # Store initial opinions (anchors for Friedkin-Johnsen)
        self._initial_opinions = np.array(
            [a["opinion_vector"] for a in agents], dtype=np.float64,
        )
        # Current opinions (mutated each step)
        self._opinions = self._initial_opinions.copy()
        self._dim = self._opinions.shape[1]

        # Stubbornness per agent
        self._stubbornness = np.array(
            [a.get("stubbornness", 0.5) for a in agents], dtype=np.float64,
        )

        self._confidence_threshold = confidence_threshold

        # Build adjacency: for each agent, list of (neighbor_idx, weight)
        self._adj: list[list[tuple[int, float]]] = [[] for _ in range(self.n)]
        for e in edges:
            src = self._id_to_idx.get(e["agent_id"])
            tgt = self._id_to_idx.get(e["target_id"])
            if src is not None and tgt is not None:
                self._adj[src].append((tgt, e.get("strength", 1.0)))

        # History for convergence detection
        self._history: list[np.ndarray] = []

    # ----- propagation step ------------------------------------------------

    def propagation_step(self, timestep: int) -> PropagationStepResult:
        new_opinions = np.empty_like(self._opinions)
        max_delta = 0.0

        for i in range(self.n):
            s_i = self._stubbornness[i]
            x_i = self._opinions[i]
            x_i_0 = self._initial_opinions[i]

            # Collect qualifying neighbors (within confidence bound)
            weighted_sum = np.zeros(self._dim, dtype=np.float64)
            total_weight = 0.0

            for j, w in self._adj[i]:
                x_j = self._opinions[j]
                dist = np.linalg.norm(x_j - x_i)
                if dist <= self._confidence_threshold:
                    weighted_sum += w * x_j
                    total_weight += w

            if total_weight > 0.0:
                neighbor_mean = weighted_sum / total_weight
                new_x = s_i * x_i_0 + (1.0 - s_i) * neighbor_mean
            else:
                # No qualifying neighbors: opinion unchanged
                new_x = x_i.copy()

            new_opinions[i] = new_x
            delta = np.linalg.norm(new_x - x_i)
            if delta > max_delta:
                max_delta = delta

        self._opinions = new_opinions
        self._history.append(new_opinions.copy())

        return PropagationStepResult(
            updated_opinions=new_opinions.tolist(),
            max_delta=float(max_delta),
            timestep=timestep,
        )

    # ----- convergence detection -------------------------------------------

    def detect_convergence(self, window: int = 3, epsilon: float = 0.01) -> bool:
        if len(self._history) < window:
            return False
        for k in range(1, window):
            diff = np.max(np.abs(self._history[-k] - self._history[-k - 1]))
            if diff > epsilon:
                return False
        return True

    def detect_variance_plateau(self, window: int = 3, tolerance: float = 0.01) -> bool:
        """意見分散が安定（plateau）したかを検出する。

        直近 window ステップで分散の変化率が tolerance 以内なら True。
        """
        if len(self._history) < window + 1:
            return False

        variances = [
            float(np.var(self._history[-(i + 1)]))
            for i in range(window + 1)
        ]
        # 最新 window ステップの分散変化が tolerance 以内か
        for i in range(window):
            if variances[0] == 0 and variances[i + 1] == 0:
                continue
            ref = max(variances[i + 1], 1e-10)
            if abs(variances[i] - variances[i + 1]) / ref > tolerance:
                return False
        return True

    # ----- cluster detection -----------------------------------------------

    def detect_clusters(self, eps: float = 0.2, min_samples: int = 2) -> list[ClusterInfo]:
        db = DBSCAN(eps=eps, min_samples=min_samples).fit(self._opinions)
        labels = db.labels_

        clusters: list[ClusterInfo] = []
        unique_labels = set(labels)
        unique_labels.discard(-1)  # noise

        for label in sorted(unique_labels):
            mask = labels == label
            indices = np.where(mask)[0]
            member_ids = [self.agent_ids[i] for i in indices]
            centroid = self._opinions[mask].mean(axis=0).tolist()
            clusters.append(ClusterInfo(
                label=int(label),
                member_ids=member_ids,
                centroid=centroid,
                size=len(member_ids),
            ))

        # Assign noise points as singleton clusters if any
        noise_indices = np.where(labels == -1)[0]
        next_label = max(unique_labels, default=-1) + 1
        for idx in noise_indices:
            clusters.append(ClusterInfo(
                label=next_label,
                member_ids=[self.agent_ids[idx]],
                centroid=self._opinions[idx].tolist(),
                size=1,
            ))
            next_label += 1

        return clusters
