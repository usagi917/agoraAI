"""ネットワーク生成テスト: 小世界特性（クラスタ係数、エッジ数）"""

import pytest

from src.app.services.society.network_generator import (
    generate_watts_strogatz_edges,
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
