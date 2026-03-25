"""ファクトリ関数自体のテスト"""

from tests.factories import (
    make_simulation,
    make_responses,
    make_agents,
    make_pulse_result,
    make_council_result,
    make_llm_response,
)
from src.app.models.simulation import Simulation


class TestMakeSimulation:
    def test_returns_simulation_instance(self):
        sim = make_simulation()
        assert isinstance(sim, Simulation)

    def test_default_mode_unified(self):
        sim = make_simulation()
        assert sim.mode == "unified"

    def test_override_mode(self):
        sim = make_simulation(mode="single")
        assert sim.mode == "single"

    def test_override_status(self):
        sim = make_simulation(status="running")
        assert sim.status == "running"

    def test_unique_ids(self):
        s1 = make_simulation()
        s2 = make_simulation()
        assert s1.id != s2.id


class TestMakeResponses:
    def test_returns_list_of_dicts(self):
        r = make_responses(["賛成", "反対"])
        assert len(r) == 2
        assert r[0]["stance"] == "賛成"
        assert r[1]["stance"] == "反対"

    def test_custom_confidence(self):
        r = make_responses(["中立"], confidence=0.9)
        assert r[0]["confidence"] == 0.9


class TestMakeAgents:
    def test_returns_correct_count(self):
        a = make_agents(3)
        assert len(a) == 3

    def test_has_big_five(self):
        a = make_agents(1, openness=0.8)
        assert a[0]["big_five"]["O"] == 0.8


class TestMakePulseResult:
    def test_has_required_keys(self):
        p = make_pulse_result()
        assert "agents" in p
        assert "responses" in p
        assert "aggregation" in p
        assert "evaluation" in p
        assert "usage" in p

    def test_override_population_count(self):
        p = make_pulse_result(population_count=50)
        assert p["population_count"] == 50


class TestMakeCouncilResult:
    def test_has_required_keys(self):
        c = make_council_result()
        assert "participants" in c
        assert "synthesis" in c
        assert "usage" in c

    def test_synthesis_has_consensus_points(self):
        c = make_council_result()
        assert "consensus_points" in c["synthesis"]


class TestMakeLlmResponse:
    def test_returns_tuple(self):
        content, usage = make_llm_response()
        assert isinstance(content, dict)
        assert usage["total_tokens"] == 100

    def test_custom_content(self):
        content, _ = make_llm_response(content={"key": "value"}, tokens=50)
        assert content["key"] == "value"

    def test_custom_tokens(self):
        _, usage = make_llm_response(tokens=200)
        assert usage["total_tokens"] == 200
