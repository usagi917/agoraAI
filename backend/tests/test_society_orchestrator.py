"""Society オーケストレータ統合テスト（LLMモック）"""

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch, MagicMock


class TestSocietyOrchestratorImports:
    """基本的なインポートテスト"""

    def test_import_orchestrator(self):
        from src.app.services.society.society_orchestrator import run_society
        assert callable(run_society)

    def test_import_all_services(self):
        from src.app.services.society.population_generator import generate_population
        from src.app.services.society.network_generator import generate_network
        from src.app.services.society.agent_selector import select_agents
        from src.app.services.society.activation_layer import run_activation
        from src.app.services.society.evaluation import evaluate_society_simulation
        assert all(callable(f) for f in [
            generate_population, generate_network, select_agents,
            run_activation, evaluate_society_simulation,
        ])


class TestSocietyOrchestratorFlow:
    """オーケストレーションフローのユニットテスト"""

    @pytest.mark.asyncio
    async def test_population_then_select_then_activate(self):
        """Population→Selection→Activation の一連の流れ（LLMモック）"""
        from src.app.services.society.population_generator import generate_population
        from src.app.services.society.agent_selector import select_agents
        from src.app.services.society.activation_layer import _aggregate_opinions, _parse_activation_response

        # 1. Population 生成
        agents = await generate_population("test-pop", count=100, seed=42)
        assert len(agents) == 100

        # 2. 選抜
        selected = await select_agents(agents, "日本の経済政策について", target_count=20, min_count=20, max_count=20)
        assert 15 <= len(selected) <= 60  # diversity additions may increase count

        # 3. 活性化レスポンスのパースと集計（LLM呼び出しなし）
        mock_responses = [
            _parse_activation_response({
                "stance": ["賛成", "反対", "中立", "条件付き賛成"][i % 4],
                "confidence": 0.5 + (i % 5) * 0.1,
                "reason": f"理由{i}",
                "concern": f"懸念{i % 3}",
                "priority": f"優先{i % 2}",
            })
            for i in range(len(selected))
        ]

        aggregation = _aggregate_opinions(mock_responses)
        assert aggregation["total_respondents"] == len(selected)
        assert len(aggregation["stance_distribution"]) >= 2

    @pytest.mark.asyncio
    async def test_evaluation_after_activation(self):
        """評価メトリクスの計算"""
        from src.app.services.society.population_generator import generate_population
        from src.app.services.society.evaluation import evaluate_society_simulation

        agents = await generate_population("test-pop", count=50, seed=42)
        responses = [
            {
                "stance": ["賛成", "反対", "中立"][i % 3],
                "confidence": 0.3 + (i % 7) * 0.1,
                "reason": f"理由{i}",
            }
            for i in range(50)
        ]

        metrics = await evaluate_society_simulation(agents, responses)
        assert len(metrics) >= 3  # diversity, consistency, calibration

        metric_dict = {m["metric_name"]: m["score"] for m in metrics}
        assert "diversity" in metric_dict
        assert metric_dict["diversity"] > 0  # 3 stances should give some diversity

    @pytest.mark.asyncio
    async def test_run_society_uses_configured_default_population_size(self, monkeypatch: pytest.MonkeyPatch):
        from src.app.services.society import society_orchestrator as orchestrator

        observed_counts: list[int] = []
        published_events: list[tuple[str, dict]] = []

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
                )

            async def get(self, model, obj_id):
                return self.simulation

            def add(self, obj):
                pass

            async def commit(self):
                pass

            async def rollback(self):
                pass

            async def execute(self, stmt):
                """func.count() クエリ用のフェイクレスポンス。"""
                return SimpleNamespace(scalar=lambda: 5)

        class FakeSessionContext:
            def __init__(self, session):
                self.session = session

            async def __aenter__(self):
                return self.session

            async def __aexit__(self, exc_type, exc, tb):
                return False

        fake_session = FakeSession()

        async def fake_get_or_create_population(session, population_id, count=None):
            observed_counts.append(count)
            return "pop-1", [{"id": "a1", "demographics": {"age": 35, "region": "関東（都市部）", "occupation": "会社員"}}]

        async def fake_publish(simulation_id, event, data):
            published_events.append((event, data))

        async def fake_select_agents(agents, theme, target_count=100):
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
            return {"usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, "rounds": []}

        monkeypatch.setattr(orchestrator, "async_session", lambda: FakeSessionContext(fake_session))
        monkeypatch.setattr(orchestrator, "get_default_population_size", lambda: 321)
        monkeypatch.setattr(orchestrator, "_get_or_create_population", fake_get_or_create_population)
        monkeypatch.setattr(orchestrator.sse_manager, "publish", fake_publish)
        monkeypatch.setattr(orchestrator, "_save_network", AsyncMock())
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

        monkeypatch.setattr(orchestrator, "run_meeting", fake_run_meeting)
        monkeypatch.setattr(orchestrator, "generate_meeting_report", lambda meeting_result: {"summary": "ok"})
        monkeypatch.setattr(orchestrator, "update_agent_memories", AsyncMock())
        monkeypatch.setattr(orchestrator, "evolve_social_graph", AsyncMock())

        await orchestrator.run_society("sim-1")

        assert observed_counts == [321]
        assert any(
            event == "population_status" and payload.get("target_count") == 321
            for event, payload in published_events
        )
