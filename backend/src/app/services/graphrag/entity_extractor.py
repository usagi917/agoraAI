"""EntityExtractor: チャンク単位の並列LLMエンティティ抽出"""

import asyncio
import logging

from src.app.llm.client import llm_client
from src.app.llm.prompts import ENTITY_EXTRACT_SYSTEM, ENTITY_EXTRACT_USER
from src.app.services.graphrag.ontology_generator import build_extraction_prompt_from_ontology

logger = logging.getLogger(__name__)


class EntityExtractor:
    def __init__(self, max_concurrent: int = 5):
        self.max_concurrent = max_concurrent

    async def extract_from_chunks(
        self, chunks: list[dict], run_id: str, ontology: dict | None = None,
    ) -> list[dict]:
        """複数チャンクから並列でエンティティを抽出する。"""
        # オントロジーからガイダンスを生成
        entity_guidance = ""
        if ontology:
            entity_guidance, _ = build_extraction_prompt_from_ontology(ontology)

        sem = asyncio.Semaphore(self.max_concurrent)
        tasks = [self._extract_one(chunk, sem, entity_guidance) for chunk in chunks]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_entities = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"Entity extraction failed for chunk {i}: {result}")
                continue
            all_entities.extend(result)

        logger.info(f"Extracted {len(all_entities)} entities from {len(chunks)} chunks")
        return all_entities

    async def _extract_one(
        self, chunk: dict, sem: asyncio.Semaphore, entity_guidance: str = "",
    ) -> list[dict]:
        """1チャンクからエンティティを抽出する。"""
        async with sem:
            user_prompt = ENTITY_EXTRACT_USER.format(
                chunk_text=chunk["text"],
                chunk_index=chunk["index"],
            )
            if entity_guidance:
                user_prompt += f"\n\n{entity_guidance}"

            result, _usage = await llm_client.call_with_retry(
                task_name="entity_extract",
                system_prompt=ENTITY_EXTRACT_SYSTEM,
                user_prompt=user_prompt,
                response_format={"type": "json_object"},
            )

            if isinstance(result, dict):
                entities = result.get("entities", [])
                for e in entities:
                    e["source_chunk"] = chunk["index"]
                return entities
            return []
