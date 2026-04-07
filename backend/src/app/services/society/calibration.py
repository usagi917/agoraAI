"""予測キャリブレーション: 外部Brierスコア、期待キャリブレーション誤差（ECE）、グレード評価、トランスファー補正。

公式:
  Brier外部スコア: Σ(p_i - o_i)² ただし o_i = 1 if i == observed_outcome else 0
  ECE: Σ_b (|B_b| / n) * |avg_predicted_b - avg_actual_b|
       ビンに分割して各ビンの予測確率平均と実際の的中率の差を重み付き平均。
"""

import math

from src.app.services.society.transfer_calibrator import (
    BiasProfile,
    apply_transfer_correction,
)


def brier_external(
    predicted_distribution: dict[str, float],
    observed_outcome: str,
) -> float:
    """外部Brierスコアを計算する。

    Args:
        predicted_distribution: 各クラスへの予測確率 {"賛成": 0.7, "反対": 0.3} など。
        observed_outcome: 実際に観測されたクラス名。

    Returns:
        Brier スコア (float)。0.0 = 完全予測、2.0 = 最悪予測。
        Σ(p_i - o_i)² where o_i = 1 if i == observed_outcome else 0
    """
    total = 0.0
    for outcome, prob in predicted_distribution.items():
        o_i = 1.0 if outcome == observed_outcome else 0.0
        total += (prob - o_i) ** 2
    return total


def expected_calibration_error(
    predictions: list[tuple[float, bool]],
    n_bins: int = 10,
) -> float | None:
    """期待キャリブレーション誤差（ECE）を計算する。

    Args:
        predictions: (predicted_probability, did_happen) のリスト。
            predicted_probability は 0〜1 の予測確率、
            did_happen は実際に起きたかどうかの bool。
        n_bins: ビン数（デフォルト 10）。

    Returns:
        ECE (float, 0.0〜1.0)。predictions が空なら None。
        ECE = Σ_b (|B_b| / n) * |avg_predicted_b - avg_actual_b|
    """
    if not predictions:
        return None

    n = len(predictions)
    bin_size = 1.0 / n_bins

    # ビン別に集計
    bins: list[list[tuple[float, bool]]] = [[] for _ in range(n_bins)]
    for prob, outcome in predictions:
        # ビンインデックスを算出（1.0 は最後のビンに入れる）
        bin_idx = min(int(prob / bin_size), n_bins - 1)
        bins[bin_idx].append((prob, outcome))

    ece = 0.0
    for bin_items in bins:
        if not bin_items:
            continue
        bin_n = len(bin_items)
        avg_predicted = sum(p for p, _ in bin_items) / bin_n
        avg_actual = sum(1.0 for _, o in bin_items if o) / bin_n
        ece += (bin_n / n) * abs(avg_predicted - avg_actual)

    return ece


def calibration_grade(ece: float | None) -> str:
    """ECE からキャリブレーション品質グレードを返す。

    Args:
        ece: 期待キャリブレーション誤差。None の場合はデータ不足。

    Returns:
        "well_calibrated"  : ECE < 0.05（良好）
        "moderate"         : 0.05 <= ECE < 0.15（中程度）
        "poor"             : ECE >= 0.15（不良）
        "insufficient_data": ece が None（データ不足）
    """
    if ece is None:
        return "insufficient_data"
    if ece < 0.05:
        return "well_calibrated"
    if ece < 0.15:
        return "moderate"
    return "poor"


def platt_recalibrate(
    confidence: float,
    shrink_factor: float = 0.8,
) -> float:
    """エージェント confidence を Platt-style で再キャリブレーションする。

    データ不足時の固定補正: calibrated = 0.5 + shrink_factor * (conf - 0.5)
    shrink_factor < 1.0 で 0.5 方向に圧縮。

    Args:
        confidence: 元の confidence (0.0〜1.0)
        shrink_factor: 圧縮係数 (デフォルト 0.8)

    Returns:
        再キャリブレーション済み confidence (0.0〜1.0)
    """
    calibrated = 0.5 + shrink_factor * (confidence - 0.5)
    return max(0.0, min(1.0, calibrated))


def extremeness_aversion_correction(
    distribution: dict[str, float],
    gamma: float = 0.7,
) -> dict[str, float]:
    """Extremeness aversion 補正: 中庸バイアスを逆補正する。

    p_k' = p_k^gamma / Σ(p_j^gamma)
    gamma < 1.0 で両端を膨張（中立寄りバイアスを補正）。
    gamma = 1.0 で無変更。

    Args:
        distribution: スタンス分布 (合計1.0)
        gamma: 補正指数 (デフォルト 0.7)

    Returns:
        補正後の正規化分布
    """
    if gamma == 1.0:
        return dict(distribution)

    powered = {}
    for k, v in distribution.items():
        powered[k] = v ** gamma if v > 0 else 0.0

    total = sum(powered.values())
    if total > 0:
        return {k: v / total for k, v in powered.items()}
    return dict(distribution)


class TopicShrinkCalibrator:
    """トピック別 shrink factor でキャリブレーションする。

    train() でカテゴリ別に最適な shrink factor を学習し、
    recalibrate() でトピック別に confidence を補正する。
    未知カテゴリは global shrink factor (デフォルト 0.8) にフォールバック。
    """

    def __init__(self, global_shrink: float = 0.8) -> None:
        self._global_shrink = global_shrink
        self._topic_factors: dict[str, float] = {}

    def recalibrate(self, confidence: float, category: str) -> float:
        """トピック別 shrink factor で confidence を再キャリブレーション."""
        shrink = self._topic_factors.get(category, self._global_shrink)
        calibrated = 0.5 + shrink * (confidence - 0.5)
        return max(0.0, min(1.0, calibrated))

    def train(self, comparisons: list[dict]) -> None:
        """カテゴリ別 shrink factor を学習する.

        各 comparison は {"category", "predicted_confidence", "actual_accuracy"} を持つ。
        カテゴリごとに、predicted_confidence と actual_accuracy の乖離から
        最適な shrink factor を推定する。
        """
        from collections import defaultdict

        by_category: dict[str, list[tuple[float, float]]] = defaultdict(list)
        for comp in comparisons:
            cat = comp["category"]
            by_category[cat].append(
                (comp["predicted_confidence"], comp["actual_accuracy"])
            )

        for cat, pairs in by_category.items():
            # 簡易推定: shrink = mean(actual - 0.5) / mean(predicted - 0.5)
            pred_devs = [p - 0.5 for p, _ in pairs]
            actual_devs = [a - 0.5 for _, a in pairs]

            mean_pred = sum(pred_devs) / len(pred_devs) if pred_devs else 0.0
            mean_actual = sum(actual_devs) / len(actual_devs) if actual_devs else 0.0

            if abs(mean_pred) > 1e-8:
                shrink = mean_actual / mean_pred
                shrink = max(0.1, min(1.0, shrink))
            else:
                shrink = self._global_shrink

            self._topic_factors[cat] = round(shrink, 4)


def apply_transfer_calibration(
    raw_distribution: dict[str, float],
    bias_profile: BiasProfile,
    theme_category: str,
) -> dict[str, float]:
    """トランスファー補正を適用する薄いラッパー。

    transfer_calibrator.apply_transfer_correction() を呼び出す。
    """
    return apply_transfer_correction(raw_distribution, bias_profile, theme_category)
