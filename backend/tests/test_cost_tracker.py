"""cost_tracker のコスト計算ロジックテスト"""

from src.app.services.cost_tracker import COST_TABLE


def test_cost_table_known_models():
    assert "gpt-4o" in COST_TABLE
    assert "gpt-4o-mini" in COST_TABLE
    assert COST_TABLE["gpt-4o"]["input"] > 0
    assert COST_TABLE["gpt-4o"]["output"] > 0


def test_gpt4o_cost_calculation():
    costs = COST_TABLE["gpt-4o"]
    prompt_tokens = 1000
    completion_tokens = 500
    estimated = (
        prompt_tokens * costs["input"] / 1_000_000
        + completion_tokens * costs["output"] / 1_000_000
    )
    assert estimated == pytest.approx(0.0075, abs=1e-6)


def test_nano_is_cheapest():
    nano_cost = COST_TABLE["gpt-5-nano-2025-08-07"]
    gpt4o_cost = COST_TABLE["gpt-4o"]
    assert nano_cost["input"] < gpt4o_cost["input"]
    assert nano_cost["output"] < gpt4o_cost["output"]


import pytest
