"""評価メトリクスのテスト"""

import pytest

from src.app.services.society.evaluation import (
    brier_score,
    calibration_score,
    diversity_index,
    evaluate_society_simulation,
    internal_consistency,
    kl_divergence,
)


class TestDiversityIndex:
    def test_uniform_distribution(self):
        """均等な分布 → 高い多様性"""
        responses = [
            {"stance": "賛成"},
            {"stance": "反対"},
            {"stance": "中立"},
            {"stance": "条件付き賛成"},
        ]
        score = diversity_index(responses)
        assert score > 0.9  # near-perfect diversity

    def test_single_stance(self):
        """全員同じスタンス → 多様性ゼロ"""
        responses = [{"stance": "賛成"}] * 10
        score = diversity_index(responses)
        assert score == 0.0

    def test_mostly_one_stance(self):
        """偏った分布 → 低い多様性"""
        responses = [{"stance": "賛成"}] * 9 + [{"stance": "反対"}]
        score = diversity_index(responses)
        assert 0.0 < score < 0.7

    def test_empty(self):
        assert diversity_index([]) == 0.0


class TestInternalConsistency:
    def test_consistent_profile(self):
        agents = [
            {"big_five": {"O": 0.1, "C": 0.8, "E": 0.3, "A": 0.5, "N": 0.8}, "values": {}},
        ]
        responses = [
            {"stance": "反対", "confidence": 0.4, "reason": ""},
        ]
        score = internal_consistency(agents, responses)
        # Low O → 反対 should be consistent, High N → low confidence also consistent
        assert score >= 0.0

    def test_empty_inputs(self):
        assert internal_consistency([], []) == 0.0

    def test_mismatched_lengths(self):
        assert internal_consistency([{}], []) == 0.0


class TestCalibrationScore:
    def test_well_calibrated(self):
        """多数派が高信頼度、少数派が低信頼度 → 良いキャリブレーション"""
        responses = [
            {"stance": "賛成", "confidence": 0.8},
            {"stance": "賛成", "confidence": 0.9},
            {"stance": "賛成", "confidence": 0.7},
            {"stance": "反対", "confidence": 0.3},
        ]
        score = calibration_score(responses)
        assert score > 0.7

    def test_overconfident_minority(self):
        """少数意見なのに高信頼度 → ペナルティ"""
        responses = [
            {"stance": "賛成", "confidence": 0.8},
        ] * 9 + [
            {"stance": "反対", "confidence": 0.95},  # 10% but high confidence
        ]
        score = calibration_score(responses)
        assert score < 1.0

    def test_empty(self):
        assert calibration_score([]) == 0.0


class TestBrierScore:
    def test_perfect_calibration(self):
        """多数派が高信頼度、少数派が低信頼度 → 低い Brier Score"""
        responses = [
            {"stance": "賛成", "confidence": 0.9},
            {"stance": "賛成", "confidence": 0.8},
            {"stance": "賛成", "confidence": 0.85},
            {"stance": "反対", "confidence": 0.1},
        ]
        score = brier_score(responses)
        assert score is not None
        assert score < 0.1

    def test_poor_calibration(self):
        """少数派が高信頼度 → 高い Brier Score"""
        responses = [
            {"stance": "賛成", "confidence": 0.3},
            {"stance": "賛成", "confidence": 0.2},
            {"stance": "賛成", "confidence": 0.1},
            {"stance": "反対", "confidence": 0.95},
        ]
        score = brier_score(responses)
        assert score is not None
        assert score > 0.3

    def test_too_few_responses(self):
        assert brier_score([]) is None
        assert brier_score([{"stance": "賛成", "confidence": 0.5}]) is None

    def test_all_same_stance(self):
        """全員同じスタンスで高信頼度 → 低い Brier Score"""
        responses = [{"stance": "賛成", "confidence": 0.9}] * 5
        score = brier_score(responses)
        assert score is not None
        assert score < 0.05


class TestKLDivergence:
    def test_uniform_distribution(self):
        """均一分布 → KL divergence ≈ 0"""
        responses = [
            {"stance": "賛成"},
            {"stance": "反対"},
            {"stance": "中立"},
        ]
        score = kl_divergence(responses)
        assert score is not None
        assert score == 0.0  # 完全均一 → ゼロ

    def test_skewed_distribution(self):
        """偏った分布 → KL divergence > 0"""
        responses = [{"stance": "賛成"}] * 8 + [{"stance": "反対"}] * 2
        score = kl_divergence(responses)
        assert score is not None
        assert score > 0.2

    def test_single_category(self):
        """1カテゴリのみ → 0"""
        responses = [{"stance": "賛成"}] * 5
        assert kl_divergence(responses) == 0.0

    def test_empty(self):
        assert kl_divergence([]) is None

    def test_custom_baseline(self):
        """カスタムベースラインとの比較"""
        responses = [
            {"stance": "賛成"},
            {"stance": "賛成"},
            {"stance": "反対"},
        ]
        baseline = {"賛成": 0.5, "反対": 0.5}
        score = kl_divergence(responses, baseline=baseline)
        assert score is not None
        assert score > 0.0


class TestEvaluateSocietySimulation:
    @pytest.mark.asyncio
    async def test_returns_all_metrics(self):
        agents = [
            {"big_five": {"O": 0.5, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5}, "values": {}}
            for _ in range(10)
        ]
        responses = [
            {"stance": ["賛成", "反対", "中立"][i % 3], "confidence": 0.5 + i * 0.05, "reason": ""}
            for i in range(10)
        ]
        metrics = await evaluate_society_simulation(agents, responses)
        metric_names = {m["metric_name"] for m in metrics}
        assert "diversity" in metric_names
        assert "consistency" in metric_names
        assert "calibration" in metric_names
        assert "brier_score" in metric_names
        assert "kl_divergence" in metric_names

    @pytest.mark.asyncio
    async def test_scores_in_range(self):
        agents = [{"big_five": {}, "values": {}} for _ in range(5)]
        responses = [{"stance": "中立", "confidence": 0.5, "reason": ""} for _ in range(5)]
        metrics = await evaluate_society_simulation(agents, responses)
        for m in metrics:
            assert 0.0 <= m["score"] <= 1.0
