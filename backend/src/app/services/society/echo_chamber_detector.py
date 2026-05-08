"""エコーチェンバー検出 — 連結成分クラスタ + スタンス偏在度."""

from __future__ import annotations

from collections import Counter


def _connected_components(
    nodes: list[int],
    edges: list[tuple[int, int]],
) -> list[list[int]]:
    """無向グラフの連結成分を Union-Find で求める。"""
    parent: dict[int, int] = {n: n for n in nodes}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    node_set = set(nodes)
    for a, b in edges:
        if a in node_set and b in node_set and a != b:
            union(a, b)

    components: dict[int, list[int]] = {}
    for n in nodes:
        root = find(n)
        components.setdefault(root, []).append(n)
    # 安定した順序のため、各成分を最小ノードでソート
    out = list(components.values())
    for comp in out:
        comp.sort()
    out.sort(key=lambda c: c[0])
    return out


def detect_echo_chambers(
    responses: list[dict],
    graph_edges: list[tuple[int, int]],
) -> dict:
    """エコーチェンバー検出を実行する。

    Args:
        responses: 各エージェントの最新スタンスを含む dict のリスト。
        graph_edges: 無向辺 (i, j) のリスト。

    Returns:
        ``{"clusters": [[agent_ids,...], ...],
           "polarity_per_cluster": [...],
           "echo_score": float}``
    """
    if not responses:
        return {"clusters": [], "polarity_per_cluster": [], "echo_score": 0.0}

    stance_by_id: dict[int, str] = {
        r["agent_id"]: r["stance"] for r in responses
    }
    agent_ids = [r["agent_id"] for r in responses]

    clusters = _connected_components(agent_ids, graph_edges)

    polarities: list[float] = []
    for cluster in clusters:
        stances = [stance_by_id[a] for a in cluster if a in stance_by_id]
        if not stances:
            polarities.append(0.0)
            continue
        counts = Counter(stances)
        top_count = counts.most_common(1)[0][1]
        polarities.append(top_count / len(stances))

    total_size = sum(len(c) for c in clusters)
    if total_size == 0:
        echo_score = 0.0
    else:
        weighted = sum(
            polarity * len(cluster)
            for cluster, polarity in zip(clusters, polarities)
        )
        echo_score = weighted / total_size

    return {
        "clusters": clusters,
        "polarity_per_cluster": polarities,
        "echo_score": float(echo_score),
    }
