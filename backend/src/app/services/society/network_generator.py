"""ネットワーク生成: Watts-Strogatz 小世界ネットワーク + Barabasi-Albert + ハイブリッド"""

import logging
import random
import uuid
from typing import Any

import networkx as nx

from src.app.config import settings

logger = logging.getLogger(__name__)

RELATION_TYPES = ["friend", "family", "colleague", "neighbor", "acquaintance"]
RELATION_WEIGHTS = [0.20, 0.10, 0.25, 0.15, 0.30]


def _edge_id(
    population_id: str,
    agent_id: str,
    target_id: str,
    relation_type: str,
    seed: int | None,
) -> str:
    if seed is None:
        return str(uuid.uuid4())
    name = f"{population_id}:{agent_id}:{target_id}:{relation_type}:{seed}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, name))


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


def _determine_relation_type(similarity: float, rng: random.Random | None = None) -> str:
    """類似度に基づいて関係タイプを決定する。"""
    rng = rng or random
    if similarity > 0.8:
        # 高い類似度: friend/colleague が多い
        return rng.choices(
            ["friend", "family", "colleague"],
            weights=[0.4, 0.2, 0.4],
            k=1,
        )[0]
    elif similarity > 0.5:
        return rng.choices(
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
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """Watts-Strogatz 小世界ネットワークを生成する。

    1. リング格子で k 近傍を接続
    2. 確率 beta で各エッジを再配線（ショートカット追加）
    3. 属性ベースクラスタリングが有効な場合、属性類似度でソートしてからリング構築
    """
    n = len(agents)
    if n < 3:
        return []
    rng = random.Random(seed) if seed is not None else random.Random()

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
    edges_list = sorted(edges_set)
    for idx, (i, j) in enumerate(edges_list):
        if rng.random() < beta:
            # j を新しいランダムターゲットに置き換え
            new_j = rng.randint(0, n - 1)
            attempts = 0
            while new_j == i or (min(i, new_j), max(i, new_j)) in edges_set:
                new_j = rng.randint(0, n - 1)
                attempts += 1
                if attempts > 100:
                    break
            if attempts <= 100:
                edges_set.discard((min(i, j), max(i, j)))
                edges_set.add((min(i, new_j), max(i, new_j)))

    # エッジオブジェクト生成
    edge_objects = []
    for i, j in sorted(edges_set):
        similarity = _attribute_similarity(agents[i], agents[j])
        relation_type = _determine_relation_type(similarity, rng)
        strength = round(0.3 + similarity * 0.5 + rng.uniform(-0.1, 0.1), 3)
        strength = max(0.1, min(1.0, strength))

        edge_objects.append({
            "id": _edge_id(population_id, agents[i]["id"], agents[j]["id"], relation_type, seed),
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


def generate_barabasi_albert_edges(
    agents: list[dict],
    population_id: str,
    m: int = 3,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """Barabasi-Albert preferential attachment ネットワークを生成する。

    スケールフリー特性を持ち、少数のハブノードが多数の接続を持つ。
    これは現実の社会ネットワーク（インフルエンサー等）をモデル化する。

    Args:
        agents: エージェントリスト
        population_id: 人口ID
        m: 新規ノードあたりの接続数（次数パラメータ）
        seed: 再現性のためのランダムシード

    Returns:
        エッジオブジェクトのリスト
    """
    n = len(agents)
    if n <= m:
        return []

    rng = random.Random(seed) if seed is not None else random.Random()
    G = nx.barabasi_albert_graph(n, m, seed=seed)

    # Compute degree for strength assignment
    degrees = dict(G.degree())
    max_degree = max(degrees.values()) if degrees else 1

    edge_objects = []
    for u, v in sorted(G.edges()):
        # Strength proportional to the average degree of the two endpoints
        avg_deg = (degrees[u] + degrees[v]) / 2
        strength = round(0.3 + 0.5 * (avg_deg / max_degree) + rng.uniform(-0.05, 0.05), 3)
        strength = max(0.1, min(1.0, strength))

        similarity = _attribute_similarity(agents[u], agents[v])
        relation_type = _determine_relation_type(similarity, rng)

        edge_objects.append({
            "id": _edge_id(population_id, agents[u]["id"], agents[v]["id"], relation_type, seed),
            "population_id": population_id,
            "agent_id": agents[u]["id"],
            "target_id": agents[v]["id"],
            "relation_type": relation_type,
            "strength": strength,
        })

    logger.info(
        "Generated %d BA edges for %d agents (m=%d)",
        len(edge_objects), n, m,
    )
    return edge_objects


def generate_hybrid_edges(
    agents: list[dict],
    population_id: str,
    k: int = 6,
    beta: float = 0.3,
    m: int = 3,
    ba_ratio: float = 0.3,
    cluster_by_attributes: bool = True,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """ハイブリッドネットワーク: WS 小世界 + BA スケールフリー。

    WS のクラスタリング特性と BA のハブ特性を組み合わせる。
    ba_ratio で BA エッジの割合を制御する。

    Args:
        agents: エージェントリスト
        population_id: 人口ID
        k: WS の近傍接続数
        beta: WS の再配線確率
        m: BA の新規ノードあたり接続数
        ba_ratio: BA エッジの割合 (0.0 = WS のみ, 1.0 = BA のみ)
        cluster_by_attributes: 属性ベースクラスタリング
        seed: ランダムシード

    Returns:
        マージされたエッジオブジェクトのリスト
    """
    ba_ratio = max(0.0, min(1.0, ba_ratio))

    if ba_ratio == 0.0:
        return generate_watts_strogatz_edges(agents, population_id, k, beta, cluster_by_attributes, seed)

    if ba_ratio == 1.0:
        return generate_barabasi_albert_edges(agents, population_id, m, seed)

    # Generate both edge sets
    ws_seed = None if seed is None else seed + 1009
    ba_seed = None if seed is None else seed + 2003
    sample_rng = random.Random(seed + 3001) if seed is not None else random.Random()
    ws_edges = generate_watts_strogatz_edges(agents, population_id, k, beta, cluster_by_attributes, ws_seed)
    ba_edges = generate_barabasi_albert_edges(agents, population_id, m, ba_seed)

    # Sample from each according to ba_ratio
    n_ws = max(1, int(len(ws_edges) * (1 - ba_ratio)))
    n_ba = max(1, int(len(ba_edges) * ba_ratio))

    sampled_ws = sample_rng.sample(ws_edges, min(n_ws, len(ws_edges)))
    sampled_ba = sample_rng.sample(ba_edges, min(n_ba, len(ba_edges)))

    # Merge and deduplicate by (agent_id, target_id)
    seen: set[tuple[str, str]] = set()
    merged: list[dict[str, Any]] = []

    for e in sampled_ws + sampled_ba:
        pair = (e["agent_id"], e["target_id"])
        reverse_pair = (e["target_id"], e["agent_id"])
        if pair not in seen and reverse_pair not in seen:
            seen.add(pair)
            merged.append(e)

    logger.info(
        "Generated %d hybrid edges (WS: %d, BA: %d) for %d agents",
        len(merged), len(sampled_ws), len(sampled_ba), len(agents),
    )
    return merged


async def generate_network(
    agents: list[dict],
    population_id: str,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """人口ミックス設定に基づいてネットワークを生成する。

    config の type フィールドでトポロジーをディスパッチ:
    - "watts_strogatz" (デフォルト): WS 小世界
    - "barabasi_albert": BA スケールフリー
    - "hybrid": WS + BA ハイブリッド
    """
    mix_config = settings.load_population_mix_config()
    network_cfg = mix_config.get("population", {}).get("network", {})

    network_type = network_cfg.get("type", "watts_strogatz")
    k = network_cfg.get("k", 6)
    beta = network_cfg.get("beta", 0.3)
    cluster = network_cfg.get("cluster_by_attributes", True)
    m = network_cfg.get("m", 3)
    ba_ratio = network_cfg.get("ba_ratio", 0.3)

    if network_type == "barabasi_albert":
        return generate_barabasi_albert_edges(agents, population_id, m, seed)
    elif network_type == "hybrid":
        return generate_hybrid_edges(
            agents, population_id, k, beta, m, ba_ratio, cluster, seed,
        )
    else:
        # Default: watts_strogatz
        return generate_watts_strogatz_edges(agents, population_id, k, beta, cluster, seed)
