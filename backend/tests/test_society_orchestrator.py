"""Society オーケストレータ統合テスト（LLMモック）"""

import pytest
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
