"""stakeholder_mapper ユニットテスト"""
import uuid

import pytest

from src.app.services.graphrag.pipeline import KnowledgeGraph
from src.app.services.graphrag.stakeholder_mapper import (
    SOURCE_ENTITY_ID_FIELD,
    StakeholderSeed,
    map_stakeholders,
)


def _kg(entities=None, relations=None, communities=None):
    return KnowledgeGraph(
        entities=entities or [],
        relations=relations or [],
        communities=communities or [],
    )


def _entity(name, type_="person", description="", community_label="community_0"):
    return {
        "id": str(uuid.uuid4()),
        "name": name,
        "type": type_,
        "description": description,
        "community_label": community_label,
    }


def _rel(source, target):
    return {"source": source, "target": target, "type": "related", "confidence": 0.8}


# ---------------------------------------------------------------------------


def test_map_empty_kg():
    seeds = map_stakeholders(_kg())
    assert seeds == []


def test_map_all_location_entities():
    entities = [_entity(f"place_{i}", type_="location") for i in range(5)]
    seeds = map_stakeholders(_kg(entities=entities))
    assert seeds == []


def test_map_zero_relations():
    entities = [_entity("Charlie"), _entity("Alice"), _entity("Bob")]
    seeds = map_stakeholders(_kg(entities=entities))
    # All degree=0 → deterministic sort by name
    assert [s.name for s in seeds] == ["Alice", "Bob", "Charlie"]


def test_map_community_label_none():
    entity = _entity("Nakamura")
    entity["community_label"] = None
    seeds = map_stakeholders(_kg(entities=[entity]))
    assert len(seeds) == 1
    assert seeds[0].community == "_none"


def test_map_below_min_count():
    # 3 valid entities → returns 3; caller decides fallback, not mapper
    entities = [_entity(f"person_{i}") for i in range(3)]
    seeds = map_stakeholders(_kg(entities=entities))
    assert len(seeds) == 3


def test_map_community_diversity():
    # 2 communities × 3 entities each; A0 and B0 have degree 2
    entities_a = [_entity(f"A{i}", community_label="community_0") for i in range(3)]
    entities_b = [_entity(f"B{i}", community_label="community_1") for i in range(3)]
    relations = [
        _rel("A0", "A1"), _rel("A0", "A2"),
        _rel("B0", "B1"), _rel("B0", "B2"),
    ]
    seeds = map_stakeholders(_kg(entities=entities_a + entities_b, relations=relations), max_count=2)
    names = {s.name for s in seeds}
    assert "A0" in names
    assert "B0" in names
    assert len(seeds) == 2


def test_map_description_truncated():
    entity = _entity("Tanaka", description="x" * 1000)
    seeds = map_stakeholders(_kg(entities=[entity]))
    assert len(seeds) == 1
    assert len(seeds[0].description) == 500


def test_map_max_count_respected():
    entities = [_entity(f"p{i}") for i in range(20)]
    seeds = map_stakeholders(_kg(entities=entities), max_count=15)
    assert len(seeds) == 15
