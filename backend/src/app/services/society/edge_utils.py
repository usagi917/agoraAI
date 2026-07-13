"""ソーシャルグラフのエッジ変換ユーティリティ。"""


def mirror_edges(edges: list[dict]) -> list[dict]:
    """無向タイを双方向へ展開し、方向ごとの重複と自己ループを除く。"""
    seen: set[tuple[str, str]] = set()
    result: list[dict] = []
    for edge in edges:
        source = edge["agent_id"]
        target = edge["target_id"]
        strength = edge.get("strength", 1.0)
        for agent_id, target_id in ((source, target), (target, source)):
            if agent_id == target_id or (agent_id, target_id) in seen:
                continue
            seen.add((agent_id, target_id))
            result.append({
                "agent_id": agent_id,
                "target_id": target_id,
                "strength": strength,
            })
    return result
