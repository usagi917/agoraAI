"""phases/intervention.py のテスト"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.factories import make_simulation


DUMMY_INTERVENTION_CANDIDATES = [
    {"label": "段階的規制対応", "hypothesis": "段階的に対応", "score": 0.8, "target_issues": ["規制リスク"]},
    {"label": "技術革新投資", "hypothesis": "技術で解決", "score": 0.6, "target_issues": ["技術的課題"]},
]


class TestInterventionResult:
    def test_has_required_fields(self):
        from src.app.services.phases.intervention import InterventionResult
        result = InterventionResult(
            cycles=[{"cycle": 0, "score": 0.5}],
            best_cycle={"cycle": 0, "score": 0.5},
            interventions=DUMMY_INTERVENTION_CANDIDATES,
            convergence_score=0.75,
            usage={"total_tokens": 100},
        )
        assert len(result.cycles) == 1
        assert result.convergence_score == 0.75
        assert len(result.interventions) == 2


class TestRunIntervention:
    @pytest.fixture
    def mock_deps(self):
        patches = {
            "plan": patch(
                "src.app.services.phases.intervention.plan_interventions",
                new_callable=AsyncMock,
                return_value=DUMMY_INTERVENTION_CANDIDATES,
            ),
            "select": patch(
                "src.app.services.phases.intervention.select_intervention",
                return_value=DUMMY_INTERVENTION_CANDIDATES[0],
            ),
            "compute_score": patch(
                "src.app.services.phases.intervention.compute_objective_score",
                return_value=0.7,
            ),
            "stop_condition": patch(
                "src.app.services.phases.intervention.evaluate_stop_condition",
                return_value=False,  # ループ続行
            ),
            "sse": patch("src.app.services.phases.intervention.sse_manager"),
        }
        mocks = {}
        for key, p in patches.items():
            mocks[key] = p.start()
        mocks["sse"].publish = AsyncMock()
        yield mocks
        for p in patches.values():
            p.stop()

    @pytest.mark.asyncio
    async def test_returns_intervention_result(self, mock_deps):
        # 2サイクル目で停止
        mock_deps["stop_condition"].side_effect = [False, True]

        from src.app.services.phases.intervention import run_intervention, InterventionResult

        sim = make_simulation()
        session = AsyncMock()
        context = {
            "theme": "test",
            "pulse_result": {"aggregation": {}},
            "issues": [{"label": "issue1"}],
        }

        result = await run_intervention(session, sim, context, max_cycles=3)
        assert isinstance(result, InterventionResult)

    @pytest.mark.asyncio
    async def test_respects_max_cycles(self, mock_deps):
        mock_deps["stop_condition"].return_value = False  # 常にループ続行

        from src.app.services.phases.intervention import run_intervention

        sim = make_simulation()
        session = AsyncMock()
        context = {"theme": "test", "pulse_result": {}, "issues": []}

        result = await run_intervention(session, sim, context, max_cycles=2)
        assert len(result.cycles) <= 2

    @pytest.mark.asyncio
    async def test_stops_at_target_score(self, mock_deps):
        mock_deps["stop_condition"].side_effect = [True]  # 即停止

        from src.app.services.phases.intervention import run_intervention

        sim = make_simulation()
        session = AsyncMock()
        context = {"theme": "test", "pulse_result": {}, "issues": []}

        result = await run_intervention(session, sim, context, max_cycles=5)
        assert len(result.cycles) == 1

    @pytest.mark.asyncio
    async def test_returns_best_cycle(self, mock_deps):
        mock_deps["compute_score"].side_effect = [0.5, 0.8]
        mock_deps["stop_condition"].side_effect = [False, True]

        from src.app.services.phases.intervention import run_intervention

        sim = make_simulation()
        session = AsyncMock()
        context = {"theme": "test", "pulse_result": {}, "issues": []}

        result = await run_intervention(session, sim, context, max_cycles=3)
        assert result.best_cycle["score"] == 0.8

    @pytest.mark.asyncio
    async def test_returns_convergence_score(self, mock_deps):
        mock_deps["compute_score"].side_effect = [0.5, 0.7]
        mock_deps["stop_condition"].side_effect = [False, True]

        from src.app.services.phases.intervention import run_intervention

        sim = make_simulation()
        session = AsyncMock()
        context = {"theme": "test", "pulse_result": {}, "issues": []}

        result = await run_intervention(session, sim, context, max_cycles=3)
        assert result.convergence_score == 0.7  # 最終スコア

    @pytest.mark.asyncio
    async def test_calls_plan_interventions(self, mock_deps):
        # 2サイクル: 1サイクル目で介入計画 → 2サイクル目で停止
        mock_deps["stop_condition"].side_effect = [False, True]

        from src.app.services.phases.intervention import run_intervention

        sim = make_simulation()
        session = AsyncMock()
        context = {"theme": "test", "pulse_result": {}, "issues": [{"label": "issue1"}]}

        await run_intervention(session, sim, context, max_cycles=3)
        mock_deps["plan"].assert_awaited()

    @pytest.mark.asyncio
    async def test_cycle_0_has_no_intervention(self, mock_deps):
        mock_deps["stop_condition"].return_value = True

        from src.app.services.phases.intervention import run_intervention

        sim = make_simulation()
        session = AsyncMock()
        context = {"theme": "test", "pulse_result": {}, "issues": []}

        result = await run_intervention(session, sim, context, max_cycles=1)
        assert result.cycles[0].get("intervention") is None
