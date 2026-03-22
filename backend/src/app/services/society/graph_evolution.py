"""社会グラフ進化: Meeting での相互作用に基づくエッジ強度更新"""

import logging

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.social_edge import SocialEdge

logger = logging.getLogger(__name__)


def _graph_participants(meeting_participants: list[dict]) -> list[tuple[int, str]]:
    """DB に存在する市民代表だけをグラフ更新の対象にする。"""
    participants: list[tuple[int, str]] = []
    for p in meeting_participants:
        if p.get("role") != "citizen_representative":
            continue
        agent_profile = p.get("agent_profile", {}) or {}
        agent_id = agent_profile.get("id")
        if not agent_id:
            continue
        participant_index = p.get("participant_index")
        if participant_index is None:
            participant_index = len(participants)
        participants.append((int(participant_index), agent_id))
    return participants


def _compute_interaction_strength(
    meeting_rounds: list[list[dict]],
    agent_id: str,
    target_id: str,
    agent_index: int,
    target_index: int,
) -> float:
    """Meeting 中の相互作用からエッジ強度の変化量を計算する。

    同じラウンドで議論した回数に基づく。
    """
    co_occurrence = 0
    agreement = 0
    total_rounds = len(meeting_rounds)

    for round_args in meeting_rounds:
        agent_in_round = any(a.get("participant_index") == agent_index for a in round_args)
        target_in_round = any(a.get("participant_index") == target_index for a in round_args)

        if agent_in_round and target_in_round:
            co_occurrence += 1

            # スタンス一致度チェック
            agent_pos = next(
                (a.get("position", "") for a in round_args if a.get("participant_index") == agent_index), ""
            )
            target_pos = next(
                (a.get("position", "") for a in round_args if a.get("participant_index") == target_index), ""
            )
            if agent_pos and target_pos and agent_pos == target_pos:
                agreement += 1

    if total_rounds == 0 or co_occurrence == 0:
        return 0.0

    # 相互作用頻度 + 合意度で強度変化を計算
    interaction_ratio = co_occurrence / total_rounds
    agreement_ratio = agreement / co_occurrence if co_occurrence > 0 else 0.0

    # 正の変化: 0〜0.15
    return round((interaction_ratio * 0.1 + agreement_ratio * 0.05), 4)


async def evolve_social_graph(
    session: AsyncSession,
    population_id: str,
    meeting_result: dict,
    meeting_participants: list[dict],
) -> int:
    """Meeting の相互作用に基づいてソーシャルグラフのエッジ強度を更新する。

    Returns:
        更新されたエッジ数
    """
    rounds = meeting_result.get("rounds", [])
    if not rounds:
        return 0

    graph_participants = _graph_participants(meeting_participants)
    if len(graph_participants) < 2:
        return 0

    updated = 0

    for pos_a, (round_index_a, id_a) in enumerate(graph_participants):
        for pos_b, (round_index_b, id_b) in enumerate(graph_participants):
            if pos_a >= pos_b:
                continue

            delta = _compute_interaction_strength(
                rounds, id_a, id_b, round_index_a, round_index_b,
            )
            if delta <= 0:
                continue

            # 既存エッジを探す
            edge_a, edge_b = min(id_a, id_b), max(id_a, id_b)
            result = await session.execute(
                select(SocialEdge).where(
                    and_(
                        SocialEdge.population_id == population_id,
                        SocialEdge.agent_id == edge_a,
                        SocialEdge.target_id == edge_b,
                    )
                ).limit(1)
            )
            edge = result.scalar_one_or_none()

            if edge:
                edge.strength = min(1.0, edge.strength + delta)
                updated += 1
            else:
                # 新規エッジ作成（Meeting で初めて交流）
                import uuid
                new_edge = SocialEdge(
                    id=str(uuid.uuid4()),
                    population_id=population_id,
                    agent_id=edge_a,
                    target_id=edge_b,
                    relation_type="colleague",
                    strength=min(1.0, 0.3 + delta),
                )
                session.add(new_edge)
                updated += 1

    if updated:
        await session.commit()

    logger.info("Evolved %d social edges from meeting interactions", updated)
    return updated
