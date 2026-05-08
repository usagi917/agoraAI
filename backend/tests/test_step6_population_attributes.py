"""Step 6: 母集団属性追加 + 代表性補正 のテスト

TDD RED フェーズ: 実装前に失敗することを確認する。
"""

import random

import pytest

from src.app.services.society.population_generator import (
    _assign_primary_clusters,
    _derive_employment_status,
    _derive_household_type,
    _generate_demographics,
)
from src.app.services.society.statistical_inference import attach_population_weights


# ---------------------------------------------------------------------------
# テスト 1: employment_status が age/occupation から正しく導出される
# ---------------------------------------------------------------------------


class TestEmploymentStatus:
    """employment_status が age/occupation から正しく導出されるテスト"""

    def test_student_occupation_yields_student(self):
        assert _derive_employment_status(age=20, occupation="学生") == "student"

    def test_retired_occupation_yields_retired(self):
        assert _derive_employment_status(age=68, occupation="退職者") == "retired"

    def test_homemaker_occupation_yields_homemaker(self):
        assert _derive_employment_status(age=40, occupation="主婦/主夫") == "homemaker"

    def test_part_time_occupation_yields_part_time(self):
        assert _derive_employment_status(age=30, occupation="パート/アルバイト") == "part_time"

    def test_self_employed_occupations(self):
        for occ in ["自営業", "フリーランス", "経営者"]:
            assert _derive_employment_status(age=35, occupation=occ) == "self_employed", occ

    def test_regular_worker_yields_employed(self):
        for occ in ["会社員", "公務員", "エンジニア", "教師", "医師"]:
            assert _derive_employment_status(age=35, occupation=occ) == "employed", occ

    def test_demographics_includes_employment_status(self):
        """生成された demographics に employment_status が含まれること"""
        random.seed(42)
        demo = _generate_demographics({})
        assert "employment_status" in demo
        assert demo["employment_status"] in {
            "employed", "part_time", "self_employed",
            "homemaker", "student", "retired",
        }

    def test_employment_status_consistent_with_occupation(self):
        """employment_status は occupation と矛盾しないこと（200件サンプル）"""
        random.seed(42)
        _STRICT_MAP = {
            "学生": "student",
            "退職者": "retired",
            "主婦/主夫": "homemaker",
            "パート/アルバイト": "part_time",
            "自営業": "self_employed",
            "フリーランス": "self_employed",
            "経営者": "self_employed",
        }
        for _ in range(200):
            demo = _generate_demographics({})
            occ = demo["occupation"]
            status = demo["employment_status"]
            if occ in _STRICT_MAP:
                assert status == _STRICT_MAP[occ], f"{occ} → {status}"
            else:
                assert status == "employed", f"{occ} → {status}"


# ---------------------------------------------------------------------------
# テスト 2: household_type が確率的に生成される
# ---------------------------------------------------------------------------


class TestHouseholdType:
    """household_type が確率的に生成されるテスト"""

    VALID_TYPES = {
        "single", "couple", "couple_with_children",
        "single_parent", "with_parents", "extended_family",
    }

    def test_returns_valid_category(self):
        random.seed(42)
        for age in [20, 35, 50, 70]:
            ht = _derive_household_type(age=age)
            assert ht in self.VALID_TYPES, f"age={age} → {ht}"

    def test_demographics_includes_household_type(self):
        random.seed(42)
        demo = _generate_demographics({})
        assert "household_type" in demo
        assert demo["household_type"] in self.VALID_TYPES

    def test_young_adults_more_likely_single_or_with_parents(self):
        """20代は single + with_parents が 40% 以上"""
        random.seed(42)
        results = [_derive_household_type(age=22) for _ in range(500)]
        ratio = sum(1 for r in results if r in ("single", "with_parents")) / len(results)
        assert ratio >= 0.40, f"20代の single/with_parents 比率 {ratio:.2f} が低すぎる"

    def test_middle_age_more_likely_couple_with_children(self):
        """40代は couple_with_children が 25% 以上"""
        random.seed(42)
        results = [_derive_household_type(age=42) for _ in range(500)]
        ratio = sum(1 for r in results if r == "couple_with_children") / len(results)
        assert ratio >= 0.25, f"40代の couple_with_children 比率 {ratio:.2f} が低すぎる"

    def test_elderly_more_likely_couple_or_single(self):
        """70代以上は couple + single が 35% 以上"""
        random.seed(42)
        results = [_derive_household_type(age=73) for _ in range(500)]
        ratio = sum(1 for r in results if r in ("couple", "single")) / len(results)
        assert ratio >= 0.35, f"70代以上の couple/single 比率 {ratio:.2f} が低すぎる"

    def test_distribution_covers_at_least_three_types(self):
        """全年齢範囲で少なくとも 3 種類の household_type が出現する"""
        random.seed(42)
        results = {_derive_household_type(age=random.randint(18, 80)) for _ in range(200)}
        assert len(results) >= 3, f"出現した型: {results}"


# ---------------------------------------------------------------------------
# テスト 3: attach_population_weights() の IPF 重み正当性
# ---------------------------------------------------------------------------


class TestAttachPopulationWeights:
    """attach_population_weights() の IPF 重み正当性テスト"""

    # census 分布を使うと 70+ が目標と同程度（約25%）サンプリングされ IPF が収束しやすい
    _CENSUS_POP_CFG = {"demographics": {"age": {"distribution": "census", "min": 18, "max": 85}}}

    def _make_agents(self, n: int, seed: int = 42) -> list[dict]:
        random.seed(seed)
        return [{"demographics": _generate_demographics(self._CENSUS_POP_CFG)} for _ in range(n)]

    def test_returns_weight_per_agent(self):
        agents = self._make_agents(100)
        weights = attach_population_weights(agents)
        assert len(weights) == len(agents)

    def test_all_weights_are_positive(self):
        agents = self._make_agents(100)
        weights = attach_population_weights(agents)
        assert all(w > 0 for w in weights), "ゼロ以下のウェイトが存在する"

    def test_weights_mean_approximately_one(self):
        agents = self._make_agents(200)
        weights = attach_population_weights(agents)
        mean_w = sum(weights) / len(weights)
        assert abs(mean_w - 1.0) < 0.10, f"ウェイト平均 {mean_w:.3f} が 1.0 から乖離"

    def test_weighted_age_bracket_near_target(self):
        """ウェイト付き age_bracket 分布がターゲットに ±0.10 以内で一致"""
        from src.app.services.society.age_utils import age_bracket_4
        from src.app.services.society.statistical_inference import load_target_marginals

        agents = self._make_agents(500)
        weights = attach_population_weights(agents)
        target = load_target_marginals()["age_bracket"]

        total_w = sum(weights)
        bracket_w: dict[str, float] = {}
        for agent, w in zip(agents, weights):
            bracket = age_bracket_4(agent["demographics"]["age"])
            bracket_w[bracket] = bracket_w.get(bracket, 0.0) + w / total_w

        for bracket, target_prop in target.items():
            actual = bracket_w.get(bracket, 0.0)
            assert abs(actual - target_prop) < 0.10, (
                f"bracket {bracket}: actual={actual:.3f}, target={target_prop:.3f}"
            )

    def test_cap_limits_weights(self):
        agents = self._make_agents(100)
        cap = 4.0
        weights = attach_population_weights(agents, cap=cap)
        assert all(w <= cap + 1e-9 for w in weights)

    def test_include_employment_changes_weights(self):
        """include_employment=True/False でウェイトが変化すること"""
        agents = self._make_agents(200)
        w_no_emp = attach_population_weights(agents, include_employment=False)
        w_with_emp = attach_population_weights(agents, include_employment=True)
        total_diff = sum(abs(a - b) for a, b in zip(w_no_emp, w_with_emp))
        assert total_diff > 0.0, "employment_status を加えてもウェイトが変化しない"


# ---------------------------------------------------------------------------
# テスト 4: primary cluster の割当
# ---------------------------------------------------------------------------


class TestPrimaryClusterAssignment:
    """primary cluster（家庭・職場/学校・地域）の割当テスト"""

    def _make_agent(self, age: int, occupation: str, employment_status: str) -> dict:
        return {
            "demographics": {
                "age": age,
                "occupation": occupation,
                "employment_status": employment_status,
                "region": "関東（都市部）",
            }
        }

    def test_returns_same_length_as_input(self):
        random.seed(42)
        agents = [{"demographics": _generate_demographics({})} for _ in range(50)]
        result = _assign_primary_clusters(agents)
        assert len(result) == len(agents)

    def test_all_agents_get_primary_cluster_key(self):
        random.seed(42)
        agents = [{"demographics": _generate_demographics({})} for _ in range(30)]
        result = _assign_primary_clusters(agents)
        for item in result:
            assert "primary_cluster" in item

    def test_primary_cluster_is_valid_value(self):
        random.seed(42)
        agents = [{"demographics": _generate_demographics({})} for _ in range(50)]
        result = _assign_primary_clusters(agents)
        valid = {"home", "workplace", "school", "neighborhood"}
        for item in result:
            assert item["primary_cluster"] in valid, item["primary_cluster"]

    def test_student_assigned_to_school(self):
        agent = self._make_agent(20, "学生", "student")
        result = _assign_primary_clusters([agent])
        assert result[0]["primary_cluster"] == "school"

    def test_employed_assigned_to_workplace(self):
        agent = self._make_agent(35, "会社員", "employed")
        result = _assign_primary_clusters([agent])
        assert result[0]["primary_cluster"] == "workplace"

    def test_self_employed_assigned_to_workplace(self):
        agent = self._make_agent(40, "自営業", "self_employed")
        result = _assign_primary_clusters([agent])
        assert result[0]["primary_cluster"] == "workplace"

    def test_homemaker_assigned_to_home(self):
        agent = self._make_agent(38, "主婦/主夫", "homemaker")
        result = _assign_primary_clusters([agent])
        assert result[0]["primary_cluster"] == "home"

    def test_retired_assigned_to_neighborhood(self):
        agent = self._make_agent(70, "退職者", "retired")
        result = _assign_primary_clusters([agent])
        assert result[0]["primary_cluster"] == "neighborhood"

    def test_part_time_assigned_to_workplace(self):
        agent = self._make_agent(25, "パート/アルバイト", "part_time")
        result = _assign_primary_clusters([agent])
        assert result[0]["primary_cluster"] == "workplace"
