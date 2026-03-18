"""ActionResolver: 複数エージェントの行動衝突解決"""

import json
import logging

from src.app.llm.client import llm_client
from src.app.llm.prompts import GM_ACTION_RESOLVE_SYSTEM, GM_ACTION_RESOLVE_USER
from src.app.llm.validator import validate_action_resolution
from src.app.services.cost_tracker import record_usage

logger = logging.getLogger(__name__)


class ActionResolver:
    """複数エージェントの同時行動の衝突を検出・解決する。"""

    def __init__(self, resolution_mode: str = "priority"):
        self.resolution_mode = resolution_mode

    async def resolve(
        self,
        session,
        run_id: str,
        agent_actions: list[dict],
        world_state: dict,
    ) -> list[dict]:
        """行動の衝突を解決する。"""
        if len(agent_actions) <= 1:
            return agent_actions

        actions_str = json.dumps(
            [
                {
                    "agent_id": a.get("agent_id"),
                    "agent_name": a.get("agent_name"),
                    "action": a.get("action", ""),
                    "impact": a.get("impact", ""),
                }
                for a in agent_actions
            ],
            ensure_ascii=False,
        )

        compact_state = json.dumps(
            {
                "entities": [
                    {"id": e.get("id"), "label": e.get("label")}
                    for e in world_state.get("entities", [])[:20]
                ],
            },
            ensure_ascii=False,
        )

        user_prompt = GM_ACTION_RESOLVE_USER.format(
            agent_actions=actions_str,
            world_state=compact_state,
        )

        result, usage = await llm_client.call_with_retry(
            task_name="gm_action_resolve",
            system_prompt=GM_ACTION_RESOLVE_SYSTEM,
            user_prompt=user_prompt,
            response_format={"type": "json_object"},
            validate_fn=validate_action_resolution,
        )

        await record_usage(session, run_id, "gm_action_resolve", usage)

        if isinstance(result, dict):
            resolved = result.get("resolved_actions", [])
            conflicts = result.get("conflicts_detected", [])
            if conflicts:
                logger.info(f"Resolved {len(conflicts)} conflicts")
            return resolved

        return agent_actions
