"""主張クラスタリング: embedding + LLM による多段階クラスタリング

Phase 1: Embedding cosine similarity で粗いクラスタを生成
Phase 2: LLM でクラスタ間の意味的重複を検出し統合
Phase 3: 代表テキストを LLM で再生成（複数主張の統合要約）
"""

import json
import logging
import uuid

import httpx
import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.config import settings
from src.app.llm.client import llm_client
from src.app.models.claim_cluster import ClaimCluster

logger = logging.getLogger(__name__)

# クラスタリング設定
MAX_FINAL_SCENARIOS = 7  # 最終シナリオ数の上限
EMBEDDING_DISTANCE_THRESHOLD = 0.65  # Phase 1: より積極的にクラスタ化 (旧: 0.85)


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


async def _llm_merge_clusters(clusters: list[dict]) -> list[list[int]]:
    """LLM でクラスタ間の意味的重複を検出し、統合グループを返す。

    MiroFish の InsightForge パターンに倣い、
    多次元的にクラスタの意味的類似性を分析する。
    """
    if len(clusters) <= MAX_FINAL_SCENARIOS:
        return [[i] for i in range(len(clusters))]

    cluster_summaries = []
    for i, c in enumerate(clusters):
        texts = [claim["claim_text"] for claim in c.get("claims", [])]
        summary = c["representative_text"]
        if len(texts) > 1:
            summary += f" (他{len(texts)-1}件の類似主張を含む)"
        cluster_summaries.append(f"[{i}] {summary}")

    prompt = f"""以下の{len(cluster_summaries)}個のシナリオクラスタを分析し、意味的に重複・類似するものを統合グループにまとめてください。
最終的に{MAX_FINAL_SCENARIOS}個以下のグループにしてください。

## クラスタ一覧
{chr(10).join(cluster_summaries)}

## ルール
- 同じテーマ・結論を異なる表現で述べているクラスタは統合する
- 明確に異なるシナリオ（楽観/悲観、異なるアクター、異なる因果関係）は分離する
- 各グループに統合後のシナリオ説明文を生成する

## 出力形式（JSON）
{{
  "groups": [
    {{
      "cluster_indices": [0, 3, 5],
      "merged_description": "統合後のシナリオ説明（具体的かつ簡潔に）"
    }}
  ]
}}

重要: 必ず有効な JSON のみを出力してください。"""

    try:
        result, _ = await llm_client.call(
            task_name="report_generate",
            system_prompt="あなたはシナリオ分析の専門家です。類似するシナリオを統合し、重複を排除してください。",
            user_prompt=prompt,
            response_format={"type": "json_object"},
        )
        if isinstance(result, dict):
            groups = result.get("groups", [])
            if groups:
                return [
                    {
                        "indices": g["cluster_indices"],
                        "description": g.get("merged_description", ""),
                    }
                    for g in groups
                ]
    except Exception as e:
        logger.warning(f"LLM cluster merge failed, using top-N fallback: {e}")

    # フォールバック: 上位N個を選択
    return [{"indices": [i], "description": ""} for i in range(min(len(clusters), MAX_FINAL_SCENARIOS))]


async def cluster_claims(
    session: AsyncSession,
    simulation_id: str,
    claims: list[dict],
    distance_threshold: float = EMBEDDING_DISTANCE_THRESHOLD,
) -> list[dict]:
    """多段階クラスタリング: Embedding → LLM統合 → 代表テキスト再生成。"""
    if not claims:
        return []

    # === Phase 1: Embedding ベースの粗いクラスタリング ===
    texts = [c["claim_text"] for c in claims]
    try:
        embeddings = await _get_embeddings(texts)
    except Exception as e:
        logger.warning(f"Embedding API failed, falling back to simple clustering: {e}")
        return await _fallback_clustering(session, simulation_id, claims)

    if not embeddings:
        return await _fallback_clustering(session, simulation_id, claims)

    X = np.array(embeddings)
    sim_matrix = cosine_similarity(X)
    distance_matrix = 1.0 - sim_matrix

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

    # Phase 1 クラスタ構築
    cluster_map: dict[int, list[dict]] = {}
    for i, label in enumerate(labels):
        if label not in cluster_map:
            cluster_map[label] = []
        claim_with_embedding = {**claims[i], "embedding": embeddings[i]}
        cluster_map[label].append(claim_with_embedding)

    phase1_clusters = []
    for cluster_idx, cluster_claims_list in sorted(cluster_map.items()):
        representative = max(cluster_claims_list, key=lambda c: c["confidence"])
        colony_ids = set(c["colony_id"] for c in cluster_claims_list)
        all_colony_ids = set(c["colony_id"] for c in claims)
        agreement_ratio = len(colony_ids) / max(len(all_colony_ids), 1)
        mean_confidence = float(np.mean([c["confidence"] for c in cluster_claims_list]))

        phase1_clusters.append({
            "representative_text": representative["claim_text"],
            "claim_count": len(cluster_claims_list),
            "agreement_ratio": agreement_ratio,
            "mean_confidence": mean_confidence,
            "colony_ids": list(colony_ids),
            "claims": cluster_claims_list,
        })

    logger.info(f"Phase 1: {len(claims)} claims → {len(phase1_clusters)} clusters")

    # === Phase 2: LLM によるクラスタ統合 ===
    if len(phase1_clusters) > MAX_FINAL_SCENARIOS:
        merge_groups = await _llm_merge_clusters(phase1_clusters)
    else:
        merge_groups = [{"indices": [i], "description": ""} for i in range(len(phase1_clusters))]

    # === Phase 3: 統合クラスタの構築 ===
    final_clusters = []
    for group_idx, group in enumerate(merge_groups):
        indices = group["indices"]
        merged_description = group.get("description", "")

        # 統合されるクラスタの全主張を集約
        all_group_claims = []
        all_colony_ids = set()
        total_confidence = 0.0
        total_count = 0

        for idx in indices:
            if idx < len(phase1_clusters):
                c = phase1_clusters[idx]
                all_group_claims.extend(c["claims"])
                all_colony_ids.update(c["colony_ids"])
                total_confidence += c["mean_confidence"] * c["claim_count"]
                total_count += c["claim_count"]

        if not all_group_claims:
            continue

        # 代表テキスト: LLM統合説明があればそれを使用、なければ最高confidence
        if merged_description:
            rep_text = merged_description
        else:
            rep_text = max(all_group_claims, key=lambda c: c["confidence"])["claim_text"]

        all_colony_ids_global = set(c["colony_id"] for c in claims)
        agreement_ratio = len(all_colony_ids) / max(len(all_colony_ids_global), 1)
        mean_confidence = total_confidence / max(total_count, 1)

        # centroid
        group_embeddings = [c["embedding"] for c in all_group_claims if "embedding" in c]
        centroid = np.mean(group_embeddings, axis=0).tolist() if group_embeddings else []

        cluster_record = ClaimCluster(
            id=str(uuid.uuid4()),
            simulation_id=simulation_id,
            cluster_index=group_idx,
            representative_text=rep_text,
            claim_count=total_count,
            agreement_ratio=float(agreement_ratio),
            mean_confidence=float(mean_confidence),
            centroid_embedding=centroid,
        )
        session.add(cluster_record)

        final_clusters.append({
            "cluster_id": cluster_record.id,
            "cluster_index": group_idx,
            "representative_text": rep_text,
            "claim_count": total_count,
            "agreement_ratio": float(agreement_ratio),
            "mean_confidence": float(mean_confidence),
            "colony_ids": list(all_colony_ids),
            "claims": all_group_claims,
        })

    await session.flush()
    logger.info(
        f"Phase 2+3: {len(phase1_clusters)} clusters → {len(final_clusters)} final scenarios "
        f"for swarm {simulation_id}"
    )
    return final_clusters


async def _fallback_clustering(
    session: AsyncSession,
    simulation_id: str,
    claims: list[dict],
) -> list[dict]:
    """Embedding API が使えない場合のフォールバック: LLM のみでクラスタリング。"""
    # まず LLM で直接グルーピングを試みる
    if len(claims) > 1:
        claim_texts = [f"[{i}] {c['claim_text']}" for i, c in enumerate(claims)]
        prompt = f"""以下の{len(claims)}個の予測主張を意味的にグルーピングしてください。
{MAX_FINAL_SCENARIOS}個以下のグループにまとめ、各グループの統合説明を生成してください。

{chr(10).join(claim_texts)}

## 出力形式（JSON）
{{
  "groups": [
    {{
      "claim_indices": [0, 3],
      "description": "グループの統合説明"
    }}
  ]
}}

重要: 必ず有効な JSON のみを出力してください。"""

        try:
            result, _ = await llm_client.call(
                task_name="report_generate",
                system_prompt="あなたは予測主張の分類専門家です。",
                user_prompt=prompt,
                response_format={"type": "json_object"},
            )
            if isinstance(result, dict) and result.get("groups"):
                clusters = []
                all_colony_ids = set(c["colony_id"] for c in claims)
                for gi, group in enumerate(result["groups"]):
                    indices = group.get("claim_indices", [])
                    group_claims = [claims[i] for i in indices if i < len(claims)]
                    if not group_claims:
                        continue
                    colony_ids = set(c["colony_id"] for c in group_claims)
                    mean_conf = float(np.mean([c["confidence"] for c in group_claims]))

                    cluster_record = ClaimCluster(
                        id=str(uuid.uuid4()),
                        simulation_id=simulation_id,
                        cluster_index=gi,
                        representative_text=group.get("description", group_claims[0]["claim_text"]),
                        claim_count=len(group_claims),
                        agreement_ratio=len(colony_ids) / max(len(all_colony_ids), 1),
                        mean_confidence=mean_conf,
                    )
                    session.add(cluster_record)
                    clusters.append({
                        "cluster_id": cluster_record.id,
                        "cluster_index": gi,
                        "representative_text": cluster_record.representative_text,
                        "claim_count": len(group_claims),
                        "agreement_ratio": float(cluster_record.agreement_ratio),
                        "mean_confidence": mean_conf,
                        "colony_ids": list(colony_ids),
                        "claims": group_claims,
                    })
                await session.flush()
                return clusters
        except Exception as e:
            logger.warning(f"LLM fallback clustering failed: {e}")

    # 最終フォールバック: 各主張を独立クラスタ
    clusters = []
    for i, claim in enumerate(claims):
        cluster_id = str(uuid.uuid4())
        cluster_record = ClaimCluster(
            id=cluster_id,
            simulation_id=simulation_id,
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

    await session.flush()
    return clusters
