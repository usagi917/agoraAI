"""代表者選出テスト"""

import pytest

from src.app.services.society.representative_selector import (
    select_representatives,
    _cluster_by_stance,
)


class TestClusterByStance:
    def test_groups_correctly(self):
        agents = [{"id": "a1"}, {"id": "a2"}, {"id": "a3"}]
        responses = [
            {"stance": "賛成"},
            {"stance": "反対"},
            {"stance": "賛成"},
        ]
        clusters = _cluster_by_stance(agents, responses)
        assert len(clusters["賛成"]) == 2
        assert len(clusters["反対"]) == 1


class TestSelectRepresentatives:
    def test_selects_citizens_and_experts(self):
        agents = [
            {"id": f"a{i}", "demographics": {"occupation": f"職業{i}", "age": 30 + i, "region": "関東（都市部）"}, "big_five": {}, "speech_style": "丁寧で慎重"}
            for i in range(20)
        ]
        responses = [
            {"stance": ["賛成", "反対", "中立", "条件付き賛成"][i % 4], "confidence": 0.5 + i * 0.02, "reason": f"理由{i}"}
            for i in range(20)
        ]
        participants = select_representatives(agents, responses, max_citizen_reps=6, max_experts=4)

        citizen_count = sum(1 for p in participants if p["role"] == "citizen_representative")
        expert_count = sum(1 for p in participants if p["role"] == "expert")

        assert citizen_count <= 6
        assert expert_count <= 4
        assert len(participants) == citizen_count + expert_count

    def test_experts_have_required_fields(self):
        agents = [{"id": "a1", "demographics": {"occupation": "test", "age": 30, "region": "test"}, "big_five": {}, "speech_style": "test"}]
        responses = [{"stance": "中立", "confidence": 0.5}]
        participants = select_representatives(agents, responses, max_citizen_reps=1, max_experts=2)

        experts = [p for p in participants if p["role"] == "expert"]
        for e in experts:
            assert "expertise" in e
            assert "agent_profile" in e
            assert e["agent_profile"]["id"]

    def test_citizens_from_multiple_stances(self):
        agents = [
            {"id": f"a{i}", "demographics": {"occupation": "test", "age": 30, "region": "test"}, "big_five": {}, "speech_style": "test"}
            for i in range(12)
        ]
        responses = [
            {"stance": ["賛成", "反対", "中立"][i % 3], "confidence": 0.5 + i * 0.03}
            for i in range(12)
        ]
        participants = select_representatives(agents, responses, max_citizen_reps=6, max_experts=0)
        stances = {p.get("stance") for p in participants if p["role"] == "citizen_representative"}
        assert len(stances) >= 2
