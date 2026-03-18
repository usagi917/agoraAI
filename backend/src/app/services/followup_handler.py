"""フォローアップ質問処理"""

import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.llm.client import llm_client
from src.app.llm.prompts import FOLLOWUP_SYSTEM, FOLLOWUP_USER
from src.app.services.cost_tracker import record_usage

logger = logging.getLogger(__name__)


async def handle_followup(
    session: AsyncSession,
    run_id: str,
    question: str,
    report_content: str,
    world_state: dict,
) -> str:
    """フォローアップ質問に回答する。"""

    user_prompt = FOLLOWUP_USER.format(
        report=report_content[:4000],
        world_state=json.dumps(world_state, ensure_ascii=False, indent=2)[:4000],
        question=question,
    )

    result, usage = await llm_client.call(
        task_name="followup",
        system_prompt=FOLLOWUP_SYSTEM,
        user_prompt=user_prompt,
    )

    await record_usage(session, run_id, "followup", usage)

    answer = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
    logger.info(f"Followup answered for run {run_id}")
    return answer
