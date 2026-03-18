"""ActionExecutor: 行動の自然言語記述生成"""

import json
import logging

from src.app.llm.client import llm_client
from src.app.llm.prompts import BDI_EXECUTE_SYSTEM, BDI_EXECUTE_USER
from src.app.services.cost_tracker import record_usage

logger = logging.getLogger(__name__)


class ActionExecutor:
    """選択された行動を具体的な自然言語記述に変換する。"""

    async def execute(
        self,
        session,
        run_id: str,
        agent_name: str,
        agent_role: str,
        chosen_action: str,
        context: dict,
    ) -> dict:
        """行動を実行し、結果を返す。"""
        context_str = json.dumps(
            {
                "round": context.get("round_number", 0),
                "recent_events": [e.get("title", "") for e in context.get("events", [])[:5]],
                "world_summary": context.get("world_summary", "")[:500],
            },
            ensure_ascii=False,
        )

        user_prompt = BDI_EXECUTE_USER.format(
            agent_name=agent_name,
            agent_role=agent_role,
            chosen_action=chosen_action,
            context=context_str,
        )

        result, usage = await llm_client.call_with_retry(
            task_name="bdi_execute",
            system_prompt=BDI_EXECUTE_SYSTEM,
            user_prompt=user_prompt,
            response_format={"type": "json_object"},
        )

        await record_usage(session, run_id, f"bdi_execute_{agent_name}", usage)

        if not isinstance(result, dict):
            return {
                "action_description": chosen_action,
                "impact": "",
                "entity_updates": [],
                "relation_updates": [],
            }

        return result
