"""4 種類ベースライン分布計算と比較モジュール

Step 10 で実装するベースライン比較機能:
- compute_random_baseline:          一様ランダム分布（seed 固定で再現性保証）
- compute_initial_baseline:         活性化レイヤー直後の初期分布
- compare_against_baselines:        4 ベースラインと simulated 分布の相対改善率を計算
- compute_live_median:              live 実行 EMD の中央値
- compute_relative_improvement:     ベースライン比の相対改善率
- build_rolling_backtest_summary:   rolling backtest サマリー
- build_evaluation_summary_response: summary endpoint 用レスポンス構造

会話なし・イベントなし ベースラインはシミュレーション実行時のアブレーション結果を
呼び出し側が渡す設計（`no_conversation_baseline`, `no_event_baseline` 引数）。
"""

from __future__ import annotations

import random
from statistics import median
from typing import TypedDict

from src.app.utils.distribution_metrics import earth_movers_distance

# =============================================================
# 1. ベースライン分布計算
# =============================================================

def compute_random_baseline(
    stances: list[str],
    seed: int,
) -> dict[str, float]:
    """一様ランダム分布をベースラインとして生成する。

    Dirichlet(1, 1, ...) に相当する指数分布の正規化によりサンプリングする。
    seed 固定により同一呼び出しは同一分布を返す。

    Args:
        stances: スタンスラベルのリスト
        seed:    乱数シード（再現性確保用）

    Returns:
        スタンス → 確率の辞書（合計≈1）
    """
    rng = random.Random(seed)
    raw = [rng.expovariate(1.0) for _ in stances]
    total = sum(raw)
    return {s: v / total for s, v in zip(stances, raw)}


def compute_initial_baseline(
    activation_distribution: dict[str, float],
) -> dict[str, float]:
    """活性化レイヤー直後の初期分布（伝播前）をベースラインとして返す。

    ネットワーク伝播・会話・イベント注入前の分布のコピーを返す。

    Args:
        activation_distribution: 活性化レイヤーのスタンス分布

    Returns:
        コピーされた分布辞書
    """
    return dict(activation_distribution)


# =============================================================
# 2. ベースライン比較
# =============================================================

class BaselineComparison(TypedDict):
    simulated_emd: float | None
    random_emd: float | None
    initial_emd: float | None
    no_conversation_emd: float | None
    no_event_emd: float | None
    vs_random_improvement: float | None
    vs_initial_improvement: float | None
    vs_no_conversation_improvement: float | None
    vs_no_event_improvement: float | None
    primary_metric: str


def compare_against_baselines(
    simulated: dict[str, float],
    actual: dict[str, float],
    random_baseline: dict[str, float],
    initial_baseline: dict[str, float],
    no_conversation_baseline: dict[str, float] | None = None,
    no_event_baseline: dict[str, float] | None = None,
) -> BaselineComparison:
    """4 ベースラインと simulated 分布の相対改善率を計算する。

    primary metric は EMD (Earth Mover's Distance)。

    Args:
        simulated:                 シミュレーション最終分布
        actual:                    実績分布（調査データ）
        random_baseline:           ランダムベースライン分布
        initial_baseline:          初期値固定ベースライン分布
        no_conversation_baseline:  会話なしベースライン分布（省略可）
        no_event_baseline:         イベントなしベースライン分布（省略可）

    Returns:
        BaselineComparison
    """
    sim_emd = earth_movers_distance(simulated, actual)
    rnd_emd = earth_movers_distance(random_baseline, actual)
    ini_emd = earth_movers_distance(initial_baseline, actual)
    nc_emd = earth_movers_distance(no_conversation_baseline, actual) if no_conversation_baseline else None
    ne_emd = earth_movers_distance(no_event_baseline, actual) if no_event_baseline else None

    return BaselineComparison(
        simulated_emd=sim_emd,
        random_emd=rnd_emd,
        initial_emd=ini_emd,
        no_conversation_emd=nc_emd,
        no_event_emd=ne_emd,
        vs_random_improvement=compute_relative_improvement(rnd_emd, sim_emd),
        vs_initial_improvement=compute_relative_improvement(ini_emd, sim_emd),
        vs_no_conversation_improvement=(
            compute_relative_improvement(nc_emd, sim_emd) if nc_emd is not None else None
        ),
        vs_no_event_improvement=(
            compute_relative_improvement(ne_emd, sim_emd) if ne_emd is not None else None
        ),
        primary_metric="emd",
    )


# =============================================================
# 3. rolling backtest / live median
# =============================================================

def compute_live_median(emd_values: list[float]) -> float | None:
    """live 実行 EMD 値の中央値を計算する。

    Args:
        emd_values: EMD 値のリスト

    Returns:
        中央値。リストが空なら None。
    """
    if not emd_values:
        return None
    return median(emd_values)


def compute_relative_improvement(
    baseline_emd: float | None,
    candidate_emd: float | None,
) -> float | None:
    """ベースライン比の相対改善率を計算する。

    improvement = (baseline - candidate) / baseline

    正の値 = 改善、負の値 = 悪化。

    Args:
        baseline_emd:  ベースラインの EMD
        candidate_emd: 改善候補の EMD

    Returns:
        改善率。baseline が 0 または None の場合は None（ゼロ除算回避）。
    """
    if baseline_emd is None or candidate_emd is None:
        return None
    if baseline_emd == 0.0:
        return None
    return (baseline_emd - candidate_emd) / baseline_emd


class RollingBacktestSummary(TypedDict):
    median_emd: float | None
    pass_rate: float
    run_count: int


def build_rolling_backtest_summary(
    live_runs: list[dict],
) -> RollingBacktestSummary:
    """rolling backtest の live 実行サマリーを集計する。

    各 live 実行結果（avg_emd, gate）から中央値 EMD と pass 率を算出する。

    Args:
        live_runs: live 実行結果のリスト（各要素に "avg_emd" と "gate" を含む）

    Returns:
        RollingBacktestSummary
    """
    if not live_runs:
        return RollingBacktestSummary(median_emd=None, pass_rate=0.0, run_count=0)

    emd_values = [r["avg_emd"] for r in live_runs if r.get("avg_emd") is not None]
    pass_count = sum(1 for r in live_runs if r.get("gate") == "pass")

    return RollingBacktestSummary(
        median_emd=compute_live_median(emd_values),
        pass_rate=pass_count / len(live_runs),
        run_count=len(live_runs),
    )


# =============================================================
# 4. summary endpoint 用レスポンス構造
# =============================================================

def build_evaluation_summary_response(
    sim_id: str,
    gate_result: dict,
    baseline_comparison: dict,
    live_replay_warning: bool = False,
) -> dict:
    """summary endpoint のレスポンス辞書を構築する。

    Args:
        sim_id:               シミュレーション ID
        gate_result:          build_validation_summary / run_deterministic_gate の結果
        baseline_comparison:  compare_against_baselines の結果
        live_replay_warning:  live replay 乖離 warning フラグ

    Returns:
        summary endpoint のレスポンス辞書
    """
    return {
        "simulation_id": sim_id,
        "gate": gate_result.get("gate"),
        "avg_emd": gate_result.get("avg_emd"),
        "avg_jsd": gate_result.get("avg_jsd"),
        "avg_brier": gate_result.get("avg_brier"),
        "total_count": gate_result.get("total_count", 0),
        "validated_count": gate_result.get("validated_count", 0),
        "gate_eligible_count": gate_result.get("gate_eligible_count", 0),
        "theme_category": gate_result.get("theme_category"),
        "baseline_comparison": dict(baseline_comparison),
        "live_replay_warning": live_replay_warning,
    }
