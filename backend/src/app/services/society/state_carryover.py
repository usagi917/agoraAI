"""Phase 2: 時間 step 間で agent state を引き継ぐユーティリティ.

scenario_pair_factory._clone_population と同じ思想だが、time_axis_orchestrator
から呼びやすいように pure 関数として切り出す。
"""

from __future__ import annotations

import copy
from typing import Any, Iterable


def carry_agents(prev_agents: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """前 step の agents を deep copy して引き継ぐ.

    rolling_summary / episodes / confidence など memory 系フィールドは保持される。
    """
    return [copy.deepcopy(agent) for agent in prev_agents]


def carry_edges(
    prev_edges: Iterable[tuple[int, int]],
    remaining_ids: set[int] | None = None,
) -> list[tuple[int, int]]:
    """前 step の edges を引き継ぐ. remaining_ids が指定されていれば
    両端ともそのセットに含まれる edge のみ残す.
    """
    edges = list(prev_edges)
    if remaining_ids is None:
        return [tuple(e) for e in edges]
    return [tuple(e) for e in edges if e[0] in remaining_ids and e[1] in remaining_ids]


def carry_state(prev_state: dict[str, Any]) -> dict[str, Any]:
    """state 辞書 (agents + edges + metadata) を deep copy で引き継ぐ."""
    new_state: dict[str, Any] = {}
    if "agents" in prev_state:
        new_state["agents"] = carry_agents(prev_state["agents"])
    if "edges" in prev_state:
        new_state["edges"] = [tuple(e) for e in prev_state["edges"]]
    for key, value in prev_state.items():
        if key in ("agents", "edges"):
            continue
        new_state[key] = copy.deepcopy(value)
    return new_state
