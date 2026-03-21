"""ネットワーク生成: Watts-Strogatz 小世界ネットワーク + 属性ベースクラスタリング"""

import logging
import random
import uuid
from typing import Any

from src.app.config import settings

logger = logging.getLogger(__name__)

RELATION_TYPES = ["friend", "family", "colleague", "neighbor", "acquaintance"]
RELATION_WEIGHTS = [0.20, 0.10, 0.25, 0.15, 0.30]


def _attribute_similarity(a: dict, b: dict) -> float:
    """2つのエージェントプロフィールの属性類似度を計算する (0-1)。"""
    score = 0.0
    count = 0

    # 地域
    if a.get("demographics", {}).get("region") == b.get("demographics", {}).get("region"):
        score += 1.0
    count += 1

    # 年齢（10歳以内で類似）
    age_a = a.get("demographics", {}).get("age", 40)
    age_b = b.get("demographics", {}).get("age", 40)
    age_diff = abs(age_a - age_b)
    score += max(0, 1.0 - age_diff / 30.0)
    count += 1

    # 教育レベル
    if a.get("demographics", {}).get("education") == b.get("demographics", {}).get("education"):
        score += 1.0
    count += 1

    # 収入層
    if a.get("demographics", {}).get("income_bracket") == b.get("demographics", {}).get("income_bracket"):
        score += 1.0
    count += 1

    return score / count if count > 0 else 0.0


def _determine_relation_type(similarity: float) -> str:
    """類似度に基づいて関係タイプを決定する。"""
    if similarity > 0.8:
        # 高い類似度: friend/colleague が多い
        return random.choices(
            ["friend", "family", "colleague"],
            weights=[0.4, 0.2, 0.4],
            k=1,
        )[0]
    elif similarity > 0.5:
        return random.choices(
            RELATION_TYPES,
            weights=RELATION_WEIGHTS,
            k=1,
        )[0]
    else:
        return "acquaintance"


def generate_watts_strogatz_edges(
    agents: list[dict],
    population_id: str,
    k: int = 6,
    beta: float = 0.3,
    cluster_by_attributes: bool = True,
) -> list[dict[str, Any]]:
    """Watts-Strogatz 小世界ネットワークを生成する。

    1. リング格子で k 近傍を接続
    2. 確率 beta で各エッジを再配線（ショートカット追加）
    3. 属性ベースクラスタリングが有効な場合、属性類似度でソートしてからリング構築
    """
    n = len(agents)
    if n < 3:
        return []

    # 属性ベースクラスタリング: 地域→年齢でソートし、類似住民が近傍になるようにする
    if cluster_by_attributes:
        sorted_indices = sorted(
            range(n),
            key=lambda i: (
                agents[i].get("demographics", {}).get("region", ""),
                agents[i].get("demographics", {}).get("age", 0),
            ),
        )
    else:
        sorted_indices = list(range(n))

    # index_map: ソート後の位置 → 元のエージェントindex
    # リング上の位置pos → sorted_indices[pos]が元のエージェントインデックス

    edges_set: set[tuple[int, int]] = set()

    # Step 1: リング格子
    half_k = k // 2
    for pos in range(n):
        for j in range(1, half_k + 1):
            neighbor_pos = (pos + j) % n
            orig_i = sorted_indices[pos]
            orig_j = sorted_indices[neighbor_pos]
            edge = (min(orig_i, orig_j), max(orig_i, orig_j))
            edges_set.add(edge)

    # Step 2: 再配線
    edges_list = list(edges_set)
    for idx, (i, j) in enumerate(edges_list):
        if random.random() < beta:
            # j を新しいランダムターゲットに置き換え
            new_j = random.randint(0, n - 1)
            attempts = 0
            while new_j == i or (min(i, new_j), max(i, new_j)) in edges_set:
                new_j = random.randint(0, n - 1)
                attempts += 1
                if attempts > 100:
                    break
            if attempts <= 100:
                edges_set.discard((min(i, j), max(i, j)))
                edges_set.add((min(i, new_j), max(i, new_j)))

    # エッジオブジェクト生成
    edge_objects = []
    for i, j in edges_set:
        similarity = _attribute_similarity(agents[i], agents[j])
        relation_type = _determine_relation_type(similarity)
        strength = round(0.3 + similarity * 0.5 + random.uniform(-0.1, 0.1), 3)
        strength = max(0.1, min(1.0, strength))

        edge_objects.append({
            "id": str(uuid.uuid4()),
            "population_id": population_id,
            "agent_id": agents[i]["id"],
            "target_id": agents[j]["id"],
            "relation_type": relation_type,
            "strength": strength,
        })

    logger.info(
        "Generated %d social edges for %d agents (k=%d, beta=%.2f)",
        len(edge_objects), n, k, beta,
    )
    return edge_objects


async def generate_network(
    agents: list[dict],
    population_id: str,
) -> list[dict[str, Any]]:
    """人口ミックス設定に基づいてネットワークを生成する。"""
    mix_config = settings.load_population_mix_config()
    network_cfg = mix_config.get("population", {}).get("network", {})

    k = network_cfg.get("k", 6)
    beta = network_cfg.get("beta", 0.3)
    cluster = network_cfg.get("cluster_by_attributes", True)

    return generate_watts_strogatz_edges(agents, population_id, k, beta, cluster)
