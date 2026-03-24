"""RelationExtractor: エンティティペア間の関係抽出（イントラ + クロスチャンク）"""

import asyncio
import logging

from src.app.llm.client import llm_client
from src.app.llm.prompts import RELATION_EXTRACT_SYSTEM, RELATION_EXTRACT_USER
from src.app.services.graphrag.ontology_generator import build_extraction_prompt_from_ontology

logger = logging.getLogger(__name__)


class RelationExtractor:
    def __init__(self, max_concurrent: int = 5, cross_chunk_top_n: int = 20):
        self.max_concurrent = max_concurrent
        self.cross_chunk_top_n = cross_chunk_top_n

    async def extract_relations(
        self,
        entities: list[dict],
        chunks: list[dict],
        ontology: dict | None = None,
    ) -> list[dict]:
        """エンティティとチャンクから関係を抽出する。

        1. イントラチャンク: 同一チャンク内の共起エンティティペアから関係抽出
        2. クロスチャンク: 重要度上位エンティティ間の概念的関係を抽出
        """
        # オントロジーからガイダンスを生成
        _, relation_guidance = (
            build_extraction_prompt_from_ontology(ontology)
            if ontology else ("", "")
        )

        # チャンクごとにエンティティをグループ化
        chunk_entities: dict[int, list[dict]] = {}
        for e in entities:
            ci = e.get("source_chunk", 0)
            chunk_entities.setdefault(ci, []).append(e)

        chunk_text_map = {c["index"]: c["text"] for c in chunks}

        # === イントラチャンク関係抽出 ===
        sem = asyncio.Semaphore(self.max_concurrent)
        tasks = []
        for chunk_idx, ents in chunk_entities.items():
            if len(ents) < 2:
                continue
            chunk_text = chunk_text_map.get(chunk_idx, "")
            entity_names = [e["name"] for e in ents]
            tasks.append(self._extract_chunk_relations(
                entity_names, chunk_text, sem, relation_guidance,
            ))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_relations = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"Intra-chunk relation extraction failed: {result}")
                continue
            all_relations.extend(result)

        logger.info(f"Intra-chunk: extracted {len(all_relations)} relations")

        # === クロスチャンク関係抽出 ===
        cross_relations = await self._extract_cross_chunk_relations(
            entities, chunks, sem, relation_guidance,
        )
        all_relations.extend(cross_relations)

        logger.info(
            f"Total: {len(all_relations)} relations "
            f"(intra: {len(all_relations) - len(cross_relations)}, cross: {len(cross_relations)})"
        )
        return all_relations

    async def _extract_chunk_relations(
        self,
        entity_names: list[str],
        chunk_text: str,
        sem: asyncio.Semaphore,
        relation_guidance: str = "",
    ) -> list[dict]:
        """チャンク内のエンティティ間の関係を抽出する。"""
        async with sem:
            entities_str = ", ".join(entity_names)
            user_prompt = RELATION_EXTRACT_USER.format(
                entities=entities_str,
                chunk_text=chunk_text,
            )
            if relation_guidance:
                user_prompt += f"\n\n{relation_guidance}"

            result, _usage = await llm_client.call_with_retry(
                task_name="relation_extract",
                system_prompt=RELATION_EXTRACT_SYSTEM,
                user_prompt=user_prompt,
                response_format={"type": "json_object"},
            )

            if isinstance(result, dict):
                return result.get("relations", [])
            return []

    async def _extract_cross_chunk_relations(
        self,
        entities: list[dict],
        chunks: list[dict],
        sem: asyncio.Semaphore,
        relation_guidance: str = "",
    ) -> list[dict]:
        """異なるチャンクに出現する重要エンティティ間の概念的関係を抽出する。"""
        # importance_score 上位のエンティティを選出
        sorted_entities = sorted(
            entities,
            key=lambda e: e.get("importance_score", 0.5),
            reverse=True,
        )
        top_entities = sorted_entities[:self.cross_chunk_top_n]

        if len(top_entities) < 2:
            return []

        # チャンクインデックスでグループ化
        entity_chunks: dict[str, int] = {
            e["name"]: e.get("source_chunk", 0) for e in top_entities
        }

        # 異なるチャンクに属するペアを候補として選出
        cross_pairs: list[tuple[str, str]] = []
        names = [e["name"] for e in top_entities]
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                if entity_chunks.get(names[i]) != entity_chunks.get(names[j]):
                    cross_pairs.append((names[i], names[j]))

        if not cross_pairs:
            return []

        # バッチでLLM検証（最大10ペアずつ）
        batch_size = 10
        all_cross_relations = []

        for batch_start in range(0, len(cross_pairs), batch_size):
            batch = cross_pairs[batch_start:batch_start + batch_size]
            relations = await self._validate_cross_chunk_batch(
                batch, top_entities, sem, relation_guidance,
            )
            all_cross_relations.extend(relations)

        logger.info(
            f"Cross-chunk: validated {len(cross_pairs)} pairs, "
            f"found {len(all_cross_relations)} relations"
        )
        return all_cross_relations

    async def _validate_cross_chunk_batch(
        self,
        pairs: list[tuple[str, str]],
        entities: list[dict],
        sem: asyncio.Semaphore,
        relation_guidance: str = "",
    ) -> list[dict]:
        """クロスチャンクエンティティペアのバッチ関係検証。"""
        entity_descriptions = {
            e["name"]: e.get("description", "") for e in entities
        }

        pairs_text = "\n".join(
            f"- {a} ({entity_descriptions.get(a, '')}) ←→ {b} ({entity_descriptions.get(b, '')})"
            for a, b in pairs
        )

        system_prompt = (
            "あなたはナレッジグラフの関係抽出の専門家です。\n"
            "以下のエンティティペアについて、概念的な関係があるかを判定してください。\n"
            "関係がないペアは出力に含めないでください。\n"
            "confidence は 0.5 以上のもののみ出力してください。"
        )

        user_prompt = (
            f"以下のエンティティペア間に関係があるか判定してください:\n\n{pairs_text}\n\n"
            "出力はJSON形式で:\n"
            '{"relations": [{"source": "名前", "target": "名前", '
            '"type": "関係型", "evidence": "推定根拠", "confidence": 0.0-1.0}]}'
        )
        if relation_guidance:
            user_prompt += f"\n\n{relation_guidance}"

        async with sem:
            try:
                result, _usage = await llm_client.call_with_retry(
                    task_name="cross_chunk_relation",
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_format={"type": "json_object"},
                )
                if isinstance(result, dict):
                    relations = result.get("relations", [])
                    # confidence 0.5 以上のみ
                    return [r for r in relations if r.get("confidence", 0) >= 0.5]
            except Exception as e:
                logger.warning(f"Cross-chunk relation validation failed: {e}")

        return []
