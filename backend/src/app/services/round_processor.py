"""ラウンドプロセッサ: 1ラウンド分のシミュレーション実行

cognitive_mode == "advanced" の場合は GameMaster に委譲する。
"""

import json
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.llm.client import llm_client
from src.app.llm.prompts import ROUND_PROCESS_SYSTEM, ROUND_PROCESS_USER
from src.app.llm.validator import validate_round_result
from src.app.models.entity import Entity
from src.app.models.relation import Relation
from src.app.models.run import Run
from src.app.models.timeline_event import TimelineEvent
from src.app.models.world_state import WorldState
from src.app.services.cost_tracker import record_usage
from src.app.services.quality import build_evidence_bundle
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)


async def _resolve_project_id(session: AsyncSession, run_id: str) -> str | None:
    result = await session.execute(select(Run.project_id).where(Run.id == run_id))
    return result.scalar_one_or_none()


def _select_salient_world_state(
    world_state: dict,
    *,
    max_entities: int = 20,
    max_relations: int = 24,
) -> dict:
    entities = sorted(
        world_state.get("entities", []),
        key=lambda entity: (
            float(entity.get("importance_score", 0.0) or 0.0),
            float(entity.get("activity_score", 0.0) or 0.0),
        ),
        reverse=True,
    )[:max_entities]
    selected_entity_ids = {entity.get("id") for entity in entities}

    relations = sorted(
        [
            relation
            for relation in world_state.get("relations", [])
            if relation.get("source") in selected_entity_ids
            or relation.get("target") in selected_entity_ids
        ],
        key=lambda relation: float(relation.get("weight", 0.0) or 0.0),
        reverse=True,
    )[:max_relations]

    return {
        "entities": [
            {
                "id": entity["id"],
                "label": entity.get("label"),
                "type": entity.get("entity_type"),
                "importance": entity.get("importance_score"),
                "stance": entity.get("stance"),
                "activity": entity.get("activity_score"),
                "status": entity.get("status"),
            }
            for entity in entities
        ],
        "relations": [
            {
                "source": relation["source"],
                "target": relation["target"],
                "type": relation.get("relation_type"),
                "weight": relation.get("weight"),
            }
            for relation in relations
        ],
        "world_summary": world_state.get("world_summary", ""),
    }


def _select_salient_agents(agents: dict, *, max_agents: int = 12) -> dict:
    selected_agents = sorted(
        agents.get("agents", []),
        key=lambda agent: (
            len(agent.get("goals", []) or []),
            len(agent.get("relationships", []) or []),
        ),
        reverse=True,
    )[:max_agents]
    return {
        "agents": [
            {
                "id": agent["id"],
                "name": agent.get("name"),
                "role": agent.get("role"),
                "goals": agent.get("goals", [])[:3],
                "strategy": agent.get("strategy", ""),
            }
            for agent in selected_agents
        ]
    }


async def process_round_advanced(
    session: AsyncSession,
    run_id: str,
    round_number: int,
    world_state: dict,
    cognitive_agents: list,
    recent_events: list[dict],
    sse_channel: str | None = None,
) -> dict:
    """advanced モード: GameMaster でラウンドを処理する。"""
    from src.app.services.game_master.game_master import GameMaster

    gm = GameMaster()
    return await gm.run_round(
        session, run_id, round_number, world_state,
        cognitive_agents, recent_events, sse_channel,
    )


async def process_round(
    session: AsyncSession,
    run_id: str,
    round_number: int,
    world_state: dict,
    agents: dict,
    template_prompt: str,
    prompt_text: str = "",
    sse_channel: str | None = None,
) -> dict:
    """1ラウンド分のシミュレーションを実行する。"""

    channel = sse_channel or run_id

    compact_state = _select_salient_world_state(world_state)
    compact_agents = _select_salient_agents(agents)
    project_id = await _resolve_project_id(session, run_id)
    evidence_bundle = await build_evidence_bundle(
        session,
        project_id,
        prompt_text,
        query_text="\n".join(
            [
                str(round_number),
                template_prompt,
                prompt_text,
                compact_state.get("world_summary", ""),
                " ".join(entity.get("label", "") for entity in compact_state.get("entities", [])[:8]),
            ]
        ),
        max_documents=3,
        max_document_chunks=2,
        max_refs=6,
        max_chars=6000,
    )
    user_prompt = ROUND_PROCESS_USER.format(
        round_number=round_number,
        template_prompt=template_prompt,
        user_prompt=prompt_text or "（指示なし）",
        world_state=json.dumps(compact_state, ensure_ascii=False),
        agents=json.dumps(compact_agents, ensure_ascii=False),
        evidence_context=evidence_bundle["context_text"] or "関連根拠なし",
    )

    result, usage = await llm_client.call_with_retry(
        task_name="round_process",
        system_prompt=ROUND_PROCESS_SYSTEM,
        user_prompt=user_prompt,
        response_format={"type": "json_object"},
        validate_fn=validate_round_result,
    )

    await record_usage(session, run_id, f"round_{round_number}", usage)

    if not isinstance(result, dict):
        raise ValueError(f"ラウンド処理の LLM 応答が JSON ではありませんでした: {str(result)[:100]}")

    # エンティティ更新を world_state に反映
    entity_map = {e["id"]: e for e in world_state.get("entities", [])}
    for update in result.get("entity_updates", []):
        eid = update.get("entity_id", "")
        if eid in entity_map:
            changes = update.get("changes", {})
            entity_map[eid].update(changes)

    # リレーション更新を world_state に反映
    relation_map = {
        (r.get("source"), r.get("target")): r
        for r in world_state.get("relations", [])
    }
    for update in result.get("relation_updates", []):
        key = (update.get("source", ""), update.get("target", ""))
        if key in relation_map:
            relation_map[key].update(update.get("changes", {}))

    # タイムラインイベント保存
    for event_data in result.get("events", []):
        event = TimelineEvent(
            id=str(uuid.uuid4()),
            run_id=run_id,
            round_number=round_number,
            event_type=event_data.get("event_type", "unknown"),
            title=event_data.get("title", ""),
            description=event_data.get("description", ""),
            severity=float(event_data.get("severity", 0.5)),
            involved_entities=event_data.get("involved_entities", []),
        )
        session.add(event)
        await sse_manager.publish(channel, "timeline_event", {
            "round": round_number,
            "event_type": event_data.get("event_type", "unknown"),
            "title": event_data.get("title", ""),
            "description": event_data.get("description", ""),
            "severity": float(event_data.get("severity", 0.5)),
            "involved_entities": event_data.get("involved_entities", []),
        })

    # 更新された world_state を保存
    updated_world_state = {
        **world_state,
        "entities": list(entity_map.values()),
    }

    ws = WorldState(
        id=str(uuid.uuid4()),
        run_id=run_id,
        round_number=round_number,
        state_data=updated_world_state,
    )
    session.add(ws)
    await session.flush()

    logger.info(
        f"Round {round_number} processed for run {run_id}: "
        f"{len(result.get('events', []))} events"
    )

    return {
        "round_result": result,
        "updated_world_state": updated_world_state,
    }
