"""Step 10: runtime gate / baseline 比較 / summary endpoint テスト

TDD RED フェーズ:
- 4 ベースライン（ランダム / 初期値固定 / 会話なし / イベントなし）算出可能テスト
- summary endpoint レスポンス構造テスト
- CI → gate_runner.py → deterministic replay の E2E テスト
- rolling backtest / live median 集計テスト
"""

from __future__ import annotations

import pytest
import yaml


# =============================================================
# 1. ランダムベースライン
# =============================================================

class TestRandomBaseline:
    """compute_random_baseline のテスト"""

    def test_returns_valid_distribution(self):
        """ランダムベースラインは有効な確率分布（合計≈1）を返す"""
        from src.app.services.society.baseline_comparator import compute_random_baseline

        stances = ["賛成", "条件付き賛成", "中立", "条件付き反対", "反対"]
        dist = compute_random_baseline(stances, seed=42)

        assert abs(sum(dist.values()) - 1.0) < 1e-9
        assert set(dist.keys()) == set(stances)

    def test_seed_produces_deterministic_result(self):
        """同一 seed で同一分布を生成する"""
        from src.app.services.society.baseline_comparator import compute_random_baseline

        stances = ["賛成", "条件付き賛成", "中立", "条件付き反対", "反対"]
        d1 = compute_random_baseline(stances, seed=42)
        d2 = compute_random_baseline(stances, seed=42)

        assert d1 == d2

    def test_different_seeds_produce_different_results(self):
        """異なる seed では異なる分布が生成される"""
        from src.app.services.society.baseline_comparator import compute_random_baseline

        stances = ["賛成", "条件付き賛成", "中立", "条件付き反対", "反対"]
        d1 = compute_random_baseline(stances, seed=1)
        d2 = compute_random_baseline(stances, seed=99)

        assert d1 != d2

    def test_all_values_are_positive(self):
        """全確率値が正の値"""
        from src.app.services.society.baseline_comparator import compute_random_baseline

        stances = ["賛成", "条件付き賛成", "中立", "条件付き反対", "反対"]
        dist = compute_random_baseline(stances, seed=42)

        assert all(v > 0 for v in dist.values())


# =============================================================
# 2. 初期値固定ベースライン
# =============================================================

class TestInitialBaseline:
    """compute_initial_baseline のテスト"""

    def test_returns_same_distribution(self):
        """初期値固定ベースラインは入力分布をそのまま返す"""
        from src.app.services.society.baseline_comparator import compute_initial_baseline

        activation_dist = {
            "賛成": 0.30, "条件付き賛成": 0.25, "中立": 0.20,
            "条件付き反対": 0.15, "反対": 0.10,
        }
        result = compute_initial_baseline(activation_dist)

        assert result == activation_dist

    def test_returns_copy_not_reference(self):
        """変更が元の分布に影響しない（コピーを返す）"""
        from src.app.services.society.baseline_comparator import compute_initial_baseline

        activation_dist = {
            "賛成": 0.30, "条件付き賛成": 0.25, "中立": 0.20,
            "条件付き反対": 0.15, "反対": 0.10,
        }
        result = compute_initial_baseline(activation_dist)
        result["賛成"] = 0.99

        assert activation_dist["賛成"] == pytest.approx(0.30)


# =============================================================
# 3. ベースライン比較（4 ベースライン対応）
# =============================================================

_SIM = {"賛成": 0.28, "条件付き賛成": 0.24, "中立": 0.22, "条件付き反対": 0.15, "反対": 0.11}
_ACT = {"賛成": 0.30, "条件付き賛成": 0.25, "中立": 0.20, "条件付き反対": 0.15, "反対": 0.10}
_RAND = {"賛成": 0.20, "条件付き賛成": 0.20, "中立": 0.20, "条件付き反対": 0.20, "反対": 0.20}
_INIT = {"賛成": 0.15, "条件付き賛成": 0.20, "中立": 0.30, "条件付き反対": 0.20, "反対": 0.15}


class TestBaselineComparison:
    """compare_against_baselines のテスト"""

    def test_returns_required_fields(self):
        """必須フィールドを含む辞書を返す"""
        from src.app.services.society.baseline_comparator import compare_against_baselines

        result = compare_against_baselines(_SIM, _ACT, _RAND, _INIT)

        required_keys = (
            "simulated_emd", "random_emd", "initial_emd",
            "no_conversation_emd", "no_event_emd",
            "vs_random_improvement", "vs_initial_improvement",
            "primary_metric",
        )
        for k in required_keys:
            assert k in result, f"Missing key: {k}"

    def test_primary_metric_is_emd(self):
        """primary_metric が 'emd'"""
        from src.app.services.society.baseline_comparator import compare_against_baselines

        result = compare_against_baselines(_SIM, _ACT, _RAND, _INIT)

        assert result["primary_metric"] == "emd"

    def test_vs_random_improvement_positive_when_simulated_better(self):
        """simulated が random より実績に近い場合、vs_random_improvement > 0"""
        from src.app.services.society.baseline_comparator import compare_against_baselines

        # simulated は actual に近い
        sim_close = {"賛成": 0.29, "条件付き賛成": 0.25, "中立": 0.20, "条件付き反対": 0.15, "反対": 0.11}
        # random は actual から遠い
        rand_far = {"賛成": 0.05, "条件付き賛成": 0.05, "中立": 0.05, "条件付き反対": 0.40, "反対": 0.45}

        result = compare_against_baselines(sim_close, _ACT, rand_far, _INIT)

        assert result["vs_random_improvement"] > 0

    def test_optional_baselines_none_allowed(self):
        """no_conversation / no_event が None の場合も動作する"""
        from src.app.services.society.baseline_comparator import compare_against_baselines

        result = compare_against_baselines(
            _SIM, _ACT, _RAND, _INIT,
            no_conversation_baseline=None,
            no_event_baseline=None,
        )

        assert result["no_conversation_emd"] is None
        assert result["no_event_emd"] is None

    def test_no_conversation_baseline_emd_computed(self):
        """no_conversation_baseline を渡すと no_conversation_emd が計算される"""
        from src.app.services.society.baseline_comparator import compare_against_baselines

        no_conv = {"賛成": 0.22, "条件付き賛成": 0.22, "中立": 0.22, "条件付き反対": 0.18, "反対": 0.16}

        result = compare_against_baselines(
            _SIM, _ACT, _RAND, _INIT, no_conversation_baseline=no_conv,
        )

        assert result["no_conversation_emd"] is not None
        assert result["no_conversation_emd"] >= 0

    def test_no_event_baseline_emd_computed(self):
        """no_event_baseline を渡すと no_event_emd が計算される"""
        from src.app.services.society.baseline_comparator import compare_against_baselines

        no_event = {"賛成": 0.26, "条件付き賛成": 0.24, "中立": 0.22, "条件付き反対": 0.16, "反対": 0.12}

        result = compare_against_baselines(
            _SIM, _ACT, _RAND, _INIT, no_event_baseline=no_event,
        )

        assert result["no_event_emd"] is not None
        assert result["no_event_emd"] >= 0

    def test_simulated_emd_is_non_negative(self):
        """simulated_emd が非負"""
        from src.app.services.society.baseline_comparator import compare_against_baselines

        result = compare_against_baselines(_SIM, _ACT, _RAND, _INIT)

        assert result["simulated_emd"] is not None
        assert result["simulated_emd"] >= 0


# =============================================================
# 4. summary endpoint レスポンス構造
# =============================================================

class TestEvaluationSummaryResponse:
    """build_evaluation_summary_response のテスト"""

    def _make_gate_result(self, gate: str = "pass") -> dict:
        return {
            "gate": gate,
            "avg_emd": 0.07 if gate != "inconclusive" else None,
            "avg_jsd": 0.05 if gate != "inconclusive" else None,
            "avg_brier": 0.10 if gate != "inconclusive" else None,
            "total_count": 5,
            "validated_count": 5,
            "gate_eligible_count": 5,
            "theme_category": "economy",
        }

    def _make_baseline_comparison(self) -> dict:
        return {
            "simulated_emd": 0.07,
            "random_emd": 0.30,
            "initial_emd": 0.20,
            "no_conversation_emd": None,
            "no_event_emd": None,
            "vs_random_improvement": 0.77,
            "vs_initial_improvement": 0.65,
            "primary_metric": "emd",
        }

    def test_has_required_fields(self):
        """必須フィールドが全て含まれる"""
        from src.app.services.society.baseline_comparator import build_evaluation_summary_response

        response = build_evaluation_summary_response(
            sim_id="test-sim-123",
            gate_result=self._make_gate_result("pass"),
            baseline_comparison=self._make_baseline_comparison(),
        )

        required_keys = (
            "simulation_id", "gate", "avg_emd", "avg_jsd", "avg_brier",
            "total_count", "validated_count", "gate_eligible_count",
            "theme_category", "baseline_comparison", "live_replay_warning",
        )
        for k in required_keys:
            assert k in response, f"Missing key: {k}"

    def test_gate_matches_input(self):
        """gate フィールドが入力と一致する"""
        from src.app.services.society.baseline_comparator import build_evaluation_summary_response

        response = build_evaluation_summary_response(
            sim_id="sim-fail",
            gate_result=self._make_gate_result("fail"),
            baseline_comparison=self._make_baseline_comparison(),
        )

        assert response["gate"] == "fail"

    def test_inconclusive_gate(self):
        """inconclusive ゲート結果が正しく返される"""
        from src.app.services.society.baseline_comparator import build_evaluation_summary_response

        gate_result = {
            "gate": "inconclusive", "avg_emd": None, "avg_jsd": None,
            "avg_brier": None, "total_count": 0, "validated_count": 0,
            "gate_eligible_count": 0, "theme_category": None,
        }
        baseline_comparison = {
            "simulated_emd": None, "random_emd": None, "initial_emd": None,
            "no_conversation_emd": None, "no_event_emd": None,
            "vs_random_improvement": None, "vs_initial_improvement": None,
            "primary_metric": "emd",
        }

        response = build_evaluation_summary_response(
            sim_id="sim-inconclusive",
            gate_result=gate_result,
            baseline_comparison=baseline_comparison,
        )

        assert response["gate"] == "inconclusive"
        assert response["avg_emd"] is None

    def test_simulation_id_propagated(self):
        """simulation_id が正しく伝播される"""
        from src.app.services.society.baseline_comparator import build_evaluation_summary_response

        response = build_evaluation_summary_response(
            sim_id="my-unique-sim-id",
            gate_result=self._make_gate_result(),
            baseline_comparison=self._make_baseline_comparison(),
        )

        assert response["simulation_id"] == "my-unique-sim-id"

    def test_live_replay_warning_default_false(self):
        """live_replay_warning のデフォルトは False"""
        from src.app.services.society.baseline_comparator import build_evaluation_summary_response

        response = build_evaluation_summary_response(
            sim_id="sim-x",
            gate_result=self._make_gate_result(),
            baseline_comparison=self._make_baseline_comparison(),
        )

        assert response["live_replay_warning"] is False

    def test_live_replay_warning_true_propagated(self):
        """live_replay_warning=True が正しく反映される"""
        from src.app.services.society.baseline_comparator import build_evaluation_summary_response

        response = build_evaluation_summary_response(
            sim_id="sim-x",
            gate_result=self._make_gate_result(),
            baseline_comparison=self._make_baseline_comparison(),
            live_replay_warning=True,
        )

        assert response["live_replay_warning"] is True


# =============================================================
# 5. CI gate runner E2E テスト
# =============================================================

def _write_gate_fixture(
    tmp_path,
    category: str,
    cases: list[dict],
    filename: str | None = None,
    seed: int = 42,
) -> None:
    """テスト用 gate fixture YAML を tmp_path に書き込む。"""
    data = {
        "preset_id": category,
        "theme_category": category,
        "seed": seed,
        "cases": cases,
    }
    name = filename or f"{category}_gate.yaml"
    (tmp_path / name).write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")


_CASES_PASS = [
    {
        "case_id": f"p{i:03d}", "theme": f"テスト{i}", "survey_source": "src",
        "gate_eligible": True,
        "simulated_distribution": {"賛成": 0.28, "条件付き賛成": 0.24, "中立": 0.22, "条件付き反対": 0.15, "反対": 0.11},
        "actual_distribution":    {"賛成": 0.30, "条件付き賛成": 0.25, "中立": 0.20, "条件付き反対": 0.15, "反対": 0.10},
    }
    for i in range(1, 4)
]

_CASES_FAIL = [
    {
        "case_id": f"f{i:03d}", "theme": f"失敗{i}", "survey_source": "src",
        "gate_eligible": True,
        "simulated_distribution": {"賛成": 0.05, "条件付き賛成": 0.05, "中立": 0.05, "条件付き反対": 0.40, "反対": 0.45},
        "actual_distribution":    {"賛成": 0.45, "条件付き賛成": 0.25, "中立": 0.15, "条件付き反対": 0.10, "反対": 0.05},
    }
    for i in range(1, 4)
]


class TestCIGateRunnerE2E:
    """run_ci_gate_check の E2E テスト"""

    def test_returns_required_fields(self, tmp_path):
        """CI gate check の結果に必須フィールドが含まれる"""
        from src.app.evaluation.gate_runner import run_ci_gate_check

        result = run_ci_gate_check(fixture_dir=str(tmp_path))

        for k in ("overall", "categories", "fixture_count"):
            assert k in result, f"Missing key: {k}"

    def test_empty_dir_returns_inconclusive(self, tmp_path):
        """空のディレクトリでは overall=inconclusive, categories={}"""
        from src.app.evaluation.gate_runner import run_ci_gate_check

        result = run_ci_gate_check(fixture_dir=str(tmp_path))

        assert result["overall"] == "inconclusive"
        assert result["categories"] == {}
        assert result["fixture_count"] == 0

    def test_all_pass_returns_overall_pass(self, tmp_path):
        """全カテゴリ pass → overall が pass"""
        from src.app.evaluation.gate_runner import run_ci_gate_check

        _write_gate_fixture(tmp_path, "economy", _CASES_PASS)

        result = run_ci_gate_check(fixture_dir=str(tmp_path))

        assert result["overall"] == "pass"

    def test_any_fail_returns_overall_fail(self, tmp_path):
        """いずれかのカテゴリが fail → overall が fail"""
        from src.app.evaluation.gate_runner import run_ci_gate_check

        _write_gate_fixture(tmp_path, "security", _CASES_FAIL)

        result = run_ci_gate_check(fixture_dir=str(tmp_path))

        assert result["overall"] == "fail"

    def test_categories_keyed_by_theme_category(self, tmp_path):
        """categories は theme_category をキーとした辞書"""
        from src.app.evaluation.gate_runner import run_ci_gate_check

        _write_gate_fixture(tmp_path, "economy", _CASES_PASS)

        result = run_ci_gate_check(fixture_dir=str(tmp_path))

        assert "economy" in result["categories"]

    def test_fixture_count_matches_yaml_files(self, tmp_path):
        """fixture_count が _gate.yaml ファイル数と一致する"""
        from src.app.evaluation.gate_runner import run_ci_gate_check

        _write_gate_fixture(tmp_path, "economy", _CASES_PASS)
        _write_gate_fixture(tmp_path, "security", _CASES_PASS)

        result = run_ci_gate_check(fixture_dir=str(tmp_path))

        assert result["fixture_count"] == 2

    def test_reproducible_with_same_fixtures(self, tmp_path):
        """同一 fixture で 2 回呼ぶと同一 overall 結果"""
        from src.app.evaluation.gate_runner import run_ci_gate_check

        _write_gate_fixture(tmp_path, "economy", _CASES_PASS)

        r1 = run_ci_gate_check(fixture_dir=str(tmp_path))
        r2 = run_ci_gate_check(fixture_dir=str(tmp_path))

        assert r1["overall"] == r2["overall"]

    def test_mixed_pass_fail_returns_fail(self, tmp_path):
        """pass と fail が混在 → overall は fail"""
        from src.app.evaluation.gate_runner import run_ci_gate_check

        _write_gate_fixture(tmp_path, "economy", _CASES_PASS)
        _write_gate_fixture(tmp_path, "security", _CASES_FAIL)

        result = run_ci_gate_check(fixture_dir=str(tmp_path))

        assert result["overall"] == "fail"

    def test_non_gate_yaml_files_are_ignored(self, tmp_path):
        """_gate.yaml 以外のファイルは無視される"""
        from src.app.evaluation.gate_runner import run_ci_gate_check

        # 無関係な YAML ファイル
        (tmp_path / "config.yaml").write_text("key: value", encoding="utf-8")
        (tmp_path / "README.md").write_text("# readme", encoding="utf-8")

        result = run_ci_gate_check(fixture_dir=str(tmp_path))

        assert result["fixture_count"] == 0
        assert result["overall"] == "inconclusive"


# =============================================================
# 6. rolling backtest / live median 集計
# =============================================================

class TestRollingBacktest:
    """rolling backtest と live median 集計テスト"""

    def test_live_median_single_value(self):
        """単一値の median は自身"""
        from src.app.services.society.baseline_comparator import compute_live_median

        assert compute_live_median([0.10]) == pytest.approx(0.10)

    def test_live_median_odd_count(self):
        """奇数個の median は中央値"""
        from src.app.services.society.baseline_comparator import compute_live_median

        values = [0.10, 0.20, 0.30, 0.40, 0.50]
        assert compute_live_median(values) == pytest.approx(0.30)

    def test_live_median_even_count(self):
        """偶数個の median は中間 2 値の平均"""
        from src.app.services.society.baseline_comparator import compute_live_median

        values = [0.10, 0.20, 0.30, 0.40]
        assert compute_live_median(values) == pytest.approx(0.25)

    def test_live_median_empty_returns_none(self):
        """空リストは None を返す"""
        from src.app.services.society.baseline_comparator import compute_live_median

        assert compute_live_median([]) is None

    def test_relative_improvement_positive(self):
        """baseline_emd > candidate_emd → 正の改善率"""
        from src.app.services.society.baseline_comparator import compute_relative_improvement

        result = compute_relative_improvement(baseline_emd=0.30, candidate_emd=0.15)

        assert result == pytest.approx(0.50)  # 50% 改善

    def test_relative_improvement_zero_when_equal(self):
        """同値 → 改善率 0"""
        from src.app.services.society.baseline_comparator import compute_relative_improvement

        result = compute_relative_improvement(baseline_emd=0.15, candidate_emd=0.15)

        assert result == pytest.approx(0.0)

    def test_relative_improvement_negative_when_worse(self):
        """candidate が baseline より悪い → 負の改善率"""
        from src.app.services.society.baseline_comparator import compute_relative_improvement

        result = compute_relative_improvement(baseline_emd=0.15, candidate_emd=0.30)

        assert result == pytest.approx(-1.0)

    def test_relative_improvement_zero_baseline_returns_none(self):
        """baseline_emd が 0 → None（ゼロ除算回避）"""
        from src.app.services.society.baseline_comparator import compute_relative_improvement

        assert compute_relative_improvement(baseline_emd=0.0, candidate_emd=0.10) is None

    def test_relative_improvement_none_baseline_returns_none(self):
        """baseline_emd が None → None"""
        from src.app.services.society.baseline_comparator import compute_relative_improvement

        assert compute_relative_improvement(baseline_emd=None, candidate_emd=0.10) is None

    def test_rolling_summary_structure(self):
        """build_rolling_backtest_summary が正しい構造を返す"""
        from src.app.services.society.baseline_comparator import build_rolling_backtest_summary

        live_runs = [
            {"avg_emd": 0.10, "gate": "pass"},
            {"avg_emd": 0.12, "gate": "pass"},
            {"avg_emd": 0.08, "gate": "pass"},
        ]
        result = build_rolling_backtest_summary(live_runs)

        for k in ("median_emd", "pass_rate", "run_count"):
            assert k in result, f"Missing key: {k}"

    def test_rolling_summary_pass_rate(self):
        """pass が 2/3 の場合、pass_rate ≈ 0.667"""
        from src.app.services.society.baseline_comparator import build_rolling_backtest_summary

        live_runs = [
            {"avg_emd": 0.10, "gate": "pass"},
            {"avg_emd": 0.12, "gate": "pass"},
            {"avg_emd": 0.20, "gate": "fail"},
        ]
        result = build_rolling_backtest_summary(live_runs)

        assert result["pass_rate"] == pytest.approx(2 / 3)

    def test_rolling_summary_median_emd(self):
        """median_emd が正しく計算される"""
        from src.app.services.society.baseline_comparator import build_rolling_backtest_summary

        live_runs = [
            {"avg_emd": 0.10, "gate": "pass"},
            {"avg_emd": 0.20, "gate": "fail"},
            {"avg_emd": 0.30, "gate": "fail"},
        ]
        result = build_rolling_backtest_summary(live_runs)

        assert result["median_emd"] == pytest.approx(0.20)

    def test_rolling_summary_empty_list(self):
        """空リストは run_count=0, median_emd=None, pass_rate=0"""
        from src.app.services.society.baseline_comparator import build_rolling_backtest_summary

        result = build_rolling_backtest_summary([])

        assert result["run_count"] == 0
        assert result["median_emd"] is None
        assert result["pass_rate"] == pytest.approx(0.0)

    def test_rolling_summary_run_count(self):
        """run_count が live_runs の件数と一致する"""
        from src.app.services.society.baseline_comparator import build_rolling_backtest_summary

        live_runs = [{"avg_emd": 0.10, "gate": "pass"}] * 5
        result = build_rolling_backtest_summary(live_runs)

        assert result["run_count"] == 5
