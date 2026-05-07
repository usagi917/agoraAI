"""Step 5: deterministic gate runner テスト

TDD RED フェーズ:
- 同一 fixture + 同一 seed → 同一結果の再現性テスト
- fixture 欠損時のエラーハンドリングテスト
- gate 結果と live 実行の乖離 warning テスト
"""

from __future__ import annotations

import warnings

import pytest
import yaml

from src.app.evaluation.gate_runner import (
    GateRunnerResult,
    MAX_LIVE_REPLAY_GAP,
    check_live_replay_gap,
    load_gate_fixture,
    run_deterministic_gate,
)

# テスト用スタンス分布（EMD ≈ 0.07、閾値以下）
_SIM_PASS = {
    "賛成": 0.28,
    "条件付き賛成": 0.24,
    "中立": 0.22,
    "条件付き反対": 0.15,
    "反対": 0.11,
}
_ACT_PASS = {
    "賛成": 0.30,
    "条件付き賛成": 0.25,
    "中立": 0.20,
    "条件付き反対": 0.15,
    "反対": 0.10,
}

# テスト用スタンス分布（EMD ≈ 2.0、閾値超え）
_SIM_FAIL = {
    "賛成": 0.05,
    "条件付き賛成": 0.05,
    "中立": 0.05,
    "条件付き反対": 0.40,
    "反対": 0.45,
}
_ACT_FAIL = {
    "賛成": 0.45,
    "条件付き賛成": 0.25,
    "中立": 0.15,
    "条件付き反対": 0.10,
    "反対": 0.05,
}


def _write_fixture(
    tmp_path,
    cases: list,
    theme_category: str = "economy",
    seed: int = 42,
):
    """テスト用 gate fixture YAML を作成するヘルパー。"""
    data = {
        "preset_id": theme_category,
        "theme_category": theme_category,
        "seed": seed,
        "cases": cases,
    }
    path = tmp_path / f"{theme_category}_gate.yaml"
    path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
    return path


def _make_passing_cases(n: int = 2) -> list[dict]:
    """pass 判定を期待できる cases を n 件生成する。"""
    return [
        {
            "case_id": f"t{i:03d}",
            "theme": f"テストテーマ{i}",
            "survey_source": f"テスト調査ソース-{i}",
            "gate_eligible": True,
            "simulated_distribution": dict(_SIM_PASS),
            "actual_distribution": dict(_ACT_PASS),
        }
        for i in range(1, n + 1)
    ]


def _make_failing_cases(n: int = 3) -> list[dict]:
    """fail 判定を期待できる cases を n 件生成する。"""
    return [
        {
            "case_id": f"fail-{i:03d}",
            "theme": f"失敗テストテーマ{i}",
            "survey_source": f"失敗調査ソース-{i}",
            "gate_eligible": True,
            "simulated_distribution": dict(_SIM_FAIL),
            "actual_distribution": dict(_ACT_FAIL),
        }
        for i in range(1, n + 1)
    ]


# =============================================
# 再現性テスト
# =============================================


class TestGateRunnerReproducibility:
    """同一 fixture + 同一 seed → 同一結果の再現性テスト"""

    def test_same_fixture_same_seed_returns_same_gate(self, tmp_path):
        """同一 fixture を seed=42 で 2 回呼び出すと同一の gate 判定が返る"""
        path = _write_fixture(tmp_path, _make_passing_cases(3))

        result1 = run_deterministic_gate(path, seed=42)
        result2 = run_deterministic_gate(path, seed=42)

        assert result1["gate"] == result2["gate"]

    def test_same_fixture_same_seed_returns_same_metrics(self, tmp_path):
        """同一 fixture を seed=42 で 2 回呼び出すと avg_emd/jsd/brier が一致する"""
        path = _write_fixture(tmp_path, _make_passing_cases(3))

        result1 = run_deterministic_gate(path, seed=42)
        result2 = run_deterministic_gate(path, seed=42)

        assert result1["avg_emd"] == result2["avg_emd"]
        assert result1["avg_jsd"] == result2["avg_jsd"]
        assert result1["avg_brier"] == result2["avg_brier"]

    def test_different_seeds_return_same_result(self, tmp_path):
        """fixture ベースの計算は seed に依存しないため、seed 違いでも同一結果"""
        path = _write_fixture(tmp_path, _make_passing_cases(3))

        result_s1 = run_deterministic_gate(path, seed=1)
        result_s99 = run_deterministic_gate(path, seed=99)

        assert result_s1["gate"] == result_s99["gate"]
        assert result_s1["avg_emd"] == result_s99["avg_emd"]

    def test_seed_is_stored_in_result(self, tmp_path):
        """実行時に渡した seed が結果の seed フィールドに格納される"""
        path = _write_fixture(tmp_path, _make_passing_cases(2))

        result = run_deterministic_gate(path, seed=42)

        assert result["seed"] == 42

    def test_result_structure_contains_required_fields(self, tmp_path):
        """GateRunnerResult に必須フィールドが全て含まれる"""
        path = _write_fixture(tmp_path, _make_passing_cases(2))

        result = run_deterministic_gate(path, seed=42)

        required_keys = (
            "gate",
            "theme_category",
            "avg_emd",
            "avg_jsd",
            "avg_brier",
            "case_results",
            "total_count",
            "validated_count",
            "gate_eligible_count",
            "seed",
            "live_replay_warning",
        )
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

    def test_passing_fixture_returns_pass(self, tmp_path):
        """EMD/JSD/Brier が閾値未満の fixture は gate=pass を返す"""
        path = _write_fixture(tmp_path, _make_passing_cases(3))

        result = run_deterministic_gate(path, seed=42)

        assert result["gate"] == "pass"

    def test_failing_fixture_returns_fail(self, tmp_path):
        """EMD が閾値以上の fixture は gate=fail を返す"""
        path = _write_fixture(tmp_path, _make_failing_cases(3))

        result = run_deterministic_gate(path, seed=42)

        assert result["gate"] == "fail"
        assert result["avg_emd"] is not None
        assert result["avg_emd"] >= 0.15

    def test_case_results_list_length_matches_cases(self, tmp_path):
        """case_results の件数が fixture の cases 件数と一致する"""
        n = 3
        path = _write_fixture(tmp_path, _make_passing_cases(n))

        result = run_deterministic_gate(path, seed=42)

        assert len(result["case_results"]) == n

    def test_case_results_contain_per_case_metrics(self, tmp_path):
        """各 case_result に emd/jsd/brier_score が含まれる"""
        path = _write_fixture(tmp_path, _make_passing_cases(2))

        result = run_deterministic_gate(path, seed=42)

        for case_result in result["case_results"]:
            assert case_result["emd"] is not None
            assert case_result["jsd"] is not None
            assert case_result["brier_score"] is not None

    def test_theme_category_is_propagated(self, tmp_path):
        """fixture の theme_category が結果に反映される"""
        path = _write_fixture(tmp_path, _make_passing_cases(2), theme_category="security")

        result = run_deterministic_gate(path, seed=42)

        assert result["theme_category"] == "security"


# =============================================
# fixture 欠損時のエラーハンドリングテスト
# =============================================


class TestGateRunnerFixtureMissing:
    """fixture 欠損時のエラーハンドリングテスト"""

    def test_missing_fixture_raises_file_not_found_error(self):
        """存在しない fixture パスを指定すると FileNotFoundError が発生する"""
        with pytest.raises(FileNotFoundError):
            run_deterministic_gate("/nonexistent/path/no_such_fixture.yaml")

    def test_empty_cases_returns_inconclusive(self, tmp_path):
        """cases が空リストの fixture は inconclusive を返す"""
        path = _write_fixture(tmp_path, [])

        result = run_deterministic_gate(path, seed=42)

        assert result["gate"] == "inconclusive"

    def test_insufficient_cases_returns_inconclusive(self, tmp_path):
        """MIN_VALIDATED_PER_CATEGORY (2) 未満の cases → inconclusive"""
        path = _write_fixture(tmp_path, _make_passing_cases(1))

        result = run_deterministic_gate(path, seed=42)

        assert result["gate"] == "inconclusive"

    def test_load_gate_fixture_returns_dict(self, tmp_path):
        """load_gate_fixture が辞書を返す"""
        path = _write_fixture(tmp_path, _make_passing_cases(2))

        data = load_gate_fixture(path)

        assert isinstance(data, dict)
        assert "cases" in data
        assert "theme_category" in data

    def test_load_gate_fixture_missing_raises_file_not_found(self):
        """load_gate_fixture が存在しないパスで FileNotFoundError を発生する"""
        with pytest.raises(FileNotFoundError):
            load_gate_fixture("/nonexistent/path.yaml")

    def test_missing_actual_distribution_makes_report_only(self, tmp_path):
        """actual_distribution がない case は report_only 扱い → validated_count=0 → inconclusive"""
        cases = [
            {
                "case_id": f"no-actual-{i}",
                "theme": f"実績なしテーマ{i}",
                "survey_source": f"src-{i}",
                "gate_eligible": True,
                "simulated_distribution": dict(_SIM_PASS),
                # actual_distribution なし
            }
            for i in range(1, 4)
        ]
        path = _write_fixture(tmp_path, cases)

        result = run_deterministic_gate(path, seed=42)

        assert result["validated_count"] == 0
        assert result["gate"] == "inconclusive"

    def test_case_without_actual_has_none_metrics(self, tmp_path):
        """actual_distribution がない case の emd/jsd/brier_score は None"""
        cases = [
            {
                "case_id": "no-actual",
                "theme": "実績なしテーマ",
                "survey_source": "src-X",
                "gate_eligible": True,
                "simulated_distribution": dict(_SIM_PASS),
            }
        ]
        path = _write_fixture(tmp_path, cases)

        result = run_deterministic_gate(path, seed=42)

        assert len(result["case_results"]) == 1
        cr = result["case_results"][0]
        assert cr["emd"] is None
        assert cr["jsd"] is None
        assert cr["brier_score"] is None

    def test_gate_eligible_false_excluded_from_gate(self, tmp_path):
        """gate_eligible=False のケースはゲート判定から除外される"""
        from src.app.services.society.validation_pipeline import MIN_VALIDATED_PER_CATEGORY

        # gate_eligible=True のみ pass 分布を持つ cases（ちょうど MIN_VALIDATED_PER_CATEGORY 件）
        eligible_cases = [
            {
                "case_id": f"eligible-{i}",
                "theme": f"eligible テーマ{i}",
                "survey_source": f"eligible-src-{i}",
                "gate_eligible": True,
                "simulated_distribution": dict(_SIM_PASS),
                "actual_distribution": dict(_ACT_PASS),
            }
            for i in range(MIN_VALIDATED_PER_CATEGORY)
        ]
        # gate_eligible=False で高 EMD のケース（gate に影響しない）
        ineligible_cases = [
            {
                "case_id": "ineligible-001",
                "theme": "除外テーマ",
                "survey_source": "ineligible-src",
                "gate_eligible": False,
                "simulated_distribution": dict(_SIM_FAIL),
                "actual_distribution": dict(_ACT_FAIL),
            }
        ]
        path = _write_fixture(tmp_path, eligible_cases + ineligible_cases)

        result = run_deterministic_gate(path, seed=42)

        assert result["gate"] == "pass"
        assert result["gate_eligible_count"] == MIN_VALIDATED_PER_CATEGORY


# =============================================
# gate 結果と live 実行の乖離 warning テスト
# =============================================


class TestGateRunnerLiveReplayGap:
    """gate 結果と live 実行の乖離 warning テスト"""

    def test_no_warning_when_gap_within_threshold(self, tmp_path):
        """live replay gap が MAX_LIVE_REPLAY_GAP 以内 → check_live_replay_gap が False を返す"""
        path = _write_fixture(tmp_path, _make_passing_cases(3))
        result = run_deterministic_gate(path, seed=42)

        assert result["avg_emd"] is not None
        # fixture EMD の 50% 以内の乖離（閾値を下回る）
        near_live_emd = result["avg_emd"] + MAX_LIVE_REPLAY_GAP * 0.5

        has_gap = check_live_replay_gap(result, live_avg_emd=near_live_emd)

        assert has_gap is False

    def test_warning_when_gap_exceeds_threshold(self, tmp_path):
        """live replay gap が MAX_LIVE_REPLAY_GAP を超える → check_live_replay_gap が True を返す"""
        path = _write_fixture(tmp_path, _make_passing_cases(3))
        result = run_deterministic_gate(path, seed=42)

        assert result["avg_emd"] is not None
        # fixture EMD の 2 倍以上の乖離（閾値を超える）
        far_live_emd = result["avg_emd"] + MAX_LIVE_REPLAY_GAP * 2.0

        has_gap = check_live_replay_gap(result, live_avg_emd=far_live_emd)

        assert has_gap is True

    def test_warning_emitted_as_runtime_warning(self, tmp_path):
        """乖離が閾値超えの場合 RuntimeWarning が発行される"""
        path = _write_fixture(tmp_path, _make_passing_cases(3))
        result = run_deterministic_gate(path, seed=42)

        assert result["avg_emd"] is not None
        far_live_emd = result["avg_emd"] + 0.10  # 明らかに大きい乖離

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            check_live_replay_gap(result, live_avg_emd=far_live_emd)

        assert any(issubclass(w.category, RuntimeWarning) for w in caught)

    def test_no_warning_when_avg_emd_is_none(self, tmp_path):
        """fixture avg_emd が None（inconclusive 等）の場合は常に False"""
        path = _write_fixture(tmp_path, [])
        result = run_deterministic_gate(path, seed=42)

        # empty cases → avg_emd = None
        has_gap = check_live_replay_gap(result, live_avg_emd=0.10)

        assert has_gap is False

    def test_no_warning_when_live_emd_is_none(self, tmp_path):
        """live_avg_emd が None の場合は常に False"""
        path = _write_fixture(tmp_path, _make_passing_cases(3))
        result = run_deterministic_gate(path, seed=42)

        has_gap = check_live_replay_gap(result, live_avg_emd=None)

        assert has_gap is False

    def test_initial_live_replay_warning_is_false(self, tmp_path):
        """run_deterministic_gate の初期結果は live_replay_warning=False"""
        path = _write_fixture(tmp_path, _make_passing_cases(2))

        result = run_deterministic_gate(path, seed=42)

        assert result["live_replay_warning"] is False

    def test_exact_threshold_is_not_a_warning(self, tmp_path):
        """gap がちょうど threshold と等しい場合は warning なし（> でなく >= で判定しない）"""
        path = _write_fixture(tmp_path, _make_passing_cases(3))
        result = run_deterministic_gate(path, seed=42)

        assert result["avg_emd"] is not None
        exact_gap_live_emd = result["avg_emd"] + MAX_LIVE_REPLAY_GAP

        has_gap = check_live_replay_gap(result, live_avg_emd=exact_gap_live_emd)

        # gap == threshold → warning なし（strict greater-than）
        assert has_gap is False


# =============================================
# 実 fixture ファイルとの統合テスト
# =============================================


class TestGateRunnerWithRealFixtures:
    """tests/fixtures/gate/ の実ファイルを使った統合テスト"""

    @pytest.fixture
    def fixtures_gate_dir(self):
        import os
        return os.path.join(os.path.dirname(__file__), "fixtures", "gate")

    def test_economy_fixture_loads_successfully(self, fixtures_gate_dir):
        """economy_gate.yaml が正常にロードできる"""
        import os
        path = os.path.join(fixtures_gate_dir, "economy_gate.yaml")
        data = load_gate_fixture(path)
        assert data["theme_category"] == "economy"
        assert len(data["cases"]) >= 2

    def test_security_fixture_loads_successfully(self, fixtures_gate_dir):
        """security_gate.yaml が正常にロードできる"""
        import os
        path = os.path.join(fixtures_gate_dir, "security_gate.yaml")
        data = load_gate_fixture(path)
        assert data["theme_category"] == "security"
        assert len(data["cases"]) >= 2

    def test_unknown_theme_category_returns_inconclusive(self, tmp_path):
        """theme_category="unknown" の fixture は gate=inconclusive を返す"""
        path = _write_fixture(tmp_path, _make_passing_cases(3), theme_category="unknown")

        result = run_deterministic_gate(path, seed=42)

        assert result["gate"] == "inconclusive"

    def test_unknown_theme_category_inconclusive_even_with_passing_cases(self, tmp_path):
        """unknown カテゴリは metrics が pass 基準でも inconclusive になる"""
        # 十分な件数の pass ケースを作成
        cases = _make_passing_cases(5)
        path = _write_fixture(tmp_path, cases, theme_category="unknown")

        result = run_deterministic_gate(path, seed=42)

        assert result["gate"] == "inconclusive"
        assert result["theme_category"] == "unknown"

    def test_economy_gate_runs_deterministically(self, fixtures_gate_dir):
        """economy_gate.yaml で run_deterministic_gate が決定論的に動作する"""
        import os
        path = os.path.join(fixtures_gate_dir, "economy_gate.yaml")
        result1 = run_deterministic_gate(path, seed=42)
        result2 = run_deterministic_gate(path, seed=42)
        assert result1["gate"] == result2["gate"]
        assert result1["avg_emd"] == result2["avg_emd"]

    def test_security_gate_runs_deterministically(self, fixtures_gate_dir):
        """security_gate.yaml で run_deterministic_gate が決定論的に動作する"""
        import os
        path = os.path.join(fixtures_gate_dir, "security_gate.yaml")
        result1 = run_deterministic_gate(path, seed=42)
        result2 = run_deterministic_gate(path, seed=42)
        assert result1["gate"] == result2["gate"]
        assert result1["avg_emd"] == result2["avg_emd"]
