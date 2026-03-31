"""統計的推論モジュールのテスト (TDD RED phase)

テスト対象: backend/src/app/services/society/statistical_inference.py
"""

import math
import pytest
from src.app.services.society.statistical_inference import (
    effective_sample_size,
    margin_of_error,
    weighted_stance_distribution,
    bootstrap_confidence_intervals,
    compute_poststratification_weights,
)


# ---------------------------------------------------------------------------
# effective_sample_size
# ---------------------------------------------------------------------------


class TestEffectiveSampleSize:
    def test_effective_sample_size_uniform_weights(self):
        """全員ウェイト1.0 のとき n_eff = n"""
        n = 10
        weights = [1.0] * n
        result = effective_sample_size(weights)
        assert math.isclose(result, n, rel_tol=1e-9)

    def test_effective_sample_size_skewed_weights(self):
        """偏ったウェイトのとき n_eff < n"""
        # 1人だけウェイトが大きく、残りは非常に小さい
        weights = [100.0] + [0.01] * 99
        n_eff = effective_sample_size(weights)
        assert n_eff < len(weights)

    def test_effective_sample_size_single_element(self):
        """要素が1つのとき n_eff = 1"""
        result = effective_sample_size([5.0])
        assert math.isclose(result, 1.0, rel_tol=1e-9)

    def test_effective_sample_size_two_equal(self):
        """要素が2つ均等なとき n_eff = 2"""
        result = effective_sample_size([3.0, 3.0])
        assert math.isclose(result, 2.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# margin_of_error
# ---------------------------------------------------------------------------


class TestMarginOfError:
    def test_margin_of_error_known_values(self):
        """p=0.5, n=100 のとき MoE ≈ 0.098"""
        moe = margin_of_error(proportion=0.5, n_eff=100.0)
        assert math.isclose(moe, 0.098, abs_tol=0.001)

    def test_margin_of_error_custom_z(self):
        """z=1.645 (90% CI) のとき MoE が小さくなる"""
        moe_95 = margin_of_error(proportion=0.5, n_eff=100.0, z=1.96)
        moe_90 = margin_of_error(proportion=0.5, n_eff=100.0, z=1.645)
        assert moe_90 < moe_95

    def test_margin_of_error_larger_n_shrinks(self):
        """サンプルサイズが大きいほど MoE が小さい"""
        moe_small = margin_of_error(proportion=0.5, n_eff=100.0)
        moe_large = margin_of_error(proportion=0.5, n_eff=400.0)
        assert moe_large < moe_small

    def test_margin_of_error_extreme_proportion(self):
        """p=0 or p=1 のとき MoE=0"""
        assert math.isclose(margin_of_error(proportion=0.0, n_eff=100.0), 0.0, abs_tol=1e-9)
        assert math.isclose(margin_of_error(proportion=1.0, n_eff=100.0), 0.0, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# weighted_stance_distribution
# ---------------------------------------------------------------------------


class TestWeightedStanceDistribution:
    def _make_responses(self, stances):
        return [{"stance": s, "confidence": 0.7} for s in stances]

    def test_weighted_stance_distribution_sums_to_one(self):
        """重み付き分布の合計が 1.0"""
        responses = self._make_responses(["賛成", "反対", "中立", "賛成"])
        weights = [1.0, 1.0, 1.0, 1.0]
        dist = weighted_stance_distribution(responses, weights)
        total = sum(dist.values())
        assert math.isclose(total, 1.0, rel_tol=1e-9)

    def test_weighted_stance_matches_manual_calculation(self):
        """手計算との一致: 賛成×2 (w=2), 反対×1 (w=1) → 賛成=4/5, 反対=1/5"""
        responses = [
            {"stance": "賛成", "confidence": 0.9},
            {"stance": "賛成", "confidence": 0.8},
            {"stance": "反対", "confidence": 0.6},
        ]
        weights = [2.0, 2.0, 1.0]
        dist = weighted_stance_distribution(responses, weights)
        assert math.isclose(dist.get("賛成", 0.0), 4.0 / 5.0, rel_tol=1e-6)
        assert math.isclose(dist.get("反対", 0.0), 1.0 / 5.0, rel_tol=1e-6)

    def test_weighted_stance_empty_responses(self):
        """空のレスポンスでは空辞書を返す"""
        dist = weighted_stance_distribution([], [])
        assert dist == {}

    def test_weighted_stance_all_same_stance(self):
        """全員同じスタンスのとき その値が 1.0"""
        responses = self._make_responses(["賛成"] * 5)
        weights = [1.0] * 5
        dist = weighted_stance_distribution(responses, weights)
        assert math.isclose(dist.get("賛成", 0.0), 1.0, rel_tol=1e-9)

    def test_weighted_stance_five_valid_stances(self):
        """5種類全てのスタンスが正しく計上される"""
        stances = ["賛成", "反対", "条件付き賛成", "条件付き反対", "中立"]
        responses = [{"stance": s, "confidence": 0.5} for s in stances]
        weights = [1.0] * 5
        dist = weighted_stance_distribution(responses, weights)
        assert math.isclose(sum(dist.values()), 1.0, rel_tol=1e-9)
        for stance in stances:
            assert stance in dist


# ---------------------------------------------------------------------------
# bootstrap_confidence_intervals
# ---------------------------------------------------------------------------


class TestBootstrapConfidenceIntervals:
    def _responses_and_weights(self, n=50, seed=42):
        import random
        random.seed(seed)
        stances = ["賛成", "反対", "中立", "条件付き賛成", "条件付き反対"]
        responses = [
            {"stance": random.choice(stances), "confidence": 0.7}
            for _ in range(n)
        ]
        weights = [1.0] * n
        return responses, weights

    def test_bootstrap_ci_contains_point_estimate(self):
        """点推定値が 95% CI に含まれる"""
        responses, weights = self._responses_and_weights(n=50)
        cis = bootstrap_confidence_intervals(responses, weights, n_bootstrap=200, ci=0.95)

        # 点推定 = 単純な weighted_stance_distribution の値
        point_dist = weighted_stance_distribution(responses, weights)

        for stance, (lo, hi) in cis.items():
            point = point_dist.get(stance, 0.0)
            assert lo <= point <= hi, (
                f"stance={stance}: point={point:.4f} not in CI [{lo:.4f}, {hi:.4f}]"
            )

    def test_bootstrap_ci_width_shrinks_with_sample_size(self):
        """サンプルサイズが増えると CI 幅が縮小する"""
        import random
        random.seed(0)

        stances = ["賛成", "反対", "中立"]

        def make_data(n):
            resp = [{"stance": random.choice(stances), "confidence": 0.7} for _ in range(n)]
            wts = [1.0] * n
            return resp, wts

        resp_small, wts_small = make_data(20)
        resp_large, wts_large = make_data(200)

        ci_small = bootstrap_confidence_intervals(resp_small, wts_small, n_bootstrap=300, ci=0.95)
        ci_large = bootstrap_confidence_intervals(resp_large, wts_large, n_bootstrap=300, ci=0.95)

        # 少なくとも 1 つのスタンスでCI幅が縮小していることを確認
        common_stances = set(ci_small.keys()) & set(ci_large.keys())
        assert len(common_stances) > 0

        width_small = sum(hi - lo for lo, hi in ci_small.values()) / len(ci_small)
        width_large = sum(hi - lo for lo, hi in ci_large.values()) / len(ci_large)
        assert width_large < width_small

    def test_bootstrap_ci_bounds_valid(self):
        """CI の下限 <= 上限、かつ [0, 1] の範囲内"""
        responses, weights = self._responses_and_weights(n=40)
        cis = bootstrap_confidence_intervals(responses, weights, n_bootstrap=100, ci=0.95)
        for stance, (lo, hi) in cis.items():
            assert 0.0 <= lo <= hi <= 1.0, f"Invalid CI for {stance}: [{lo}, {hi}]"

    def test_bootstrap_ci_empty_responses(self):
        """空のレスポンスでは空辞書を返す"""
        cis = bootstrap_confidence_intervals([], [], n_bootstrap=100, ci=0.95)
        assert cis == {}


# ---------------------------------------------------------------------------
# compute_poststratification_weights
# ---------------------------------------------------------------------------


class TestComputePoststratificationWeights:
    def _make_agents(self, age_regions):
        """(age_int, region) のリストから agents を生成"""
        agents = []
        for age, region in age_regions:
            bracket = (
                "18-29" if age < 30 else
                "30-49" if age < 50 else
                "50-69" if age < 70 else
                "70+"
            )
            agents.append({
                "demographics": {
                    "age": age,
                    "age_bracket": bracket,
                    "region": region,
                    "gender": "male",
                    "income_bracket": "middle",
                }
            })
        return agents

    def _make_agents_without_age_bracket(self, age_regions):
        """production 形式に合わせて age_bracket を持たない agents を生成"""
        return [
            {
                "demographics": {
                    "age": age,
                    "region": region,
                    "gender": "male",
                    "income_bracket": "middle",
                }
            }
            for age, region in age_regions
        ]

    def _make_responses(self, n):
        return [{"stance": "中立", "confidence": 0.5} for _ in range(n)]

    def _target_marginals(self):
        return {
            "age_bracket": {
                "18-29": 0.15,
                "30-49": 0.35,
                "50-69": 0.30,
                "70+": 0.20,
            },
            "region": {
                "関東": 0.35,
                "関西": 0.18,
                "中部": 0.15,
                "九州": 0.10,
                "その他": 0.22,
            },
            "gender": {
                "male": 0.485,
                "female": 0.510,
                "other": 0.005,
            },
        }

    def test_poststratification_corrects_overrepresentation(self):
        """関東が過剰代表のとき、関東エージェントのウェイトが下がる"""
        # 関東を意図的に過剰代表させる（60% 関東）
        agents = self._make_agents(
            [(25, "関東")] * 6 + [(35, "関西")] * 2 + [(55, "中部")] * 2
        )
        responses = self._make_responses(10)
        target = self._target_marginals()

        weights = compute_poststratification_weights(agents, responses, target, cap=5.0)

        assert len(weights) == 10

        kantou_weights = [weights[i] for i, a in enumerate(agents) if a["demographics"]["region"] == "関東"]
        other_weights = [weights[i] for i, a in enumerate(agents) if a["demographics"]["region"] != "関東"]

        avg_kantou = sum(kantou_weights) / len(kantou_weights)
        avg_other = sum(other_weights) / len(other_weights)

        # 関東が過剰代表 → 関東の平均ウェイトは他より小さいはず
        assert avg_kantou < avg_other

    def test_poststratification_derives_age_bracket_from_age(self):
        """age_bracket が無くても age から年齢帯補正が効くこと。"""
        agents = self._make_agents_without_age_bracket(
            [(25, "関東")] * 6 + [(35, "関西")] * 2 + [(55, "中部")] * 2
        )
        responses = self._make_responses(10)
        target = self._target_marginals()

        weights = compute_poststratification_weights(agents, responses, target, cap=5.0)

        young_weights = [
            weights[i] for i, a in enumerate(agents)
            if a["demographics"]["age"] < 30
        ]
        older_weights = [
            weights[i] for i, a in enumerate(agents)
            if a["demographics"]["age"] >= 30
        ]

        assert len(young_weights) == 6
        assert len(older_weights) == 4
        assert sum(young_weights) / len(young_weights) < sum(older_weights) / len(older_weights)

    def test_poststratification_weight_cap(self):
        """cap=5.0 のとき、いかなるウェイトも 5.0 を超えない"""
        agents = self._make_agents(
            [(75, "その他")] * 1 +  # 70+ は 20% が目標だが 1/10 = 10% → ウェイト高い
            [(25, "関東")] * 9
        )
        responses = self._make_responses(10)
        target = self._target_marginals()

        weights = compute_poststratification_weights(agents, responses, target, cap=5.0)

        assert all(w <= 5.0 for w in weights), f"Some weights exceed cap: {weights}"

    def test_poststratification_weights_positive(self):
        """全ウェイトが正の値"""
        agents = self._make_agents(
            [(20, "関東"), (35, "関西"), (55, "中部"), (70, "九州"), (28, "その他")]
        )
        responses = self._make_responses(5)
        target = self._target_marginals()

        weights = compute_poststratification_weights(agents, responses, target, cap=5.0)

        assert all(w > 0 for w in weights), f"Some weights are non-positive: {weights}"

    def test_poststratification_returns_correct_length(self):
        """返り値のリスト長がエージェント数と一致する"""
        n = 8
        agents = self._make_agents(
            [(25, "関東"), (35, "関西"), (55, "中部"), (70, "九州"),
             (28, "関東"), (40, "関東"), (60, "関西"), (22, "その他")]
        )
        responses = self._make_responses(n)
        target = self._target_marginals()

        weights = compute_poststratification_weights(agents, responses, target, cap=5.0)

        assert len(weights) == n

    def test_poststratification_mean_one_after_cap(self):
        """cap 適用後もウェイトの平均が ≈ 1.0 であること。

        1人だけ稀少カテゴリ（70+ & その他 & other）で cap=2.0 とすると、
        raking で高ウェイトが割り当てられた後 cap でクリップされる。
        再正規化がなければ mean ≠ 1.0 になる。
        """
        agents = [
            {"demographics": {"age": 75, "age_bracket": "70+", "region": "その他", "gender": "other"}},
        ] + [
            {"demographics": {"age": 25, "age_bracket": "18-29", "region": "関東", "gender": "male"}}
            for _ in range(19)
        ]
        responses = self._make_responses(20)
        target = {
            "age_bracket": {"18-29": 0.13, "30-49": 0.30, "50-69": 0.31, "70+": 0.26},
            "region": {"関東": 0.35, "その他": 0.65},
            "gender": {"male": 0.485, "other": 0.515},
        }

        weights = compute_poststratification_weights(agents, responses, target, cap=2.0)

        mean_w = sum(weights) / len(weights)
        assert math.isclose(mean_w, 1.0, abs_tol=0.05), (
            f"Mean weight after cap should be ≈ 1.0, got {mean_w:.4f}"
        )
