"""Phase 2: state_carryover のテスト"""

from __future__ import annotations


def _agent(idx: int, **overrides):
    base = {
        "agent_id": idx,
        "stance": "中立",
        "confidence": 0.5,
        "rolling_summary": f"agent {idx} summary",
        "episodes": [{"id": f"e{idx}-1", "text": "past event"}],
    }
    base.update(overrides)
    return base


class TestCarryAgents:
    def test_carries_rolling_summary_and_episodes(self):
        from src.app.services.society.state_carryover import carry_agents

        prev = [_agent(0), _agent(1)]
        carried = carry_agents(prev)

        assert carried[0]["rolling_summary"] == "agent 0 summary"
        assert carried[0]["episodes"][0]["text"] == "past event"
        # 元と独立 (deep copy)
        carried[0]["episodes"].append({"id": "x"})
        assert len(prev[0]["episodes"]) == 1

    def test_preserves_confidence_distribution(self):
        from src.app.services.society.state_carryover import carry_agents

        prev = [_agent(0, confidence=0.9), _agent(1, confidence=0.1)]
        carried = carry_agents(prev)

        confs = [a["confidence"] for a in carried]
        assert confs == [0.9, 0.1]

    def test_carries_edges(self):
        from src.app.services.society.state_carryover import carry_state

        prev_state = {
            "agents": [_agent(0), _agent(1)],
            "edges": [(0, 1)],
        }
        new_state = carry_state(prev_state)

        assert new_state["edges"] == [(0, 1)]
        # 独立性
        new_state["edges"].append((0, 2))
        assert prev_state["edges"] == [(0, 1)]


class TestCarryEdges:
    def test_filters_edges_by_remaining_agents(self):
        from src.app.services.society.state_carryover import carry_edges

        prev_edges = [(0, 1), (1, 2), (2, 3)]
        remaining_ids = {0, 1, 2}
        carried = carry_edges(prev_edges, remaining_ids)

        assert (0, 1) in carried
        assert (1, 2) in carried
        assert (2, 3) not in carried
