"""Tests for Emergence Tracker: cluster evolution, phase transitions, influence maps.

Verifies:
- Cluster formation/split/merge tracking across timesteps
- Phase transition detection (sudden cluster count changes)
- Influence map computation (which agents drove opinion change)
- Tipping point detection
"""

import pytest

from src.app.services.society.emergence_tracker import EmergenceTracker


def _make_timestep(t: int, opinions: list[list[float]], agent_ids: list[str]) -> dict:
    return {
        "timestep": t,
        "opinions": opinions,
        "agent_ids": agent_ids,
    }


class TestClusterTracking:
    """Track cluster formation and evolution across timesteps."""

    def test_detects_cluster_formation(self):
        tracker = EmergenceTracker()
        ids = [f"a{i}" for i in range(6)]

        # Timestep 0: all spread out → single cluster or scattered
        tracker.record_timestep(_make_timestep(0, [[0.1], [0.3], [0.5], [0.7], [0.9], [0.95]], ids))
        # Timestep 1: two groups form
        tracker.record_timestep(_make_timestep(1, [[0.1], [0.12], [0.11], [0.9], [0.88], [0.91]], ids))

        evolution = tracker.get_cluster_evolution()
        assert len(evolution) == 2
        # Second timestep should have 2 clusters
        assert evolution[1]["cluster_count"] == 2

    def test_detects_cluster_merge(self):
        tracker = EmergenceTracker()
        ids = [f"a{i}" for i in range(4)]

        # Timestep 0: two clusters
        tracker.record_timestep(_make_timestep(0, [[0.1], [0.12], [0.9], [0.88]], ids))
        # Timestep 1: merge into one
        tracker.record_timestep(_make_timestep(1, [[0.5], [0.51], [0.49], [0.52]], ids))

        evolution = tracker.get_cluster_evolution()
        assert evolution[0]["cluster_count"] == 2
        assert evolution[1]["cluster_count"] == 1


class TestPhaseTransition:
    """Detect sudden changes in cluster count."""

    def test_detects_split(self):
        tracker = EmergenceTracker()
        ids = [f"a{i}" for i in range(6)]

        # Gradual then sudden split
        for t in range(5):
            tracker.record_timestep(_make_timestep(
                t, [[0.5], [0.5], [0.5], [0.5], [0.5], [0.5]], ids,
            ))
        # Sudden split at t=5
        tracker.record_timestep(_make_timestep(
            5, [[0.1], [0.12], [0.11], [0.9], [0.88], [0.91]], ids,
        ))

        transitions = tracker.detect_phase_transitions()
        assert len(transitions) >= 1
        assert transitions[0]["timestep"] == 5
        assert transitions[0]["type"] == "split"

    def test_no_transition_when_stable(self):
        tracker = EmergenceTracker()
        ids = [f"a{i}" for i in range(4)]

        for t in range(5):
            tracker.record_timestep(_make_timestep(
                t, [[0.1], [0.12], [0.9], [0.88]], ids,
            ))

        transitions = tracker.detect_phase_transitions()
        assert len(transitions) == 0


class TestInfluenceMap:
    """Compute which agents drove the most opinion change."""

    def test_influence_map_identifies_driver(self):
        tracker = EmergenceTracker()
        ids = ["driver", "follower1", "follower2"]
        edges = [
            {"agent_id": "driver", "target_id": "follower1", "strength": 1.0},
            {"agent_id": "driver", "target_id": "follower2", "strength": 1.0},
        ]

        # Driver stays fixed, followers change
        tracker.record_timestep(_make_timestep(0, [[0.9], [0.5], [0.5]], ids))
        tracker.record_timestep(_make_timestep(1, [[0.9], [0.7], [0.7]], ids))

        influence = tracker.compute_influence_map(edges)
        # Driver should have highest influence score
        assert influence["driver"] > influence["follower1"]
        assert influence["driver"] > influence["follower2"]


class TestTippingPoint:
    """Detect timesteps where small changes triggered cascades."""

    def test_detects_cascade(self):
        tracker = EmergenceTracker()
        ids = [f"a{i}" for i in range(10)]

        # Stable for 5 steps
        stable = [[0.5]] * 10
        for t in range(5):
            tracker.record_timestep(_make_timestep(t, stable, ids))

        # Cascade at t=5: sudden large shift for many agents
        cascade = [[0.1], [0.12], [0.11], [0.9], [0.88], [0.91], [0.13], [0.87], [0.14], [0.86]]
        tracker.record_timestep(_make_timestep(5, cascade, ids))

        tipping = tracker.detect_tipping_points(min_cascade_ratio=0.5)
        assert len(tipping) >= 1
        assert tipping[0]["timestep"] == 5
