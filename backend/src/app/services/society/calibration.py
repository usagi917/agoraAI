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


def apply_transfer_calibration(
    raw_distribution: dict[str, float],
    bias_profile: BiasProfile,
    theme_category: str,
) -> dict[str, float]:
    """トランスファー補正を適用する薄いラッパー。

    transfer_calibrator.apply_transfer_correction() を呼び出す。
    """
    return apply_transfer_correction(raw_distribution, bias_profile, theme_category)
