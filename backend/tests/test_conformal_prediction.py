"""P2-2: Split Conformal Prediction のテスト"""

import pytest


class TestConformalPredictionIntervals:
    """split conformal + 重み付き分位点のテスト."""

    def test_basic_intervals(self):
        """基本的な信頼区間が返されること."""
        from src.app.services.society.statistical_inference import conformal_prediction_intervals

        # キャリブレーションデータ: 残差 = |predicted - actual|
        calibration_residuals = [0.02, 0.05, 0.03, 0.08, 0.01, 0.04, 0.06, 0.07, 0.02, 0.03]
        predicted_values = {"賛成": 0.5, "反対": 0.3, "中立": 0.2}

        intervals = conformal_prediction_intervals(
            predicted_values, calibration_residuals, alpha=0.1,
        )

        assert "賛成" in intervals
        assert "反対" in intervals
        assert "中立" in intervals

        for stance, (lower, upper) in intervals.items():
            assert lower <= predicted_values[stance] <= upper
            assert lower >= 0.0

    def test_wider_intervals_with_higher_confidence(self):
        """alpha が小さいほど（信頼度が高いほど）区間が広い."""
        from src.app.services.society.statistical_inference import conformal_prediction_intervals

        residuals = [0.05, 0.10, 0.03, 0.08, 0.15, 0.04, 0.06, 0.02, 0.07, 0.12]
        predicted = {"賛成": 0.5}

        interval_90 = conformal_prediction_intervals(predicted, residuals, alpha=0.1)
        interval_80 = conformal_prediction_intervals(predicted, residuals, alpha=0.2)

        width_90 = interval_90["賛成"][1] - interval_90["賛成"][0]
        width_80 = interval_80["賛成"][1] - interval_80["賛成"][0]

        assert width_90 >= width_80

    def test_with_independence_weights(self):
        """独立性重みが反映されること."""
        from src.app.services.society.statistical_inference import conformal_prediction_intervals

        residuals = [0.05, 0.10, 0.03, 0.08, 0.15]
        predicted = {"賛成": 0.5}
        weights = [1.0, 0.5, 1.0, 0.3, 0.8]  # 独立性の低いエージェントは重み小

        intervals = conformal_prediction_intervals(
            predicted, residuals, alpha=0.1, weights=weights,
        )

        assert "賛成" in intervals
        lower, upper = intervals["賛成"]
        assert lower <= 0.5 <= upper

    def test_empty_residuals(self):
        """残差が空ならフォールバック（bootstrap）区間を返す."""
        from src.app.services.society.statistical_inference import conformal_prediction_intervals

        predicted = {"賛成": 0.5}
        intervals = conformal_prediction_intervals(predicted, [], alpha=0.1)

        assert "賛成" in intervals
        lower, upper = intervals["賛成"]
        assert lower <= 0.5 <= upper
