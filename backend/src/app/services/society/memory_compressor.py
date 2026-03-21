"""記憶圧縮: シミュレーション後に agent_profile.memory_summary を更新"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.agent_profile import AgentProfile

logger = logging.getLogger(__name__)


def compress_memory(
    previous_summary: str,
    activation_response: dict,
    meeting_participation: dict | None = None,
) -> str:
    """エージェントの経験を圧縮して memory_summary を更新する。

    LLM は使用しない。構造化テキストに変換する。
    """
    parts = []

    if previous_summary:
        parts.append(previous_summary.strip())

    # 活性化時の意見を記録
    stance = activation_response.get("stance", "")
    confidence = activation_response.get("confidence", 0.5)
    reason = activation_response.get("reason", "")
    if stance:
        parts.append(f"[活性化] スタンス:{stance} 信頼度:{confidence:.0%} 理由:{reason}")

    # Meeting 参加経験を記録
    if meeting_participation:
        role = meeting_participation.get("role", "")
        final_position = meeting_participation.get("final_position", "")
        if final_position:
            parts.append(f"[Meeting] 役割:{role} 最終立場:{final_position}")

    return "\n".join(parts)


async def update_agent_memories(
    session: AsyncSession,
    agents: list[dict],
    responses: list[dict],
    meeting_result: dict | None = None,
) -> int:
    """活性化結果を基にエージェントの memory_summary を更新する。

    Returns:
        更新されたエージェント数
    """
    # Meeting 参加者のマッピング
    meeting_participants = {}
    if meeting_result:
        for round_args in meeting_result.get("rounds", []):
            for arg in round_args:
                idx = arg.get("participant_index", -1)
                if idx >= 0:
                    meeting_participants[idx] = {
                        "role": arg.get("role", ""),
                        "final_position": arg.get("position", ""),
                    }

    updated = 0
    for i, (agent, resp) in enumerate(zip(agents, responses)):
        agent_id = agent.get("id")
        if not agent_id:
            continue

        meeting_data = meeting_participants.get(i)
        previous = agent.get("memory_summary", "")
        new_summary = compress_memory(previous, resp, meeting_data)

        if new_summary != previous:
            db_agent = await session.get(AgentProfile, agent_id)
            if db_agent:
                db_agent.memory_summary = new_summary
                updated += 1

    if updated:
        await session.commit()

    logger.info("Updated memory for %d agents", updated)
    return updated
