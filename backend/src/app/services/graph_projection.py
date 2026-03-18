"""グラフ投影: world_state → graph_state + graph_diff（決定的処理、LLM 不要）"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.graph_state import GraphState
from src.app.models.graph_diff import GraphDiff

MAX_NODES = 20
MAX_EDGES = 40


def project_graph(world_state: dict) -> dict:
    """world_state から graph_state を生成する（top-K 選択）。"""
    entities = world_state.get("entities", [])
    relations = world_state.get("relations", [])

    # importance_score でソート、上位 MAX_NODES を選択
    sorted_entities = sorted(
        entities,
        key=lambda e: float(e.get("importance_score", 0)),
        reverse=True,
    )[:MAX_NODES]

    selected_ids = {e["id"] for e in sorted_entities}

    # ノード生成
    nodes = []
    for e in sorted_entities:
        nodes.append({
            "id": e["id"],
            "label": e.get("label", ""),
            "type": e.get("entity_type", "unknown"),
            "importance_score": float(e.get("importance_score", 0.5)),
            "stance": e.get("stance", ""),
            "activity_score": float(e.get("activity_score", 0.5)),
            "sentiment_score": float(e.get("sentiment_score", 0.0)),
            "status": e.get("status", "active"),
            "group": e.get("group", ""),
        })

    # 選択されたエンティティ間のリレーションのみ、重み順で MAX_EDGES まで
    filtered_relations = [
        r for r in relations
        if r.get("source") in selected_ids and r.get("target") in selected_ids
    ]
    sorted_relations = sorted(
        filtered_relations,
        key=lambda r: float(r.get("weight", 0)),
        reverse=True,
    )[:MAX_EDGES]

    edges = []
    for r in sorted_relations:
        edges.append({
            "id": r.get("id", f"{r['source']}_{r['target']}"),
            "source": r["source"],
            "target": r["target"],
            "relation_type": r.get("relation_type", "unknown"),
            "weight": float(r.get("weight", 0.5)),
            "direction": r.get("direction", "directed"),
            "status": r.get("status", "active"),
        })

    return {"nodes": nodes, "edges": edges}


def compute_diff(prev_graph: dict | None, curr_graph: dict) -> dict:
    """前ラウンドと現ラウンドのグラフを比較して diff を生成する。"""
    if prev_graph is None:
        return {
            "added_nodes": curr_graph["nodes"],
            "updated_nodes": [],
            "removed_nodes": [],
            "added_edges": curr_graph["edges"],
            "updated_edges": [],
            "removed_edges": [],
            "highlights": [n["id"] for n in curr_graph["nodes"][:5]],
        }

    prev_node_map = {n["id"]: n for n in prev_graph.get("nodes", [])}
    curr_node_map = {n["id"]: n for n in curr_graph.get("nodes", [])}
    prev_edge_map = {e["id"]: e for e in prev_graph.get("edges", [])}
    curr_edge_map = {e["id"]: e for e in curr_graph.get("edges", [])}

    added_nodes = [n for nid, n in curr_node_map.items() if nid not in prev_node_map]
    removed_nodes = [n for nid, n in prev_node_map.items() if nid not in curr_node_map]
    updated_nodes = [
        n for nid, n in curr_node_map.items()
        if nid in prev_node_map and n != prev_node_map[nid]
    ]

    added_edges = [e for eid, e in curr_edge_map.items() if eid not in prev_edge_map]
    removed_edges = [e for eid, e in prev_edge_map.items() if eid not in curr_edge_map]
    updated_edges = [
        e for eid, e in curr_edge_map.items()
        if eid in prev_edge_map and e != prev_edge_map[eid]
    ]

    # ハイライト: 変化が大きいエンティティ
    highlights = [n["id"] for n in added_nodes + updated_nodes][:5]

    return {
        "added_nodes": added_nodes,
        "updated_nodes": updated_nodes,
        "removed_nodes": removed_nodes,
        "added_edges": added_edges,
        "updated_edges": updated_edges,
        "removed_edges": removed_edges,
        "highlights": highlights,
    }


async def save_graph_state(
    session: AsyncSession,
    run_id: str,
    round_number: int,
    graph: dict,
    diff: dict,
    event_summary: str = "",
) -> None:
    """グラフ状態と diff を DB に保存する。"""
    graph_state = GraphState(
        id=str(uuid.uuid4()),
        run_id=run_id,
        round_number=round_number,
        nodes=graph["nodes"],
        edges=graph["edges"],
        focus_entities=[],
        highlights=diff.get("highlights", []),
        event_refs=[],
    )
    session.add(graph_state)

    graph_diff = GraphDiff(
        id=str(uuid.uuid4()),
        run_id=run_id,
        round_number=round_number,
        added_nodes=diff.get("added_nodes", []),
        updated_nodes=diff.get("updated_nodes", []),
        removed_nodes=diff.get("removed_nodes", []),
        added_edges=diff.get("added_edges", []),
        updated_edges=diff.get("updated_edges", []),
        removed_edges=diff.get("removed_edges", []),
        highlights=diff.get("highlights", []),
        event_summary=event_summary,
    )
    session.add(graph_diff)
    await session.flush()
