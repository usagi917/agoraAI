"""echo_chamber_detector のテスト: 連結成分クラスタ + スタンス偏在度."""

from __future__ import annotations

import pytest

from src.app.services.society.echo_chamber_detector import detect_echo_chambers


def _resp(agent_id: int, stance: str, confidence: float = 0.7) -> dict:
    return {"agent_id": agent_id, "stance": stance, "confidence": confidence}


# ---------------------------------------------------------------------------
# Basic detection
# ---------------------------------------------------------------------------

def test_detect_returns_required_keys():
    responses = [_resp(0, "賛成"), _resp(1, "賛成")]
    edges = [(0, 1)]

    result = detect_echo_chambers(responses, edges)

    assert "clusters" in result
    assert "polarity_per_cluster" in result
    assert "echo_score" in result
    assert isinstance(result["clusters"], list)
    assert isinstance(result["polarity_per_cluster"], list)
    assert isinstance(result["echo_score"], float)


def test_single_agent_no_edges():
    responses = [_resp(0, "賛成")]
    edges: list[tuple[int, int]] = []

    result = detect_echo_chambers(responses, edges)

    assert len(result["clusters"]) == 1
    assert result["clusters"][0] == [0]
    # 1 員クラスタは完全に偏在 (1.0)
    assert result["polarity_per_cluster"][0] == pytest.approx(1.0)
    assert result["echo_score"] == pytest.approx(1.0)


def test_empty_inputs():
    """エージェント無しの場合は空のクラスタを返し echo_score は 0。"""
    result = detect_echo_chambers([], [])

    assert result["clusters"] == []
    assert result["polarity_per_cluster"] == []
    assert result["echo_score"] == pytest.approx(0.0)


def test_no_edges_creates_singleton_clusters():
    """辺がない場合、各エージェントは独立したシングルトンクラスタ。"""
    responses = [_resp(0, "賛成"), _resp(1, "反対"), _resp(2, "中立")]
    edges: list[tuple[int, int]] = []

    result = detect_echo_chambers(responses, edges)

    assert len(result["clusters"]) == 3
    for cluster in result["clusters"]:
        assert len(cluster) == 1


# ---------------------------------------------------------------------------
# Echo chamber on partitioned graph
# ---------------------------------------------------------------------------

def test_partitioned_graph_creates_two_clusters():
    """二つの分離された成分は 2 クラスタとして検出される。"""
    responses = [
        _resp(0, "賛成"),
        _resp(1, "賛成"),
        _resp(2, "賛成"),
        _resp(3, "反対"),
        _resp(4, "反対"),
        _resp(5, "反対"),
    ]
    edges = [(0, 1), (1, 2), (3, 4), (4, 5)]

    result = detect_echo_chambers(responses, edges)

    assert len(result["clusters"]) == 2
    cluster_sets = [set(c) for c in result["clusters"]]
    assert {0, 1, 2} in cluster_sets
    assert {3, 4, 5} in cluster_sets
    # 両クラスタとも同一スタンスのみ → 偏在度 1.0
    for p in result["polarity_per_cluster"]:
        assert p == pytest.approx(1.0)
    # 完全な echo chamber
    assert result["echo_score"] == pytest.approx(1.0)


def test_polarity_reflects_stance_share():
    """クラスタ内の最大スタンス占有率が polarity となる。"""
    responses = [
        _resp(0, "賛成"),
        _resp(1, "賛成"),
        _resp(2, "賛成"),
        _resp(3, "反対"),
    ]
    # 全員連結
    edges = [(0, 1), (1, 2), (2, 3)]

    result = detect_echo_chambers(responses, edges)

    assert len(result["clusters"]) == 1
    # 4 名中 3 名が "賛成" → 0.75
    assert result["polarity_per_cluster"][0] == pytest.approx(0.75)


def test_mixed_clusters_lower_echo_score():
    """混在クラスタの方が echo_score は低い (= 単一スタンスより低い)。"""
    # シナリオ A: 完全に二極化 (echo chamber)
    responses_a = [
        _resp(0, "賛成"), _resp(1, "賛成"),
        _resp(2, "反対"), _resp(3, "反対"),
    ]
    edges_a = [(0, 1), (2, 3)]
    score_a = detect_echo_chambers(responses_a, edges_a)["echo_score"]

    # シナリオ B: 混合 (echo ではない)
    responses_b = [
        _resp(0, "賛成"), _resp(1, "反対"),
        _resp(2, "賛成"), _resp(3, "反対"),
    ]
    edges_b = [(0, 1), (2, 3)]
    score_b = detect_echo_chambers(responses_b, edges_b)["echo_score"]

    assert score_a > score_b
    assert score_a == pytest.approx(1.0)
    assert score_b == pytest.approx(0.5)


def test_echo_score_weighted_by_cluster_size():
    """echo_score はクラスタサイズで加重平均される。"""
    # 大クラスタ (size=4, polarity=1.0) + 小クラスタ (size=2, polarity=0.5)
    responses = [
        _resp(0, "賛成"), _resp(1, "賛成"), _resp(2, "賛成"), _resp(3, "賛成"),
        _resp(4, "賛成"), _resp(5, "反対"),
    ]
    edges = [(0, 1), (1, 2), (2, 3), (4, 5)]

    result = detect_echo_chambers(responses, edges)
    # weighted = (4 * 1.0 + 2 * 0.5) / 6 = 5/6 ≈ 0.8333
    assert result["echo_score"] == pytest.approx(5.0 / 6.0, rel=1e-3)


def test_undirected_edges():
    """edges は無向として扱われる。"""
    responses = [_resp(0, "賛成"), _resp(1, "賛成")]
    edges = [(1, 0)]  # reversed direction

    result = detect_echo_chambers(responses, edges)

    assert len(result["clusters"]) == 1
    assert set(result["clusters"][0]) == {0, 1}
