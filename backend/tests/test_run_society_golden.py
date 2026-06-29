"""run_society の永続化 characterization(golden)テスト。

run_society は12フェーズを通して SocietyResult レコードを layer 別に永続化する。
P5 でこの巨大関数を _phase_xxx へ分割する際、永続化されるレイヤ集合や
最終ステータスが変わっていないことを保証する安全網。
ハーネスは test_society_orchestrator.py の既存 end-to-end テストの構成を流用する。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_run_society_persists_expected_layers(monkeypatch: pytest.MonkeyPatch):
    from src.app.services.society import society_orchestrator as orchestrator

    persisted_layers: list[str] = []
    published_events: list[str] = []

    class FakeSession:
        def __init__(self):
            self.simulation = SimpleNamespace(
                id="sim-1",
                prompt_text="日本の経済政策について",
                population_id=None,
                status="running",
                completed_at=None,
                metadata_json={},
                error_message=None,
                seed=42,
                scenario_pair_id=None,
            )

        async def get(self, model, obj_id):
            return self.simulation

        def add(self, obj):
            if obj.__class__.__name__ == "SocietyResult":
                persisted_layers.append(obj.layer)

        async def commit(self):
            pass

        async def rollback(self):
            pass

        async def execute(self, stmt):
            return SimpleNamespace(scalar=lambda: 5)

    class FakeSessionContext:
        def __init__(self, session):
            self.session = session

        async def __aenter__(self):
            return self.session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    fake_session = FakeSession()

    async def fake_get_or_create_population(session, population_id, count=None, seed=None, *, strict=False):
        return "pop-1", [
            {"id": "a1", "demographics": {"age": 35, "region": "関東（都市部）", "occupation": "会社員"}}
        ]

    async def fake_publish(simulation_id, event, data):
        published_events.append(event)

    async def fake_select_agents(agents, theme, target_count=100, edges=None):
        return agents

    async def fake_run_activation(selected_agents, theme, on_progress=None):
        if on_progress is not None:
            await on_progress(1, 1)
        return {
            "aggregation": {"stance_distribution": {"賛成": 1}, "total_respondents": 1},
            "representatives": [{"id": "a1"}],
            "responses": [{"stance": "賛成", "confidence": 0.8, "reason": "test"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    async def fake_evaluate_society_simulation(selected_agents, responses):
        return [{"metric_name": "diversity", "score": 0.5, "details": {}}]

    async def fake_run_meeting(participants, theme, simulation_id=None, num_rounds=3):
        return {
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "rounds": [[{
                "participant_index": 0,
                "participant_name": "会社員・35歳",
                "role": "citizen_representative",
                "expertise": "",
                "round": 1,
                "position": "賛成",
                "argument": "経済成長のため",
                "evidence": "GDP成長率",
                "concerns": [],
                "questions_to_others": [],
            }]],
            "participants": [{"role": "citizen_representative", "display_name": "会社員・35歳", "stance": "賛成"}],
            "synthesis": {"consensus_points": ["経済成長は重要"], "key_insights": []},
        }

    monkeypatch.setattr(orchestrator, "async_session", lambda: FakeSessionContext(fake_session))
    monkeypatch.setattr(orchestrator, "get_default_population_size", lambda: 5)
    monkeypatch.setattr(orchestrator, "_get_or_create_population", fake_get_or_create_population)
    monkeypatch.setattr(orchestrator.sse_manager, "publish", fake_publish)
    monkeypatch.setattr(orchestrator, "_save_network", AsyncMock())
    monkeypatch.setattr(orchestrator, "_load_population_edges", AsyncMock(return_value=[]))
    monkeypatch.setattr(orchestrator, "select_agents", fake_select_agents)
    monkeypatch.setattr(orchestrator, "run_activation", fake_run_activation)
    monkeypatch.setattr(orchestrator, "evaluate_society_simulation", fake_evaluate_society_simulation)
    monkeypatch.setattr(orchestrator, "select_representatives", lambda *args, **kwargs: [
        {
            "role": "citizen_representative",
            "agent_profile": {"id": "a1", "agent_index": 0, "demographics": {"age": 35, "region": "関東（都市部）", "occupation": "会社員"}},
            "display_name": "会社員・35歳",
            "stance": "賛成",
            "expertise": "",
        }
    ])
    monkeypatch.setattr(orchestrator, "run_meeting", fake_run_meeting)
    monkeypatch.setattr(orchestrator, "generate_meeting_report", lambda meeting_result: {"summary": "ok"})
    monkeypatch.setattr(orchestrator, "update_agent_memories", AsyncMock())
    monkeypatch.setattr(orchestrator, "evolve_social_graph", AsyncMock())

    await orchestrator.run_society("sim-1")

    # 永続化されるレイヤ集合(エッジ無し=伝播フェーズ無しの代表ケース)を golden として固定。
    # P5 のフェーズ抽出でレイヤの欠落/改名が起きたら即検知する。
    assert set(persisted_layers) == {
        "activation",
        "deliberation_quality",
        "demographic_analysis",
        "evaluation",
        "meeting",
        "narrative",
    }, f"永続化レイヤ集合が変化した: {sorted(set(persisted_layers))}"

    # パイプライン完走の契約: 最終ステータスと主要 SSE イベント。
    assert fake_session.simulation.status == "completed"
    for required_event in ("society_started", "society_activation_completed", "society_completed"):
        assert required_event in published_events, f"必須 SSE イベント欠落: {required_event}"
