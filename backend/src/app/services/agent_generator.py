"""エージェント生成: world_state → agent profiles"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.llm.client import llm_client
from src.app.llm.prompts import (
    AGENT_GENERATE_SYSTEM,
    AGENT_GENERATE_USER,
    AGENT_SEEDS_SYSTEM,
    AGENT_SEEDS_USER,
)
from src.app.llm.validator import validate_agents
from src.app.services.cost_tracker import record_usage
from src.app.services.graphrag.stakeholder_mapper import SOURCE_ENTITY_ID_FIELD

if TYPE_CHECKING:
    from src.app.services.graphrag.stakeholder_mapper import StakeholderSeed

logger = logging.getLogger(__name__)


async def generate_agents(
    session: AsyncSession,
    run_id: str,
    world_state: dict,
    template_prompt: str,
    prompt_text: str = "",
    *,
    stakeholder_seeds: list[StakeholderSeed] | None = None,
) -> dict:
    """世界モデルからエージェントプロファイルを生成する。

    stakeholder_seeds が指定された場合、KG エンティティを根拠とするエージェントを生成する。
    seeds が空またはNoneの場合は既存のジェネリック生成パスを使用する。
    """
    if stakeholder_seeds:
        return await _generate_from_seeds(
            session, run_id, world_state, template_prompt, prompt_text, stakeholder_seeds,
        )
    return await _generate_generic(session, run_id, world_state, template_prompt, prompt_text)


async def _generate_generic(
    session: AsyncSession,
    run_id: str,
    world_state: dict,
    template_prompt: str,
    prompt_text: str,
) -> dict:
    """ジェネリックなエージェント生成（既存の動作）。"""
    compact_state = {
        "entities": [
            {"id": e["id"], "label": e.get("label"), "type": e.get("entity_type"), "group": e.get("group")}
            for e in world_state.get("entities", [])
        ],
        "relations": [
            {"source": r["source"], "target": r["target"], "type": r.get("relation_type")}
            for r in world_state.get("relations", [])
        ],
        "summary": world_state.get("world_summary", ""),
    }
    user_prompt = AGENT_GENERATE_USER.format(
        template_prompt=template_prompt,
        user_prompt=prompt_text or "（指示なし）",
        world_state=json.dumps(compact_state, ensure_ascii=False, indent=2)[:4000],
    )

    result, usage = await llm_client.call_with_retry(
        task_name="agent_generate",
        system_prompt=AGENT_GENERATE_SYSTEM,
        user_prompt=user_prompt,
        response_format={"type": "json_object"},
        validate_fn=validate_agents,
    )

    await record_usage(session, run_id, "agent_generate", usage)

    if not isinstance(result, dict):
        raise ValueError(f"エージェント生成の LLM 応答が JSON ではありませんでした: {str(result)[:100]}")

    logger.info("Generated %d agents for run %s", len(result.get("agents", [])), run_id)
    return result


async def _generate_from_seeds(
    session: AsyncSession,
    run_id: str,
    world_state: dict,
    template_prompt: str,
    prompt_text: str,
    seeds: list[StakeholderSeed],
) -> dict:
    """KG ステークホルダーシードを根拠とするエージェント生成。

    LLM が返したエージェントの source_entity_id をシードの UUID と照合し、
    一致しないエージェントは除外する。全件除外された場合はジェネリック生成にフォールバック。
    """
    seeds_json = json.dumps(
        [
            {
                "entity_id": s.entity_id,
                "name": s.name,
                "entity_type": s.entity_type,
                "goals_hint": s.goals_hint,
                "community": s.community,
                "description": s.description,
            }
            for s in seeds
        ],
        ensure_ascii=False,
        indent=2,
    )
    user_prompt = AGENT_SEEDS_USER.format(
        template_prompt=template_prompt,
        user_prompt=prompt_text or "（指示なし）",
        seeds_json=seeds_json,
    )

    result, usage = await llm_client.call_with_retry(
        task_name="agent_generate",
        system_prompt=AGENT_SEEDS_SYSTEM,
        user_prompt=user_prompt,
        response_format={"type": "json_object"},
        validate_fn=validate_agents,
    )

    await record_usage(session, run_id, "agent_generate", usage)

    if not isinstance(result, dict):
        raise ValueError(f"seeds エージェント生成の LLM 応答が JSON ではありませんでした: {str(result)[:100]}")

    # source_entity_id でフィルタリング
    seed_ids = {s.entity_id for s in seeds}
    valid_agents = []
    for agent in result.get("agents", []):
        sid = agent.get(SOURCE_ENTITY_ID_FIELD)
        if sid in seed_ids:
            valid_agents.append(agent)
        else:
            logger.warning(
                "Agent '%s' has unknown %s '%s', excluding",
                agent.get("name"), SOURCE_ENTITY_ID_FIELD, sid,
            )

    if not valid_agents:
        logger.warning(
            "All %d seeded agents excluded (UUID mismatch), falling back to generic generation",
            len(result.get("agents", [])),
        )
        return await _generate_generic(session, run_id, world_state, template_prompt, prompt_text)

    logger.info(
        "Generated %d/%d grounded agents for run %s",
        len(valid_agents), len(seeds), run_id,
    )
    return {"agents": valid_agents}
