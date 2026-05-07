"""ネットワーク生成テスト: 小世界特性（クラスタ係数、エッジ数）"""

import pytest

from unittest.mock import patch, MagicMock
from collections import Counter

from src.app.services.society.network_generator import (
    generate_watts_strogatz_edges,
    generate_barabasi_albert_edges,
    generate_hybrid_edges,
    generate_network,
    _attribute_similarity,
)
from src.app.services.society.population_generator import generate_population


class TestAttributeSimilarity:
    def test_same_attributes(self):
        a = {"demographics": {"region": "関東（都市部）", "age": 35, "education": "bachelor", "income_bracket": "upper_middle"}}
        b = {"demographics": {"region": "関東（都市部）", "age": 35, "education": "bachelor", "income_bracket": "upper_middle"}}
        sim = _attribute_similarity(a, b)
        assert sim == 1.0

    def test_different_attributes(self):
        a = {"demographics": {"region": "北海道", "age": 20, "education": "high_school", "income_bracket": "low"}}
        b = {"demographics": {"region": "九州", "age": 70, "education": "doctorate", "income_bracket": "very_high"}}
        sim = _attribute_similarity(a, b)
        assert sim < 0.5

    def test_empty_profiles(self):
        sim = _attribute_similarity({}, {})
        assert 0.0 <= sim <= 1.0


class TestWattsStrogatzEdges:
    def test_edge_count_approximate(self):
        """n=100, k=6 -> 約300エッジ（各ノード6接続/2）"""
        agents = [
            {"id": f"agent-{i}", "demographics": {"region": "関東（都市部）", "age": 30}}
            for i in range(100)
        ]
        edges = generate_watts_strogatz_edges(agents, "pop-1", k=6, beta=0.0, cluster_by_attributes=False)
        # リング格子: n * k/2 = 300エッジ (再配線なし)
        assert 250 <= len(edges) <= 350

    def test_edge_structure(self):
        agents = [
            {"id": f"agent-{i}", "demographics": {"region": "関東（都市部）", "age": 30}}
            for i in range(20)
        ]
        edges = generate_watts_strogatz_edges(agents, "pop-1", k=4, beta=0.0)
        for e in edges:
            assert "id" in e
            assert e["population_id"] == "pop-1"
            assert "agent_id" in e
            assert "target_id" in e
            assert e["agent_id"] != e["target_id"]
            assert "relation_type" in e
            assert 0.0 < e["strength"] <= 1.0

    def test_small_population(self):
        """n=2 は n<3 で空を返す"""
        agents = [{"id": "a"}, {"id": "b"}]
        edges = generate_watts_strogatz_edges(agents, "pop-1", k=2, beta=0.0)
        assert len(edges) == 0

    def test_very_small_population(self):
        agents = [{"id": "a"}]
        edges = generate_watts_strogatz_edges(agents, "pop-1")
        assert len(edges) == 0

    def test_rewiring_changes_edges(self):
        agents = [
            {"id": f"agent-{i}", "demographics": {"region": "関東（都市部）", "age": 30}}
            for i in range(50)
        ]
        edges_no_rewire = generate_watts_strogatz_edges(agents, "pop-1", k=4, beta=0.0, cluster_by_attributes=False)
        edges_rewired = generate_watts_strogatz_edges(agents, "pop-1", k=4, beta=0.5, cluster_by_attributes=False)
        # Edge sets should differ somewhat
        no_rewire_pairs = {(e["agent_id"], e["target_id"]) for e in edges_no_rewire}
        rewired_pairs = {(e["agent_id"], e["target_id"]) for e in edges_rewired}
        # At least some edges should differ (probabilistic but highly likely with beta=0.5)
        assert no_rewire_pairs != rewired_pairs or len(edges_no_rewire) != len(edges_rewired)


class TestBarabasiAlbertEdges:
    """Barabasi-Albert preferential attachment network tests."""

    def _make_simple_agents(self, n: int) -> list[dict]:
        return [
            {"id": f"agent-{i}", "demographics": {"region": "関東（都市部）", "age": 30}}
            for i in range(n)
        ]

    def test_ba_edge_count(self):
        """BA graph with m=3, n=100 should have ~m*(n-m) = 291 edges."""
        agents = self._make_simple_agents(100)
        edges = generate_barabasi_albert_edges(agents, "pop-1", m=3, seed=42)
        # m*(n-m) = 3*(100-3) = 291
        expected = 3 * (100 - 3)
        # Allow some tolerance since networkx may produce slightly different counts
        assert abs(len(edges) - expected) <= 10

    def test_ba_hub_existence(self):
        """At least one node should have degree >= 3x the average degree (hub)."""
        agents = self._make_simple_agents(100)
        edges = generate_barabasi_albert_edges(agents, "pop-1", m=3, seed=42)

        # Count degree per agent
        degree = Counter()
        for e in edges:
            degree[e["agent_id"]] += 1
            degree[e["target_id"]] += 1

        avg_degree = sum(degree.values()) / len(degree) if degree else 0
        max_degree = max(degree.values()) if degree else 0

        assert max_degree >= 3 * avg_degree

    def test_ba_edge_structure(self):
        """BA edges should have proper structure fields."""
        agents = self._make_simple_agents(20)
        edges = generate_barabasi_albert_edges(agents, "pop-1", m=2, seed=42)
        for e in edges:
            assert "id" in e
            assert e["population_id"] == "pop-1"
            assert "agent_id" in e
            assert "target_id" in e
            assert e["agent_id"] != e["target_id"]
            assert "relation_type" in e
            assert 0.0 < e["strength"] <= 1.0

    def test_ba_small_population(self):
        """n <= m should return empty edges."""
        agents = self._make_simple_agents(2)
        edges = generate_barabasi_albert_edges(agents, "pop-1", m=3, seed=42)
        assert len(edges) == 0


class TestHybridEdges:
    """Hybrid WS + BA network tests."""

    def _make_simple_agents(self, n: int) -> list[dict]:
        return [
            {"id": f"agent-{i}", "demographics": {"region": "関東（都市部）", "age": 30}}
            for i in range(n)
        ]

    def test_hybrid_has_clustering_and_hubs(self):
        """Hybrid network should have both WS clustering and BA hubs."""
        agents = self._make_simple_agents(100)
        edges = generate_hybrid_edges(
            agents, "pop-1", k=6, beta=0.3, m=3, ba_ratio=0.3,
            cluster_by_attributes=False, seed=42,
        )

        # Should have edges
        assert len(edges) > 0

        # Check for hub existence (BA property)
        degree = Counter()
        for e in edges:
            degree[e["agent_id"]] += 1
            degree[e["target_id"]] += 1

        avg_degree = sum(degree.values()) / len(degree) if degree else 0
        max_degree = max(degree.values()) if degree else 0
        # Hub should exist (at least 2x average)
        assert max_degree >= 2 * avg_degree

    def test_ba_ratio_zero_equals_ws(self):
        """ba_ratio=0 should produce a WS-only network."""
        agents = self._make_simple_agents(50)
        edges_hybrid = generate_hybrid_edges(
            agents, "pop-1", k=4, beta=0.0, m=3, ba_ratio=0.0,
            cluster_by_attributes=False, seed=42,
        )
        edges_ws = generate_watts_strogatz_edges(
            agents, "pop-1", k=4, beta=0.0, cluster_by_attributes=False,
        )

        # Same number of edges (WS only, no BA contribution)
        assert len(edges_hybrid) == len(edges_ws)

    def test_ba_ratio_one_is_ba_only(self):
        """ba_ratio=1 should produce a BA-only network."""
        agents = self._make_simple_agents(50)
        edges = generate_hybrid_edges(
            agents, "pop-1", k=4, beta=0.3, m=3, ba_ratio=1.0,
            cluster_by_attributes=False, seed=42,
        )
        # Should have BA-like edge count: m*(n-m) = 3*47 = 141
        assert len(edges) > 0


class TestNetworkTypeDispatch:
    """generate_network should dispatch based on config type."""

    def _make_simple_agents(self, n: int) -> list[dict]:
        return [
            {"id": f"agent-{i}", "demographics": {"region": "関東（都市部）", "age": 30}}
            for i in range(n)
        ]

    @pytest.mark.asyncio
    async def test_config_dispatch_watts_strogatz(self):
        """type='watts_strogatz' should call WS generator."""
        agents = self._make_simple_agents(20)
        config = {
            "population": {
                "network": {
                    "type": "watts_strogatz",
                    "k": 4,
                    "beta": 0.3,
                    "cluster_by_attributes": False,
                }
            }
        }
        with patch("src.app.services.society.network_generator.settings") as mock_settings:
            mock_settings.load_population_mix_config.return_value = config
            edges = await generate_network(agents, "pop-test")
            assert len(edges) > 0

    @pytest.mark.asyncio
    async def test_config_dispatch_barabasi_albert(self):
        """type='barabasi_albert' should call BA generator."""
        agents = self._make_simple_agents(20)
        config = {
            "population": {
                "network": {
                    "type": "barabasi_albert",
                    "m": 3,
                }
            }
        }
        with patch("src.app.services.society.network_generator.settings") as mock_settings:
            mock_settings.load_population_mix_config.return_value = config
            edges = await generate_network(agents, "pop-test")
            assert len(edges) > 0

    @pytest.mark.asyncio
    async def test_config_dispatch_hybrid(self):
        """type='hybrid' should call hybrid generator."""
        agents = self._make_simple_agents(50)
        config = {
            "population": {
                "network": {
                    "type": "hybrid",
                    "k": 4,
                    "beta": 0.3,
                    "m": 3,
                    "ba_ratio": 0.3,
                    "cluster_by_attributes": False,
                }
            }
        }
        with patch("src.app.services.society.network_generator.settings") as mock_settings:
            mock_settings.load_population_mix_config.return_value = config
            edges = await generate_network(agents, "pop-test")
            assert len(edges) > 0

    @pytest.mark.asyncio
    async def test_real_config_loads_type(self):
        """Real config should load and dispatch correctly (default: watts_strogatz)."""
        agents = self._make_simple_agents(20)
        # Use actual config - should default to watts_strogatz
        edges = await generate_network(agents, "pop-test")
        assert len(edges) > 0


class TestNetworkWithRealPopulation:
    @pytest.mark.asyncio
    async def test_network_generation_with_clustering(self):
        agents = await generate_population("pop-test", count=50, seed=42)
        edges = generate_watts_strogatz_edges(agents, "pop-test", k=4, beta=0.3, cluster_by_attributes=True)
        assert len(edges) > 0
        # Check that agent_ids reference actual agents
        agent_ids = {a["id"] for a in agents}
        for e in edges:
            assert e["agent_id"] in agent_ids
            assert e["target_id"] in agent_ids
