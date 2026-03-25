"""phases/issue_mining.py のテスト"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.factories import make_simulation, make_pulse_result


DUMMY_ISSUE_CANDIDATES = [
    {"label": "規制リスク", "score": 0.85, "description": "AI規制が強化される可能性"},
    {"label": "技術的課題", "score": 0.7, "description": "技術的な実装困難性"},
    {"label": "市場変動", "score": 0.6, "description": "市場環境の急変リスク"},
]

DUMMY_SELECTED_ISSUES = DUMMY_ISSUE_CANDIDATES[:2]

DUMMY_INTERVENTION_COMPARISON = [
    {"label": "段階的規制対応", "score": 0.75, "hypothesis": "段階的に規制に対応する"},
    {"label": "技術革新", "score": 0.6, "hypothesis": "技術で問題を解決する"},
]


class TestIssueMiningResult:
    def test_has_required_fields(self):
        from src.app.services.phases.issue_mining import IssueMiningResult
        result = IssueMiningResult(
            issues=DUMMY_ISSUE_CANDIDATES,
            selected_issues=DUMMY_SELECTED_ISSUES,
            intervention_comparison=DUMMY_INTERVENTION_COMPARISON,
            usage={"total_tokens": 100},
        )
        assert len(result.issues) == 3
        assert len(result.selected_issues) == 2
        assert len(result.intervention_comparison) == 2


class TestRunIssueMining:
    @pytest.fixture
    def mock_deps(self):
        patches = {
            "mine": patch(
                "src.app.services.phases.issue_mining.mine_issue_candidates",
                new_callable=AsyncMock,
                return_value=DUMMY_ISSUE_CANDIDATES,
            ),
            "select": patch(
                "src.app.services.phases.issue_mining.select_top_issues",
                return_value=DUMMY_SELECTED_ISSUES,
            ),
            "intervention": patch(
                "src.app.services.phases.issue_mining.build_intervention_comparison",
                new_callable=AsyncMock,
                return_value=DUMMY_INTERVENTION_COMPARISON,
            ),
            "sse": patch("src.app.services.phases.issue_mining.sse_manager"),
        }
        mocks = {}
        for key, p in patches.items():
            mocks[key] = p.start()
        mocks["sse"].publish = AsyncMock()
        yield mocks
        for p in patches.values():
            p.stop()

    @pytest.mark.asyncio
    async def test_returns_issue_mining_result(self, mock_deps):
        from src.app.services.phases.issue_mining import run_issue_mining, IssueMiningResult

        sim = make_simulation()
        session = AsyncMock()
        pulse_data = make_pulse_result()
        context = {"theme": "test", "pulse_result": pulse_data}

        result = await run_issue_mining(session, sim, context)
        assert isinstance(result, IssueMiningResult)

    @pytest.mark.asyncio
    async def test_returns_ranked_issues(self, mock_deps):
        from src.app.services.phases.issue_mining import run_issue_mining

        sim = make_simulation()
        session = AsyncMock()
        context = {"theme": "test", "pulse_result": make_pulse_result()}

        result = await run_issue_mining(session, sim, context)
        assert len(result.issues) == 3
        assert result.issues[0]["score"] >= result.issues[1]["score"]

    @pytest.mark.asyncio
    async def test_returns_intervention_comparison(self, mock_deps):
        from src.app.services.phases.issue_mining import run_issue_mining

        sim = make_simulation()
        session = AsyncMock()
        context = {"theme": "test", "pulse_result": make_pulse_result()}

        result = await run_issue_mining(session, sim, context)
        assert len(result.intervention_comparison) > 0

    @pytest.mark.asyncio
    async def test_calls_mine_issue_candidates(self, mock_deps):
        from src.app.services.phases.issue_mining import run_issue_mining

        sim = make_simulation()
        session = AsyncMock()
        context = {"theme": "test", "pulse_result": make_pulse_result()}

        await run_issue_mining(session, sim, context)
        mock_deps["mine"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_respects_max_issues(self, mock_deps):
        from src.app.services.phases.issue_mining import run_issue_mining

        sim = make_simulation()
        session = AsyncMock()
        context = {"theme": "test", "pulse_result": make_pulse_result()}

        await run_issue_mining(session, sim, context, max_issues=2)
        mock_deps["select"].assert_called_once()
        call_args = mock_deps["select"].call_args
        assert call_args[1].get("max_count") == 2 or call_args[0][-1] == 2

    @pytest.mark.asyncio
    async def test_empty_pulse_returns_empty(self, mock_deps):
        mock_deps["mine"].return_value = []
        mock_deps["select"].return_value = []
        mock_deps["intervention"].return_value = []

        from src.app.services.phases.issue_mining import run_issue_mining

        sim = make_simulation()
        session = AsyncMock()
        context = {"theme": "test", "pulse_result": {}}

        result = await run_issue_mining(session, sim, context)
        assert result.issues == []
        assert result.selected_issues == []
