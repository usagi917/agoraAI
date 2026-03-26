"""主張抽出: Colony の結果から構造化された予測主張を LLM で抽出する"""

import json
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.llm.client import llm_client
from src.app.llm.prompts import CLAIM_EXTRACT_SYSTEM_V2, CLAIM_EXTRACT_USER_V2
from src.app.models.outcome_claim import OutcomeClaim
from src.app.services.cost_tracker import record_usage

logger = logging.getLogger(__name__)


async def extract_claims(
    session: AsyncSession,
    simulation_id: str,
    colony_results: list[dict],
) -> list[dict]:
    """全 Colony の結果から予測主張を抽出する。"""
    all_claims = []

    for colony_result in colony_results:
        colony_id = colony_result["colony_id"]
        colony_config = colony_result.get("colony_config")
        perspective = ""
        if colony_config:
            perspective = f"{colony_config.perspective_label} (温度: {colony_config.temperature}, 対立的: {colony_config.adversarial})"

        world_state = colony_result.get("world_state", {})
        events = colony_result.get("events", [])
        agents = colony_result.get("agents", {})

        # プロンプトサイズ縮小（より多くのコンテキストを保持）
        compact_state = {
            "entities": [
                {"label": e.get("label"), "type": e.get("entity_type"),
                 "stance": e.get("stance"), "importance": e.get("importance_score"),
                 "sentiment": e.get("sentiment_score")}
                for e in world_state.get("entities", [])
            ],
            "summary": world_state.get("world_summary", ""),
        }
        compact_events = [
            {"title": ev.get("title"), "type": ev.get("event_type"),
             "description": ev.get("description", "")[:300],
             "severity": ev.get("severity")}
            for ev in events[:15]
        ]
        compact_agents = [
            {"name": a.get("name"), "role": a.get("role"),
             "goals": a.get("goals", [])[:2]}
            for a in agents.get("agents", [])
        ]

        user_prompt = CLAIM_EXTRACT_USER_V2.format(
            perspective=perspective or "デフォルト視点",
            world_state=json.dumps(compact_state, ensure_ascii=False)[:3000],
            events=json.dumps(compact_events, ensure_ascii=False)[:2000],
            agents=json.dumps(compact_agents, ensure_ascii=False)[:1000],
        )

        try:
            result, usage = await llm_client.call(
                task_name="claim_extract",
                system_prompt=CLAIM_EXTRACT_SYSTEM_V2,
                user_prompt=user_prompt,
                response_format={"type": "json_object"},
            )
            await record_usage(session, simulation_id, f"claim_extract_{colony_id[:8]}", usage)

            if isinstance(result, dict):
                claims = result.get("claims", [])
                for claim_data in claims:
                    claim = OutcomeClaim(
                        id=str(uuid.uuid4()),
                        simulation_id=simulation_id,
                        colony_id=colony_id,
                        claim_text=claim_data.get("claim_text", ""),
                        claim_type=claim_data.get("claim_type", "prediction"),
                        confidence=float(claim_data.get("confidence", 0.5)),
                        evidence=claim_data.get("evidence", ""),
                        entities_involved=claim_data.get("entities_involved", []),
                    )
                    session.add(claim)
                    all_claims.append({
                        "id": claim.id,
                        "colony_id": colony_id,
                        "claim_text": claim.claim_text,
                        "claim_type": claim.claim_type,
                        "confidence": claim.confidence,
                        "evidence": claim.evidence,
                        "entities_involved": claim.entities_involved,
                    })

                logger.info(
                    f"Extracted {len(claims)} claims from colony {colony_id[:8]}"
                )
        except Exception as e:
            logger.error(f"Claim extraction failed for colony {colony_id[:8]}: {e}")

    await session.flush()
    logger.info(f"Total claims extracted for swarm {simulation_id}: {len(all_claims)}")
    return all_claims
