"""主張クラスタリング: embedding による意味的クラスタリング

OpenAI embedding API で各主張をベクトル化し、
cosine similarity に基づいてクラスタリングする。
"""

import logging
import uuid

import httpx
import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.config import settings
from src.app.models.claim_cluster import ClaimCluster

logger = logging.getLogger(__name__)


async def _get_embeddings(texts: list[str]) -> list[list[float]]:
    """OpenAI embedding API でテキストをベクトル化する。"""
    if not texts:
        return []

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/embeddings",
            json={
                "model": "text-embedding-3-small",
                "input": texts,
            },
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    embeddings = [item["embedding"] for item in data["data"]]
    return embeddings


async def cluster_claims(
    session: AsyncSession,
    swarm_id: str,
    claims: list[dict],
    distance_threshold: float = 0.85,
) -> list[dict]:
    """主張をクラスタリングし、各クラスタの代表テキストと統計を返す。"""
    if not claims:
        return []

    # embedding 取得
    texts = [c["claim_text"] for c in claims]
    try:
        embeddings = await _get_embeddings(texts)
    except Exception as e:
        logger.warning(f"Embedding API failed, falling back to simple clustering: {e}")
        return _fallback_clustering(session, swarm_id, claims)

    if not embeddings:
        return _fallback_clustering(session, swarm_id, claims)

    # embedding を numpy 配列に変換
    X = np.array(embeddings)

    # cosine similarity 行列
    sim_matrix = cosine_similarity(X)
    distance_matrix = 1.0 - sim_matrix

    # AgglomerativeClustering
    n_claims = len(claims)
    if n_claims <= 1:
        labels = [0]
    else:
        clustering = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=1.0 - distance_threshold,
            metric="precomputed",
            linkage="average",
        )
        labels = clustering.fit_predict(distance_matrix)

    # クラスタ構築
    cluster_map: dict[int, list[dict]] = {}
    for i, label in enumerate(labels):
        if label not in cluster_map:
            cluster_map[label] = []
        claim_with_embedding = {**claims[i], "embedding": embeddings[i]}
        cluster_map[label].append(claim_with_embedding)

    clusters = []
    for cluster_idx, cluster_claims_list in sorted(cluster_map.items()):
        # 最も confidence が高い主張を代表テキストとする
        representative = max(cluster_claims_list, key=lambda c: c["confidence"])

        # クラスタの centroid
        cluster_embeddings = np.array([c["embedding"] for c in cluster_claims_list])
        centroid = cluster_embeddings.mean(axis=0).tolist()

        # 合意率 = このクラスタの Colony 数 / 全 Colony 数
        colony_ids = set(c["colony_id"] for c in cluster_claims_list)
        all_colony_ids = set(c["colony_id"] for c in claims)
        agreement_ratio = len(colony_ids) / max(len(all_colony_ids), 1)

        # 平均 confidence
        mean_confidence = np.mean([c["confidence"] for c in cluster_claims_list])

        cluster_record = ClaimCluster(
            id=str(uuid.uuid4()),
            swarm_id=swarm_id,
            cluster_index=cluster_idx,
            representative_text=representative["claim_text"],
            claim_count=len(cluster_claims_list),
            agreement_ratio=float(agreement_ratio),
            mean_confidence=float(mean_confidence),
            centroid_embedding=centroid,
        )
        session.add(cluster_record)

        clusters.append({
            "cluster_id": cluster_record.id,
            "cluster_index": cluster_idx,
            "representative_text": representative["claim_text"],
            "claim_count": len(cluster_claims_list),
            "agreement_ratio": float(agreement_ratio),
            "mean_confidence": float(mean_confidence),
            "colony_ids": list(colony_ids),
            "claims": cluster_claims_list,
        })

    await session.flush()
    logger.info(f"Clustered {len(claims)} claims into {len(clusters)} clusters for swarm {swarm_id}")
    return clusters


def _fallback_clustering(
    session: AsyncSession,
    swarm_id: str,
    claims: list[dict],
) -> list[dict]:
    """Embedding API が使えない場合のフォールバック: 各主張を独立クラスタとする。"""
    clusters = []
    for i, claim in enumerate(claims):
        cluster_id = str(uuid.uuid4())
        cluster_record = ClaimCluster(
            id=cluster_id,
            swarm_id=swarm_id,
            cluster_index=i,
            representative_text=claim["claim_text"],
            claim_count=1,
            agreement_ratio=1.0 / max(len(set(c["colony_id"] for c in claims)), 1),
            mean_confidence=claim["confidence"],
        )
        session.add(cluster_record)

        clusters.append({
            "cluster_id": cluster_id,
            "cluster_index": i,
            "representative_text": claim["claim_text"],
            "claim_count": 1,
            "agreement_ratio": cluster_record.agreement_ratio,
            "mean_confidence": claim["confidence"],
            "colony_ids": [claim["colony_id"]],
            "claims": [claim],
        })

    return clusters
