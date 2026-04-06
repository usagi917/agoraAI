"""transfer_calibrator モジュールのテスト

LLM→Human バイアス補正: バイアスプロファイル構築、分布補正、不確実性推定
"""

import pytest

from src.app.services.society.transfer_calibrator import (
    StanceBias,
    BiasProfile,
    compute_bias_profile,
    apply_transfer_correction,
    compute_transfer_uncertainty,
)

STANCES = ["賛成", "条件付き賛成", "中立", "条件付き反対", "反対"]


def _make_comparison(
    theme_category: str,
    sim_dist: dict[str, float],
    actual_dist: dict[str, float],
) -> dict:
    """テスト用の比較データを作成"""
    return {
        "theme": "test",
        "theme_category": theme_category,
        "simulated_distribution": sim_dist,
        "actual_distribution": actual_dist,
    }


class TestComputeBiasProfile:
    def test_compute_bias_profile_single_comparison(self):
        """1件の比較データからバイアスプロファイル構築"""
        comparisons = [
            _make_comparison(
                "economy",
                {"賛成": 0.40, "条件付き賛成": 0.20, "中立": 0.15, "条件付き反対": 0.15, "反対": 0.10},
                {"賛成": 0.30, "条件付き賛成": 0.20, "中立": 0.20, "条件付き反対": 0.15, "反対": 0.15},
            )
        ]
        profile = compute_bias_profile(comparisons)
        assert "economy" in profile
        assert "賛成" in profile["economy"]
        # sim - actual = 0.40 - 0.30 = 0.10
        assert abs(profile["economy"]["賛成"]["mean_deviation"] - 0.10) < 0.001

    def test_compute_bias_profile_multiple_comparisons(self):
        """複数件の比較データで平均ズレを算出"""
        comparisons = [
            _make_comparison(
                "economy",
                {"賛成": 0.40, "条件付き賛成": 0.20, "中立": 0.15, "条件付き反対": 0.15, "反対": 0.10},
                {"賛成": 0.30, "条件付き賛成": 0.20, "中立": 0.20, "条件付き反対": 0.15, "反対": 0.15},
            ),
            _make_comparison(
                "economy",
                {"賛成": 0.50, "条件付き賛成": 0.15, "中立": 0.15, "条件付き反対": 0.10, "反対": 0.10},
                {"賛成": 0.35, "条件付き賛成": 0.20, "中立": 0.20, "条件付き反対": 0.15, "反対": 0.10},
            ),
        ]
        profile = compute_bias_profile(comparisons)
        # 賛成の平均ズレ: (0.10 + 0.15) / 2 = 0.125
        assert abs(profile["economy"]["賛成"]["mean_deviation"] - 0.125) < 0.001
        assert profile["economy"]["賛成"]["sample_count"] == 2

    def test_compute_bias_profile_by_category(self):
        """テーマカテゴリ別にプロファイルが分かれる"""
        comparisons = [
            _make_comparison(
                "economy",
                {"賛成": 0.40, "条件付き賛成": 0.20, "中立": 0.15, "条件付き反対": 0.15, "反対": 0.10},
                {"賛成": 0.30, "条件付き賛成": 0.20, "中立": 0.20, "条件付き反対": 0.15, "反対": 0.15},
            ),
            _make_comparison(
                "politics",
                {"賛成": 0.20, "条件付き賛成": 0.30, "中立": 0.20, "条件付き反対": 0.15, "反対": 0.15},
                {"賛成": 0.25, "条件付き賛成": 0.25, "中立": 0.25, "条件付き反対": 0.15, "反対": 0.10},
            ),
        ]
        profile = compute_bias_profile(comparisons)
        assert "economy" in profile
        assert "politics" in profile


class TestApplyTransferCorrection:
    def _build_profile(self, category: str, sample_count: int) -> BiasProfile:
        return {
            category: {
                "賛成": {"mean_deviation": 0.10, "sample_count": sample_count, "std_deviation": 0.02},
                "条件付き賛成": {"mean_deviation": 0.0, "sample_count": sample_count, "std_deviation": 0.01},
                "中立": {"mean_deviation": -0.05, "sample_count": sample_count, "std_deviation": 0.02},
                "条件付き反対": {"mean_deviation": -0.03, "sample_count": sample_count, "std_deviation": 0.01},
                "反対": {"mean_deviation": -0.02, "sample_count": sample_count, "std_deviation": 0.01},
            }
        }

    def test_apply_transfer_correction_shifts_distribution(self):
        """補正が分布をズレの逆方向にシフト"""
        dist = {"賛成": 0.40, "条件付き賛成": 0.20, "中立": 0.15, "条件付き反対": 0.15, "反対": 0.10}
        profile = self._build_profile("economy", 20)
        corrected = apply_transfer_correction(dist, profile, "economy")
        # 賛成は正のバイアスがあるので、補正後は減少
        assert corrected["賛成"] < dist["賛成"]

    def test_apply_transfer_correction_preserves_normalization(self):
        """補正後の分布合計 = 1.0"""
        dist = {"賛成": 0.40, "条件付き賛成": 0.20, "中立": 0.15, "条件付き反対": 0.15, "反対": 0.10}
        profile = self._build_profile("economy", 20)
        corrected = apply_transfer_correction(dist, profile, "economy")
        assert abs(sum(corrected.values()) - 1.0) < 0.001

    def test_apply_transfer_correction_no_negative_probabilities(self):
        """補正後に負の確率が生まれない"""
        dist = {"賛成": 0.05, "条件付き賛成": 0.05, "中立": 0.05, "条件付き反対": 0.05, "反対": 0.80}
        profile = self._build_profile("economy", 20)
        corrected = apply_transfer_correction(dist, profile, "economy")
        for v in corrected.values():
            assert v >= 0

    def test_no_correction_when_insufficient_data(self):
        """sample_count < 閾値 (3) では補正適用しない"""
        dist = {"賛成": 0.40, "条件付き賛成": 0.20, "中立": 0.15, "条件付き反対": 0.15, "反対": 0.10}
        profile = self._build_profile("economy", 2)
        corrected = apply_transfer_correction(dist, profile, "economy", min_samples=3)
        assert corrected == dist

    def test_shrinkage_with_few_samples(self):
        """sample_count=3 では shrinkage が強く、補正がほぼ無い"""
        dist = {"賛成": 0.40, "条件付き賛成": 0.20, "中立": 0.15, "条件付き反対": 0.15, "反対": 0.10}
        profile = self._build_profile("economy", 3)
        corrected = apply_transfer_correction(dist, profile, "economy", min_samples=3)
        # 小さな補正しかかからない
        assert abs(corrected["賛成"] - dist["賛成"]) < 0.05

    def test_full_correction_with_many_samples(self):
        """sample_count=20 では shrinkage が弱く、補正が効く"""
        dist = {"賛成": 0.40, "条件付き賛成": 0.20, "中立": 0.15, "条件付き反対": 0.15, "反対": 0.10}
        profile = self._build_profile("economy", 20)
        corrected = apply_transfer_correction(dist, profile, "economy")
        # 十分な補正がかかる
        assert abs(corrected["賛成"] - dist["賛成"]) > 0.05


class TestComputeTransferUncertainty:
    def _build_profile(self, category: str, std: float) -> BiasProfile:
        return {
            category: {
                stance: {"mean_deviation": 0.05, "sample_count": 10, "std_deviation": std}
                for stance in STANCES
            }
        }

    def test_compute_transfer_uncertainty(self):
        """不確実性の値が0以上で返る"""
        profile = self._build_profile("economy", 0.05)
        result = compute_transfer_uncertainty(profile, "economy")
        assert result >= 0

    def test_compute_transfer_uncertainty_decreases_with_more_data(self):
        """データ増加で不確実性が減少"""
        profile_few = {
            "economy": {
                stance: {"mean_deviation": 0.05, "sample_count": 3, "std_deviation": 0.10}
                for stance in STANCES
            }
        }
        profile_many = {
            "economy": {
                stance: {"mean_deviation": 0.05, "sample_count": 20, "std_deviation": 0.03}
                for stance in STANCES
            }
        }
        uncertainty_few = compute_transfer_uncertainty(profile_few, "economy")
        uncertainty_many = compute_transfer_uncertainty(profile_many, "economy")
        assert uncertainty_few > uncertainty_many


# ---------------------------------------------------------------------------
# Phase E: James-Stein shrinkage + 時間減衰
# ---------------------------------------------------------------------------


class TestTimeDecayBiasProfile:
    """Phase E: 時間減衰付きバイアスプロファイル構築テスト。"""

    def test_recent_data_weighted_more(self):
        """最近のデータがより大きい重みを持つこと。"""
        # 古いデータ: 賛成に大きなバイアス (+0.20)
        old_comp = _make_comparison(
            "economy",
            {"賛成": 0.50, "条件付き賛成": 0.20, "中立": 0.15, "条件付き反対": 0.10, "反対": 0.05},
            {"賛成": 0.30, "条件付き賛成": 0.20, "中立": 0.20, "条件付き反対": 0.15, "反対": 0.15},
        )
        old_comp["days_since"] = 365  # 1年前

        # 新しいデータ: 賛成にバイアスなし
        new_comp = _make_comparison(
            "economy",
            {"賛成": 0.30, "条件付き賛成": 0.20, "中立": 0.20, "条件付き反対": 0.15, "反対": 0.15},
            {"賛成": 0.30, "条件付き賛成": 0.20, "中立": 0.20, "条件付き反対": 0.15, "反対": 0.15},
        )
        new_comp["days_since"] = 10  # 10日前

        profile = compute_bias_profile([old_comp, new_comp])
        # 時間減衰があれば、新しいデータ（バイアスなし）の影響が大きい
        # → 平均バイアスは 0.10 より小さくなるはず
        assert profile["economy"]["賛成"]["mean_deviation"] < 0.10

    def test_no_days_since_falls_back_to_equal_weight(self):
        """days_since がないデータは等重み扱い。"""
        comps = [
            _make_comparison(
                "economy",
                {"賛成": 0.40, "条件付き賛成": 0.20, "中立": 0.15, "条件付き反対": 0.15, "反対": 0.10},
                {"賛成": 0.30, "条件付き賛成": 0.20, "中立": 0.20, "条件付き反対": 0.15, "反対": 0.15},
            ),
            _make_comparison(
                "economy",
                {"賛成": 0.50, "条件付き賛成": 0.15, "中立": 0.15, "条件付き反対": 0.10, "反対": 0.10},
                {"賛成": 0.35, "条件付き賛成": 0.20, "中立": 0.20, "条件付き反対": 0.15, "反対": 0.10},
            ),
        ]
        profile = compute_bias_profile(comps)
        # days_since がなければ等重み → 平均 = (0.10 + 0.15) / 2 = 0.125
        assert abs(profile["economy"]["賛成"]["mean_deviation"] - 0.125) < 0.001


class TestJamesSteinShrinkage:
    """Phase E: James-Stein shrinkage のテスト。"""

    def test_shrinkage_toward_grand_mean(self):
        """複数カテゴリがある場合、全カテゴリの平均に向かって shrink。"""
        # 2つのカテゴリ、economy は大きなバイアス、politics は小さなバイアス
        profile: BiasProfile = {
            "economy": {
                "賛成": {"mean_deviation": 0.20, "sample_count": 5, "std_deviation": 0.05},
                "条件付き賛成": {"mean_deviation": 0.0, "sample_count": 5, "std_deviation": 0.02},
                "中立": {"mean_deviation": -0.10, "sample_count": 5, "std_deviation": 0.03},
                "条件付き反対": {"mean_deviation": -0.05, "sample_count": 5, "std_deviation": 0.02},
                "反対": {"mean_deviation": -0.05, "sample_count": 5, "std_deviation": 0.02},
            },
            "politics": {
                "賛成": {"mean_deviation": 0.02, "sample_count": 10, "std_deviation": 0.02},
                "条件付き賛成": {"mean_deviation": 0.01, "sample_count": 10, "std_deviation": 0.01},
                "中立": {"mean_deviation": -0.01, "sample_count": 10, "std_deviation": 0.01},
                "条件付き反対": {"mean_deviation": -0.01, "sample_count": 10, "std_deviation": 0.01},
                "反対": {"mean_deviation": -0.01, "sample_count": 10, "std_deviation": 0.01},
            },
        }
        dist = {"賛成": 0.40, "条件付き賛成": 0.20, "中立": 0.15, "条件付き反対": 0.15, "反対": 0.10}
        corrected = apply_transfer_correction(dist, profile, "economy")
        # 補正後は正規化されて合計1.0
        assert abs(sum(corrected.values()) - 1.0) < 0.001
        # 賛成は正のバイアスなので減少
        assert corrected["賛成"] < dist["賛成"]
