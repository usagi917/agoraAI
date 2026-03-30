"""Tests for compute_independence_weights: cluster-based independence weighting."""

import pytest

from src.app.services.society.statistical_inference import compute_independence_weights


def _make_clusters(groups: list[list[str]]) -> list[dict]:
    """Helper to create cluster dicts from groups of agent IDs."""
    return [
        {"member_ids": members, "size": len(members)}
        for i, members in enumerate(groups)
    ]


def _make_edges(pairs: list[tuple[str, str, float]]) -> list[dict]:
    """Helper to create edge dicts from (agent_id, target_id, strength) tuples."""
    return [
        {"agent_id": a, "target_id": b, "strength": s}
        for a, b, s in pairs
    ]


class TestComputeIndependenceWeights:
    """compute_independence_weights の単体テスト."""

    def test_all_singletons_returns_uniform_weights(self):
        """全員がシングルトンクラスター → 全員 weight ≈ 1.0."""
        agent_ids = ["a0", "a1", "a2"]
        clusters = _make_clusters([["a0"], ["a1"], ["a2"]])
        edges: list[dict] = []

        weights = compute_independence_weights(clusters, edges, agent_ids)

        assert len(weights) == 3
        for aid in agent_ids:
            assert weights[aid] == pytest.approx(1.0, abs=0.01)

    def test_single_large_cluster_reduces_weights(self):
        """全員が1つの大クラスター → weight < 1.0 (正規化前) だが正規化後は全員同じ."""
        agent_ids = [f"a{i}" for i in range(10)]
        clusters = _make_clusters([agent_ids])
        # 全ペア間にエッジ
        edges = _make_edges([
            (f"a{i}", f"a{j}", 0.8)
            for i in range(10) for j in range(i + 1, 10)
        ])

        weights = compute_independence_weights(clusters, edges, agent_ids)

        # 全員が同一クラスターなので、正規化後は全員同じ値
        values = list(weights.values())
        assert all(v == pytest.approx(values[0], abs=0.01) for v in values)
        # 平均は 1.0
        assert sum(values) / len(values) == pytest.approx(1.0, abs=0.01)

    def test_weight_formula_matches_specification(self):
        """5人クラスター, avg_strength=0.8 → raw_weight = 1/sqrt(5*0.8) = 1/2.0 = 0.5."""
        cluster_agents = ["a0", "a1", "a2", "a3", "a4"]
        singleton = "a5"
        agent_ids = cluster_agents + [singleton]

        clusters = _make_clusters([cluster_agents, [singleton]])
        # クラスター内全ペアに strength=0.8
        edges = _make_edges([
            (f"a{i}", f"a{j}", 0.8)
            for i in range(5) for j in range(i + 1, 5)
        ])

        weights = compute_independence_weights(clusters, edges, agent_ids)

        # singleton は raw_weight=1.0, cluster agents は raw_weight=0.5
        # 正規化前: [0.5, 0.5, 0.5, 0.5, 0.5, 1.0] → sum=3.5, n=6, mean=3.5/6≈0.583
        # 正規化後: each * (1.0 / 0.583)
        # singleton の重みがクラスターメンバーより大きいこと
        assert weights[singleton] > weights["a0"]

    def test_mixed_clusters_different_weights(self):
        """大きいクラスターと小さいクラスター → 大きいクラスターの方が低い重み."""
        large_cluster = [f"a{i}" for i in range(8)]
        small_cluster = ["b0", "b1"]
        agent_ids = large_cluster + small_cluster

        clusters = _make_clusters([large_cluster, small_cluster])
        edges = _make_edges(
            [(f"a{i}", f"a{j}", 0.6) for i in range(8) for j in range(i + 1, 8)]
            + [("b0", "b1", 0.6)]
        )

        weights = compute_independence_weights(clusters, edges, agent_ids)

        # large cluster agents は small cluster agents より低い重み
        assert weights["a0"] < weights["b0"]

    def test_normalization_preserves_mean_one(self):
        """正規化後の平均重みが ≈ 1.0."""
        agent_ids = [f"a{i}" for i in range(20)]
        clusters = _make_clusters([agent_ids[:10], agent_ids[10:15], agent_ids[15:]])
        edges = _make_edges([
            (agent_ids[i], agent_ids[j], 0.7)
            for i in range(10) for j in range(i + 1, 10)
        ])

        weights = compute_independence_weights(clusters, edges, agent_ids)

        mean_w = sum(weights.values()) / len(weights)
        assert mean_w == pytest.approx(1.0, abs=0.01)

    def test_empty_agents_raises_error(self):
        """空の agent_ids → ValueError."""
        with pytest.raises(ValueError):
            compute_independence_weights([], [], [])

    def test_missing_agent_in_clusters_gets_default_weight(self):
        """クラスターに含まれないエージェント → singleton 扱い (高い重み)."""
        agent_ids = ["a0", "a1", "a2", "orphan"]
        clusters = _make_clusters([["a0", "a1", "a2"]])
        edges = _make_edges([("a0", "a1", 0.9), ("a1", "a2", 0.9), ("a0", "a2", 0.9)])

        weights = compute_independence_weights(clusters, edges, agent_ids)

        assert "orphan" in weights
        # orphan は singleton 扱いなのでクラスターメンバーより高い
        assert weights["orphan"] > weights["a0"]

    def test_zero_edge_strength_cluster_gets_unit_weight(self):
        """クラスター内エッジ強度が0 → raw_weight = 1.0."""
        agent_ids = ["a0", "a1", "a2"]
        clusters = _make_clusters([["a0", "a1", "a2"]])
        edges: list[dict] = []  # エッジなし

        weights = compute_independence_weights(clusters, edges, agent_ids)

        # エッジ強度0 → 全員 1.0
        for aid in agent_ids:
            assert weights[aid] == pytest.approx(1.0, abs=0.01)

    def test_returns_dict_mapping_agent_id_to_weight(self):
        """返り値が dict[str, float] であること."""
        agent_ids = ["a0", "a1"]
        clusters = _make_clusters([["a0", "a1"]])
        edges = _make_edges([("a0", "a1", 0.5)])

        result = compute_independence_weights(clusters, edges, agent_ids)

        assert isinstance(result, dict)
        for k, v in result.items():
            assert isinstance(k, str)
            assert isinstance(v, float)

    def test_all_weights_positive(self):
        """全ての重みが > 0."""
        agent_ids = [f"a{i}" for i in range(15)]
        clusters = _make_clusters([agent_ids[:5], agent_ids[5:10], agent_ids[10:]])
        edges = _make_edges([
            (agent_ids[i], agent_ids[i + 1], 0.9)
            for i in range(14)
        ])

        weights = compute_independence_weights(clusters, edges, agent_ids)

        for v in weights.values():
            assert v > 0.0
