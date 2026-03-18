"""PerceptionEngine: 環境知覚（情報非対称性の実現）"""

import json
import logging
import random

from src.app.llm.client import llm_client
from src.app.llm.prompts import BDI_PERCEIVE_SYSTEM, BDI_PERCEIVE_USER
from src.app.services.cost_tracker import record_usage

logger = logging.getLogger(__name__)


class PerceptionEngine:
    """エージェントの環境知覚を管理する。

    情報非対称性を実現:
    - visibility_radius: 全体情報のうち観察可能な割合
    - noise_level: 知覚ノイズ
    """

    def __init__(self, visibility_radius: float = 0.7, noise_level: float = 0.1):
        self.visibility_radius = visibility_radius
        self.noise_level = noise_level

    def filter_environment(
        self,
        world_state: dict,
        agent_entity_id: str | None,
        agent_relationships: list[dict] | None = None,
    ) -> dict:
        """エージェントの視点から環境をフィルタリングする。"""
        entities = world_state.get("entities", [])
        relations = world_state.get("relations", [])

        if not entities:
            return world_state

        # 自身に関連するエンティティは優先的に可視化
        related_ids = set()
        if agent_entity_id:
            related_ids.add(agent_entity_id)
        if agent_relationships:
            for rel in agent_relationships:
                related_ids.add(rel.get("target_agent", ""))

        # 関連エンティティ + ランダムサンプリングで可視範囲を決定
        visible_entities = []
        for e in entities:
            if e.get("id") in related_ids:
                visible_entities.append(e)
            elif random.random() < self.visibility_radius:
                visible_entities.append(self._add_noise(e))

        visible_ids = {e["id"] for e in visible_entities}
        visible_relations = [
            r for r in relations
            if r.get("source") in visible_ids and r.get("target") in visible_ids
        ]

        return {
            **world_state,
            "entities": visible_entities,
            "relations": visible_relations,
        }

    def _add_noise(self, entity: dict) -> dict:
        """エンティティの知覚にノイズを追加する。"""
        if self.noise_level <= 0:
            return entity

        noisy = dict(entity)
        for key in ("importance_score", "activity_score", "sentiment_score"):
            if key in noisy and isinstance(noisy[key], (int, float)):
                noise = random.gauss(0, self.noise_level)
                noisy[key] = max(0.0, min(1.0, float(noisy[key]) + noise))
        return noisy

    async def perceive(
        self,
        session,
        run_id: str,
        agent_name: str,
        agent_role: str,
        agent_goals: list[str],
        filtered_environment: dict,
        relevant_memories: list[dict],
        recent_events: list[dict],
    ) -> list[dict]:
        """LLMで環境から重要な観察を抽出する。"""
        env_str = json.dumps(
            {
                "entities": [
                    {"id": e.get("id"), "label": e.get("label"), "type": e.get("entity_type"),
                     "importance": e.get("importance_score")}
                    for e in filtered_environment.get("entities", [])[:20]
                ],
                "relations": [
                    {"source": r.get("source"), "target": r.get("target"), "type": r.get("relation_type")}
                    for r in filtered_environment.get("relations", [])[:20]
                ],
            },
            ensure_ascii=False,
        )

        memories_str = "\n".join(
            f"- {m['content']}" for m in relevant_memories[:10]
        ) or "なし"

        events_str = "\n".join(
            f"- {e.get('title', '')}: {e.get('description', '')}" for e in recent_events[:10]
        ) or "なし"

        user_prompt = BDI_PERCEIVE_USER.format(
            agent_name=agent_name,
            agent_role=agent_role,
            agent_goals=json.dumps(agent_goals, ensure_ascii=False),
            environment=env_str,
            relevant_memories=memories_str,
            recent_events=events_str,
        )

        result, usage = await llm_client.call_with_retry(
            task_name="bdi_perceive",
            system_prompt=BDI_PERCEIVE_SYSTEM,
            user_prompt=user_prompt,
            response_format={"type": "json_object"},
        )

        await record_usage(session, run_id, f"bdi_perceive_{agent_name}", usage)

        if isinstance(result, dict):
            return result.get("observations", [])
        return []
