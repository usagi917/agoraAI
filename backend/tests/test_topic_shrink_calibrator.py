"""P2-1: TopicShrinkCalibrator のテスト"""

import pytest


class TestTopicShrinkCalibrator:
    """トピック別 shrink factor キャリブレータ."""

    def test_default_shrink_factor(self):
        """未学習時はグローバル shrink factor (0.8) を使用."""
        from src.app.services.society.calibration import TopicShrinkCalibrator

        cal = TopicShrinkCalibrator()
        result = cal.recalibrate(0.9, category="unknown_topic")
        # default shrink = 0.8: 0.5 + 0.8 * (0.9 - 0.5) = 0.82
        assert result == pytest.approx(0.82)

    def test_recalibrate_with_trained_factor(self):
        """学習済みカテゴリでは対応する shrink factor を使用."""
        from src.app.services.society.calibration import TopicShrinkCalibrator

        cal = TopicShrinkCalibrator()
        cal._topic_factors = {"politics": 0.6, "economy": 0.9}

        result = cal.recalibrate(0.9, category="politics")
        # shrink = 0.6: 0.5 + 0.6 * (0.9 - 0.5) = 0.74
        assert result == pytest.approx(0.74)

    def test_recalibrate_unknown_uses_global(self):
        """未知カテゴリでは global fallback を使用."""
        from src.app.services.society.calibration import TopicShrinkCalibrator

        cal = TopicShrinkCalibrator()
        cal._topic_factors = {"politics": 0.6}

        result_known = cal.recalibrate(0.9, category="politics")
        result_unknown = cal.recalibrate(0.9, category="sports")

        assert result_known != result_unknown  # 異なる shrink factor
        # unknown は global_shrink (0.8) を使うので platt_recalibrate(0.9) と同じ
        assert result_unknown == pytest.approx(0.82)

    def test_train_produces_factors(self):
        """train() が各カテゴリの shrink factor を学習すること."""
        from src.app.services.society.calibration import TopicShrinkCalibrator

        cal = TopicShrinkCalibrator()

        # 簡易比較データ: カテゴリ別に予測と実績の乖離を示す
        comparisons = [
            {"category": "politics", "predicted_confidence": 0.9, "actual_accuracy": 0.6},
            {"category": "politics", "predicted_confidence": 0.8, "actual_accuracy": 0.5},
            {"category": "economy", "predicted_confidence": 0.7, "actual_accuracy": 0.65},
            {"category": "economy", "predicted_confidence": 0.6, "actual_accuracy": 0.55},
        ]

        cal.train(comparisons)

        assert "politics" in cal._topic_factors
        assert "economy" in cal._topic_factors
        # politics は乖離が大きいので shrink factor が低いはず
        assert 0.0 < cal._topic_factors["politics"] <= 1.0
        assert 0.0 < cal._topic_factors["economy"] <= 1.0

    def test_confidence_clamped(self):
        """出力が 0.0～1.0 にクランプされること."""
        from src.app.services.society.calibration import TopicShrinkCalibrator

        cal = TopicShrinkCalibrator()
        assert cal.recalibrate(0.0, category="any") >= 0.0
        assert cal.recalibrate(1.0, category="any") <= 1.0
