"""評価スキャフォールド: Society シミュレーションの品質評価メトリクス"""

import logging
import math
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)


def diversity_index(responses: list[dict]) -> float:
    """Shannon entropy ベースの意見多様性指標 (0-1 正規化)。

    スタンスの分布が均等なほど 1 に近づく。
    """
    if not responses:
        return 0.0

    stances = [r.get("stance", "中立") for r in responses]
    counter = Counter(stances)
    total = len(stances)
    n_categories = len(counter)

    if n_categories <= 1:
        return 0.0

    entropy = 0.0
    for count in counter.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log2(p)

    # 最大エントロピーで正規化
    max_entropy = math.log2(n_categories)
    return round(entropy / max_entropy, 4) if max_entropy > 0 else 0.0


def internal_consistency(agents: list[dict], responses: list[dict]) -> float:
    """プロフィールと回答の整合性スコア (0-1)。

    例: 保守的なプロフィール（低O, 高C）の住民が「伝統重視」を優先しているか等を検証。
    """
    if not agents or not responses or len(agents) != len(responses):
        return 0.0

    consistent_count = 0
    total = len(agents)

    for agent, resp in zip(agents, responses):
        big_five = agent.get("big_five", {})
        values = agent.get("values", {})
        stance = resp.get("stance", "中立")

        score = 0.0
        checks = 0

        # Check 1: 高 Openness → 革新的スタンスとの整合
        if big_five.get("O", 0.5) > 0.7:
            if stance in ("賛成", "条件付き賛成"):
                score += 1.0
            elif stance == "中立":
                score += 0.5
            checks += 1
        elif big_five.get("O", 0.5) < 0.3:
            if stance in ("反対", "条件付き反対"):
                score += 1.0
            elif stance == "中立":
                score += 0.5
            checks += 1

        # Check 2: 高 Neuroticism → 低 confidence との整合
        if big_five.get("N", 0.5) > 0.7:
            if resp.get("confidence", 0.5) < 0.6:
                score += 1.0
            checks += 1

        # Check 3: 価値観との整合
        if values:
            top_value = max(values, key=values.get) if values else ""
            reason = resp.get("reason", "").lower()
            if top_value and top_value in reason:
                score += 1.0
            checks += 1

        if checks > 0 and score / checks >= 0.5:
            consistent_count += 1

    return round(consistent_count / total, 4) if total > 0 else 0.0


def calibration_score(responses: list[dict]) -> float:
    """回答の信頼度キャリブレーション (0-1)。

    各スタンスの回答者の平均信頼度が、そのスタンスの人数比と整合しているかを測定。
    過信（少数意見なのに高信頼度）にペナルティ。
    """
    if not responses:
        return 0.0

    stance_groups: dict[str, list[float]] = {}
    for r in responses:
        stance = r.get("stance", "中立")
        conf = r.get("confidence", 0.5)
        if stance not in stance_groups:
            stance_groups[stance] = []
        stance_groups[stance].append(conf)

    total = len(responses)
    penalties = []

    for stance, confidences in stance_groups.items():
        proportion = len(confidences) / total
        avg_conf = sum(confidences) / len(confidences)
        # 過信ペナルティ: 少数意見なのに高信頼度
        if proportion < 0.2 and avg_conf > 0.8:
            penalties.append(0.3)
        elif proportion < 0.1 and avg_conf > 0.6:
            penalties.append(0.2)

    penalty = sum(penalties)
    return round(max(0.0, 1.0 - penalty), 4)


def brier_score_stub() -> float | None:
    """Brier Score スタブ（実際の結果データが必要）。"""
    return None


def kl_divergence_stub() -> float | None:
    """KL-divergence スタブ（ベースライン分布が必要）。"""
    return None


async def evaluate_society_simulation(
    agents: list[dict],
    responses: list[dict],
) -> list[dict[str, Any]]:
    """Society シミュレーションの評価メトリクスを計算する。

    Returns:
        メトリクスのリスト [{metric_name, score, details, baseline_type, baseline_score}]
    """
    metrics = []

    # Diversity Index
    div_score = diversity_index(responses)
    metrics.append({
        "metric_name": "diversity",
        "score": div_score,
        "details": {"method": "shannon_entropy_normalized"},
        "baseline_type": None,
        "baseline_score": None,
    })

    # Internal Consistency
    con_score = internal_consistency(agents, responses)
    metrics.append({
        "metric_name": "consistency",
        "score": con_score,
        "details": {"method": "profile_response_alignment"},
        "baseline_type": None,
        "baseline_score": None,
    })

    # Calibration
    cal_score = calibration_score(responses)
    metrics.append({
        "metric_name": "calibration",
        "score": cal_score,
        "details": {"method": "overconfidence_penalty"},
        "baseline_type": None,
        "baseline_score": None,
    })

    # Brier Score (stub)
    brier = brier_score_stub()
    if brier is not None:
        metrics.append({
            "metric_name": "brier_score",
            "score": brier,
            "details": {"method": "stub"},
            "baseline_type": None,
            "baseline_score": None,
        })

    # KL Divergence (stub)
    kl = kl_divergence_stub()
    if kl is not None:
        metrics.append({
            "metric_name": "kl_divergence",
            "score": kl,
            "details": {"method": "stub"},
            "baseline_type": None,
            "baseline_score": None,
        })

    logger.info("Evaluation complete: %s", {m["metric_name"]: m["score"] for m in metrics})
    return metrics
