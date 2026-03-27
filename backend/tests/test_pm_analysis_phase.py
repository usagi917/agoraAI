"""phases/pm_analysis.py のテスト"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.factories import make_simulation


DUMMY_PM_RESULT = {
    "type": "pm_board",
    "sections": {
        "core_question": "このプロジェクトは実行すべきか？",
        "assumptions": ["仮説1", "仮説2"],
        "uncertainties": ["不確実性1"],
        "risks": ["リスク1"],
        "winning_hypothesis": {"hypothesis": "テスト仮説"},
        "customer_validation_plan": {"plan": "テスト計画"},
        "market_view": {"market": "テスト市場"},
        "gtm_hypothesis": {"gtm": "テストGTM"},
        "mvp_scope": {"scope": "テストMVP"},
        "plan_30_60_90": {"30": "計画30日"},
        "top_5_actions": ["アクション1", "アクション2"],
    },
    "contradictions": ["矛盾1"],
    "overall_confidence": 0.72,
    "key_decision_points": ["判断ポイント1"],
    "pm_analyses": [
        {"persona": "strategy_pm", "display_name": "戦略PM", "analysis": {"key": "value"}},
    ],
    "synthesis": {"top_5_actions": ["アクション1"]},
    "usage": {"total_tokens": 500},
    "decision_brief": {"recommendation": "Go"},
    "content": "# PM分析レポート",
}


class TestPMAnalysisResult:
    """PMAnalysisResult のデータ構造テスト"""

    def test_has_required_fields(self):
        from src.app.services.phases.pm_analysis import PMAnalysisResult
        result = PMAnalysisResult(
            analyses=[{"persona": "strategy_pm"}],
            synthesis={"top_5_actions": []},
            sections={"core_question": "test"},
            decision_brief={"recommendation": "Go"},
            usage={"total_tokens": 100},
        )
        assert result.analyses[0]["persona"] == "strategy_pm"
        assert result.decision_brief["recommendation"] == "Go"


class TestRunPMAnalysis:
    """run_pm_analysis() の動作テスト"""

    @pytest.mark.asyncio
    @patch("src.app.services.phases.pm_analysis.run_pm_board", new_callable=AsyncMock, return_value=DUMMY_PM_RESULT)
    async def test_returns_pm_analysis_result(self, mock_run_pm):
        from src.app.services.phases.pm_analysis import run_pm_analysis, PMAnalysisResult

        sim = make_simulation()
        session = AsyncMock()
        context = {"theme": "AI規制分析", "document_text": "テスト文書"}

        result = await run_pm_analysis(session, sim, context)
        assert isinstance(result, PMAnalysisResult)

    @pytest.mark.asyncio
    @patch("src.app.services.phases.pm_analysis.run_pm_board", new_callable=AsyncMock, return_value=DUMMY_PM_RESULT)
    async def test_returns_11_sections(self, mock_run_pm):
        from src.app.services.phases.pm_analysis import run_pm_analysis

        sim = make_simulation()
        session = AsyncMock()
        context = {"theme": "test"}

        result = await run_pm_analysis(session, sim, context)
        assert "core_question" in result.sections
        assert "plan_30_60_90" in result.sections
        assert "top_5_actions" in result.sections

    @pytest.mark.asyncio
    @patch("src.app.services.phases.pm_analysis.run_pm_board", new_callable=AsyncMock, return_value=DUMMY_PM_RESULT)
    async def test_returns_decision_brief(self, mock_run_pm):
        from src.app.services.phases.pm_analysis import run_pm_analysis

        sim = make_simulation()
        session = AsyncMock()
        context = {"theme": "test"}

        result = await run_pm_analysis(session, sim, context)
        assert "recommendation" in result.decision_brief

    @pytest.mark.asyncio
    @patch("src.app.services.phases.pm_analysis.run_pm_board", new_callable=AsyncMock, return_value=DUMMY_PM_RESULT)
    async def test_calls_run_pm_board_with_correct_args(self, mock_run_pm):
        from src.app.services.phases.pm_analysis import run_pm_analysis

        sim = make_simulation()
        session = AsyncMock()
        context = {"theme": "AI分析", "document_text": "文書内容"}

        await run_pm_analysis(session, sim, context)

        mock_run_pm.assert_awaited_once()
        call_kwargs = mock_run_pm.call_args
        assert call_kwargs.kwargs["prompt_text"] == "AI分析"
        assert call_kwargs.kwargs["document_text"] == "文書内容"

    @pytest.mark.asyncio
    @patch("src.app.services.phases.pm_analysis.run_pm_board", new_callable=AsyncMock, return_value=DUMMY_PM_RESULT)
    async def test_passes_scenario_candidates_from_context(self, mock_run_pm):
        from src.app.services.phases.pm_analysis import run_pm_analysis

        sim = make_simulation()
        session = AsyncMock()
        scenarios = [{"description": "シナリオ1", "score": 0.8}]
        context = {"theme": "test", "scenarios": scenarios}

        await run_pm_analysis(session, sim, context)

        call_kwargs = mock_run_pm.call_args
        assert call_kwargs.kwargs["scenario_candidates"] == scenarios

    @pytest.mark.asyncio
    @patch("src.app.services.phases.pm_analysis.run_pm_board", new_callable=AsyncMock, return_value=DUMMY_PM_RESULT)
    async def test_returns_pm_analyses_list(self, mock_run_pm):
        from src.app.services.phases.pm_analysis import run_pm_analysis

        sim = make_simulation()
        session = AsyncMock()
        context = {"theme": "test"}

        result = await run_pm_analysis(session, sim, context)
        assert len(result.analyses) > 0
        assert result.analyses[0]["persona"] == "strategy_pm"

    @pytest.mark.asyncio
    @patch("src.app.services.phases.pm_analysis.run_pm_board", new_callable=AsyncMock, side_effect=ValueError("全PM失敗"))
    async def test_error_propagated(self, mock_run_pm):
        from src.app.services.phases.pm_analysis import run_pm_analysis

        sim = make_simulation()
        session = AsyncMock()
        context = {"theme": "test"}

        with pytest.raises(ValueError, match="全PM失敗"):
            await run_pm_analysis(session, sim, context)
