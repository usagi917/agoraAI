"""評価フレームワーク（BaseMetric + EvaluationRunner）テスト"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch


# ---- 3.2 BaseMetric + 具象メトリクス ----

class TestBaseMetric:
    def test_is_abstract(self):
        from src.app.evaluation.base import BaseMetric
        with pytest.raises(TypeError):
            BaseMetric()

    def test_subclass_must_implement_compute(self):
        from src.app.evaluation.base import BaseMetric

        class BadMetric(BaseMetric):
            name = "bad"
            description = "test"

        with pytest.raises(TypeError):
            BadMetric()


class TestDiversityMetric:
    def test_compute_uniform_distribution(self):
        from src.app.evaluation.metrics import DiversityMetric
        metric = DiversityMetric()
        responses = [
            {"stance": "賛成"}, {"stance": "反対"},
            {"stance": "中立"}, {"stance": "条件付き賛成"},
        ]
        result = metric.compute(responses=responses)
        assert result["score"] > 0.9  # 均等分布 → 高多様性

    def test_compute_single_stance(self):
        from src.app.evaluation.metrics import DiversityMetric
        metric = DiversityMetric()
        responses = [{"stance": "賛成"}] * 5
        result = metric.compute(responses=responses)
        assert result["score"] == 0.0

    def test_compute_empty(self):
        from src.app.evaluation.metrics import DiversityMetric
        metric = DiversityMetric()
        result = metric.compute(responses=[])
        assert result["score"] == 0.0

    def test_has_name(self):
        from src.app.evaluation.metrics import DiversityMetric
        assert DiversityMetric().name == "diversity"


class TestConsistencyMetric:
    def test_compute_consistent_agents(self):
        from src.app.evaluation.metrics import ConsistencyMetric
        metric = ConsistencyMetric()
        agents = [
            {"big_five": {"O": 0.9, "N": 0.2}, "values": {"innovation": 0.9}},
        ]
        responses = [
            {"stance": "賛成", "confidence": 0.8, "reason": "innovation drives growth"},
        ]
        result = metric.compute(agents=agents, responses=responses)
        assert result["score"] > 0.0

    def test_compute_empty(self):
        from src.app.evaluation.metrics import ConsistencyMetric
        metric = ConsistencyMetric()
        result = metric.compute(agents=[], responses=[])
        assert result["score"] == 0.0


class TestConvergenceMetric:
    def test_compute_high_agreement(self):
        from src.app.evaluation.metrics import ConvergenceMetric
        metric = ConvergenceMetric()
        responses = [{"stance": "賛成", "confidence": 0.8}] * 8 + [
            {"stance": "反対", "confidence": 0.3}] * 2
        result = metric.compute(responses=responses)
        assert result["score"] > 0.5

    def test_compute_no_agreement(self):
        from src.app.evaluation.metrics import ConvergenceMetric
        metric = ConvergenceMetric()
        responses = [
            {"stance": "賛成"}, {"stance": "反対"},
            {"stance": "中立"}, {"stance": "条件付き"},
        ]
        result = metric.compute(responses=responses)
        assert result["score"] < 0.5

    def test_has_name(self):
        from src.app.evaluation.metrics import ConvergenceMetric
        assert ConvergenceMetric().name == "convergence"


class TestCoverageMetric:
    def test_compute_all_stances_covered(self):
        from src.app.evaluation.metrics import CoverageMetric
        metric = CoverageMetric()
        responses = [
            {"stance": "賛成"}, {"stance": "反対"},
            {"stance": "中立"}, {"stance": "条件付き賛成"},
            {"stance": "条件付き反対"},
        ]
        result = metric.compute(responses=responses)
        assert result["score"] == 1.0  # 5/5 stances covered

    def test_compute_single_stance(self):
        from src.app.evaluation.metrics import CoverageMetric
        metric = CoverageMetric()
        responses = [{"stance": "賛成"}] * 5
        result = metric.compute(responses=responses)
        assert result["score"] < 1.0

    def test_has_name(self):
        from src.app.evaluation.metrics import CoverageMetric
        assert CoverageMetric().name == "coverage"


# ---- 3.3 EvaluationRunner ----

class TestEvaluationRunner:
    def test_register_metric(self):
        from src.app.evaluation.runner import EvaluationRunner
        from src.app.evaluation.metrics import DiversityMetric
        runner = EvaluationRunner()
        runner.register(DiversityMetric())
        assert len(runner.metrics) == 1

    def test_run_all_returns_results(self):
        from src.app.evaluation.runner import EvaluationRunner
        from src.app.evaluation.metrics import DiversityMetric, ConsistencyMetric

        runner = EvaluationRunner()
        runner.register(DiversityMetric())
        runner.register(ConsistencyMetric())

        results = runner.run_all(
            agents=[{"big_five": {"O": 0.5}, "values": {}}],
            responses=[{"stance": "賛成", "confidence": 0.5, "reason": "test"}],
        )
        assert len(results) == 2
        assert all("metric_name" in r and "score" in r for r in results)

    def test_run_all_includes_metric_names(self):
        from src.app.evaluation.runner import EvaluationRunner
        from src.app.evaluation.metrics import DiversityMetric

        runner = EvaluationRunner()
        runner.register(DiversityMetric())

        results = runner.run_all(responses=[{"stance": "賛成"}])
        assert results[0]["metric_name"] == "diversity"

    def test_default_runner_has_all_metrics(self):
        from src.app.evaluation.runner import create_default_runner

        runner = create_default_runner()
        assert len(runner.metrics) >= 4

    @pytest.mark.asyncio
    async def test_run_and_save(self, db_session):
        from src.app.evaluation.runner import create_default_runner
        from sqlalchemy import select
        from src.app.models.evaluation_result import EvaluationResult
        from src.app.models.simulation import Simulation

        sim = Simulation(
            mode="standard", prompt_text="test", template_name="g",
            execution_profile="preview",
        )
        db_session.add(sim)
        await db_session.commit()
        await db_session.refresh(sim)

        runner = create_default_runner()
        results = runner.run_all(
            responses=[
                {"stance": "賛成", "confidence": 0.8, "reason": "good"},
                {"stance": "反対", "confidence": 0.6, "reason": "bad"},
            ],
            agents=[
                {"big_five": {"O": 0.5}, "values": {}},
                {"big_five": {"O": 0.3}, "values": {}},
            ],
        )

        for result in results:
            db_session.add(
                EvaluationResult(
                    simulation_id=sim.id,
                    metric_name=result["metric_name"],
                    score=result["score"],
                    details=result.get("details", {}),
                )
            )
        await db_session.commit()

        saved_result = await db_session.execute(
            select(EvaluationResult).where(EvaluationResult.simulation_id == sim.id)
        )
        saved = saved_result.scalars().all()
        assert len(saved) == len(results)
