"""P3-1 ~ P3-2: Opinion Dynamics 改善テスト"""

import numpy as np
import pytest


class TestHeterogeneousThresholds:
    """P3-1: エージェント別異質閾値のテスト."""

    def test_per_agent_thresholds(self):
        """各エージェントが異なる confidence threshold を持つこと."""
        from src.app.services.society.opinion_dynamics import compute_heterogeneous_thresholds

        agents = [
            {"id": "a1", "big_five": {"C": 0.2, "O": 0.8}},  # 低 C, 高 O → 広い閾値
            {"id": "a2", "big_five": {"C": 0.9, "O": 0.2}},  # 高 C, 低 O → 狭い閾値
        ]

        thresholds = compute_heterogeneous_thresholds(agents, base_epsilon=0.3)

        assert len(thresholds) == 2
        # 低 C (= 低 confidence) → 閾値が広がる → threshold 大
        assert thresholds[0] > thresholds[1]

    def test_deterministic_with_seed(self):
        """同一 seed で同じ閾値が生成されること."""
        from src.app.services.society.opinion_dynamics import compute_heterogeneous_thresholds

        agents = [
            {"id": "a1", "big_five": {"C": 0.5, "O": 0.5}},
            {"id": "a2", "big_five": {"C": 0.7, "O": 0.3}},
        ]

        t1 = compute_heterogeneous_thresholds(agents, base_epsilon=0.3, seed=42)
        t2 = compute_heterogeneous_thresholds(agents, base_epsilon=0.3, seed=42)

        np.testing.assert_array_almost_equal(t1, t2)

    def test_engine_accepts_per_agent_thresholds(self):
        """OpinionDynamicsEngine が per-agent thresholds を受け付けること."""
        from src.app.services.society.opinion_dynamics import OpinionDynamicsEngine

        agents = [
            {"id": "a1", "opinion_vector": [0.5, 0.5], "stubbornness": 0.5},
            {"id": "a2", "opinion_vector": [0.6, 0.4], "stubbornness": 0.5},
        ]
        edges = [{"agent_id": "a1", "target_id": "a2", "strength": 0.8}]

        # per-agent thresholds as ndarray
        thresholds = np.array([0.3, 0.1])
        engine = OpinionDynamicsEngine(agents, edges, confidence_threshold=thresholds)

        result = engine.propagation_step(1)
        assert result.timestep == 1


class TestEdgeWeightDecay:
    """P3-2: edge_weight_decay パラメータのテスト."""

    def test_decay_reduces_influence_over_time(self):
        """decay があるとステップごとにエッジ重みが減衰する."""
        from src.app.services.society.opinion_dynamics import OpinionDynamicsEngine

        agents = [
            {"id": "a1", "opinion_vector": [0.2, 0.8], "stubbornness": 0.3},
            {"id": "a2", "opinion_vector": [0.8, 0.2], "stubbornness": 0.3},
        ]
        edges = [
            {"agent_id": "a1", "target_id": "a2", "strength": 1.0},
            {"agent_id": "a2", "target_id": "a1", "strength": 1.0},
        ]

        # decay なし
        engine_no_decay = OpinionDynamicsEngine(agents, edges, confidence_threshold=1.0)
        engine_no_decay.propagation_step(1)
        r1 = engine_no_decay.propagation_step(2)

        # decay あり
        engine_decay = OpinionDynamicsEngine(
            agents, edges, confidence_threshold=1.0, edge_weight_decay=0.3,
        )
        engine_decay.propagation_step(1)
        r2 = engine_decay.propagation_step(2)

        # decay ありの方が delta が小さい（影響が弱まる）
        assert r2.max_delta <= r1.max_delta + 0.01  # 許容誤差付き
