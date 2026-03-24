"""KGEvolutionService のユニットテスト"""

import pytest

from src.app.services.society.kg_evolution_service import KGEvolutionService, _sanitize_id


class TestSanitizeId:
    def test_simple_ascii(self):
        assert _sanitize_id("carbon_tax") == "carbon_tax"

    def test_japanese(self):
        result = _sanitize_id("炭素税")
        assert result == "炭素税"

    def test_mixed(self):
        result = _sanitize_id("CO2 排出量")
        assert "CO2" in result
        assert "排出量" in result

    def test_special_chars(self):
        result = _sanitize_id("A/B テスト (2024)")
        assert "/" not in result
        assert "(" not in result


class TestBuildDiff:
    def setup_method(self):
        self.service = KGEvolutionService()

    def test_empty_updates(self):
        updates = {"new_entities": [], "new_relations": [], "updated_entities": []}
        diff = self.service._build_diff(updates, 1, "test")
        assert diff["added_nodes"] == []
        assert diff["added_edges"] == []
        assert diff["updated_nodes"] == []

    def test_new_entities_become_added_nodes(self):
        updates = {
            "new_entities": [
                {"name": "炭素税", "type": "policy", "description": "CO2課税", "importance_score": 0.8},
                {"name": "経済成長", "type": "concept", "description": "GDP", "importance_score": 0.6},
            ],
            "new_relations": [],
            "updated_entities": [],
        }
        diff = self.service._build_diff(updates, 1, "test")
        assert len(diff["added_nodes"]) == 2
        node = diff["added_nodes"][0]
        assert node["id"] == "kg-炭素税"
        assert node["label"] == "炭素税"
        assert node["type"] == "policy"
        assert node["importance_score"] == 0.8
        assert node["group"] == "knowledge"

    def test_duplicate_entities_skipped(self):
        updates1 = {
            "new_entities": [{"name": "炭素税", "type": "policy", "importance_score": 0.8}],
            "new_relations": [],
            "updated_entities": [],
        }
        self.service._build_diff(updates1, 1, "test")

        updates2 = {
            "new_entities": [{"name": "炭素税", "type": "policy", "importance_score": 0.9}],
            "new_relations": [],
            "updated_entities": [],
        }
        diff = self.service._build_diff(updates2, 2, "test")
        assert len(diff["added_nodes"]) == 0

    def test_new_relations_become_added_edges(self):
        # First add entities
        self.service._entity_index["炭素税"] = {"name": "炭素税"}
        self.service._entity_index["環境規制"] = {"name": "環境規制"}

        updates = {
            "new_entities": [],
            "new_relations": [
                {"source": "炭素税", "target": "環境規制", "type": "影響", "evidence": "test", "confidence": 0.7},
            ],
            "updated_entities": [],
        }
        diff = self.service._build_diff(updates, 1, "test")
        assert len(diff["added_edges"]) == 1
        edge = diff["added_edges"][0]
        assert edge["source"] == "kg-炭素税"
        assert edge["target"] == "kg-環境規制"
        assert edge["relation_type"] == "influence"
        assert edge["weight"] == 0.7

    def test_updated_entities_become_updated_nodes(self):
        self.service._entity_index["炭素税"] = {"name": "炭素税", "importance_score": 0.5}

        updates = {
            "new_entities": [],
            "new_relations": [],
            "updated_entities": [
                {"name": "炭素税", "importance_delta": 0.2, "reason": "議論で注目"},
            ],
        }
        diff = self.service._build_diff(updates, 1, "test")
        assert len(diff["updated_nodes"]) == 1
        assert diff["updated_nodes"][0]["id"] == "kg-炭素税"
        assert diff["updated_nodes"][0]["importance_score"] == 0.7

    def test_importance_clamped_to_0_1(self):
        self.service._entity_index["X"] = {"name": "X", "importance_score": 0.95}

        updates = {
            "new_entities": [],
            "new_relations": [],
            "updated_entities": [{"name": "X", "importance_delta": 0.2}],
        }
        diff = self.service._build_diff(updates, 1, "test")
        assert diff["updated_nodes"][0]["importance_score"] == 1.0

    def test_unknown_relation_type_defaults_to_influence(self):
        self.service._entity_index["A"] = {"name": "A"}
        self.service._entity_index["B"] = {"name": "B"}

        updates = {
            "new_entities": [],
            "new_relations": [
                {"source": "A", "target": "B", "type": "unknown_type", "confidence": 0.5},
            ],
            "updated_entities": [],
        }
        diff = self.service._build_diff(updates, 1, "test")
        assert diff["added_edges"][0]["relation_type"] == "influence"


class TestBuildAgentEntityLinks:
    def setup_method(self):
        self.service = KGEvolutionService()

    def test_finds_mentions(self):
        args = [
            {
                "participant_index": 3,
                "participant_name": "田中",
                "argument": "炭素税は経済に影響する",
                "evidence": "",
                "concerns": [],
            },
        ]
        updates = {
            "new_entities": [{"name": "炭素税"}],
            "updated_entities": [],
        }
        links = self.service._build_agent_entity_links(args, updates)
        assert len(links) == 1
        assert links[0]["agent_id"] == "agent-3"
        assert links[0]["entity_id"] == "kg-炭素税"

    def test_no_match(self):
        args = [
            {
                "participant_index": 0,
                "participant_name": "佐藤",
                "argument": "特に意見はない",
                "evidence": "",
                "concerns": [],
            },
        ]
        updates = {"new_entities": [{"name": "炭素税"}], "updated_entities": []}
        links = self.service._build_agent_entity_links(args, updates)
        assert len(links) == 0

    def test_missing_participant_index_skipped(self):
        args = [{"participant_name": "田中", "argument": "炭素税について"}]
        updates = {"new_entities": [{"name": "炭素税"}], "updated_entities": []}
        links = self.service._build_agent_entity_links(args, updates)
        assert len(links) == 0


class TestSeedFromExisting:
    def test_seed_entities_and_relations(self):
        service = KGEvolutionService()
        entities = [
            {"name": "A", "type": "concept", "importance_score": 0.5},
            {"name": "B", "type": "policy", "importance_score": 0.8},
        ]
        relations = [
            {"source": "A", "target": "B", "type": "影響"},
        ]
        service.seed_from_existing(entities, relations)
        assert "A" in service._entity_index
        assert "B" in service._entity_index
        assert "A::B::影響" in service._relation_index

    def test_seeded_entities_not_duplicated_in_diff(self):
        service = KGEvolutionService()
        service.seed_from_existing(
            [{"name": "A", "type": "concept", "importance_score": 0.5}], []
        )
        updates = {
            "new_entities": [{"name": "A", "type": "concept", "importance_score": 0.9}],
            "new_relations": [],
            "updated_entities": [],
        }
        diff = service._build_diff(updates, 1, "test")
        assert len(diff["added_nodes"]) == 0
