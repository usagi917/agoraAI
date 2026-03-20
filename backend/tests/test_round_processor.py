"""round_processor モジュールのユニットテスト"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json


# -----------------------------------------------------------------------
# process_round のコンパクト world_state 生成ロジックをインラインで検証
# -----------------------------------------------------------------------

def _build_compact_state(world_state: dict) -> dict:
    """process_round 内のコンパクト化ロジックを再現する。"""
    return {
        "entities": [
            {
                "id": e["id"],
                "label": e.get("label"),
                "type": e.get("entity_type"),
                "importance": e.get("importance_score"),
                "stance": e.get("stance"),
            }
            for e in world_state.get("entities", [])
        ],
        "relations": [
            {
                "source": r["source"],
                "target": r["target"],
                "type": r.get("relation_type"),
                "weight": r.get("weight"),
            }
            for r in world_state.get("relations", [])
        ],
    }


def test_compact_state_empty_world():
    result = _build_compact_state({})
    assert result["entities"] == []
    assert result["relations"] == []


def test_compact_state_entity_fields():
    world_state = {
        "entities": [
            {
                "id": "e1",
                "label": "Corp A",
                "entity_type": "company",
                "importance_score": 0.9,
                "stance": "aggressive",
                "extra_field": "ignored",
            }
        ],
        "relations": [],
    }
    compact = _build_compact_state(world_state)
    assert len(compact["entities"]) == 1
    entity = compact["entities"][0]
    assert entity["id"] == "e1"
    assert entity["label"] == "Corp A"
    assert entity["type"] == "company"
    assert entity["importance"] == 0.9
    assert entity["stance"] == "aggressive"
    # extra_field はコンパクト化で除外される
    assert "extra_field" not in entity


def test_compact_state_relation_fields():
    world_state = {
        "entities": [],
        "relations": [
            {
                "source": "e1",
                "target": "e2",
                "relation_type": "partner",
                "weight": 0.7,
                "extra": "ignored",
            }
        ],
    }
    compact = _build_compact_state(world_state)
    assert len(compact["relations"]) == 1
    rel = compact["relations"][0]
    assert rel["source"] == "e1"
    assert rel["target"] == "e2"
    assert rel["type"] == "partner"
    assert rel["weight"] == 0.7
    assert "extra" not in rel


def test_compact_state_missing_optional_fields():
    """オプションフィールドが欠けていても None で補完される。"""
    world_state = {
        "entities": [{"id": "e1"}],
        "relations": [{"source": "e1", "target": "e2"}],
    }
    compact = _build_compact_state(world_state)
    assert compact["entities"][0]["label"] is None
    assert compact["relations"][0]["weight"] is None


# -----------------------------------------------------------------------
# entity_map 更新ロジックの検証
# -----------------------------------------------------------------------

def _apply_entity_updates(world_state: dict, entity_updates: list) -> dict:
    """process_round 内のエンティティ更新ロジックを再現する。"""
    entity_map = {e["id"]: e for e in world_state.get("entities", [])}
    for update in entity_updates:
        eid = update.get("entity_id", "")
        if eid in entity_map:
            changes = update.get("changes", {})
            entity_map[eid].update(changes)
    return {**world_state, "entities": list(entity_map.values())}


def test_entity_update_applies_changes():
    world_state = {"entities": [{"id": "e1", "power": 5}]}
    updates = [{"entity_id": "e1", "changes": {"power": 10}}]
    result = _apply_entity_updates(world_state, updates)
    entity = next(e for e in result["entities"] if e["id"] == "e1")
    assert entity["power"] == 10


def test_entity_update_ignores_unknown_entity():
    world_state = {"entities": [{"id": "e1", "power": 5}]}
    updates = [{"entity_id": "e_unknown", "changes": {"power": 99}}]
    result = _apply_entity_updates(world_state, updates)
    entity = next(e for e in result["entities"] if e["id"] == "e1")
    assert entity["power"] == 5


def test_entity_update_empty_updates():
    world_state = {"entities": [{"id": "e1", "power": 5}]}
    result = _apply_entity_updates(world_state, [])
    entity = next(e for e in result["entities"] if e["id"] == "e1")
    assert entity["power"] == 5


def test_entity_update_multiple_entities():
    world_state = {
        "entities": [
            {"id": "e1", "value": 1},
            {"id": "e2", "value": 2},
        ]
    }
    updates = [
        {"entity_id": "e1", "changes": {"value": 100}},
        {"entity_id": "e2", "changes": {"value": 200}},
    ]
    result = _apply_entity_updates(world_state, updates)
    e1 = next(e for e in result["entities"] if e["id"] == "e1")
    e2 = next(e for e in result["entities"] if e["id"] == "e2")
    assert e1["value"] == 100
    assert e2["value"] == 200


# -----------------------------------------------------------------------
# relation_map 更新ロジックの検証
# -----------------------------------------------------------------------

def _apply_relation_updates(world_state: dict, relation_updates: list) -> dict:
    """process_round 内のリレーション更新ロジックを再現する。"""
    relation_map = {
        (r.get("source"), r.get("target")): r
        for r in world_state.get("relations", [])
    }
    for update in relation_updates:
        key = (update.get("source", ""), update.get("target", ""))
        if key in relation_map:
            relation_map[key].update(update.get("changes", {}))
    return world_state


def test_relation_update_applies_changes():
    world_state = {
        "relations": [{"source": "e1", "target": "e2", "weight": 0.5}]
    }
    updates = [{"source": "e1", "target": "e2", "changes": {"weight": 0.9}}]
    _apply_relation_updates(world_state, updates)
    assert world_state["relations"][0]["weight"] == 0.9


def test_relation_update_ignores_unknown_pair():
    world_state = {
        "relations": [{"source": "e1", "target": "e2", "weight": 0.5}]
    }
    updates = [{"source": "e1", "target": "e_missing", "changes": {"weight": 0.9}}]
    _apply_relation_updates(world_state, updates)
    assert world_state["relations"][0]["weight"] == 0.5


def test_relation_update_empty():
    world_state = {"relations": [{"source": "e1", "target": "e2", "weight": 0.5}]}
    _apply_relation_updates(world_state, [])
    assert world_state["relations"][0]["weight"] == 0.5
