"""P1-2: レトロダクション検証パイプラインのテスト"""

import pytest


class TestRetrodictionCase:
    """レトロダクションケース (YAML fixture) のパースと検証."""

    def test_load_fixture(self):
        """YAML fixture を読み込めること."""
        from src.app.evaluation.retrodiction_runner import load_retrodiction_fixtures

        cases = load_retrodiction_fixtures("tests/fixtures/survey_data_sample.yaml")
        assert len(cases) >= 2
        first = cases[0]
        assert "theme" in first
        assert "stance_distribution" in first
        assert isinstance(first["stance_distribution"], dict)

    def test_fixture_has_required_fields(self):
        """各 fixture に必須フィールドがあること."""
        from src.app.evaluation.retrodiction_runner import load_retrodiction_fixtures

        cases = load_retrodiction_fixtures("tests/fixtures/survey_data_sample.yaml")
        required_fields = {"theme", "stance_distribution", "source", "theme_category"}
        for case in cases:
            for field in required_fields:
                assert field in case, f"Missing field: {field} in {case.get('theme', '?')}"


class TestRetrodictionEvaluator:
    """シミュレーション結果と調査データの比較."""

    def test_evaluate_single_case(self):
        """1ケースの評価で JSD と Brier が返ること."""
        from src.app.evaluation.retrodiction_runner import evaluate_case

        predicted = {"賛成": 0.30, "反対": 0.20, "中立": 0.30, "条件付き賛成": 0.10, "条件付き反対": 0.10}
        observed = {"賛成": 0.25, "反対": 0.10, "中立": 0.30, "条件付き賛成": 0.20, "条件付き反対": 0.15}

        result = evaluate_case(predicted, observed)
        assert "jsd" in result
        assert "brier" in result
        assert result["jsd"] >= 0.0
        assert result["brier"] is None or result["brier"] >= 0.0

    def test_evaluate_identical_returns_zero_jsd(self):
        """同一分布では JSD=0."""
        from src.app.evaluation.retrodiction_runner import evaluate_case

        dist = {"賛成": 0.4, "反対": 0.3, "中立": 0.3}
        result = evaluate_case(dist, dist)
        assert result["jsd"] == pytest.approx(0.0, abs=1e-6)

    def test_check_regression_passes(self):
        """JSD がベースラインから 0.02 未満の悪化なら合格."""
        from src.app.evaluation.retrodiction_runner import check_regression

        assert check_regression(current_jsd=0.05, baseline_jsd=0.04) is True  # 0.01 差

    def test_check_regression_fails(self):
        """JSD がベースラインから 0.02 以上悪化したら失敗."""
        from src.app.evaluation.retrodiction_runner import check_regression

        assert check_regression(current_jsd=0.08, baseline_jsd=0.05) is False  # 0.03 差
