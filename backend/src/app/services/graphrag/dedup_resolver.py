"""DedupResolver: embedding cosine sim + LLM確認でエンティティ統合"""

import logging

import httpx
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from src.app.config import settings
from src.app.llm.client import llm_client
from src.app.llm.prompts import ENTITY_DEDUP_SYSTEM, ENTITY_DEDUP_USER

logger = logging.getLogger(__name__)


class DedupResolver:
    def __init__(self, threshold: float = 0.85):
        self.threshold = threshold

    async def deduplicate(self, entities: list[dict]) -> list[dict]:
        """エンティティの重複を検出し統合する。"""
        if len(entities) <= 1:
            return entities

        # embedding取得
        names = [e["name"] for e in entities]
        try:
            embeddings = await self._get_embeddings(names)
        except Exception as e:
            logger.warning(f"Embedding API failed for dedup, skipping: {e}")
            return entities

        if not embeddings:
            return entities

        # cosine similarity行列の計算
        X = np.array(embeddings)
        sim_matrix = cosine_similarity(X)

        # 閾値以上のペアを候補として抽出
        merge_pairs = []
        n = len(entities)
        for i in range(n):
            for j in range(i + 1, n):
                if sim_matrix[i][j] >= self.threshold:
                    merge_pairs.append((i, j, float(sim_matrix[i][j])))

        if not merge_pairs:
            # エンティティにembeddingを付与
            for i, e in enumerate(entities):
                e["embedding"] = embeddings[i]
            return entities

        # LLMで同一性を確認
        merged_indices = set()
        for i, j, sim in sorted(merge_pairs, key=lambda x: -x[2]):
            if i in merged_indices or j in merged_indices:
                continue

            is_same = await self._confirm_merge(entities[i], entities[j])
            if is_same:
                # jをiに統合
                merged = self._merge_entities(entities[i], entities[j])
                entities[i] = merged
                merged_indices.add(j)
                logger.info(
                    f"Merged entity '{entities[j]['name']}' into '{entities[i]['name']}' (sim={sim:.3f})"
                )

        # 統合されたエンティティを除外
        result = [e for idx, e in enumerate(entities) if idx not in merged_indices]

        # embeddingを付与
        for i, e in enumerate(result):
            if "embedding" not in e and i < len(embeddings):
                e["embedding"] = embeddings[i]

        logger.info(f"Dedup: {len(entities)} -> {len(result)} entities")
        return result

    async def _get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """OpenAI embedding APIでテキストをベクトル化する。"""
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/embeddings",
                json={"model": "text-embedding-3-small", "input": texts},
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        return [item["embedding"] for item in data["data"]]

    async def _confirm_merge(self, entity_a: dict, entity_b: dict) -> bool:
        """LLMで2つのエンティティが同一かを確認する。"""
        user_prompt = ENTITY_DEDUP_USER.format(
            entity_a_name=entity_a["name"],
            entity_a_description=entity_a.get("description", ""),
            entity_b_name=entity_b["name"],
            entity_b_description=entity_b.get("description", ""),
        )

        result, _usage = await llm_client.call(
            task_name="entity_dedup",
            system_prompt=ENTITY_DEDUP_SYSTEM,
            user_prompt=user_prompt,
            response_format={"type": "json_object"},
        )

        if isinstance(result, dict):
            return result.get("is_same", False)
        return False

    def _merge_entities(self, primary: dict, secondary: dict) -> dict:
        """2つのエンティティを統合する。"""
        merged = {**primary}
        # aliasesに統合元の名前を追加
        aliases = list(set(primary.get("aliases", []) + [secondary["name"]] + secondary.get("aliases", [])))
        merged["aliases"] = aliases
        # descriptionを結合（重複しない場合）
        if secondary.get("description") and secondary["description"] not in primary.get("description", ""):
            merged["description"] = f"{primary.get('description', '')} {secondary['description']}".strip()
        return merged
