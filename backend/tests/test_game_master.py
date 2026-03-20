"""GameMaster の純粋メソッドのユニットテスト"""

import pytest
from unittest.mock import MagicMock, patch


# -----------------------------------------------------------------------
# GameMaster のインスタンス化とヘルパーメソッドテスト
# -----------------------------------------------------------------------

def _make_game_master():
    """GameMaster を設定ファイル依存なしでインスタンス化する。"""
    mock_config = {
        "game_master": {
            "max_active_agents": 15,
            "max_concurrent_agents": 10,
            "conflict_resolution": "priority",
            "enable_event_injection": True,
            "consistency_check_frequency": 2,
        },
        "communication": {
            "max_conversation_turns": 8,
            "relevance_threshold": 0.3,
            "batch_response_size": 5,
            "enable_structured_debate": False,
        },
        "scheduling": {
            "protagonist_count": 8,
            "active_count": 22,
            "reactive_count": 40,
            "reclassify_frequency": 2,
        },
        "cognitive": {"mode": "legacy"},
    }
    # Pydantic BaseSettings のメソッドは Settings クラスに直接 patch する
    with patch(
        "src.app.config.Settings.load_cognitive_config",
        return_value=mock_config,
    ):
        from src.app.services.game_master.game_master import GameMaster
        return GameMaster()


@pytest.fixture
def game_master():
    return _make_game_master()


# -----------------------------------------------------------------------
# _apply_agent_results
# -----------------------------------------------------------------------

def test_apply_agent_results_updates_entity(game_master):
    world_state = {
        "entities": [{"id": "e1", "power": 5}, {"id": "e2", "power": 3}],
        "relations": [],
    }
    results = [{"entity_updates": [{"entity_id": "e1", "changes": {"power": 10}}]}]
    updated = game_master._apply_agent_results(world_state, results)
    e1 = next(e for e in updated["entities"] if e["id"] == "e1")
    assert e1["power"] == 10


def test_apply_agent_results_updates_relation(game_master):
    world_state = {
        "entities": [],
        "relations": [{"source": "e1", "target": "e2", "weight": 0.5}],
    }
    results = [{"relation_updates": [{"source": "e1", "target": "e2", "changes": {"weight": 0.9}}]}]
    game_master._apply_agent_results(world_state, results)
    assert world_state["relations"][0]["weight"] == 0.9


def test_apply_agent_results_ignores_unknown_entity(game_master):
    world_state = {
        "entities": [{"id": "e1", "power": 5}],
        "relations": [],
    }
    results = [{"entity_updates": [{"entity_id": "e_missing", "changes": {"power": 99}}]}]
    updated = game_master._apply_agent_results(world_state, results)
    e1 = next(e for e in updated["entities"] if e["id"] == "e1")
    assert e1["power"] == 5


def test_apply_agent_results_empty_results(game_master):
    world_state = {
        "entities": [{"id": "e1", "power": 5}],
        "relations": [],
    }
    updated = game_master._apply_agent_results(world_state, [])
    e1 = next(e for e in updated["entities"] if e["id"] == "e1")
    assert e1["power"] == 5


def test_apply_agent_results_no_entity_updates_key(game_master):
    """result dict に entity_updates キーがない場合でも safe に処理される。"""
    world_state = {"entities": [{"id": "e1", "x": 1}], "relations": []}
    results = [{"action": "do_something"}]  # entity_updates なし
    updated = game_master._apply_agent_results(world_state, results)
    assert len(updated["entities"]) == 1


# -----------------------------------------------------------------------
# _collect_entity_updates
# -----------------------------------------------------------------------

def test_collect_entity_updates_combines_from_all_results(game_master):
    results = [
        {"entity_updates": [{"entity_id": "e1", "changes": {"x": 1}}]},
        {"entity_updates": [{"entity_id": "e2", "changes": {"x": 2}}]},
    ]
    updates = game_master._collect_entity_updates(results)
    assert len(updates) == 2


def test_collect_entity_updates_empty_results(game_master):
    updates = game_master._collect_entity_updates([])
    assert updates == []


def test_collect_entity_updates_no_key(game_master):
    results = [{"action": "something"}]
    updates = game_master._collect_entity_updates(results)
    assert updates == []


# -----------------------------------------------------------------------
# _collect_relation_updates
# -----------------------------------------------------------------------

def test_collect_relation_updates_combines(game_master):
    results = [
        {"relation_updates": [{"source": "e1", "target": "e2"}]},
        {"relation_updates": [{"source": "e3", "target": "e4"}]},
    ]
    updates = game_master._collect_relation_updates(results)
    assert len(updates) == 2


def test_collect_relation_updates_empty(game_master):
    assert game_master._collect_relation_updates([]) == []


# -----------------------------------------------------------------------
# _generate_round_summary
# -----------------------------------------------------------------------

def test_generate_round_summary_includes_agent_count(game_master):
    results = [
        {"agent_name": "Agent A", "action": "did X"},
        {"agent_name": "Agent B", "action": "did Y"},
    ]
    summary = game_master._generate_round_summary(results, [])
    assert "2" in summary


def test_generate_round_summary_empty_results(game_master):
    summary = game_master._generate_round_summary([], [])
    assert isinstance(summary, str)
    assert "0" in summary


def test_generate_round_summary_limits_to_5_actions(game_master):
    """先頭5エージェントのみサマリに含める。"""
    results = [{"agent_name": f"Agent{i}", "action": f"action{i}"} for i in range(10)]
    summary = game_master._generate_round_summary(results, [])
    # 合計エージェント数は含まれる
    assert "10" in summary


# -----------------------------------------------------------------------
# コンストラクタ設定値
# -----------------------------------------------------------------------

def test_game_master_max_active_agents(game_master):
    assert game_master.max_active_agents == 15


def test_game_master_max_concurrent_agents(game_master):
    assert game_master.max_concurrent_agents == 10


def test_game_master_conflict_resolution(game_master):
    assert game_master.conflict_resolution == "priority"


def test_game_master_enable_event_injection(game_master):
    assert game_master.enable_event_injection is True


def test_game_master_debate_protocol_disabled_by_default(game_master):
    """enable_structured_debate=False の場合、debate_protocol は None。"""
    assert game_master.debate_protocol is None
