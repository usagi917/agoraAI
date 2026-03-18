"""ラウンドプロセッサ: 1ラウンド分のシミュレーション実行

cognitive_mode == "advanced" の場合は GameMaster に委譲する。
"""

import json
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.llm.client import llm_client
from src.app.llm.prompts import ROUND_PROCESS_SYSTEM, ROUND_PROCESS_USER
from src.app.llm.validator import validate_round_result
from src.app.models.entity import Entity
from src.app.models.relation import Relation
from src.app.models.timeline_event import TimelineEvent
from src.app.models.world_state import WorldState
from src.app.services.cost_tracker import record_usage

logger = logging.getLogger(__name__)


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
) -> dict:
    """1ラウンド分のシミュレーションを実行する。"""

    # プロンプトサイズ縮小
    compact_state = {
        "entities": [
            {"id": e["id"], "label": e.get("label"), "type": e.get("entity_type"),
             "importance": e.get("importance_score"), "stance": e.get("stance")}
            for e in world_state.get("entities", [])
        ],
        "relations": [
            {"source": r["source"], "target": r["target"], "type": r.get("relation_type"),
             "weight": r.get("weight")}
            for r in world_state.get("relations", [])
        ],
    }
    compact_agents = {
        "agents": [
            {"id": a["id"], "name": a.get("name"), "role": a.get("role"), "goals": a.get("goals", [])}
            for a in agents.get("agents", [])
        ]
    }
    user_prompt = ROUND_PROCESS_USER.format(
        round_number=round_number,
        template_prompt=template_prompt,
        user_prompt=prompt_text or "（指示なし）",
        world_state=json.dumps(compact_state, ensure_ascii=False)[:4000],
        agents=json.dumps(compact_agents, ensure_ascii=False)[:2000],
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
