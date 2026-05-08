"""P1-2: レトロダクション検証パイプラインのテスト"""

import json
from pathlib import Path

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


class TestEvaluateCaseECE:
    """evaluate_case が ECE を含むこと (Phase 0)."""

    def test_evaluate_case_returns_ece_key(self):
        """ECE キーが結果辞書に含まれる."""
        from src.app.evaluation.retrodiction_runner import evaluate_case

        predicted = {"賛成": 0.30, "反対": 0.20, "中立": 0.30, "条件付き賛成": 0.10, "条件付き反対": 0.10}
        observed = {"賛成": 0.25, "反対": 0.10, "中立": 0.30, "条件付き賛成": 0.20, "条件付き反対": 0.15}

        result = evaluate_case(predicted, observed)
        assert "ece" in result
        assert result["ece"] is None or 0.0 <= result["ece"] <= 1.0

    def test_evaluate_identical_returns_zero_ece(self):
        """同一分布では ECE もほぼ 0."""
        from src.app.evaluation.retrodiction_runner import evaluate_case

        dist = {"賛成": 0.4, "反対": 0.3, "中立": 0.3}
        result = evaluate_case(dist, dist)
        assert result["ece"] == pytest.approx(0.0, abs=1e-6)


class TestRunBatch:
    """run_batch: 複数 fixture を一括評価する (Phase 0)."""

    def test_run_batch_aggregates_metrics(self):
        """複数 fixture を一括評価して集計値を返す."""
        from src.app.evaluation.retrodiction_runner import run_batch

        fixtures = [
            {
                "theme": "テーマA",
                "theme_category": "politics",
                "stance_distribution": {"賛成": 0.4, "反対": 0.3, "中立": 0.3},
            },
            {
                "theme": "テーマB",
                "theme_category": "economy",
                "stance_distribution": {"賛成": 0.5, "反対": 0.2, "中立": 0.3},
            },
        ]

        # mock predictor: predicted == observed (完全予測)
        def mock_predictor(case):
            return case["stance_distribution"]

        result = run_batch(fixtures, mock_predictor)
        assert "cases" in result
        assert "summary" in result
        assert len(result["cases"]) == 2
        assert "mean_jsd" in result["summary"]
        assert "mean_brier" in result["summary"]
        assert "mean_ece" in result["summary"]
        # 完全予測なので JSD ≈ 0
        assert result["summary"]["mean_jsd"] == pytest.approx(0.0, abs=1e-6)

    def test_run_batch_uses_injected_predictor(self):
        """predictor をモック関数で差替可能 (LLM コスト隔離)."""
        from src.app.evaluation.retrodiction_runner import run_batch

        fixtures = [
            {
                "theme": "テーマX",
                "theme_category": "test",
                "stance_distribution": {"賛成": 0.5, "反対": 0.5},
            }
        ]

        called = {"count": 0}

        def tracking_predictor(case):
            called["count"] += 1
            return {"賛成": 0.6, "反対": 0.4}

        result = run_batch(fixtures, tracking_predictor)
        assert called["count"] == 1
        assert result["cases"][0]["theme"] == "テーマX"
        assert result["cases"][0]["jsd"] > 0.0


class TestSaveBaseline:
    """save_baseline: JSON 書き出し (Phase 0)."""

    def test_save_baseline_writes_json(self, tmp_path):
        """baseline 結果が JSON で保存される."""
        from src.app.evaluation.retrodiction_runner import save_baseline

        result = {
            "cases": [{"theme": "T", "jsd": 0.05, "brier": 0.02, "ece": 0.01}],
            "summary": {"mean_jsd": 0.05, "mean_brier": 0.02, "mean_ece": 0.01, "n": 1},
        }
        out_path = tmp_path / "baseline_v0.json"
        save_baseline(result, out_path)

        assert out_path.exists()
        with open(out_path) as f:
            loaded = json.load(f)
        assert loaded["summary"]["mean_jsd"] == 0.05
        assert loaded["cases"][0]["theme"] == "T"
