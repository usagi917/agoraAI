"""RelationExtractor: エンティティペア間の関係抽出"""

import asyncio
import logging
from itertools import combinations

from src.app.llm.client import llm_client
from src.app.llm.prompts import RELATION_EXTRACT_SYSTEM, RELATION_EXTRACT_USER

logger = logging.getLogger(__name__)


class RelationExtractor:
    def __init__(self, max_concurrent: int = 5):
        self.max_concurrent = max_concurrent

    async def extract_relations(
        self, entities: list[dict], chunks: list[dict]
    ) -> list[dict]:
        """エンティティとチャンクから関係を抽出する。

        同一チャンクに出現するエンティティペアを候補として関係抽出を行う。
        """
        # チャンクごとにエンティティをグループ化
        chunk_entities: dict[int, list[dict]] = {}
        for e in entities:
            ci = e.get("source_chunk", 0)
            chunk_entities.setdefault(ci, []).append(e)

        # チャンクテキストのマップ
        chunk_text_map = {c["index"]: c["text"] for c in chunks}

        # 各チャンク内のエンティティペアについて関係抽出
        sem = asyncio.Semaphore(self.max_concurrent)
        tasks = []
        for chunk_idx, ents in chunk_entities.items():
            if len(ents) < 2:
                continue
            chunk_text = chunk_text_map.get(chunk_idx, "")
            entity_names = [e["name"] for e in ents]
            tasks.append(self._extract_chunk_relations(entity_names, chunk_text, sem))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_relations = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"Relation extraction failed: {result}")
                continue
            all_relations.extend(result)

        logger.info(f"Extracted {len(all_relations)} relations")
        return all_relations

    async def _extract_chunk_relations(
        self,
        entity_names: list[str],
        chunk_text: str,
        sem: asyncio.Semaphore,
    ) -> list[dict]:
        """チャンク内のエンティティ間の関係を抽出する。"""
        async with sem:
            entities_str = ", ".join(entity_names)
            user_prompt = RELATION_EXTRACT_USER.format(
                entities=entities_str,
                chunk_text=chunk_text,
            )

            result, _usage = await llm_client.call_with_retry(
                task_name="relation_extract",
                system_prompt=RELATION_EXTRACT_SYSTEM,
                user_prompt=user_prompt,
                response_format={"type": "json_object"},
            )

            if isinstance(result, dict):
                return result.get("relations", [])
            return []
