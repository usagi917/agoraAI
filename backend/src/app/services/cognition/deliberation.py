"""DeliberationEngine: 熟慮・計画生成"""

import json
import logging

from src.app.llm.client import llm_client
from src.app.llm.prompts import BDI_DELIBERATE_SYSTEM, BDI_DELIBERATE_USER
from src.app.llm.validator import validate_bdi_deliberation
from src.app.services.cost_tracker import record_usage
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)


class DeliberationEngine:
    """BDI推論: 信念+欲求+意図+観察→行動計画の推論。"""

    def __init__(self, max_intentions: int = 3, commitment_decay: float = 0.1):
        self.max_intentions = max_intentions
        self.commitment_decay = commitment_decay

    async def deliberate(
        self,
        session,
        run_id: str,
        agent_name: str,
        beliefs: list[dict],
        desires: list[dict],
        intentions: list[dict],
        observations: list[dict],
        mental_models: dict,
        incoming_messages: list[dict] | None = None,
    ) -> dict:
        """行動の熟慮・推論を行う。"""
        beliefs_str = json.dumps(beliefs[:20], ensure_ascii=False) if beliefs else "[]"
        desires_str = json.dumps(desires, ensure_ascii=False) if desires else "[]"
        intentions_str = json.dumps(intentions, ensure_ascii=False) if intentions else "[]"
        observations_str = json.dumps(observations[:10], ensure_ascii=False) if observations else "[]"
        models_str = json.dumps(
            {k: {"predicted_action": v.get("predicted_action", ""), "trust": v.get("trust_level", 0.5)}
             for k, v in list(mental_models.items())[:5]},
            ensure_ascii=False,
        ) if mental_models else "{}"

        messages_str = json.dumps(
            [{"sender": m.get("sender_id", ""), "type": m.get("message_type", "say"),
              "content": m.get("content", "")[:200]}
             for m in (incoming_messages or [])[:10]],
            ensure_ascii=False,
        ) if incoming_messages else "[]"

        user_prompt = BDI_DELIBERATE_USER.format(
            agent_name=agent_name,
            beliefs=beliefs_str,
            desires=desires_str,
            intentions=intentions_str,
            observations=observations_str,
            mental_models=models_str,
            incoming_messages=messages_str,
        )

        await sse_manager.publish(run_id, "agent_thinking_started", {
            "agent_name": agent_name,
            "stage": "deliberation",
        })

        result, usage = await llm_client.call_with_retry(
            task_name="bdi_deliberate",
            system_prompt=BDI_DELIBERATE_SYSTEM,
            user_prompt=user_prompt,
            response_format={"type": "json_object"},
            validate_fn=validate_bdi_deliberation,
        )

        await record_usage(session, run_id, f"bdi_deliberate_{agent_name}", usage)

        if not isinstance(result, dict):
            await sse_manager.publish(run_id, "agent_thinking_completed", {
                "agent_name": agent_name,
                "chosen_action": "待機",
                "reasoning_chain": "推論失敗",
                "status": "failed",
            })
            return {
                "reasoning_chain": "推論失敗",
                "chosen_action": "待機",
                "expected_outcomes": [],
                "commitment_strength": 0.5,
                "belief_updates": [],
            }

        await sse_manager.publish(run_id, "agent_thinking_completed", {
            "agent_name": agent_name,
            "chosen_action": result.get("chosen_action", ""),
            "reasoning_chain": result.get("reasoning_chain", "")[:500],
            "status": "success",
        })

        return result

    def decay_commitments(self, intentions: list[dict]) -> list[dict]:
        """意図のコミットメント強度を減衰させる。"""
        updated = []
        for intention in intentions:
            strength = intention.get("commitment_strength", 1.0)
            new_strength = max(0.0, strength - self.commitment_decay)
            if new_strength > 0.1:  # 閾値以下は破棄
                intention["commitment_strength"] = new_strength
                updated.append(intention)
        return updated[:self.max_intentions]
