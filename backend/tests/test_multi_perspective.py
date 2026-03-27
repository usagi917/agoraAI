"""phases/multi_perspective.py のテスト（TDD RED → GREEN）"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import asdict

from tests.factories import make_simulation, make_llm_response


# --- テスト用ダミーデータ ---

DUMMY_WORLD_STATE = {
    "entities": [
        {"label": "AI企業", "entity_type": "Organization", "importance_score": 0.9},
        {"label": "規制当局", "entity_type": "Organization", "importance_score": 0.8},
    ],
    "relations": [{"source": "AI企業", "target": "規制当局", "type": "regulated_by"}],
    "world_summary": "AI規制を巡る状況",
}

DUMMY_COLONY_RESULT = {
    "world_state": DUMMY_WORLD_STATE,
    "events": [{"title": "新規制案", "event_type": "policy", "description": "テスト", "severity": "medium"}],
    "agents": {"agents": [{"name": "Agent-1", "role": "analyst", "goals": ["分析"]}]},
    "report_content": "テストレポート内容",
}

DUMMY_CLAIMS = [
    {"id": "c1", "colony_id": "col-1", "claim_text": "AI規制が強化される",
     "claim_type": "prediction", "confidence": 0.8, "evidence": "政策動向", "entities_involved": ["規制当局"]},
    {"id": "c2", "colony_id": "col-2", "claim_text": "企業の自主規制が進む",
     "claim_type": "prediction", "confidence": 0.6, "evidence": "業界動向", "entities_involved": ["AI企業"]},
]

DUMMY_CLUSTERS = [
    {"cluster_id": "cl1", "cluster_index": 0, "representative_text": "AI規制強化シナリオ",
     "claim_count": 3, "agreement_ratio": 0.8, "mean_confidence": 0.75,
     "colony_ids": ["col-1", "col-2"], "claims": DUMMY_CLAIMS},
]

DUMMY_AGGREGATION = {
    "scenarios": [
        {"description": "AI規制強化シナリオ", "scenario_score": 0.6, "support_ratio": 0.8},
    ],
    "diversity_score": 0.45,
    "entropy": 0.92,
    "agreement_matrix": {"colony_ids": ["col-1", "col-2"], "matrix": [[1.0, 0.5], [0.5, 1.0]]},
}


class TestMultiPerspectiveResult:
    """MultiPerspectiveResult のデータ構造テスト"""

    def test_has_required_fields(self):
        from src.app.services.phases.multi_perspective import MultiPerspectiveResult
        result = MultiPerspectiveResult(
            perspectives=[{"id": "p1"}],
            scenarios=[{"desc": "s1"}],
            agreement_matrix={"matrix": []},
            integrated_report="report",
            diversity_score=0.5,
            entropy=0.8,
            usage={"total_tokens": 100},
        )
        assert result.perspectives == [{"id": "p1"}]
        assert result.scenarios == [{"desc": "s1"}]
        assert result.integrated_report == "report"
        assert result.diversity_score == 0.5
        assert result.entropy == 0.8
        assert result.usage["total_tokens"] == 100


class TestRunMultiPerspective:
    """run_multi_perspective() の動作テスト"""

    @pytest.fixture
    def mock_deps(self):
        """全依存をモックする"""
        patches = {
            "colony_factory": patch(
                "src.app.services.phases.multi_perspective.generate_colony_configs",
                return_value=[
                    MagicMock(
                        colony_id=f"col-{i}",
                        colony_index=i,
                        perspective_id=f"perspective_{i}",
                        perspective_label=f"視点{i}",
                        temperature=0.5 + i * 0.1,
                        round_count=2,
                        adversarial=(i == 2),
                        prompt_variant="",
                    )
                    for i in range(3)
                ],
            ),
            "simulator": patch(
                "src.app.services.phases.multi_perspective.SingleRunSimulator",
            ),
            "extract": patch(
                "src.app.services.phases.multi_perspective.extract_claims",
                new_callable=AsyncMock,
                return_value=DUMMY_CLAIMS,
            ),
            "cluster": patch(
                "src.app.services.phases.multi_perspective.cluster_claims",
                new_callable=AsyncMock,
                return_value=DUMMY_CLUSTERS,
            ),
            "aggregate": patch(
                "src.app.services.phases.multi_perspective.aggregate_clusters",
                new_callable=AsyncMock,
                return_value=DUMMY_AGGREGATION,
            ),
            "report": patch(
                "src.app.services.phases.multi_perspective.generate_swarm_integrated_report",
                new_callable=AsyncMock,
                return_value="# 統合レポート\n\nテスト内容",
            ),
            "sse": patch(
                "src.app.services.phases.multi_perspective.sse_manager",
            ),
        }
        mocks = {}
        for key, p in patches.items():
            mocks[key] = p.start()

        # SingleRunSimulator モックの設定
        mock_sim_instance = AsyncMock()
        mock_sim_instance.run = AsyncMock(return_value=DUMMY_COLONY_RESULT)
        mocks["simulator"].return_value = mock_sim_instance

        # SSE モックの設定
        mocks["sse"].publish = AsyncMock()

        yield mocks

        for p in patches.values():
            p.stop()

    @pytest.mark.asyncio
    async def test_returns_multi_perspective_result(self, mock_deps):
        """正常完了時に MultiPerspectiveResult を返す"""
        from src.app.services.phases.multi_perspective import (
            run_multi_perspective,
            MultiPerspectiveResult,
        )

        sim = make_simulation(mode="unified", execution_profile="preview")
        session = AsyncMock()
        session.commit = AsyncMock()

        context = {
            "theme": "AI規制の影響分析",
            "world_state": DUMMY_WORLD_STATE,
            "template_prompts": {},
        }

        result = await run_multi_perspective(session, sim, context, perspective_count=3)

        assert isinstance(result, MultiPerspectiveResult)

    @pytest.mark.asyncio
    async def test_returns_scenarios(self, mock_deps):
        """結果にシナリオが含まれる"""
        from src.app.services.phases.multi_perspective import run_multi_perspective

        sim = make_simulation()
        session = AsyncMock()
        session.commit = AsyncMock()
        context = {"theme": "test", "world_state": DUMMY_WORLD_STATE, "template_prompts": {}}

        result = await run_multi_perspective(session, sim, context, perspective_count=3)

        assert len(result.scenarios) > 0
        assert result.scenarios[0]["description"] == "AI規制強化シナリオ"

    @pytest.mark.asyncio
    async def test_returns_agreement_matrix(self, mock_deps):
        """結果に合意マトリクスが含まれる"""
        from src.app.services.phases.multi_perspective import run_multi_perspective

        sim = make_simulation()
        session = AsyncMock()
        session.commit = AsyncMock()
        context = {"theme": "test", "world_state": DUMMY_WORLD_STATE, "template_prompts": {}}

        result = await run_multi_perspective(session, sim, context, perspective_count=3)

        assert "matrix" in result.agreement_matrix

    @pytest.mark.asyncio
    async def test_returns_integrated_report(self, mock_deps):
        """統合レポートが生成される"""
        from src.app.services.phases.multi_perspective import run_multi_perspective

        sim = make_simulation()
        session = AsyncMock()
        session.commit = AsyncMock()
        context = {"theme": "test", "world_state": DUMMY_WORLD_STATE, "template_prompts": {}}

        result = await run_multi_perspective(session, sim, context, perspective_count=3)

        assert "統合レポート" in result.integrated_report

    @pytest.mark.asyncio
    async def test_calls_extract_claims(self, mock_deps):
        """Claim 抽出が呼ばれる"""
        from src.app.services.phases.multi_perspective import run_multi_perspective

        sim = make_simulation()
        session = AsyncMock()
        session.commit = AsyncMock()
        context = {"theme": "test", "world_state": DUMMY_WORLD_STATE, "template_prompts": {}}

        await run_multi_perspective(session, sim, context, perspective_count=3)

        mock_deps["extract"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_calls_cluster_claims(self, mock_deps):
        """Claim クラスタリングが呼ばれる"""
        from src.app.services.phases.multi_perspective import run_multi_perspective

        sim = make_simulation()
        session = AsyncMock()
        session.commit = AsyncMock()
        context = {"theme": "test", "world_state": DUMMY_WORLD_STATE, "template_prompts": {}}

        await run_multi_perspective(session, sim, context, perspective_count=3)

        mock_deps["cluster"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_respects_perspective_count(self, mock_deps):
        """perspective_count に応じた数の視点が生成される"""
        from src.app.services.phases.multi_perspective import run_multi_perspective

        sim = make_simulation()
        session = AsyncMock()
        session.commit = AsyncMock()
        context = {"theme": "test", "world_state": DUMMY_WORLD_STATE, "template_prompts": {}}

        await run_multi_perspective(session, sim, context, perspective_count=3)

        # generate_colony_configs が呼ばれたことを確認
        mock_deps["colony_factory"].assert_called_once()

    @pytest.mark.asyncio
    async def test_clones_world_state_per_perspective(self, mock_deps):
        """各視点に独立した world_state のコピーが渡される"""
        from src.app.services.phases.multi_perspective import run_multi_perspective

        sim = make_simulation()
        session = AsyncMock()
        session.commit = AsyncMock()

        original_ws = {"entities": [{"label": "test"}], "relations": []}
        context = {"theme": "test", "world_state": original_ws, "template_prompts": {}}

        await run_multi_perspective(session, sim, context, perspective_count=3)

        # Simulator.run が3回呼ばれること
        simulator_instance = mock_deps["simulator"].return_value
        assert simulator_instance.run.await_count == 3

    @pytest.mark.asyncio
    async def test_diversity_score_propagated(self, mock_deps):
        """aggregation の diversity_score が結果に含まれる"""
        from src.app.services.phases.multi_perspective import run_multi_perspective

        sim = make_simulation()
        session = AsyncMock()
        session.commit = AsyncMock()
        context = {"theme": "test", "world_state": DUMMY_WORLD_STATE, "template_prompts": {}}

        result = await run_multi_perspective(session, sim, context, perspective_count=3)

        assert result.diversity_score == 0.45
        assert result.entropy == 0.92

    @pytest.mark.asyncio
    async def test_empty_world_state_still_works(self, mock_deps):
        """world_state が空でも動作する"""
        from src.app.services.phases.multi_perspective import run_multi_perspective

        sim = make_simulation()
        session = AsyncMock()
        session.commit = AsyncMock()
        context = {"theme": "test", "world_state": {}, "template_prompts": {}}

        result = await run_multi_perspective(session, sim, context, perspective_count=3)

        assert isinstance(result.perspectives, list)
