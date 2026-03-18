"""ConsistencyChecker: 世界状態の論理的整合性検証"""

import json
import logging

from src.app.llm.client import llm_client
from src.app.llm.prompts import GM_CONSISTENCY_CHECK_SYSTEM, GM_CONSISTENCY_CHECK_USER
from src.app.services.cost_tracker import record_usage

logger = logging.getLogger(__name__)


class ConsistencyChecker:
    """世界状態の一貫性を検証し、矛盾を検出・修正する。"""

    def __init__(self, check_frequency: int = 2):
        self.check_frequency = check_frequency

    def should_check(self, round_number: int) -> bool:
        """一貫性チェックを実行すべきかどうか。"""
        return round_number > 0 and round_number % self.check_frequency == 0

    async def validate(
        self,
        session,
        run_id: str,
        world_state: dict,
        recent_changes: list[dict],
    ) -> dict:
        """世界状態の整合性を検証する。"""
        compact_state = json.dumps(
            {
                "entities": [
                    {"id": e.get("id"), "label": e.get("label"),
                     "status": e.get("status"), "importance": e.get("importance_score")}
                    for e in world_state.get("entities", [])[:30]
                ],
                "relations": [
                    {"source": r.get("source"), "target": r.get("target"),
                     "type": r.get("relation_type"), "weight": r.get("weight")}
                    for r in world_state.get("relations", [])[:30]
                ],
            },
            ensure_ascii=False,
        )

        changes_str = json.dumps(recent_changes[:20], ensure_ascii=False)

        user_prompt = GM_CONSISTENCY_CHECK_USER.format(
            world_state=compact_state,
            recent_changes=changes_str,
        )

        result, usage = await llm_client.call_with_retry(
            task_name="gm_consistency_check",
            system_prompt=GM_CONSISTENCY_CHECK_SYSTEM,
            user_prompt=user_prompt,
            response_format={"type": "json_object"},
        )

        await record_usage(session, run_id, "gm_consistency_check", usage)

        if isinstance(result, dict):
            is_consistent = result.get("is_consistent", True)
            inconsistencies = result.get("inconsistencies", [])
            corrections = result.get("corrections", [])

            if not is_consistent:
                logger.warning(
                    f"Inconsistencies detected: {len(inconsistencies)} issues, "
                    f"{len(corrections)} corrections proposed"
                )

            return result

        return {"is_consistent": True, "inconsistencies": [], "corrections": []}

    def apply_corrections(self, world_state: dict, corrections: list[dict]) -> dict:
        """修正案を世界状態に適用する。"""
        entity_map = {e["id"]: e for e in world_state.get("entities", [])}

        for correction in corrections:
            entity_id = correction.get("entity_id", "")
            field = correction.get("field", "")
            corrected_value = correction.get("corrected_value")

            if entity_id in entity_map and field and corrected_value is not None:
                entity_map[entity_id][field] = corrected_value
                logger.info(f"Applied correction: {entity_id}.{field} = {corrected_value}")

        world_state["entities"] = list(entity_map.values())
        return world_state
