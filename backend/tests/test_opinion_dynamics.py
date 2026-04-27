"""Tests for Opinion Dynamics Engine (Bounded Confidence + Friedkin-Johnsen).

Mathematical properties tested:
- Bounded Confidence: agents only influenced by neighbors within confidence threshold
- Friedkin-Johnsen: stubbornness anchors agents to initial opinions
- Convergence: opinions stabilize after sufficient timesteps
- Cluster detection: separated opinion groups are identified
"""

import numpy as np
import pytest

from src.app.services.society.opinion_dynamics import (
    OpinionDynamicsEngine,
    PropagationStepResult,
    ClusterInfo,
    stubbornness_from_big_five,
    compute_heterogeneous_thresholds,
    compute_filter_bubble_thresholds,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_agents(opinions: list[float], stubbornness: list[float] | None = None) -> list[dict]:
    """Helper: create agent dicts with opinion_vector and stubbornness."""
    n = len(opinions)
    if stubbornness is None:
        stubbornness = [0.5] * n
    return [
        {
            "id": f"agent_{i}",
            "opinion_vector": [opinions[i]],
            "stubbornness": stubbornness[i],
        }
        for i in range(n)
    ]


def _make_edges(pairs: list[tuple[int, int]], strength: float = 1.0) -> list[dict]:
    """Helper: create edge dicts from index pairs."""
    return [
        {
            "agent_id": f"agent_{a}",
            "target_id": f"agent_{b}",
            "strength": strength,
        }
        for a, b in pairs
    ]


def _ring_edges(n: int, k: int = 2) -> list[tuple[int, int]]:
    """Ring lattice: each node connected to k nearest neighbors (bidirectional)."""
    pairs = []
    for i in range(n):
        for j in range(1, k // 2 + 1):
            pairs.append((i, (i + j) % n))
            pairs.append(((i + j) % n, i))
    return pairs


# ===========================================================================
# Test: Bounded Confidence (Hegselmann-Krause)
# ===========================================================================

class TestBoundedConfidence:
    """Agents should only be influenced by neighbors within confidence_threshold."""

    def test_within_threshold_agents_converge(self):
        """Two connected agents with opinions within threshold should move closer."""
        agents = _make_agents([0.3, 0.5], stubbornness=[0.4, 0.4])
        edges = _make_edges([(0, 1), (1, 0)])
        engine = OpinionDynamicsEngine(agents, edges, confidence_threshold=0.5)

        result = engine.propagation_step(timestep=0)

        op0 = result.updated_opinions[0][0]
        op1 = result.updated_opinions[1][0]
        # Both should move toward each other (partial stubbornness anchors)
        assert 0.3 < op0 < 0.5
        assert 0.3 < op1 < 0.5
        # Distance should have decreased
        assert abs(op0 - op1) < abs(0.3 - 0.5)

    def test_beyond_threshold_no_influence(self):
        """Two agents with opinions beyond threshold should NOT influence each other."""
        agents = _make_agents([0.1, 0.9], stubbornness=[0.0, 0.0])
        edges = _make_edges([(0, 1), (1, 0)])
        engine = OpinionDynamicsEngine(agents, edges, confidence_threshold=0.3)

        result = engine.propagation_step(timestep=0)

        # Opinions should be unchanged (no qualifying neighbors)
        assert result.updated_opinions[0][0] == pytest.approx(0.1, abs=1e-9)
        assert result.updated_opinions[1][0] == pytest.approx(0.9, abs=1e-9)

    def test_partial_neighborhood(self):
        """Agent with mixed-distance neighbors should only aggregate close ones."""
        # Agent 0 at 0.5, Agent 1 at 0.6 (close), Agent 2 at 0.1 (far)
        agents = _make_agents([0.5, 0.6, 0.1], stubbornness=[0.3, 0.3, 0.3])
        edges = _make_edges([(0, 1), (1, 0), (0, 2), (2, 0)])
        engine = OpinionDynamicsEngine(agents, edges, confidence_threshold=0.2)

        result = engine.propagation_step(timestep=0)

        # Agent 0 should be influenced by Agent 1 but NOT Agent 2
        op0 = result.updated_opinions[0][0]
        assert 0.5 < op0 <= 0.6  # moved toward Agent 1
        # Agent 2 should be unchanged (both neighbors are far)
        assert result.updated_opinions[2][0] == pytest.approx(0.1, abs=1e-9)


# ===========================================================================
# Test: Friedkin-Johnsen Stubbornness
# ===========================================================================

class TestFriedkinJohnsen:
    """Stubbornness should anchor agents to their initial opinions."""

    def test_full_stubbornness_no_change(self):
        """Agent with stubbornness=1.0 should never change opinion."""
        agents = _make_agents([0.2, 0.8], stubbornness=[1.0, 1.0])
        edges = _make_edges([(0, 1), (1, 0)])
        engine = OpinionDynamicsEngine(agents, edges, confidence_threshold=1.0)

        result = engine.propagation_step(timestep=0)

        assert result.updated_opinions[0][0] == pytest.approx(0.2, abs=1e-9)
        assert result.updated_opinions[1][0] == pytest.approx(0.8, abs=1e-9)

    def test_zero_stubbornness_full_social_influence(self):
        """Agent with stubbornness=0.0 moves toward neighbor, capped by MAX_CONV_DELTA.

        Step 8 introduced MAX_CONV_DELTA=0.15 clamp.
        agent 0 (0.0) targets 1.0: unclamped delta=1.0 → clamped to 0.15 → new=0.15
        agent 1 (1.0) targets 0.0: unclamped delta=-1.0 → clamped to -0.15 → new=0.85
        """
        from src.app.services.society.opinion_dynamics import MAX_CONV_DELTA

        agents = _make_agents([0.0, 1.0], stubbornness=[0.0, 0.0])
        edges = _make_edges([(0, 1), (1, 0)])
        engine = OpinionDynamicsEngine(agents, edges, confidence_threshold=1.0)

        result = engine.propagation_step(timestep=0)

        assert result.updated_opinions[0][0] == pytest.approx(MAX_CONV_DELTA, abs=1e-9)
        assert result.updated_opinions[1][0] == pytest.approx(1.0 - MAX_CONV_DELTA, abs=1e-9)

    def test_partial_stubbornness_anchoring(self):
        """Agent with stubbornness=0.5 moves toward neighbor, capped by MAX_CONV_DELTA.

        Step 8: unclamped x_0 = 0.5 * 0.0 + 0.5 * 1.0 = 0.5, delta=0.5 → clamped to 0.15
        """
        from src.app.services.society.opinion_dynamics import MAX_CONV_DELTA

        agents = _make_agents([0.0, 1.0], stubbornness=[0.5, 0.5])
        edges = _make_edges([(0, 1), (1, 0)])
        engine = OpinionDynamicsEngine(agents, edges, confidence_threshold=1.0)

        result = engine.propagation_step(timestep=0)

        # Both agents move toward each other by MAX_CONV_DELTA (unclamped was 0.5)
        assert result.updated_opinions[0][0] == pytest.approx(MAX_CONV_DELTA, abs=1e-9)
        assert result.updated_opinions[1][0] == pytest.approx(1.0 - MAX_CONV_DELTA, abs=1e-9)

    def test_stubbornness_from_big_five(self):
        """Stubbornness derived from Big Five C and A: s = 0.4 + 0.45*C - 0.1*A, clamped [0.3, 0.85].

        With default A=0.5: s = 0.4 + 0.45*C - 0.05 = 0.35 + 0.45*C.
        """
        from src.app.services.society.opinion_dynamics import stubbornness_from_big_five

        # Default A=0.5: 0.4 + 0.45*0 - 0.1*0.5 = 0.35
        assert stubbornness_from_big_five(0.0) == pytest.approx(0.35)
        # Default A=0.5: 0.4 + 0.45*0.5 - 0.1*0.5 = 0.575
        assert stubbornness_from_big_five(0.5) == pytest.approx(0.575)
        # Default A=0.5: 0.4 + 0.45*1.0 - 0.1*0.5 = 0.80
        assert stubbornness_from_big_five(1.0) == pytest.approx(0.80)
        # Explicit A=0: 0.4 + 0.45*0 - 0.1*0 = 0.4 (original formula)
        assert stubbornness_from_big_five(0.0, agreeableness=0.0) == pytest.approx(0.4)
        # Explicit A=0: 0.4 + 0.45*1.0 - 0.1*0 = 0.85
        assert stubbornness_from_big_five(1.0, agreeableness=0.0) == pytest.approx(0.85)


# ===========================================================================
# Test: Edge Strength Weighting
# ===========================================================================

class TestEdgeWeighting:
    """Stronger edges should exert more influence."""

    def test_stronger_edge_more_influence(self):
        """Agent connected to two neighbors: stronger edge pulls more."""
        # Agent 0 at 0.5, Agent 1 at 0.0 (weak edge), Agent 2 at 1.0 (strong edge)
        agents = _make_agents([0.5, 0.0, 1.0], stubbornness=[0.0, 1.0, 1.0])
        edges = [
            {"agent_id": "agent_0", "target_id": "agent_1", "strength": 0.2},
            {"agent_id": "agent_1", "target_id": "agent_0", "strength": 0.2},
            {"agent_id": "agent_0", "target_id": "agent_2", "strength": 0.8},
            {"agent_id": "agent_2", "target_id": "agent_0", "strength": 0.8},
        ]
        engine = OpinionDynamicsEngine(agents, edges, confidence_threshold=1.0)

        result = engine.propagation_step(timestep=0)

        # Agent 0 should be pulled more toward Agent 2 (1.0) than Agent 1 (0.0)
        op0 = result.updated_opinions[0][0]
        assert op0 > 0.5  # net pull toward 1.0


# ===========================================================================
# Test: Convergence Detection
# ===========================================================================

class TestConvergenceDetection:
    """Engine should detect when opinions have stabilized."""

    def test_converged_when_no_change(self):
        """Fully stubborn agents should converge immediately."""
        agents = _make_agents([0.2, 0.8], stubbornness=[1.0, 1.0])
        edges = _make_edges([(0, 1), (1, 0)])
        engine = OpinionDynamicsEngine(agents, edges, confidence_threshold=1.0)

        # Run 3 steps to build history
        for t in range(3):
            engine.propagation_step(timestep=t)

        assert engine.detect_convergence(window=3, epsilon=0.01) is True

    def test_not_converged_when_changing(self):
        """Agents still moving should not be considered converged."""
        agents = _make_agents([0.0, 1.0], stubbornness=[0.3, 0.3])
        edges = _make_edges([(0, 1), (1, 0)])
        engine = OpinionDynamicsEngine(agents, edges, confidence_threshold=1.0)

        engine.propagation_step(timestep=0)

        assert engine.detect_convergence(window=3, epsilon=0.01) is False

    def test_convergence_requires_window_steps(self):
        """Convergence requires `window` consecutive stable steps."""
        agents = _make_agents([0.5, 0.5], stubbornness=[0.5, 0.5])
        edges = _make_edges([(0, 1), (1, 0)])
        engine = OpinionDynamicsEngine(agents, edges, confidence_threshold=1.0)

        # Only 1 step, window=3
        engine.propagation_step(timestep=0)
        assert engine.detect_convergence(window=3, epsilon=0.01) is False

        # 2 more steps
        engine.propagation_step(timestep=1)
        engine.propagation_step(timestep=2)
        assert engine.detect_convergence(window=3, epsilon=0.01) is True


# ===========================================================================
# Test: Cluster Detection
# ===========================================================================

class TestClusterDetection:
    """Opinion clusters should be identified when opinions form distinct groups."""

    def test_two_clear_clusters(self):
        """Well-separated groups should form two clusters."""
        opinions = [0.1, 0.12, 0.15, 0.11, 0.9, 0.88, 0.92, 0.87]
        agents = _make_agents(opinions)
        edges = _make_edges(_ring_edges(8, k=2))
        engine = OpinionDynamicsEngine(agents, edges, confidence_threshold=0.3)

        clusters = engine.detect_clusters()

        assert len(clusters) == 2
        # Each cluster should have 4 members
        sizes = sorted([c.size for c in clusters])
        assert sizes == [4, 4]

    def test_single_cluster_when_close(self):
        """Agents with similar opinions should form one cluster."""
        opinions = [0.48, 0.49, 0.50, 0.51, 0.52]
        agents = _make_agents(opinions)
        edges = _make_edges(_ring_edges(5, k=2))
        engine = OpinionDynamicsEngine(agents, edges, confidence_threshold=0.3)

        clusters = engine.detect_clusters()

        assert len(clusters) == 1
        assert clusters[0].size == 5

    def test_cluster_info_fields(self):
        """ClusterInfo should contain required fields."""
        opinions = [0.1, 0.12, 0.9, 0.88]
        agents = _make_agents(opinions)
        edges = _make_edges(_ring_edges(4, k=2))
        engine = OpinionDynamicsEngine(agents, edges, confidence_threshold=0.3)

        clusters = engine.detect_clusters()

        for cluster in clusters:
            assert isinstance(cluster, ClusterInfo)
            assert isinstance(cluster.label, int)
            assert isinstance(cluster.member_ids, list)
            assert isinstance(cluster.centroid, list)
            assert isinstance(cluster.size, int)
            assert cluster.size == len(cluster.member_ids)


# ===========================================================================
# Test: Multi-Dimensional Opinions
# ===========================================================================

class TestMultiDimensionalOpinions:
    """Engine should support multi-dimensional opinion vectors."""

    def test_2d_opinions_converge(self):
        """Two agents with 2D opinions should move toward each other, clamped by MAX_CONV_DELTA.

        Step 8: MAX_CONV_DELTA clamp applies per dimension.
        agent 0: [0.2, 0.8], target [0.8, 0.2] → delta [0.6, -0.6] → clamped [0.15, -0.15]
        → new [0.35, 0.65]
        """
        from src.app.services.society.opinion_dynamics import MAX_CONV_DELTA

        agents = [
            {"id": "agent_0", "opinion_vector": [0.2, 0.8], "stubbornness": 0.0},
            {"id": "agent_1", "opinion_vector": [0.8, 0.2], "stubbornness": 0.0},
        ]
        edges = _make_edges([(0, 1), (1, 0)])
        engine = OpinionDynamicsEngine(agents, edges, confidence_threshold=2.0)

        result = engine.propagation_step(timestep=0)

        # Each dimension is clamped to MAX_CONV_DELTA shift
        assert result.updated_opinions[0][0] == pytest.approx(0.2 + MAX_CONV_DELTA, abs=1e-9)
        assert result.updated_opinions[0][1] == pytest.approx(0.8 - MAX_CONV_DELTA, abs=1e-9)

    def test_2d_bounded_confidence_uses_euclidean_distance(self):
        """Bounded confidence threshold should use Euclidean distance."""
        agents = [
            {"id": "agent_0", "opinion_vector": [0.0, 0.0], "stubbornness": 0.0},
            {"id": "agent_1", "opinion_vector": [0.1, 0.1], "stubbornness": 0.0},  # close
            {"id": "agent_2", "opinion_vector": [0.9, 0.9], "stubbornness": 0.0},  # far
        ]
        edges = _make_edges([(0, 1), (1, 0), (0, 2), (2, 0)])
        # sqrt(0.1^2 + 0.1^2) ≈ 0.14, sqrt(0.9^2 + 0.9^2) ≈ 1.27
        engine = OpinionDynamicsEngine(agents, edges, confidence_threshold=0.3)

        result = engine.propagation_step(timestep=0)

        # Agent 0 should be influenced by Agent 1 but not Agent 2
        assert result.updated_opinions[0][0] > 0.0
        assert result.updated_opinions[0][0] < 0.2


# ===========================================================================
# Test: PropagationStepResult Structure
# ===========================================================================

class TestPropagationStepResult:
    """Propagation step should return well-formed results."""

    def test_result_fields(self):
        agents = _make_agents([0.3, 0.7])
        edges = _make_edges([(0, 1), (1, 0)])
        engine = OpinionDynamicsEngine(agents, edges, confidence_threshold=1.0)

        result = engine.propagation_step(timestep=0)

        assert isinstance(result, PropagationStepResult)
        assert len(result.updated_opinions) == 2
        assert isinstance(result.max_delta, float)
        assert result.max_delta >= 0.0
        assert isinstance(result.timestep, int)

    def test_max_delta_tracks_largest_change(self):
        """max_delta reflects the clamped shift of the agent that moved most.

        Step 8: agent 2 (0.0 → 0.5 unclamped) is clamped to MAX_CONV_DELTA=0.15.
        """
        from src.app.services.society.opinion_dynamics import MAX_CONV_DELTA

        agents = _make_agents([0.5, 0.5, 0.0], stubbornness=[1.0, 1.0, 0.0])
        edges = _make_edges([(2, 0), (0, 2)])
        engine = OpinionDynamicsEngine(agents, edges, confidence_threshold=1.0)

        result = engine.propagation_step(timestep=0)

        # Only agent 2 changes, clamped to MAX_CONV_DELTA
        assert result.max_delta == pytest.approx(MAX_CONV_DELTA, abs=1e-9)


# ===========================================================================
# Test: Isolated Agent (No Edges)
# ===========================================================================

class TestIsolatedAgent:
    """Agents with no edges should retain their opinions."""

    def test_no_edges_no_change(self):
        agents = _make_agents([0.3, 0.7])
        edges = []  # No connections
        engine = OpinionDynamicsEngine(agents, edges, confidence_threshold=1.0)

        result = engine.propagation_step(timestep=0)

        assert result.updated_opinions[0][0] == pytest.approx(0.3, abs=1e-9)
        assert result.updated_opinions[1][0] == pytest.approx(0.7, abs=1e-9)
        assert result.max_delta == pytest.approx(0.0, abs=1e-9)


# ===========================================================================
# Test: Full Run (Multi-Step)
# ===========================================================================

class TestFullRun:
    """Integration test for multiple propagation steps."""

    def test_run_until_convergence(self):
        """Ring of 10 agents should converge to near-consensus with low stubbornness."""
        n = 10
        opinions = [i / (n - 1) for i in range(n)]  # 0.0, 0.11, ..., 1.0
        agents = _make_agents(opinions, stubbornness=[0.05] * n)
        edges = _make_edges(_ring_edges(n, k=6))
        engine = OpinionDynamicsEngine(agents, edges, confidence_threshold=1.0)

        for t in range(100):
            result = engine.propagation_step(timestep=t)
            if engine.detect_convergence(window=3, epsilon=0.001):
                break

        # Should have converged
        assert engine.detect_convergence(window=3, epsilon=0.001) is True
        # All opinions should be close to each other
        final_opinions = [op[0] for op in result.updated_opinions]
        assert max(final_opinions) - min(final_opinions) < 0.15

    def test_polarization_with_gap_beyond_threshold(self):
        """Two opinion groups separated by more than confidence_threshold stay apart."""
        # Group A: opinions near 0.1, Group B: opinions near 0.9
        # Gap (0.8) > confidence_threshold (0.3) -> no cross-group influence
        opinions = [0.08, 0.10, 0.12, 0.09, 0.11,
                    0.88, 0.90, 0.92, 0.89, 0.91]
        agents = _make_agents(opinions, stubbornness=[0.3] * 10)
        # Connect within groups + some cross-group edges (which won't qualify)
        edges = _make_edges(
            _ring_edges(5, k=4)  # group A internal
            + [(a + 5, b + 5) for a, b in _ring_edges(5, k=4)]  # group B internal
            + [(0, 5), (5, 0)]  # cross-group edge (gap too large)
        )
        engine = OpinionDynamicsEngine(agents, edges, confidence_threshold=0.3)

        for t in range(30):
            engine.propagation_step(timestep=t)
            if engine.detect_convergence(window=3, epsilon=0.005):
                break

        clusters = engine.detect_clusters()
        assert len(clusters) == 2
        sizes = sorted([c.size for c in clusters])
        assert sizes == [5, 5]


# ===========================================================================
# Phase G: Variance-based early stopping
# ===========================================================================

class TestVarianceBasedStopping:
    """Phase G: 分散ベースの早期停止テスト。"""

    def test_detect_variance_plateau(self):
        """意見分散が安定したら detect_variance_plateau が True を返す。"""
        # 全員同意見 → 分散変化なし → plateau 検出
        agents = _make_agents([0.5, 0.5, 0.5, 0.5], stubbornness=[1.0] * 4)
        edges = _make_edges([(0, 1), (1, 0), (1, 2), (2, 1), (2, 3), (3, 2)])
        engine = OpinionDynamicsEngine(agents, edges, confidence_threshold=0.5)

        for t in range(4):
            engine.propagation_step(timestep=t)

        assert engine.detect_variance_plateau(window=3, tolerance=0.01) is True

    def test_no_plateau_when_opinions_shifting(self):
        """意見が大きく変化中は plateau を検出しない。"""
        agents = _make_agents([0.0, 1.0], stubbornness=[0.3, 0.3])
        edges = _make_edges([(0, 1), (1, 0)])
        engine = OpinionDynamicsEngine(agents, edges, confidence_threshold=1.0)

        engine.propagation_step(timestep=0)

        assert engine.detect_variance_plateau(window=3, tolerance=0.01) is False


# ===========================================================================
# Test: Agreeableness in Confidence Thresholds
# ===========================================================================

class TestAgreeablenessThreshold:
    """Agreeableness (A) should widen confidence thresholds and reduce stubbornness."""

    def _make_agents_with_big_five(
        self, n: int, C: float = 0.5, O: float = 0.5, A: float = 0.5,
    ) -> list[dict]:
        """Helper: create agents with Big Five traits for threshold computation."""
        return [
            {
                "id": f"agent_{i}",
                "big_five": {"C": C, "O": O, "A": A},
            }
            for i in range(n)
        ]

    def test_high_A_wider_threshold(self):
        """A=0.9 agents should have wider confidence thresholds than A=0.1 agents."""
        agents_high_a = self._make_agents_with_big_five(5, C=0.5, O=0.5, A=0.9)
        agents_low_a = self._make_agents_with_big_five(5, C=0.5, O=0.5, A=0.1)

        thresholds_high = compute_heterogeneous_thresholds(
            agents_high_a, base_epsilon=0.3, alpha=0.15, beta=0.05, gamma=0.1, seed=42,
        )
        thresholds_low = compute_heterogeneous_thresholds(
            agents_low_a, base_epsilon=0.3, alpha=0.15, beta=0.05, gamma=0.1, seed=42,
        )

        # High A -> wider threshold (more receptive)
        for th, tl in zip(thresholds_high, thresholds_low):
            assert th > tl

    def test_gamma_zero_matches_original(self):
        """gamma=0 should produce identical results to the formula without A."""
        agents = self._make_agents_with_big_five(10, C=0.6, O=0.4, A=0.8)

        thresholds_with_gamma = compute_heterogeneous_thresholds(
            agents, base_epsilon=0.3, alpha=0.15, beta=0.05, gamma=0.0,
            noise_sigma=0.0, seed=42,
        )
        # Manual calculation: epsilon = 0.3 + 0.15*(1-0.6) + 0.05*(1-0.4) + 0.0*0.8
        expected = 0.3 + 0.15 * (1 - 0.6) + 0.05 * (1 - 0.4)
        for t in thresholds_with_gamma:
            assert t == pytest.approx(expected, abs=1e-9)

    def test_stubbornness_with_A(self):
        """A=0.9 agent should have lower stubbornness than A=0.1 agent (same C)."""
        s_high_a = stubbornness_from_big_five(0.5, agreeableness=0.9)
        s_low_a = stubbornness_from_big_five(0.5, agreeableness=0.1)

        assert s_high_a < s_low_a

    def test_stubbornness_backward_compat(self):
        """Calling stubbornness_from_big_five with only C should still work (default A=0.5)."""
        s_old = stubbornness_from_big_five(0.0)
        # Original formula: 0.4 + 0.45 * 0 = 0.4, but now with A=0.5 default:
        # 0.4 + 0.45 * 0 - 0.1 * 0.5 = 0.35, clamped to [0.3, 0.85] -> 0.35
        assert 0.3 <= s_old <= 0.85

    def test_filter_bubble_reduced_by_A(self):
        """High-A agent with SNS should have wider threshold than low-A agent with SNS."""
        agent_high_a = {
            "id": "agent_high_a",
            "big_five": {"C": 0.5, "O": 0.5, "A": 0.9},
            "information_sources": [
                {"name": "Twitter", "bubble_score": 0.8},
            ],
        }
        agent_low_a = {
            "id": "agent_low_a",
            "big_five": {"C": 0.5, "O": 0.5, "A": 0.1},
            "information_sources": [
                {"name": "Twitter", "bubble_score": 0.8},
            ],
        }

        th_high = compute_filter_bubble_thresholds(
            [agent_high_a], base_epsilon=0.3,
        )
        th_low = compute_filter_bubble_thresholds(
            [agent_low_a], base_epsilon=0.3,
        )

        # High A mitigates bubble effect -> wider threshold
        assert th_high[0] > th_low[0]
