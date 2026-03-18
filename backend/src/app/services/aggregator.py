"""ベイズ加重集約: クラスタ結果をシナリオ確率分布に変換する"""

import logging
import math
import uuid

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.aggregation_result import AggregationResult

logger = logging.getLogger(__name__)


async def aggregate_clusters(
    session: AsyncSession,
    swarm_id: str,
    clusters: list[dict],
    colony_results: list[dict],
) -> dict:
    """クラスタを統合してシナリオ確率分布を生成する。"""
    if not clusters:
        return {"scenarios": [], "diversity_score": 0.0, "entropy": 0.0}

    total_colonies = len(colony_results)

    # 各クラスタからシナリオを生成
    scenarios = []
    for cluster in clusters:
        agreement = cluster["agreement_ratio"]
        confidence = cluster["mean_confidence"]

        # 加重確率 = 合意率 * 平均信頼度
        raw_probability = agreement * confidence

        # 信頼区間 (Wilson score interval の簡易版)
        n = cluster["claim_count"]
        if n > 0:
            p = raw_probability
            z = 1.96  # 95% CI
            denominator = 1 + z * z / n
            center = (p + z * z / (2 * n)) / denominator
            margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
            ci_low = max(0.0, center - margin)
            ci_high = min(1.0, center + margin)
        else:
            ci_low, ci_high = 0.0, 1.0

        scenarios.append({
            "description": cluster["representative_text"],
            "probability": round(raw_probability, 3),
            "ci": [round(ci_low, 3), round(ci_high, 3)],
            "agreement_ratio": round(agreement, 3),
            "mean_confidence": round(confidence, 3),
            "supporting_colonies": len(cluster.get("colony_ids", [])),
            "total_colonies": total_colonies,
            "claim_count": cluster["claim_count"],
            "cluster_id": cluster["cluster_id"],
        })

    # 確率順にソート
    scenarios.sort(key=lambda s: s["probability"], reverse=True)

    # 多様性スコア (Colony 間の結果のばらつき)
    diversity_score = _compute_diversity_score(clusters, total_colonies)

    # シャノンエントロピー
    probs = [s["probability"] for s in scenarios if s["probability"] > 0]
    if probs:
        total = sum(probs)
        normalized = [p / total for p in probs]
        entropy = -sum(p * math.log2(p) for p in normalized if p > 0)
    else:
        entropy = 0.0

    # Colony 間合意マトリクス
    agreement_matrix = _compute_agreement_matrix(clusters, colony_results)

    # DB 保存
    result = AggregationResult(
        id=str(uuid.uuid4()),
        swarm_id=swarm_id,
        scenarios=scenarios,
        diversity_score=round(diversity_score, 3),
        entropy=round(entropy, 3),
        colony_agreement_matrix=agreement_matrix,
        metadata_json={
            "total_claims": sum(c["claim_count"] for c in clusters),
            "total_clusters": len(clusters),
            "total_colonies": total_colonies,
        },
    )
    session.add(result)
    await session.flush()

    logger.info(
        f"Aggregation for swarm {swarm_id}: "
        f"{len(scenarios)} scenarios, diversity={diversity_score:.3f}, entropy={entropy:.3f}"
    )

    return {
        "scenarios": scenarios,
        "diversity_score": diversity_score,
        "entropy": entropy,
        "agreement_matrix": agreement_matrix,
    }


def _compute_diversity_score(clusters: list[dict], total_colonies: int) -> float:
    """Colony 結果の多様性スコアを計算する。

    高い値 = Colony 間で結果がばらついている（良い多様性）
    低い値 = Colony が収束している（群集行動の兆候）
    """
    if not clusters or total_colonies <= 1:
        return 0.0

    # 各クラスタの合意率の分散
    agreements = [c["agreement_ratio"] for c in clusters]
    if len(agreements) <= 1:
        return 0.0

    variance = np.var(agreements)
    # 正規化: 0-1 スケール
    # 全 Colony が全クラスタに均等に分布 → 高多様性
    # 全 Colony が1つのクラスタに集中 → 低多様性
    mean_agreement = np.mean(agreements)
    if mean_agreement > 0:
        cv = math.sqrt(variance) / mean_agreement  # 変動係数
        return min(1.0, cv)
    return 0.0


def _compute_agreement_matrix(
    clusters: list[dict],
    colony_results: list[dict],
) -> dict:
    """Colony 間の合意マトリクスを計算する。"""
    colony_ids = [r["colony_id"] for r in colony_results]
    n = len(colony_ids)
    if n <= 1:
        return {"colony_ids": colony_ids, "matrix": [[1.0]]}

    # 各 Colony がどのクラスタに属する主張を持っているか
    colony_cluster_map: dict[str, set[str]] = {cid: set() for cid in colony_ids}
    for cluster in clusters:
        for cid in cluster.get("colony_ids", []):
            if cid in colony_cluster_map:
                colony_cluster_map[cid].add(cluster["cluster_id"])

    # Jaccard 類似度で合意度を計算
    matrix = []
    for i, cid_i in enumerate(colony_ids):
        row = []
        for j, cid_j in enumerate(colony_ids):
            if i == j:
                row.append(1.0)
            else:
                set_i = colony_cluster_map.get(cid_i, set())
                set_j = colony_cluster_map.get(cid_j, set())
                if set_i or set_j:
                    jaccard = len(set_i & set_j) / len(set_i | set_j)
                else:
                    jaccard = 0.0
                row.append(round(jaccard, 3))
        matrix.append(row)

    return {
        "colony_ids": colony_ids,
        "matrix": matrix,
    }
