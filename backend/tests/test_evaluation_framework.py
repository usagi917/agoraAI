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
        from src.app.repositories.simulation_repo import SimulationRepository
        from src.app.repositories.evaluation_repo import EvaluationRepository

        sim_repo = SimulationRepository(db_session)
        sim = await sim_repo.create(
            mode="standard", prompt_text="test", template_name="g",
            execution_profile="preview",
        )

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

        eval_repo = EvaluationRepository(db_session)
        await eval_repo.save_metrics(sim.id, results)

        saved = await eval_repo.get_by_simulation(sim.id)
        assert len(saved) == len(results)


class TestJSDMetric:
    """P1-1: Jensen-Shannon Divergence メトリクスのテスト."""

    def test_identical_distributions_zero(self):
        """同一の分布間の JSD は 0."""
        from src.app.evaluation.metrics import JSDMetric
        metric = JSDMetric()
        result = metric.compute(
            predicted={"賛成": 0.6, "反対": 0.3, "中立": 0.1},
            observed={"賛成": 0.6, "反対": 0.3, "中立": 0.1},
        )
        assert result["score"] == pytest.approx(0.0, abs=1e-6)

    def test_completely_different_distributions(self):
        """完全に異なる分布間の JSD は最大値に近い."""
        from src.app.evaluation.metrics import JSDMetric
        metric = JSDMetric()
        result = metric.compute(
            predicted={"賛成": 1.0, "反対": 0.0},
            observed={"賛成": 0.0, "反対": 1.0},
        )
        # JSD の最大値は ln(2) ≈ 0.693 (自然対数) or 1.0 (log2)
        assert result["score"] > 0.5

    def test_similar_distributions_low_jsd(self):
        """類似の分布間の JSD は小さい."""
        from src.app.evaluation.metrics import JSDMetric
        metric = JSDMetric()
        result = metric.compute(
            predicted={"賛成": 0.5, "反対": 0.3, "中立": 0.2},
            observed={"賛成": 0.45, "反対": 0.35, "中立": 0.2},
        )
        assert result["score"] < 0.01

    def test_handles_missing_categories(self):
        """片方の分布にないカテゴリは 0 として扱われる."""
        from src.app.evaluation.metrics import JSDMetric
        metric = JSDMetric()
        result = metric.compute(
            predicted={"賛成": 0.6, "反対": 0.4},
            observed={"賛成": 0.5, "反対": 0.3, "中立": 0.2},
        )
        assert result["score"] > 0.0

    def test_empty_distributions(self):
        """空の分布では score=0.0."""
        from src.app.evaluation.metrics import JSDMetric
        metric = JSDMetric()
        result = metric.compute(predicted={}, observed={})
        assert result["score"] == 0.0

    def test_symmetry(self):
        """JSD は対称: JSD(P||Q) == JSD(Q||P)."""
        from src.app.evaluation.metrics import JSDMetric
        metric = JSDMetric()
        r1 = metric.compute(
            predicted={"賛成": 0.7, "反対": 0.3},
            observed={"賛成": 0.4, "反対": 0.6},
        )
        r2 = metric.compute(
            predicted={"賛成": 0.4, "反対": 0.6},
            observed={"賛成": 0.7, "反対": 0.3},
        )
        assert r1["score"] == pytest.approx(r2["score"], abs=1e-10)


class TestAccuracySpec:
    """P1-1: 精度評価仕様のテスト."""

    def test_primary_metric_is_jsd(self):
        """主指標が JSD であること."""
        from src.app.evaluation.accuracy_spec import PRIMARY_METRIC
        assert PRIMARY_METRIC == "jsd"

    def test_secondary_metrics_defined(self):
        """副指標が定義されていること."""
        from src.app.evaluation.accuracy_spec import SECONDARY_METRICS
        assert "brier" in SECONDARY_METRICS
        assert "symmetric_kl" in SECONDARY_METRICS
        assert "emd" in SECONDARY_METRICS

    def test_holdout_rules(self):
        """ホールドアウトルールが定義されていること."""
        from src.app.evaluation.accuracy_spec import HOLDOUT_RULES
        assert HOLDOUT_RULES["split_method"] == "temporal"
        assert HOLDOUT_RULES["min_test_cases"] >= 5

    def test_ci_threshold(self):
        """CI 閾値が定義されていること (JSD 悪化量)."""
        from src.app.evaluation.accuracy_spec import CI_REGRESSION_THRESHOLD
        assert CI_REGRESSION_THRESHOLD == pytest.approx(0.02)


class TestSubgroupAccuracyMetric:
    """P4-3: サブグループ精度メトリクスのテスト."""

    def test_compute_subgroup_jsd(self):
        """サブグループ別 JSD が計算されること."""
        from src.app.evaluation.metrics import SubgroupAccuracyMetric

        metric = SubgroupAccuracyMetric()
        result = metric.compute(
            predicted_by_group={
                "関東": {"賛成": 0.6, "反対": 0.4},
                "関西": {"賛成": 0.5, "反対": 0.5},
            },
            observed_by_group={
                "関東": {"賛成": 0.55, "反対": 0.45},
                "関西": {"賛成": 0.3, "反対": 0.7},
            },
        )

        assert "score" in result
        assert "details" in result
        assert "subgroup_scores" in result["details"]
        assert "関東" in result["details"]["subgroup_scores"]
        assert "関西" in result["details"]["subgroup_scores"]

    def test_identifies_worst_subgroup(self):
        """最も JSD が高い（精度が低い）サブグループを特定すること."""
        from src.app.evaluation.metrics import SubgroupAccuracyMetric

        metric = SubgroupAccuracyMetric()
        result = metric.compute(
            predicted_by_group={
                "good": {"賛成": 0.5, "反対": 0.5},
                "bad": {"賛成": 0.9, "反対": 0.1},
            },
            observed_by_group={
                "good": {"賛成": 0.5, "反対": 0.5},
                "bad": {"賛成": 0.2, "反対": 0.8},
            },
        )

        assert result["details"]["worst_subgroup"] == "bad"

    def test_empty_groups(self):
        """空のグループでは score=0."""
        from src.app.evaluation.metrics import SubgroupAccuracyMetric

        metric = SubgroupAccuracyMetric()
        result = metric.compute(predicted_by_group={}, observed_by_group={})
        assert result["score"] == 0.0
