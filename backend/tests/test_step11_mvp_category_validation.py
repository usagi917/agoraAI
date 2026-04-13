"""Step 11: MVP カテゴリ拡張 テスト

TDD RED フェーズ:
- economy / security カテゴリの精度指標算出テスト
  - compute_mae: Mean Absolute Error（分布間の絶対誤差平均）
  - compute_rps: Ranked Probability Score（序数分布の CDF-based 精度）
- build_category_accuracy_report: カテゴリ別精度レポート生成テスト
  - gate_runner 結果 + baseline スナップショットから相対改善率を算出
  - improvement_flag の生成（EMD 30%改善 / MAE 20%改善）
- check_release_gate: release ゲート判定テスト
  - 全カテゴリが改善基準を満たす場合 → "pass"
  - いずれかが基準未達 → "fail"
  - データ不足 → "inconclusive"
- run_mvp_category_validation: E2E テスト
  - economy / security fixture を読み込み、baseline と比較して改善判定を出力
  - unknown カテゴリ時は calibration/comparison をスキップ
- Unknown カテゴリ guard テスト
  - category="unknown" では release gate を "inconclusive" で返す

定数:
  MIN_RELATIVE_EMD_IMPROVEMENT = 0.30 (30%以上改善)
  MIN_RELATIVE_MAE_IMPROVEMENT = 0.20 (20%以上改善)
  MVP_CATEGORIES = ["economy", "security"]
"""

from __future__ import annotations

import math

import pytest


# ===========================================================
# 定数テスト
# ===========================================================


class TestMVPConstants:
    """MVP 定数の確認テスト"""

    def test_min_relative_emd_improvement(self):
        """MIN_RELATIVE_EMD_IMPROVEMENT は 0.30 であること"""
        from src.app.services.society.mvp_category_validator import MIN_RELATIVE_EMD_IMPROVEMENT
        assert MIN_RELATIVE_EMD_IMPROVEMENT == pytest.approx(0.30)

    def test_min_relative_mae_improvement(self):
        """MIN_RELATIVE_MAE_IMPROVEMENT は 0.20 であること"""
        from src.app.services.society.mvp_category_validator import MIN_RELATIVE_MAE_IMPROVEMENT
        assert MIN_RELATIVE_MAE_IMPROVEMENT == pytest.approx(0.20)

    def test_mvp_categories_contains_economy_and_security(self):
        """MVP_CATEGORIES に economy と security が含まれること"""
        from src.app.services.society.mvp_category_validator import MVP_CATEGORIES
        assert "economy" in MVP_CATEGORIES
        assert "security" in MVP_CATEGORIES

    def test_n_live_runs(self):
        """N_LIVE_RUNS は 5 以上であること（plan.md 要件）"""
        from src.app.services.society.mvp_category_validator import N_LIVE_RUNS
        assert N_LIVE_RUNS >= 5


# ===========================================================
# 1. compute_mae テスト
# ===========================================================


class TestComputeMAE:
    """compute_mae のテスト"""

    def test_identical_distributions_zero_mae(self):
        """同一分布では MAE=0"""
        from src.app.services.society.mvp_category_validator import compute_mae
        dist = {"賛成": 0.40, "条件付き賛成": 0.25, "中立": 0.20, "条件付き反対": 0.10, "反対": 0.05}
        assert compute_mae(dist, dist) == pytest.approx(0.0)

    def test_known_mae_value(self):
        """既知の差分から MAE を計算できること"""
        from src.app.services.society.mvp_category_validator import compute_mae
        sim = {"賛成": 0.30, "条件付き賛成": 0.25, "中立": 0.25, "条件付き反対": 0.15, "反対": 0.05}
        act = {"賛成": 0.20, "条件付き賛成": 0.25, "中立": 0.25, "条件付き反対": 0.15, "反対": 0.15}
        # |0.30-0.20| + |0.25-0.25| + |0.25-0.25| + |0.15-0.15| + |0.05-0.15| = 0.10 + 0 + 0 + 0 + 0.10 = 0.20
        # MAE = 0.20 / 5 = 0.04
        assert compute_mae(sim, act) == pytest.approx(0.04)

    def test_mae_is_non_negative(self):
        """MAE は非負"""
        from src.app.services.society.mvp_category_validator import compute_mae
        sim = {"賛成": 0.10, "条件付き賛成": 0.20, "中立": 0.30, "条件付き反対": 0.25, "反対": 0.15}
        act = {"賛成": 0.40, "条件付き賛成": 0.20, "中立": 0.10, "条件付き反対": 0.20, "反対": 0.10}
        assert compute_mae(sim, act) >= 0.0

    def test_mae_symmetric(self):
        """MAE は symmetric (sim↔actual を入れ替えても同じ)"""
        from src.app.services.society.mvp_category_validator import compute_mae
        sim = {"賛成": 0.30, "条件付き賛成": 0.25, "中立": 0.20, "条件付き反対": 0.15, "反対": 0.10}
        act = {"賛成": 0.20, "条件付き賛成": 0.30, "中立": 0.25, "条件付き反対": 0.15, "反対": 0.10}
        assert compute_mae(sim, act) == pytest.approx(compute_mae(act, sim))

    def test_mae_handles_missing_keys(self):
        """片方にしかないキーは 0 として扱われること"""
        from src.app.services.society.mvp_category_validator import compute_mae
        sim = {"賛成": 0.50, "中立": 0.50}
        act = {"賛成": 0.50, "反対": 0.50}
        # keys union: {賛成, 中立, 反対}
        # |0.50-0.50| + |0.50-0| + |0-0.50| = 0 + 0.50 + 0.50 = 1.0 / 3 = 0.333...
        result = compute_mae(sim, act)
        assert result == pytest.approx(1.0 / 3, rel=1e-5)

    def test_mae_empty_distributions_returns_zero(self):
        """両方とも空辞書の場合は 0.0 を返すこと"""
        from src.app.services.society.mvp_category_validator import compute_mae
        assert compute_mae({}, {}) == pytest.approx(0.0)


# ===========================================================
# 2. compute_rps テスト
# ===========================================================


class TestComputeRPS:
    """Ranked Probability Score (RPS) のテスト"""

    _STANCES = ["賛成", "条件付き賛成", "中立", "条件付き反対", "反対"]

    def test_identical_distributions_zero_rps(self):
        """同一分布では RPS=0"""
        from src.app.services.society.mvp_category_validator import compute_rps
        dist = {"賛成": 0.20, "条件付き賛成": 0.20, "中立": 0.20, "条件付き反対": 0.20, "反対": 0.20}
        assert compute_rps(dist, dist, self._STANCES) == pytest.approx(0.0)

    def test_perfect_prediction_zero_rps(self):
        """完全一致の場合 RPS=0"""
        from src.app.services.society.mvp_category_validator import compute_rps
        dist = {"賛成": 1.0, "条件付き賛成": 0.0, "中立": 0.0, "条件付き反対": 0.0, "反対": 0.0}
        assert compute_rps(dist, dist, self._STANCES) == pytest.approx(0.0)

    def test_rps_is_non_negative(self):
        """RPS は非負"""
        from src.app.services.society.mvp_category_validator import compute_rps
        sim = {"賛成": 0.10, "条件付き賛成": 0.20, "中立": 0.30, "条件付き反対": 0.25, "反対": 0.15}
        act = {"賛成": 0.40, "条件付き賛成": 0.20, "中立": 0.10, "条件付き反対": 0.20, "反対": 0.10}
        assert compute_rps(sim, act, self._STANCES) >= 0.0

    def test_rps_formula(self):
        """RPS = 1/(K-1) * sum((CDF_pred(k) - CDF_obs(k))^2) の公式が成立すること"""
        from src.app.services.society.mvp_category_validator import compute_rps
        sim = {"賛成": 0.30, "条件付き賛成": 0.25, "中立": 0.20, "条件付き反対": 0.15, "反対": 0.10}
        act = {"賛成": 0.25, "条件付き賛成": 0.25, "中立": 0.25, "条件付き反対": 0.15, "反対": 0.10}
        stances = self._STANCES

        # CDF を手動計算
        cdf_sim = []
        cdf_act = []
        cum_s = cum_a = 0.0
        for s in stances:
            cum_s += sim.get(s, 0.0)
            cum_a += act.get(s, 0.0)
            cdf_sim.append(cum_s)
            cdf_act.append(cum_a)

        K = len(stances)
        expected = sum((cs - ca) ** 2 for cs, ca in zip(cdf_sim, cdf_act)) / (K - 1)
        assert compute_rps(sim, act, stances) == pytest.approx(expected, rel=1e-5)

    def test_rps_single_stance_returns_zero(self):
        """stance_order が 1 要素の場合は 0.0 を返すこと"""
        from src.app.services.society.mvp_category_validator import compute_rps
        assert compute_rps({"賛成": 1.0}, {"賛成": 1.0}, ["賛成"]) == pytest.approx(0.0)

    def test_rps_empty_stance_order_returns_zero(self):
        """stance_order が空の場合は 0.0 を返すこと"""
        from src.app.services.society.mvp_category_validator import compute_rps
        assert compute_rps({}, {}, []) == pytest.approx(0.0)

    def test_rps_increases_with_larger_deviation(self):
        """誤差が大きいほど RPS が大きいこと"""
        from src.app.services.society.mvp_category_validator import compute_rps
        actual = {"賛成": 0.40, "条件付き賛成": 0.30, "中立": 0.15, "条件付き反対": 0.10, "反対": 0.05}
        # 実測に近い予測
        sim_close = {"賛成": 0.38, "条件付き賛成": 0.30, "中立": 0.15, "条件付き反対": 0.11, "反対": 0.06}
        # 実測から遠い予測
        sim_far = {"賛成": 0.05, "条件付き賛成": 0.10, "中立": 0.20, "条件付き反対": 0.30, "反対": 0.35}
        rps_close = compute_rps(sim_close, actual, self._STANCES)
        rps_far = compute_rps(sim_far, actual, self._STANCES)
        assert rps_close < rps_far


# ===========================================================
# 3. build_category_accuracy_report テスト
# ===========================================================


_GATE_PASS = {
    "gate": "pass",
    "avg_emd": 0.07,
    "avg_jsd": 0.05,
    "avg_brier": 0.10,
    "total_count": 3,
    "validated_count": 3,
    "gate_eligible_count": 3,
    "theme_category": "economy",
}

_GATE_FAIL = {
    "gate": "fail",
    "avg_emd": 0.20,
    "avg_jsd": 0.15,
    "avg_brier": 0.35,
    "total_count": 3,
    "validated_count": 3,
    "gate_eligible_count": 3,
    "theme_category": "economy",
}

_BASELINE_ECONOMY = {
    "emd": 0.10,   # 現行 main の基準
    "jsd": 0.08,
    "brier": 0.15,
    "mae_pp": 0.05,
    "n_validated": 3,
    "status": "measured",
}


class TestBuildCategoryAccuracyReport:
    """build_category_accuracy_report のテスト"""

    def test_returns_required_fields(self):
        """必須フィールドを全て含む辞書を返す"""
        from src.app.services.society.mvp_category_validator import build_category_accuracy_report

        report = build_category_accuracy_report(
            category="economy",
            gate_result=_GATE_PASS,
            baseline_metrics=_BASELINE_ECONOMY,
        )

        required_keys = (
            "category", "gate", "avg_emd", "avg_jsd", "avg_brier",
            "baseline_emd", "emd_improvement", "emd_improvement_flag",
            "mae_improvement", "mae_improvement_flag",
            "release_gate_eligible",
        )
        for k in required_keys:
            assert k in report, f"Missing key: {k}"

    def test_category_matches_input(self):
        """category フィールドが入力と一致する"""
        from src.app.services.society.mvp_category_validator import build_category_accuracy_report

        report = build_category_accuracy_report(
            category="security",
            gate_result={**_GATE_PASS, "theme_category": "security"},
            baseline_metrics=_BASELINE_ECONOMY,
        )
        assert report["category"] == "security"

    def test_emd_improvement_calculated_correctly(self):
        """emd_improvement = (baseline - current) / baseline"""
        from src.app.services.society.mvp_category_validator import build_category_accuracy_report

        # baseline_emd=0.10, current=0.07 → improvement = (0.10-0.07)/0.10 = 0.30
        report = build_category_accuracy_report(
            category="economy",
            gate_result=_GATE_PASS,  # avg_emd=0.07
            baseline_metrics=_BASELINE_ECONOMY,  # emd=0.10
        )
        assert report["emd_improvement"] == pytest.approx(0.30, rel=1e-5)

    def test_emd_improvement_flag_true_when_above_threshold(self):
        """EMD 改善率 >= 0.30 の場合 emd_improvement_flag=True"""
        from src.app.services.society.mvp_category_validator import build_category_accuracy_report

        # (0.10-0.07)/0.10 = 0.30 → flag=True (閾値ちょうど)
        report = build_category_accuracy_report(
            category="economy",
            gate_result=_GATE_PASS,  # avg_emd=0.07
            baseline_metrics=_BASELINE_ECONOMY,  # emd=0.10
        )
        assert report["emd_improvement_flag"] is True

    def test_emd_improvement_flag_false_when_below_threshold(self):
        """EMD 改善率 < 0.30 の場合 emd_improvement_flag=False"""
        from src.app.services.society.mvp_category_validator import build_category_accuracy_report

        # avg_emd=0.09 → improvement = (0.10-0.09)/0.10 = 0.10 < 0.30
        gate_marginal = {**_GATE_PASS, "avg_emd": 0.09}
        report = build_category_accuracy_report(
            category="economy",
            gate_result=gate_marginal,
            baseline_metrics=_BASELINE_ECONOMY,
        )
        assert report["emd_improvement_flag"] is False

    def test_emd_improvement_none_when_baseline_null(self):
        """baseline_emd が None の場合 emd_improvement=None"""
        from src.app.services.society.mvp_category_validator import build_category_accuracy_report

        baseline_null = {**_BASELINE_ECONOMY, "emd": None}
        report = build_category_accuracy_report(
            category="economy",
            gate_result=_GATE_PASS,
            baseline_metrics=baseline_null,
        )
        assert report["emd_improvement"] is None
        assert report["emd_improvement_flag"] is False

    def test_release_gate_eligible_when_both_flags_true(self):
        """emd_improvement_flag と mae_improvement_flag が両方 True → release_gate_eligible=True"""
        from src.app.services.society.mvp_category_validator import build_category_accuracy_report

        # emd: (0.10-0.07)/0.10=0.30 >=0.30 → True
        # mae_pp in baseline=0.05; current avg_emd を proxy に使うか、
        # または mae は gate_result に含まれないため、baseline.mae_pp を参照する
        # ここでは gate_result に "avg_mae" を持たせることで検証する
        gate_with_mae = {**_GATE_PASS, "avg_mae": 0.04}  # (0.05-0.04)/0.05=0.20 >=0.20 → True
        report = build_category_accuracy_report(
            category="economy",
            gate_result=gate_with_mae,
            baseline_metrics=_BASELINE_ECONOMY,
        )
        assert report["release_gate_eligible"] is True

    def test_release_gate_not_eligible_when_emd_flag_false(self):
        """emd_improvement_flag=False の場合 release_gate_eligible=False"""
        from src.app.services.society.mvp_category_validator import build_category_accuracy_report

        gate_marginal = {**_GATE_PASS, "avg_emd": 0.09, "avg_mae": 0.04}
        report = build_category_accuracy_report(
            category="economy",
            gate_result=gate_marginal,
            baseline_metrics=_BASELINE_ECONOMY,
        )
        assert report["release_gate_eligible"] is False

    def test_baseline_emd_propagated(self):
        """baseline_emd がレポートに記録される"""
        from src.app.services.society.mvp_category_validator import build_category_accuracy_report

        report = build_category_accuracy_report(
            category="economy",
            gate_result=_GATE_PASS,
            baseline_metrics=_BASELINE_ECONOMY,
        )
        assert report["baseline_emd"] == pytest.approx(0.10)


# ===========================================================
# 4. check_release_gate テスト
# ===========================================================


_REPORT_ECONOMY_PASS = {
    "category": "economy",
    "gate": "pass",
    "avg_emd": 0.07,
    "avg_jsd": 0.05,
    "avg_brier": 0.10,
    "baseline_emd": 0.10,
    "emd_improvement": 0.30,
    "emd_improvement_flag": True,
    "mae_improvement": 0.25,
    "mae_improvement_flag": True,
    "release_gate_eligible": True,
}

_REPORT_SECURITY_PASS = {
    "category": "security",
    "gate": "pass",
    "avg_emd": 0.05,
    "avg_jsd": 0.04,
    "avg_brier": 0.08,
    "baseline_emd": 0.08,
    "emd_improvement": 0.375,
    "emd_improvement_flag": True,
    "mae_improvement": 0.30,
    "mae_improvement_flag": True,
    "release_gate_eligible": True,
}

_REPORT_ECONOMY_FAIL = {
    **_REPORT_ECONOMY_PASS,
    "emd_improvement": 0.10,
    "emd_improvement_flag": False,
    "release_gate_eligible": False,
}


class TestCheckReleaseGate:
    """check_release_gate のテスト"""

    def test_all_eligible_pass_returns_pass(self):
        """全カテゴリが release_gate_eligible=True → overall="pass" """
        from src.app.services.society.mvp_category_validator import check_release_gate

        result = check_release_gate([_REPORT_ECONOMY_PASS, _REPORT_SECURITY_PASS])
        assert result["overall"] == "pass"

    def test_any_not_eligible_returns_fail(self):
        """いずれかが release_gate_eligible=False → overall="fail" """
        from src.app.services.society.mvp_category_validator import check_release_gate

        result = check_release_gate([_REPORT_ECONOMY_FAIL, _REPORT_SECURITY_PASS])
        assert result["overall"] == "fail"

    def test_empty_reports_returns_inconclusive(self):
        """レポートが空 → overall="inconclusive" """
        from src.app.services.society.mvp_category_validator import check_release_gate

        result = check_release_gate([])
        assert result["overall"] == "inconclusive"

    def test_returns_category_summary(self):
        """categories フィールドにカテゴリ別サマリーが含まれること"""
        from src.app.services.society.mvp_category_validator import check_release_gate

        result = check_release_gate([_REPORT_ECONOMY_PASS, _REPORT_SECURITY_PASS])
        assert "categories" in result
        assert "economy" in result["categories"]
        assert "security" in result["categories"]

    def test_returns_required_fields(self):
        """必須フィールド (overall, categories, category_count) を含むこと"""
        from src.app.services.society.mvp_category_validator import check_release_gate

        result = check_release_gate([_REPORT_ECONOMY_PASS])
        for k in ("overall", "categories", "category_count"):
            assert k in result, f"Missing key: {k}"

    def test_category_count_matches(self):
        """category_count が入力レポート数と一致すること"""
        from src.app.services.society.mvp_category_validator import check_release_gate

        result = check_release_gate([_REPORT_ECONOMY_PASS, _REPORT_SECURITY_PASS])
        assert result["category_count"] == 2

    def test_unknown_category_returns_inconclusive(self):
        """category="unknown" のレポートだけの場合 → overall="inconclusive" """
        from src.app.services.society.mvp_category_validator import check_release_gate

        unknown_report = {
            **_REPORT_ECONOMY_PASS,
            "category": "unknown",
            "release_gate_eligible": False,
        }
        result = check_release_gate([unknown_report])
        assert result["overall"] == "inconclusive"

    def test_mixed_unknown_and_pass_returns_pass(self):
        """unknown カテゴリは除外し、残りが全 pass → overall="pass" """
        from src.app.services.society.mvp_category_validator import check_release_gate

        unknown_report = {**_REPORT_ECONOMY_PASS, "category": "unknown"}
        result = check_release_gate([unknown_report, _REPORT_SECURITY_PASS])
        assert result["overall"] == "pass"


# ===========================================================
# 5. run_mvp_category_validation E2E テスト
# ===========================================================


def _make_baseline_snapshot(economy_emd=0.10, security_emd=0.08) -> dict:
    """テスト用 baseline スナップショット辞書を生成する。"""
    return {
        "economy": {
            "emd": economy_emd,
            "jsd": 0.08,
            "brier": 0.15,
            "mae_pp": 0.05,
            "status": "measured",
        },
        "security": {
            "emd": security_emd,
            "jsd": 0.06,
            "brier": 0.12,
            "mae_pp": 0.04,
            "status": "measured",
        },
    }


class TestRunMVPCategoryValidation:
    """run_mvp_category_validation の E2E テスト"""

    def test_returns_required_fields(self, tmp_path):
        """必須フィールドを含む辞書を返すこと"""
        from src.app.services.society.mvp_category_validator import run_mvp_category_validation

        result = run_mvp_category_validation(
            fixture_dir=str(tmp_path),
            baseline_snapshot=_make_baseline_snapshot(),
        )

        required_keys = ("overall", "categories", "category_count", "fixture_count")
        for k in required_keys:
            assert k in result, f"Missing key: {k}"

    def test_empty_fixture_dir_returns_inconclusive(self, tmp_path):
        """fixture がない場合 overall="inconclusive" """
        from src.app.services.society.mvp_category_validator import run_mvp_category_validation

        result = run_mvp_category_validation(
            fixture_dir=str(tmp_path),
            baseline_snapshot=_make_baseline_snapshot(),
        )
        assert result["overall"] == "inconclusive"
        assert result["fixture_count"] == 0

    def test_economy_fixture_produces_economy_report(self, tmp_path):
        """economy_gate.yaml を読み込み economy カテゴリのレポートが生成されること"""
        import yaml
        from src.app.services.society.mvp_category_validator import run_mvp_category_validation

        fixture = {
            "preset_id": "economy",
            "theme_category": "economy",
            "seed": 42,
            "cases": [
                {
                    "case_id": "e001",
                    "theme": "景況感",
                    "survey_source": "テスト調査",
                    "gate_eligible": True,
                    "simulated_distribution": {
                        "賛成": 0.28, "条件付き賛成": 0.24, "中立": 0.22,
                        "条件付き反対": 0.15, "反対": 0.11,
                    },
                    "actual_distribution": {
                        "賛成": 0.30, "条件付き賛成": 0.25, "中立": 0.20,
                        "条件付き反対": 0.15, "反対": 0.10,
                    },
                }
            ],
        }
        (tmp_path / "economy_gate.yaml").write_text(
            yaml.dump(fixture, allow_unicode=True), encoding="utf-8"
        )

        result = run_mvp_category_validation(
            fixture_dir=str(tmp_path),
            baseline_snapshot=_make_baseline_snapshot(),
        )

        assert "economy" in result["categories"]
        assert result["fixture_count"] == 1

    def test_security_fixture_produces_security_report(self, tmp_path):
        """security_gate.yaml を読み込み security カテゴリのレポートが生成されること"""
        import yaml
        from src.app.services.society.mvp_category_validator import run_mvp_category_validation

        fixture = {
            "preset_id": "security",
            "theme_category": "security",
            "seed": 42,
            "cases": [
                {
                    "case_id": "s001",
                    "theme": "防衛政策",
                    "survey_source": "テスト調査",
                    "gate_eligible": True,
                    "simulated_distribution": {
                        "賛成": 0.43, "条件付き賛成": 0.26, "中立": 0.17,
                        "条件付き反対": 0.09, "反対": 0.05,
                    },
                    "actual_distribution": {
                        "賛成": 0.45, "条件付き賛成": 0.25, "中立": 0.15,
                        "条件付き反対": 0.10, "反対": 0.05,
                    },
                }
            ],
        }
        (tmp_path / "security_gate.yaml").write_text(
            yaml.dump(fixture, allow_unicode=True), encoding="utf-8"
        )

        result = run_mvp_category_validation(
            fixture_dir=str(tmp_path),
            baseline_snapshot=_make_baseline_snapshot(),
        )

        assert "security" in result["categories"]

    def test_non_gate_yaml_files_ignored(self, tmp_path):
        """_gate.yaml 以外のファイルは無視されること"""
        from src.app.services.society.mvp_category_validator import run_mvp_category_validation

        (tmp_path / "config.yaml").write_text("key: value", encoding="utf-8")
        (tmp_path / "README.md").write_text("# readme", encoding="utf-8")

        result = run_mvp_category_validation(
            fixture_dir=str(tmp_path),
            baseline_snapshot=_make_baseline_snapshot(),
        )

        assert result["fixture_count"] == 0
        assert result["overall"] == "inconclusive"

    def test_null_baseline_metrics_handled_gracefully(self, tmp_path):
        """baseline が null でもエラーにならずに inconclusive を返すこと"""
        import yaml
        from src.app.services.society.mvp_category_validator import run_mvp_category_validation

        fixture = {
            "preset_id": "economy",
            "theme_category": "economy",
            "seed": 42,
            "cases": [
                {
                    "case_id": "e001",
                    "theme": "景況感",
                    "survey_source": "テスト調査",
                    "gate_eligible": True,
                    "simulated_distribution": {
                        "賛成": 0.28, "条件付き賛成": 0.24, "中立": 0.22,
                        "条件付き反対": 0.15, "反対": 0.11,
                    },
                    "actual_distribution": {
                        "賛成": 0.30, "条件付き賛成": 0.25, "中立": 0.20,
                        "条件付き反対": 0.15, "反対": 0.10,
                    },
                }
            ],
        }
        (tmp_path / "economy_gate.yaml").write_text(
            yaml.dump(fixture, allow_unicode=True), encoding="utf-8"
        )

        null_baseline = {
            "economy": {"emd": None, "jsd": None, "brier": None, "mae_pp": None, "status": "not_measured"},
        }
        result = run_mvp_category_validation(
            fixture_dir=str(tmp_path),
            baseline_snapshot=null_baseline,
        )

        # baseline が null の場合は改善率不明 → release_gate_eligible=False → fail or inconclusive
        assert result["overall"] in ("fail", "inconclusive")

    def test_reproducible_results_same_fixture(self, tmp_path):
        """同一 fixture で 2 回実行すると同一 overall 結果を返すこと"""
        import yaml
        from src.app.services.society.mvp_category_validator import run_mvp_category_validation

        fixture = {
            "preset_id": "economy",
            "theme_category": "economy",
            "seed": 42,
            "cases": [
                {
                    "case_id": "e001",
                    "theme": "景況感",
                    "survey_source": "テスト調査",
                    "gate_eligible": True,
                    "simulated_distribution": {
                        "賛成": 0.28, "条件付き賛成": 0.24, "中立": 0.22,
                        "条件付き反対": 0.15, "反対": 0.11,
                    },
                    "actual_distribution": {
                        "賛成": 0.30, "条件付き賛成": 0.25, "中立": 0.20,
                        "条件付き反対": 0.15, "反対": 0.10,
                    },
                }
            ],
        }
        (tmp_path / "economy_gate.yaml").write_text(
            yaml.dump(fixture, allow_unicode=True), encoding="utf-8"
        )

        r1 = run_mvp_category_validation(
            fixture_dir=str(tmp_path),
            baseline_snapshot=_make_baseline_snapshot(),
        )
        r2 = run_mvp_category_validation(
            fixture_dir=str(tmp_path),
            baseline_snapshot=_make_baseline_snapshot(),
        )

        assert r1["overall"] == r2["overall"]


# ===========================================================
# 6. Unknown カテゴリ guard テスト
# ===========================================================


class TestUnknownCategoryGuard:
    """unknown カテゴリのガード動作テスト"""

    def test_build_report_unknown_category_not_release_eligible(self):
        """category="unknown" ではリリースゲート対象外になること"""
        from src.app.services.society.mvp_category_validator import build_category_accuracy_report

        gate_unknown = {**_GATE_PASS, "theme_category": "unknown"}
        report = build_category_accuracy_report(
            category="unknown",
            gate_result=gate_unknown,
            baseline_metrics=None,
        )
        assert report["release_gate_eligible"] is False

    def test_build_report_unknown_baseline_none_handled(self):
        """baseline_metrics=None の場合も KeyError にならないこと"""
        from src.app.services.society.mvp_category_validator import build_category_accuracy_report

        report = build_category_accuracy_report(
            category="unknown",
            gate_result=_GATE_PASS,
            baseline_metrics=None,
        )
        assert report["emd_improvement"] is None
        assert report["mae_improvement"] is None

    def test_check_release_gate_skips_unknown_category(self):
        """unknown カテゴリは release gate 判定から除外されること"""
        from src.app.services.society.mvp_category_validator import check_release_gate

        unknown_report = {
            "category": "unknown",
            "gate": "pass",
            "avg_emd": 0.05,
            "avg_jsd": 0.04,
            "avg_brier": 0.08,
            "baseline_emd": None,
            "emd_improvement": None,
            "emd_improvement_flag": False,
            "mae_improvement": None,
            "mae_improvement_flag": False,
            "release_gate_eligible": False,
        }

        # unknown のみ → inconclusive
        result = check_release_gate([unknown_report])
        assert result["overall"] == "inconclusive"

    def test_check_release_gate_unknown_does_not_trigger_fail(self):
        """unknown カテゴリの release_gate_eligible=False は fail を引き起こさないこと"""
        from src.app.services.society.mvp_category_validator import check_release_gate

        unknown_report = {
            "category": "unknown",
            "gate": "pass",
            "avg_emd": 0.05,
            "avg_jsd": 0.04,
            "avg_brier": 0.08,
            "baseline_emd": None,
            "emd_improvement": None,
            "emd_improvement_flag": False,
            "mae_improvement": None,
            "mae_improvement_flag": False,
            "release_gate_eligible": False,
        }

        result = check_release_gate([unknown_report, _REPORT_SECURITY_PASS])
        # unknown を除外 → security だけで pass
        assert result["overall"] == "pass"


# ===========================================================
# 7. load_baseline_snapshot テスト
# ===========================================================


class TestLoadBaselineSnapshot:
    """load_baseline_snapshot のテスト"""

    def test_loads_yaml_snapshot(self, tmp_path):
        """YAML ファイルから baseline スナップショットを読み込めること"""
        import yaml
        from src.app.services.society.mvp_category_validator import load_baseline_snapshot

        snapshot_data = {
            "baseline_metrics": {
                "economy": {
                    "jsd": 0.08, "emd": 0.10, "brier": 0.15,
                    "mae_pp": 0.05, "n_validated": 3, "status": "measured",
                },
                "security": {
                    "jsd": 0.06, "emd": 0.08, "brier": 0.12,
                    "mae_pp": 0.04, "n_validated": 2, "status": "measured",
                },
            }
        }
        snapshot_file = tmp_path / "snapshot.yaml"
        snapshot_file.write_text(yaml.dump(snapshot_data, allow_unicode=True), encoding="utf-8")

        result = load_baseline_snapshot(str(snapshot_file))

        assert "economy" in result
        assert "security" in result
        assert result["economy"]["emd"] == pytest.approx(0.10)
        assert result["security"]["emd"] == pytest.approx(0.08)

    def test_missing_file_returns_empty_dict(self):
        """存在しないファイルは空辞書を返すこと"""
        from src.app.services.society.mvp_category_validator import load_baseline_snapshot

        result = load_baseline_snapshot("/nonexistent/path/snapshot.yaml")
        assert result == {}

    def test_missing_baseline_metrics_key_returns_empty_dict(self, tmp_path):
        """baseline_metrics キーがない YAML は空辞書を返すこと"""
        import yaml
        from src.app.services.society.mvp_category_validator import load_baseline_snapshot

        snapshot_file = tmp_path / "bad.yaml"
        snapshot_file.write_text(yaml.dump({"other_key": "value"}), encoding="utf-8")

        result = load_baseline_snapshot(str(snapshot_file))
        assert result == {}

    def test_invalid_yaml_returns_empty_dict(self, tmp_path):
        """不正な YAML（パースエラー）は空辞書を返すこと"""
        from src.app.services.society.mvp_category_validator import load_baseline_snapshot

        snapshot_file = tmp_path / "invalid.yaml"
        snapshot_file.write_text("{ unclosed: brace: [", encoding="utf-8")

        result = load_baseline_snapshot(str(snapshot_file))
        assert result == {}

    def test_yaml_non_dict_root_returns_empty_dict(self, tmp_path):
        """YAML のルートが辞書でない場合（リストなど）は空辞書を返すこと"""
        from src.app.services.society.mvp_category_validator import load_baseline_snapshot

        snapshot_file = tmp_path / "list.yaml"
        snapshot_file.write_text("- item1\n- item2\n", encoding="utf-8")

        result = load_baseline_snapshot(str(snapshot_file))
        assert result == {}


# ===========================================================
# 8. 実際の gate fixture を使ったスモーク統合テスト
# ===========================================================


class TestWithActualFixtures:
    """tests/fixtures/gate/ の実 fixture を使ったスモークテスト"""

    def test_economy_fixture_gate_pass(self):
        """economy_gate.yaml を使った gate check が動作すること"""
        import os
        from src.app.evaluation.gate_runner import run_deterministic_gate

        fixture_path = os.path.join(
            os.path.dirname(__file__),
            "fixtures", "gate", "economy_gate.yaml"
        )
        if not os.path.exists(fixture_path):
            pytest.skip("economy_gate.yaml が見つかりません")

        result = run_deterministic_gate(fixture_path, seed=42)
        # gate が "pass" か "inconclusive" であること（fail は許容しない）
        assert result["gate"] in ("pass", "inconclusive")
        assert result["theme_category"] == "economy"

    def test_security_fixture_gate_pass(self):
        """security_gate.yaml を使った gate check が動作すること"""
        import os
        from src.app.evaluation.gate_runner import run_deterministic_gate

        fixture_path = os.path.join(
            os.path.dirname(__file__),
            "fixtures", "gate", "security_gate.yaml"
        )
        if not os.path.exists(fixture_path):
            pytest.skip("security_gate.yaml が見つかりません")

        result = run_deterministic_gate(fixture_path, seed=42)
        assert result["gate"] in ("pass", "inconclusive")
        assert result["theme_category"] == "security"

    def test_both_categories_run_mvp_validation(self):
        """実際の gate fixture ディレクトリで run_mvp_category_validation が動作すること"""
        import os
        from src.app.services.society.mvp_category_validator import run_mvp_category_validation

        fixture_dir = os.path.join(os.path.dirname(__file__), "fixtures", "gate")
        if not os.path.exists(fixture_dir):
            pytest.skip("fixtures/gate/ が見つかりません")

        baseline = _make_baseline_snapshot(economy_emd=0.10, security_emd=0.08)
        result = run_mvp_category_validation(
            fixture_dir=fixture_dir,
            baseline_snapshot=baseline,
        )

        assert result["fixture_count"] >= 2
        assert "economy" in result["categories"]
        assert "security" in result["categories"]
        # overall は pass か fail か inconclusive のいずれか
        assert result["overall"] in ("pass", "fail", "inconclusive")
