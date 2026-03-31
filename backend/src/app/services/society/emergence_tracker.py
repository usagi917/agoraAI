"""Emergence Tracker: cluster evolution, phase transitions, influence maps.

Tracks emergent patterns in opinion dynamics:
- Cluster formation, splitting, and merging over time
- Phase transitions (sudden shifts in the number or structure of clusters)
- Influence maps (which agents drove the most opinion change)
- Tipping points (timesteps where small perturbations triggered cascades)
"""

from __future__ import annotations

import numpy as np
from sklearn.cluster import DBSCAN


class EmergenceTracker:
    """Tracks emergent patterns across opinion propagation timesteps."""

    def __init__(self, cluster_eps: float = 0.2, cluster_min_samples: int = 2) -> None:
        self._cluster_eps = cluster_eps
        self._cluster_min_samples = cluster_min_samples
        self._timesteps: list[dict] = []
        self._cluster_history: list[dict] = []

    def record_timestep(self, data: dict) -> None:
        """Record a timestep's opinion state."""
        self._timesteps.append(data)

        opinions = np.array(data["opinions"])
        agent_ids = data["agent_ids"]

        db = DBSCAN(eps=self._cluster_eps, min_samples=self._cluster_min_samples).fit(opinions)
        labels = db.labels_
        unique_labels = set(labels)
        unique_labels.discard(-1)

        clusters = []
        for label in sorted(unique_labels):
            mask = labels == label
            indices = np.where(mask)[0]
            clusters.append({
                "label": int(label),
                "member_ids": [agent_ids[i] for i in indices],
                "centroid": opinions[mask].mean(axis=0).tolist(),
                "size": int(mask.sum()),
            })

        # Noise points as singletons
        noise_count = int((labels == -1).sum())

        self._cluster_history.append({
            "timestep": data["timestep"],
            "cluster_count": len(clusters),
            "clusters": clusters,
            "noise_count": noise_count,
        })

    def get_cluster_evolution(self) -> list[dict]:
        """Return cluster count and composition at each timestep."""
        return self._cluster_history

    def detect_phase_transitions(self, threshold: int = 1) -> list[dict]:
        """Detect timesteps where cluster count changed significantly."""
        transitions = []
        for i in range(1, len(self._cluster_history)):
            prev = self._cluster_history[i - 1]["cluster_count"]
            curr = self._cluster_history[i]["cluster_count"]
            delta = curr - prev
            if abs(delta) >= threshold:
                transition_type = "split" if delta > 0 else "merge"
                transitions.append({
                    "timestep": self._cluster_history[i]["timestep"],
                    "type": transition_type,
                    "from_count": prev,
                    "to_count": curr,
                })
        return transitions

    def compute_influence_map(self, edges: list[dict]) -> dict[str, float]:
        """Compute influence score for each agent based on neighbor opinion changes.

        An agent's influence score = sum of opinion changes in its outgoing neighbors.
        """
        if len(self._timesteps) < 2:
            return {}

        prev_opinions = {
            aid: op for aid, op in zip(
                self._timesteps[-2]["agent_ids"],
                self._timesteps[-2]["opinions"],
            )
        }
        curr_opinions = {
            aid: op for aid, op in zip(
                self._timesteps[-1]["agent_ids"],
                self._timesteps[-1]["opinions"],
            )
        }

        # Compute opinion change per agent
        change_map: dict[str, float] = {}
        for aid in curr_opinions:
            if aid in prev_opinions:
                delta = np.linalg.norm(
                    np.array(curr_opinions[aid]) - np.array(prev_opinions[aid]),
                )
                change_map[aid] = float(delta)
            else:
                change_map[aid] = 0.0

        # Influence = sum of opinion changes in outgoing neighbors
        influence: dict[str, float] = {aid: 0.0 for aid in curr_opinions}
        for edge in edges:
            src = edge["agent_id"]
            tgt = edge["target_id"]
            if src in influence and tgt in change_map:
                influence[src] += change_map[tgt] * edge.get("strength", 1.0)

        return influence

    def detect_tipping_points(
        self,
        min_cascade_ratio: float = 0.5,
        change_threshold: float = 0.15,
    ) -> list[dict]:
        """Detect timesteps where many agents shifted opinions simultaneously.

        A tipping point is a timestep where the fraction of agents whose opinion
        changed by more than change_threshold exceeds min_cascade_ratio.
        """
        tipping_points = []

        for i in range(1, len(self._timesteps)):
            prev = self._timesteps[i - 1]
            curr = self._timesteps[i]

            prev_opinions = np.array(prev["opinions"])
            curr_opinions = np.array(curr["opinions"])

            deltas = np.linalg.norm(curr_opinions - prev_opinions, axis=1)
            cascade_count = int((deltas > change_threshold).sum())
            ratio = cascade_count / len(deltas) if len(deltas) > 0 else 0.0

            if ratio >= min_cascade_ratio:
                tipping_points.append({
                    "timestep": curr["timestep"],
                    "cascade_ratio": round(ratio, 4),
                    "agents_shifted": cascade_count,
                    "total_agents": len(deltas),
                })

        return tipping_points
