"""エージェント生成: world_state → agent profiles"""

import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.llm.client import llm_client
from src.app.llm.prompts import AGENT_GENERATE_SYSTEM, AGENT_GENERATE_USER
from src.app.llm.validator import validate_agents
from src.app.services.cost_tracker import record_usage

logger = logging.getLogger(__name__)


async def generate_agents(
    session: AsyncSession,
    run_id: str,
    world_state: dict,
    template_prompt: str,
    prompt_text: str = "",
) -> dict:
    """世界モデルからエージェントプロファイルを生成する。"""

    # world_state を簡潔にしてプロンプトサイズを縮小
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

    logger.info(f"Generated {len(result.get('agents', []))} agents for run {run_id}")
    return result
