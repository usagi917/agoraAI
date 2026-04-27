"""Phase 6-1: 予測キャリブレーションのテスト (TDD RED フェーズ)

テスト対象:
- brier_external: 外部Brierスコア
- expected_calibration_error: 期待キャリブレーション誤差（ECE）
- calibration_grade: キャリブレーション品質グレード
"""

import pytest

from src.app.services.society.calibration import (
    brier_external,
    expected_calibration_error,
    calibration_grade,
    apply_transfer_calibration,
    platt_recalibrate,
)


# ---------------------------------------------------------------------------
# brier_external
# ---------------------------------------------------------------------------

class TestBrierExternal:
    def test_brier_external_perfect_prediction(self):
        """完全な予測: predicted={"賛成": 1.0, "反対": 0.0}, observed="賛成" → brier = 0.0"""
        predicted = {"賛成": 1.0, "反対": 0.0}
        result = brier_external(predicted, "賛成")
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_brier_external_worst_prediction(self):
        """最悪の予測: predicted={"賛成": 0.0, "反対": 1.0}, observed="賛成" → brier = 2.0"""
        predicted = {"賛成": 0.0, "反対": 1.0}
        result = brier_external(predicted, "賛成")
        assert result == pytest.approx(2.0, abs=1e-9)

    def test_brier_external_uncertain_prediction(self):
        """不確かな予測: predicted={"賛成": 0.5, "反対": 0.5}, observed="賛成" → brier = 0.5"""
        predicted = {"賛成": 0.5, "反対": 0.5}
        result = brier_external(predicted, "賛成")
        assert result == pytest.approx(0.5, abs=1e-9)

    def test_brier_external_three_class_perfect(self):
        """3クラス完全予測: observed class に 1.0 → brier = 0.0"""
        predicted = {"賛成": 1.0, "反対": 0.0, "中立": 0.0}
        result = brier_external(predicted, "賛成")
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_brier_external_three_class_worst(self):
        """3クラス最悪予測: observed class に 0.0、別 class に 1.0 → brier = 2.0"""
        predicted = {"賛成": 0.0, "反対": 1.0, "中立": 0.0}
        result = brier_external(predicted, "賛成")
        assert result == pytest.approx(2.0, abs=1e-9)

    def test_brier_external_returns_float(self):
        """返り値は float 型"""
        result = brier_external({"賛成": 0.7, "反対": 0.3}, "賛成")
        assert isinstance(result, float)

    def test_brier_external_range(self):
        """Brier スコアは 0.0〜2.0 の範囲"""
        predicted = {"賛成": 0.3, "反対": 0.7}
        result = brier_external(predicted, "反対")
        assert 0.0 <= result <= 2.0


# ---------------------------------------------------------------------------
# expected_calibration_error
# ---------------------------------------------------------------------------

class TestExpectedCalibrationError:
    def _make_well_calibrated(self) -> list[tuple[float, bool]]:
        """良いキャリブレーション: 予測確率とヒット率がほぼ一致するデータ"""
        predictions = []
        # 予測確率 0.1 → 約 10% 的中
        for i in range(100):
            predictions.append((0.1, i < 10))
        # 予測確率 0.5 → 約 50% 的中
        for i in range(100):
            predictions.append((0.5, i < 50))
        # 予測確率 0.9 → 約 90% 的中
        for i in range(100):
            predictions.append((0.9, i < 90))
        return predictions

    def _make_poorly_calibrated(self) -> list[tuple[float, bool]]:
        """悪いキャリブレーション: 自信過剰（高い確率を予測するが的中率は低い）"""
        predictions = []
        # 予測確率 0.9 → 実際は 10% しか的中しない（過信）
        for i in range(100):
            predictions.append((0.9, i < 10))
        # 予測確率 0.8 → 実際は 20% しか的中しない（過信）
        for i in range(100):
            predictions.append((0.8, i < 20))
        return predictions

    def test_ece_well_calibrated(self):
        """良いキャリブレーション → ECE < 0.05"""
        predictions = self._make_well_calibrated()
        ece = expected_calibration_error(predictions)
        assert ece < 0.05, f"Expected ECE < 0.05 for well-calibrated, got {ece}"

    def test_ece_poorly_calibrated(self):
        """悪いキャリブレーション → ECE > 0.15"""
        predictions = self._make_poorly_calibrated()
        ece = expected_calibration_error(predictions)
        assert ece > 0.15, f"Expected ECE > 0.15 for poorly-calibrated, got {ece}"

    def test_ece_empty_returns_none(self):
        """空リスト → None を返す"""
        result = expected_calibration_error([])
        assert result is None

    def test_ece_returns_float_or_none(self):
        """返り値は float または None"""
        predictions = [(0.7, True), (0.3, False)]
        result = expected_calibration_error(predictions)
        assert result is None or isinstance(result, float)

    def test_ece_range(self):
        """ECE は 0.0〜1.0 の範囲"""
        predictions = [(0.7, True), (0.3, False), (0.5, True), (0.5, False)]
        result = expected_calibration_error(predictions)
        if result is not None:
            assert 0.0 <= result <= 1.0

    def test_ece_perfect_calibration(self):
        """完全キャリブレーション: 確率0.0→全て外れ、確率1.0→全て当たり → ECE ≈ 0.0"""
        predictions = [(1.0, True)] * 50 + [(0.0, False)] * 50
        ece = expected_calibration_error(predictions)
        assert ece == pytest.approx(0.0, abs=1e-9)

    def test_ece_custom_n_bins(self):
        """n_bins パラメータを変えても動作する"""
        predictions = [(0.5, True), (0.5, False)] * 20
        ece_10 = expected_calibration_error(predictions, n_bins=10)
        ece_5 = expected_calibration_error(predictions, n_bins=5)
        # どちらも有効な float または None
        assert ece_10 is None or isinstance(ece_10, float)
        assert ece_5 is None or isinstance(ece_5, float)


# ---------------------------------------------------------------------------
# calibration_grade
# ---------------------------------------------------------------------------

class TestCalibrationGrade:
    def test_calibration_grade_well(self):
        """ECE = 0.03 → 'well_calibrated'"""
        assert calibration_grade(0.03) == "well_calibrated"

    def test_calibration_grade_moderate(self):
        """ECE = 0.10 → 'moderate'"""
        assert calibration_grade(0.10) == "moderate"

    def test_calibration_grade_poor(self):
        """ECE = 0.20 → 'poor'"""
        assert calibration_grade(0.20) == "poor"

    def test_calibration_grade_insufficient(self):
        """ECE = None (空の予測履歴) → 'insufficient_data'"""
        assert calibration_grade(None) == "insufficient_data"

    def test_calibration_grade_boundary_well_to_moderate(self):
        """ECE = 0.05 (境界) → 'well_calibrated' または 'moderate'"""
        grade = calibration_grade(0.05)
        assert grade in ("well_calibrated", "moderate")

    def test_calibration_grade_boundary_moderate_to_poor(self):
        """ECE = 0.15 (境界) → 'moderate' または 'poor'"""
        grade = calibration_grade(0.15)
        assert grade in ("moderate", "poor")

    def test_calibration_grade_zero_ece(self):
        """ECE = 0.0 → 'well_calibrated'"""
        assert calibration_grade(0.0) == "well_calibrated"

    def test_calibration_grade_high_ece(self):
        """ECE = 0.5 → 'poor'"""
        assert calibration_grade(0.5) == "poor"

    def test_calibration_grade_returns_string(self):
        """返り値は str 型"""
        result = calibration_grade(0.1)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# apply_transfer_calibration (Phase 6 統合)
# ---------------------------------------------------------------------------

STANCES = ["賛成", "条件付き賛成", "中立", "条件付き反対", "反対"]


class TestApplyTransferCalibration:
    def _build_profile(self):
        return {
            "economy": {
                "賛成": {"mean_deviation": 0.10, "sample_count": 20, "std_deviation": 0.02},
                "条件付き賛成": {"mean_deviation": 0.0, "sample_count": 20, "std_deviation": 0.01},
                "中立": {"mean_deviation": -0.05, "sample_count": 20, "std_deviation": 0.02},
                "条件付き反対": {"mean_deviation": -0.03, "sample_count": 20, "std_deviation": 0.01},
                "反対": {"mean_deviation": -0.02, "sample_count": 20, "std_deviation": 0.01},
            }
        }

    def test_apply_transfer_calibration(self):
        """ラッパー関数が transfer_calibrator を呼び出し、補正済み分布を返す"""
        dist = {"賛成": 0.40, "条件付き賛成": 0.20, "中立": 0.15, "条件付き反対": 0.15, "反対": 0.10}
        profile = self._build_profile()
        result = apply_transfer_calibration(dist, profile, "economy")
        assert isinstance(result, dict)
        assert abs(sum(result.values()) - 1.0) < 0.001
        # 賛成のバイアスが正なので補正後は減少
        assert result["賛成"] < dist["賛成"]

    def test_brier_external_with_calibrated_distribution(self):
        """トランスファー補正後の分布で Brier Score 計算"""
        dist = {"賛成": 0.40, "条件付き賛成": 0.20, "中立": 0.15, "条件付き反対": 0.15, "反対": 0.10}
        profile = self._build_profile()
        calibrated = apply_transfer_calibration(dist, profile, "economy")
        brier = brier_external(calibrated, "賛成")
        assert isinstance(brier, float)
        assert 0.0 <= brier <= 2.0


# ---------------------------------------------------------------------------
# Phase H: Platt recalibration
# ---------------------------------------------------------------------------


class TestPlattRecalibrate:
    """Phase H: 信頼度リキャリブレーションのテスト。"""

    def test_compresses_toward_center(self):
        """デフォルト（データなし）: confidence を 0.5 方向に圧縮。"""
        assert platt_recalibrate(0.9) < 0.9
        assert platt_recalibrate(0.1) > 0.1
        assert platt_recalibrate(0.5) == pytest.approx(0.5)

    def test_output_in_valid_range(self):
        """出力は [0, 1] の範囲。"""
        for c in [0.0, 0.1, 0.5, 0.9, 1.0]:
            result = platt_recalibrate(c)
            assert 0.0 <= result <= 1.0, f"platt_recalibrate({c}) = {result}"

    def test_monotonic(self):
        """キャリブレーション後も順序が保存される（単調変換）。"""
        vals = [platt_recalibrate(c) for c in [0.1, 0.3, 0.5, 0.7, 0.9]]
        for i in range(len(vals) - 1):
            assert vals[i] <= vals[i + 1], f"Not monotonic at {i}: {vals}"

    def test_shrink_factor(self):
        """shrink_factor=0.5 ならより強く圧縮。"""
        mild = platt_recalibrate(0.9, shrink_factor=0.8)
        strong = platt_recalibrate(0.9, shrink_factor=0.5)
        assert strong < mild


# ---------------------------------------------------------------------------
# Phase J: Extremeness Aversion Correction
# ---------------------------------------------------------------------------


class TestExtremenessAversionCorrection:
    """Phase J: 学習可能な γ による extremeness aversion 補正テスト。"""

    def test_gamma_less_than_1_amplifies_extremes(self):
        """γ < 1.0 で両端が増幅される。"""
        from src.app.services.society.calibration import extremeness_aversion_correction

        dist = {"賛成": 0.10, "条件付き賛成": 0.20, "中立": 0.40, "条件付き反対": 0.20, "反対": 0.10}
        corrected = extremeness_aversion_correction(dist, gamma=0.7)
        # 中立が最大だったのが縮小し、両端が増大
        assert corrected["中立"] < dist["中立"]
        assert corrected["賛成"] > dist["賛成"]
        assert corrected["反対"] > dist["反対"]

    def test_gamma_1_no_change(self):
        """γ = 1.0 で変化なし。"""
        from src.app.services.society.calibration import extremeness_aversion_correction

        dist = {"賛成": 0.30, "条件付き賛成": 0.20, "中立": 0.20, "条件付き反対": 0.15, "反対": 0.15}
        corrected = extremeness_aversion_correction(dist, gamma=1.0)
        for k in dist:
            assert abs(corrected[k] - dist[k]) < 0.001

    def test_preserves_normalization(self):
        """補正後の分布合計 = 1.0。"""
        from src.app.services.society.calibration import extremeness_aversion_correction

        dist = {"賛成": 0.10, "条件付き賛成": 0.20, "中立": 0.40, "条件付き反対": 0.20, "反対": 0.10}
        corrected = extremeness_aversion_correction(dist, gamma=0.5)
        assert abs(sum(corrected.values()) - 1.0) < 0.001

    def test_no_negative_values(self):
        """補正後に負の確率が生まれない。"""
        from src.app.services.society.calibration import extremeness_aversion_correction

        dist = {"賛成": 0.01, "条件付き賛成": 0.01, "中立": 0.96, "条件付き反対": 0.01, "反対": 0.01}
        corrected = extremeness_aversion_correction(dist, gamma=0.3)
        for v in corrected.values():
            assert v >= 0
