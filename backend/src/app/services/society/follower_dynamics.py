"""FDE-LLM リーダー/フォロワー分離

フォロワーエージェントの意見は、隣接リーダーの意見ベクトル加重平均で計算する。
reason/concern はテンプレートベース生成（LLM 不要）。

FollowerResponse プロトコル: {stance, confidence, reason, concern, agent_id}
既存の市場参加・クラスタリング契約をそのまま維持するため、下流コード変更不要。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def compute_follower_opinion(
    leader_opinions: list[dict[str, Any]],
    follower_id: str,
) -> dict[str, Any]:
    """隣接リーダーの意見を加重平均してフォロワーの意見を生成する.

    Args:
        leader_opinions: リーダーの意見リスト。各要素は
            {"agent_id", "stance", "confidence", "weight"} を持つ。
        follower_id: フォロワーのエージェント ID

    Returns:
        FollowerResponse プロトコル準拠の辞書
    """
    if not leader_opinions:
        return {
            "stance": "中立",
            "confidence": 0.5,
            "reason": "周囲の意見が得られないため判断を保留します。",
            "concern": "",
            "agent_id": follower_id,
        }

    # 加重多数決でスタンス決定
    stance_weights: dict[str, float] = defaultdict(float)
    total_weight = 0.0
    weighted_confidence = 0.0

    for opinion in leader_opinions:
        w = opinion.get("weight", 1.0)
        stance_weights[opinion["stance"]] += w
        weighted_confidence += opinion["confidence"] * w
        total_weight += w

    majority_stance = max(stance_weights, key=stance_weights.get)
    avg_confidence = weighted_confidence / total_weight if total_weight > 0 else 0.5

    reason = f"周囲の{len(leader_opinions)}人の意見を踏まえた判断です。"
    concern = ""

    return {
        "stance": majority_stance,
        "confidence": round(avg_confidence, 4),
        "reason": reason,
        "concern": concern,
        "agent_id": follower_id,
    }
